from collections import OrderedDict
from datetime import date,datetime
from decimal import Decimal
import math
from threading import RLock

import duckdb
import pyarrow.parquet as pq

from src.api.errors import ApiError,unavailable
from src.api.schemas.analytics import TABLE_MODELS


def json_value(value):
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if isinstance(value,Decimal):
        return int(value) if value==value.to_integral() else float(value)
    if isinstance(value,float) and not math.isfinite(value):
        return None
    return value


class AnalyticsService:
    def __init__(self,settings):
        self.settings=settings
        self._cache=OrderedDict()
        self._lock=RLock()
        self.query_count=0

    def _path(self,table):
        if table not in TABLE_MODELS:
            raise ValueError('Unknown internal table')
        return (self.settings.evaluation/'vehicle_errors.parquet' if table=='vehicle_errors'
                else self.settings.gold/f'{table}.parquet')

    def _signature(self,table):
        try:
            path=self._path(table)
            stat=path.stat()
            schema=pq.read_schema(path)
            if not set(TABLE_MODELS[table].model_fields)<=set(schema.names):
                raise ValueError('Artifact schema mismatch')
            return stat.st_mtime_ns,stat.st_size
        except (OSError,ValueError):
            raise unavailable('evaluation' if table=='vehicle_errors' else 'analytics') from None

    def ready(self):
        try:
            for table in TABLE_MODELS:
                if table!='vehicle_errors':
                    self._signature(table)
            return True
        except Exception:
            return False

    def page(self,table,filters=(),limit=25,offset=0):
        if not 1<=limit<=100 or not 0<=offset<=100_000:
            raise ApiError(422,'invalid_request','Pagination bounds are invalid.')
        signature=self._signature(table)
        filters=tuple(filters)
        key=(table,signature,filters,limit,offset)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        columns=tuple(TABLE_MODELS[table].model_fields)
        where=[]
        values=[]
        for field,operator,value in filters:
            if field not in columns or operator not in ('=','>=','<='):
                raise ValueError('Unapproved internal filter')
            where.append(f'"{field}" {operator} ?')
            values.append(value)
        clause=' WHERE '+' AND '.join(where) if where else ''
        projection=','.join(f'"{name}"' for name in columns)
        order={'trip_analytics':'vehicle_id,trip_id','vehicle_analytics':'vehicle_id',
            'daily_fleet':'trip_start_reference_day','monthly_fleet':'trip_start_reference_month',
            'powertrain_fleet':'engine_type','quality_metrics':'quality_flag',
            'vehicle_errors':'split,method,vehicle_id','fleet_overview':'observation_count'}[table]
        try:
            # Each request owns a small in-memory connection. No shared cursor,
            # persistent database, native Spark IO, or write statement is exposed.
            temp=self.settings.root/'data/tmp/duckdb-api'
            temp.mkdir(parents=True,exist_ok=True)
            with duckdb.connect(config={'threads':1,'memory_limit':f'{self.settings.analytics_memory_mb}MB',
                'temp_directory':str(temp),'max_temp_directory_size':'32MB',
                'autoinstall_known_extensions':False,'autoload_known_extensions':False}) as con:
                path=str(self._path(table))
                total=con.execute(f'SELECT count(*) FROM read_parquet(?,hive_partitioning=false){clause}',
                                  [path,*values]).fetchone()[0]
                cursor=con.execute(f'SELECT {projection} FROM read_parquet(?,hive_partitioning=false){clause} ORDER BY {order} LIMIT ? OFFSET ?',
                                   [path,*values,limit,offset])
                names=[d[0] for d in cursor.description]
                items=[{name:json_value(value) for name,value in zip(names,row)} for row in cursor.fetchall()]
            result={'items':items,'total':total,'limit':limit,'offset':offset}
        except Exception:
            raise unavailable('evaluation' if table=='vehicle_errors' else 'analytics') from None
        with self._lock:
            self.query_count+=1
            self._cache[key]=result
            self._cache.move_to_end(key)
            while len(self._cache)>self.settings.cache_entries:
                self._cache.popitem(last=False)
        return result

    def one(self,table,filters=()):
        result=self.page(table,filters,limit=1)
        if not result['items']:
            raise ApiError(404,'not_found','The requested analytics record was not found.')
        return result['items'][0]
