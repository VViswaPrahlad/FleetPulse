"""Small saved-report adapters required by the dashboard. No telemetry scan."""
import json
from functools import lru_cache

from src.api.errors import unavailable
from src.api.schemas.analytics import Response,Split,Method
from pydantic import Field
from typing import Literal


class PipelineReport(Response):
    bronze_observations:int=Field(ge=0)
    silver_observations:int=Field(ge=0)
    quarantined_observations:int=Field(ge=0)
    gold_source_observations:int=Field(ge=0)
    gold_vehicles:int=Field(ge=0)
    gold_trips:int=Field(ge=0)
    exclusion_reasons:dict[str,int]
    missing_measurements:dict[str,int]
    semantics:str='Gold aggregates Silver; Gold table row counts are not telemetry observations.'


class CohortMetric(Response):
    split:Split
    dimension:Literal['actual_target_speed_range','powertrain']
    category:str=Field(pattern=r'^[A-Za-z0-9_,\[\)]+$')
    method:Method
    windows:int=Field(ge=1)
    vehicles:int=Field(ge=1)
    mae_kmh:float=Field(ge=0)
    rmse_kmh:float=Field(ge=0)


@lru_cache(maxsize=4)
def read_report(path,mtime_ns,size):
    return json.loads(path.read_text(encoding='utf-8'))


def pipeline(settings,analytics):
    try:
        path=settings.root/'results/day3/silver_quality.json'
        stat=path.stat()
        if stat.st_size>4_000_000:
            raise ValueError('Report too large')
        report=read_report(path,stat.st_mtime_ns,stat.st_size)
        overview=analytics.one('fleet_overview')
        # Explicitly allow known public numeric names, never paths/per-file metadata.
        missing={name:int(report['retained_null_counts'][name]) for name in (
            'speed_kmh','fuel_rate_lph','maf_g_s','engine_rpm','absolute_load_pct',
            'outside_air_temp_c','battery_soc_pct','hv_battery_current_a')}
        result=PipelineReport(bronze_observations=report['input_rows'],silver_observations=report['retained_rows'],
            quarantined_observations=report['excluded_rows'],gold_source_observations=overview['observation_count'],
            gold_vehicles=overview['vehicle_count'],gold_trips=overview['trip_count'],
            exclusion_reasons={'negative_elapsed_ms':int(report['exclusion_reasons'].get('negative_elapsed_ms',0))},
            missing_measurements=missing)
        if result.bronze_observations!=result.silver_observations+result.quarantined_observations or result.gold_source_observations!=result.silver_observations:
            raise ValueError('Report reconciliation failed')
        if any(count<0 or count>result.silver_observations for count in missing.values()):
            raise ValueError('Invalid missing-measurement counts')
        return result
    except Exception:
        raise unavailable('analytics') from None


def cohorts(settings,split,dimension):
    try:
        path=settings.evaluation/'cohort_metrics.json'
        stat=path.stat()
        if stat.st_size>250_000:
            raise ValueError('Report too large')
        rows=read_report(path,stat.st_mtime_ns,stat.st_size)
        if len(rows)>100:
            raise ValueError('Too many rows')
        output=[CohortMetric(**{field:row[field] for field in CohortMetric.model_fields})
                for row in rows if row['split']==split and row['dimension']==dimension]
        return {'items':output,'total':len(output),'limit':100,'offset':0}
    except Exception:
        raise unavailable('evaluation') from None
