"""Independent NumPy interval integration and executable SQL demo validation."""
import json
import math
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,SILVER,OUTPUT,RESULTS,TABLES,sha256,footprint
from src.analytics.query import QUERIES,execute


def validate():
    start = time.perf_counter()
    expected = {}
    rows = 0
    for path in sorted(SILVER.rglob('*.parquet')):
        table = pq.read_table(path,columns=['vehicle_id','trip_id','elapsed_ms','speed_kmh','bronze_row_index'])
        vehicle,trip,elapsed,speed,index = [table[n].to_numpy() for n in table.column_names]
        order = np.lexsort((index,elapsed,trip,vehicle))
        vehicle,trip,elapsed,speed = [a[order] for a in (vehicle,trip,elapsed,speed)]
        same = (vehicle[1:]==vehicle[:-1]) & (trip[1:]==trip[:-1])
        delta = np.diff(elapsed)
        valid = same & (delta>0) & (delta<=2000) & np.isfinite(speed[1:]) & np.isfinite(speed[:-1])
        distance = np.zeros(len(table),dtype=np.float64)
        duration = np.zeros(len(table),dtype=np.float64)
        count = np.zeros(len(table),dtype=np.int64)
        eligible = np.flatnonzero(valid)+1
        distance[eligible]=(speed[eligible-1]+speed[eligible])/2*delta[valid]/3_600_000
        duration[eligible]=delta[valid]/1000
        count[eligible]=1
        starts=np.r_[0,np.flatnonzero(~same)+1]
        counts=np.add.reduceat(count,starts)
        distances=np.add.reduceat(distance,starts)
        durations=np.add.reduceat(duration,starts)
        for j,k in enumerate(starts):
            key=(int(vehicle[k]),int(trip[k]))
            if key in expected:
                raise RuntimeError('Independent validation found a cross-file trip')
            expected[key]=(int(counts[j]),float(distances[j]),float(durations[j]))
        rows+=len(table)
    trips = pq.read_table(OUTPUT/'trip_analytics.parquet').to_pylist()
    max_error=0.
    for actual in trips:
        count,distance,duration = expected.pop((actual['vehicle_id'],actual['trip_id']))
        if actual['eligible_speed_interval_count']!=count:
            raise RuntimeError('Eligible interval count mismatch')
        if count:
            error=abs(actual['observed_distance_km']-distance)
            max_error=max(error,max_error)
            if not math.isclose(actual['observed_distance_km'],distance,rel_tol=1e-11,abs_tol=1e-10):
                raise RuntimeError('Independent trip distance mismatch')
            if not math.isclose(actual['observed_speed_interval_s'],duration,rel_tol=1e-11,abs_tol=1e-8):
                raise RuntimeError('Independent trip duration mismatch')
        elif any(actual[n] is not None for n in ('observed_distance_km','observed_speed_interval_s','speed_time_weighted_mean_kmh')):
            raise RuntimeError('Unsupported intervals did not retain NULL semantics')
    if expected:
        raise RuntimeError('Trips missing in Gold')
    demo = {}
    for path in sorted(QUERIES.glob('*.sql')):
        query_start=time.perf_counter()
        output=execute(path.stem)
        demo[path.stem]={'rows':len(output),'runtime_seconds':time.perf_counter()-query_start}
        (RESULTS/f'query_{path.stem}.json').write_text(json.dumps(output,indent=2,default=str)+'\n',encoding='utf-8')
    result={'passed':True,'silver_rows':rows,'trips_independently_checked':len(trips),
        'max_trip_distance_absolute_error_km':max_error,'sql_queries':demo,
        'runtime_seconds':time.perf_counter()-start,'project_bytes':footprint()}
    (RESULTS/'independent_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    validate()
