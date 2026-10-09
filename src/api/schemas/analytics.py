from datetime import date
from typing import Any,Generic,Literal,TypeVar

from pydantic import BaseModel,ConfigDict,Field,create_model

Powertrain=Literal['ICE','HEV','PHEV','EV']
PowertrainValue=Literal['ICE','HEV','PHEV','EV','UNKNOWN']
Split=Literal['validation','test']
Method=Literal['hist_gradient_boosting','last_observed_speed','past_mean_persistence','training_historical_mean']


class Response(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


COUNT_FIELDS=('observation_count','vehicle_count','trip_count','source_file_count',
    'speed_observation_count','missing_speed_count','fuel_rate_observation_count','missing_fuel_rate_count',
    'stopped_observation_count','flagged_observation_count','quality_flag_occurrence_count',
    'gap_gt_2s_count','gap_gt_10s_count','duplicate_timestamp_count','eligible_speed_interval_count')
MEASURE_FIELDS=('speed_sample_mean_kmh','speed_sample_stddev_kmh','speed_min_kmh',
    'speed_sample_p50_kmh','speed_sample_p95_kmh','speed_max_kmh','max_sampling_gap_s',
    'positive_gap_p50_s','positive_gap_p95_s','observed_speed_interval_s',
    'observed_distance_km','observed_stopped_interval_s','speed_time_weighted_mean_kmh')
AnalyticsMetrics=create_model('AnalyticsMetrics',__base__=Response,
    **{name:(int,Field(ge=0)) for name in COUNT_FIELDS},
    **{name:(float|None,...) for name in MEASURE_FIELDS},
    first_trip_start_reference_day=(date,...),last_trip_start_reference_day=(date,...))
VehicleAnalytics=create_model('VehicleAnalytics',__base__=AnalyticsMetrics,
    vehicle_id=(int,...),engine_type=(PowertrainValue,...))
TripAnalytics=create_model('TripAnalytics',__base__=VehicleAnalytics,
    trip_id=(int,...),elapsed_span_s=(float,...),distinct_day_number_count=(int,...))
DailyAnalytics=create_model('DailyAnalytics',__base__=AnalyticsMetrics,
    trip_start_reference_day=(date,...))
MonthlyAnalytics=create_model('MonthlyAnalytics',__base__=AnalyticsMetrics,
    trip_start_reference_month=(date,...))
PowertrainAnalytics=create_model('PowertrainAnalytics',__base__=AnalyticsMetrics,engine_type=(PowertrainValue,...))


class QualityFlag(Response):
    quality_flag:str=Field(pattern=r'^[a-z0-9_]{1,96}$')
    observation_count:int=Field(ge=0)
    observation_fraction:float=Field(ge=0,le=1)


T=TypeVar('T')


class Page(Response,Generic[T]):
    items:list[T]=Field(max_length=100)
    total:int=Field(ge=0)
    limit:int=Field(ge=1,le=100)
    offset:int=Field(ge=0,le=100_000)


class QualitySummary(Response):
    overview:AnalyticsMetrics
    flags:Page[QualityFlag]
    semantics:str='Flag occurrences overlap; missing sensors are not imputed.'


class Health(Response):
    status:Literal['ok']='ok'
    service:str='FleetPulse API'
    version:str='1.0.0'


class Readiness(Response):
    ready:bool
    components:dict[str,bool]


class ErrorDetail(Response):
    code:str
    message:str
    details:list[dict[str,str]]|None=None


class ErrorResponse(Response):
    error:ErrorDetail


class VehicleError(Response):
    method:Method
    split:Split
    vehicle_id:int
    windows:int=Field(ge=1)
    mae_kmh:float=Field(ge=0)
    rmse_kmh:float=Field(ge=0)


class ModelMetrics(Response):
    model_id:str
    target:str
    units:Literal['km/h']='km/h'
    feature_count:int=31
    selection:dict[str,Any]
    metrics:dict[str,dict[str,dict[str,float]]]
    strongest_baseline:Method
    improvements:dict[str,dict[str,float]]
    vehicle_cluster_bootstrap:dict[str,Any]
    limitations:list[str]


TABLE_MODELS={'fleet_overview':AnalyticsMetrics,'vehicle_analytics':VehicleAnalytics,
    'trip_analytics':TripAnalytics,'daily_fleet':DailyAnalytics,'monthly_fleet':MonthlyAnalytics,
    'powertrain_fleet':PowertrainAnalytics,'quality_metrics':QualityFlag,'vehicle_errors':VehicleError}
