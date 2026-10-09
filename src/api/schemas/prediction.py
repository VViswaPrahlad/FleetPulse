import math
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,create_model,model_validator

from src.features.speed_windows import FEATURES,SENSORS


def feature_definition(name):
    units='fraction'
    bounds={}
    nullable=name.endswith('_sample_mean') and any(name==f'past_{s}_sample_mean' for s in SENSORS)
    if name=='past_sample_count':
        units='observations'
        bounds={'ge':31,'le':60001}
    elif name=='past_gap_max_s':
        units='s'
        bounds={'ge':.001,'le':2}
    elif 'fraction' in name:
        # Day 5 interval sums can yield 1.0000000000000002. Preserve those
        # original model inputs; tolerate rounding rather than clipping them.
        bounds={'ge':0,'le':1+1e-12}
    elif 'accel' in name:
        units='m/s^2'
        if 'stddev' in name or 'abs_time' in name:
            bounds={'ge':0}
    elif name=='past_speed_slope_kmh_per_s':
        units='km/h/s'
    elif 'speed' in name:
        units='km/h'
        if name!='past_speed_change_kmh':
            bounds={'ge':0}
    elif 'engine_rpm' in name:
        units='rpm'
        bounds={'ge':0}
    elif 'maf_g_s' in name:
        units='g/s'
        bounds={'ge':0}
    elif 'absolute_load' in name:
        units='%'
        bounds={'ge':0}  # Manufacturer load can exceed 100%; Silver retains it.
    elif 'outside_air_temp' in name:
        units='degC'
        bounds={'ge':-273.15}
    elif 'battery_soc' in name:
        units='%'
        bounds={'ge':0,'le':100}
    elif 'hv_battery_current' in name:
        units='A'  # Signed OEM convention retained.
    return {'name':name,'units':units,'nullable':nullable,'required':True,**bounds}


FEATURE_DEFINITIONS=tuple(feature_definition(name) for name in FEATURES)


class FeatureBase(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)

    @model_validator(mode='after')
    def coherent_prepared_statistics(self):
        count=self.past_sample_count
        if count!=math.floor(count):
            raise ValueError('Observation count must be integral')
        minimum,maximum=self.past_speed_min_kmh,self.past_speed_max_kmh
        tolerance=1e-7
        if (count-1)*self.past_gap_max_s<60-tolerance:
            raise ValueError('Sampling statistics cannot cover 60 seconds')
        if minimum>maximum:
            raise ValueError('Speed extrema are inconsistent')
        for name in ('past_speed_time_mean_kmh','past_speed_sample_mean_kmh',
                     'past_speed_median_kmh','past_speed_first_kmh','past_speed_last_kmh'):
            if not minimum-tolerance<=getattr(self,name)<=maximum+tolerance:
                raise ValueError('Speed statistic is outside extrema')
        if abs(self.past_speed_change_kmh-(self.past_speed_last_kmh-self.past_speed_first_kmh))>tolerance:
            raise ValueError('Endpoint speed change is inconsistent')
        if self.past_speed_stddev_kmh>(maximum-minimum)/2+tolerance:
            raise ValueError('Speed variability is inconsistent')
        if self.past_accel_min_m_s2>self.past_accel_max_m_s2 or not (
            self.past_accel_min_m_s2-tolerance<=self.past_accel_mean_m_s2<=self.past_accel_max_m_s2+tolerance):
            raise ValueError('Acceleration statistics are inconsistent')
        if self.past_accel_stddev_m_s2>(self.past_accel_max_m_s2-self.past_accel_min_m_s2)/2+tolerance:
            raise ValueError('Acceleration variability is inconsistent')
        absolute=self.past_accel_abs_time_mean_m_s2
        if absolute<abs(self.past_speed_change_kmh)/216-tolerance or absolute>max(
            abs(self.past_accel_min_m_s2),abs(self.past_accel_max_m_s2))+tolerance:
            raise ValueError('Absolute acceleration statistics are inconsistent')
        for sensor in SENSORS:
            mean=getattr(self,f'past_{sensor}_sample_mean')
            fraction=getattr(self,f'past_{sensor}_observed_fraction')
            if (mean is None)!=(fraction==0):
                raise ValueError('Missing sensor mean and availability disagree')
            if not math.isclose(fraction*count,round(fraction*count),abs_tol=tolerance):
                raise ValueError('Sensor availability and observation count disagree')
        if not math.isclose(self.past_stop_sample_fraction*count,
                            round(self.past_stop_sample_fraction*count),abs_tol=tolerance):
            raise ValueError('Stop sample fraction and observation count disagree')
        zeros=round(self.past_stop_sample_fraction*count)
        if (minimum>0 and zeros!=0) or (maximum==0 and zeros!=count):
            raise ValueError('Stopped observations and speed extrema disagree')
        if self.past_stop_interval_fraction>max(0,zeros-1)*self.past_gap_max_s/60+tolerance:
            raise ValueError('Stopped interval statistics are inconsistent')
        return self


PreparedFeatures=create_model('PreparedFeatures',__base__=FeatureBase,
    **{d['name']:(float|None if d['nullable'] else float,
        Field(...,description=f"Past-only statistic; units: {d['units']}.",
              **{k:d[k] for k in ('ge','le') if k in d})) for d in FEATURE_DEFINITIONS})


class PredictionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    input_kind:Literal['prepared_past_features']
    feature_schema_version:Literal['ved-speed-1']
    history_seconds:Literal[60]
    speed_unit:Literal['km/h']
    acceleration_unit:Literal['m/s^2']
    time_unit:Literal['s']
    features:PreparedFeatures


class PredictionResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    predicted_mean_speed_kmh:float
    forecast_seconds:Literal[60]=60
    history_seconds:Literal[60]=60
    units:Literal['km/h']='km/h'
    model_id:str
    input_kind:Literal['prepared_past_features']='prepared_past_features'
    warning:str='Prepared past-only features are required; the API cannot certify their source telemetry.'


class FeatureDefinition(BaseModel):
    name:str
    units:str
    nullable:bool
    required:bool
    ge:float|None=None
    le:float|None=None


class FeatureContract(BaseModel):
    schema_version:Literal['ved-speed-1']
    history_seconds:Literal[60]
    forecast_seconds:Literal[60]
    max_sampling_gap_seconds:Literal[2]
    input_kind:Literal['prepared_past_features']
    feature_order:list[str]=Field(min_length=31,max_length=31)
    features:list[FeatureDefinition]=Field(min_length=31,max_length=31)
    null_policy:str
    scope:str
