"""Exact-endpoint speed windows; no resampling, filling or future features."""
import hashlib

import numpy as np

HORIZON_MS = 60_000
GAP_MS = 2000
SEED = 'fleetpulse-speed-v1'
SENSORS = ('engine_rpm','maf_g_s','absolute_load_pct','outside_air_temp_c',
           'battery_soc_pct','hv_battery_current_a')
SPEED_FEATURES = (
    'past_speed_time_mean_kmh','past_speed_sample_mean_kmh','past_speed_median_kmh',
    'past_speed_stddev_kmh','past_speed_min_kmh','past_speed_max_kmh',
    'past_speed_first_kmh','past_speed_last_kmh','past_speed_change_kmh',
    'past_speed_slope_kmh_per_s','past_stop_interval_fraction','past_stop_sample_fraction',
    'past_accel_mean_m_s2','past_accel_stddev_m_s2','past_accel_min_m_s2',
    'past_accel_max_m_s2','past_accel_abs_time_mean_m_s2',
    'past_sample_count','past_gap_max_s',
)
FEATURES = SPEED_FEATURES + tuple(f'past_{sensor}_{stat}' for sensor in SENSORS
                                for stat in ('sample_mean','observed_fraction'))
TARGET = 'target_mean_speed_kmh'


def vehicle_split(vehicles):
    """Freeze 70/15/remaining percent of all source vehicles, independent of labels."""
    vehicles = sorted(set(int(v) for v in vehicles))
    if len(vehicles)<3:
        raise ValueError('At least three vehicles required')
    ranked = sorted(vehicles,key=lambda v:(hashlib.sha256(f'{SEED}|{v}'.encode()).hexdigest(),v))
    train = max(1,min(len(ranked)-2,int(len(ranked)*0.70)))
    validation = max(1,min(len(ranked)-train-1,int(len(ranked)*0.15)))
    if train<1 or train+validation>=len(ranked):
        raise ValueError('Split is too small')
    return {v:('train' if i<train else 'validation' if i<train+validation else 'test')
            for i,v in enumerate(ranked)}


def eligible_indices(times,speed):
    """Return (past start, prediction, target end) positions, sorted trip only.

    Every observation in the closed 120s span must have valid speed/time.
    Both members of duplicate timestamps are invalid. Future coverage is an
    offline label eligibility condition, never a feature.
    """
    times,speed=np.asarray(times),np.asarray(speed,dtype=float)
    if len(times)!=len(speed):
        raise ValueError('Length mismatch')
    if len(times)==0:
        return np.empty((0,3),dtype=np.int64)
    if np.any(~np.isfinite(times)) or np.any(np.diff(times)<0):
        raise ValueError('Trip timestamps must be finite and chronologically sorted')
    dt=np.diff(times)
    duplicate=np.zeros(len(times),dtype=bool)
    duplicate[1:] |= dt==0
    duplicate[:-1] |= dt==0
    valid=(times>=0)&(times==np.floor(times))&~duplicate&np.isfinite(speed)&(speed>=0)
    bad=np.r_[0,np.cumsum(~valid)]
    bad_edge=np.r_[0,np.cumsum((dt<=0)|(dt>GAP_MS))]
    anchors=np.flatnonzero(valid & (times%1000==0))
    left=np.searchsorted(times,times[anchors]-HORIZON_MS)
    right=np.searchsorted(times,times[anchors]+HORIZON_MS)
    exists=right<len(times)
    right=np.minimum(right,len(times)-1)
    exists &= (times[left]==times[anchors]-HORIZON_MS)&(times[right]==times[anchors]+HORIZON_MS)
    exists &= (bad[right+1]-bad[left]==0)&(bad_edge[right]-bad_edge[left]==0)
    return np.column_stack((left[exists],anchors[exists],right[exists])).astype(np.int64)


def disjoint_contexts(times,indices,strict=True):
    """Earliest-first deterministic selection; strict mode shares no endpoints."""
    chosen=[]
    previous_end=-np.inf
    for row in indices:
        left,_,right=row
        if (times[left]>previous_end if strict else times[left]>=previous_end):
            chosen.append(row)
            previous_end=times[right]
    return np.asarray(chosen,dtype=np.int64).reshape((-1,3))


def temporal_mean(times,values):
    seconds=np.diff(times)/1000.
    return float(np.sum((values[:-1]+values[1:])*0.5*seconds)/np.sum(seconds))


def past_features(times,speed,sensors=None):
    """Accept only already-sliced [t-60,t] arrays; no access to future columns."""
    times,speed=np.asarray(times),np.asarray(speed,dtype=float)
    if (len(times)<2 or times[-1]-times[0]!=HORIZON_MS
        or np.any(np.diff(times)<=0) or np.any(np.diff(times)>GAP_MS)
        or not np.all(np.isfinite(speed)&(speed>=0))):
        raise ValueError('Invalid past context')
    dt=np.diff(times)/1000.
    elapsed=(times-times[0])/1000.
    accel=np.diff(speed)/3.6/dt
    centered=elapsed-elapsed.mean()
    features=dict(zip(SPEED_FEATURES,[
        temporal_mean(times,speed),float(speed.mean()),float(np.median(speed)),
        float(speed.std(ddof=0)),float(speed.min()),float(speed.max()),
        float(speed[0]),float(speed[-1]),float(speed[-1]-speed[0]),
        float(np.sum(centered*(speed-speed.mean()))/np.sum(centered**2)),
        float(np.sum(dt[(speed[:-1]==0)&(speed[1:]==0)])/60.),float(np.mean(speed==0)),
        float(accel.mean()),float(accel.std(ddof=0)),float(accel.min()),float(accel.max()),
        float(np.sum(np.abs(accel)*dt)/60.),len(speed),float(dt.max())]))
    for sensor in SENSORS:
        values=np.asarray((sensors or {}).get(sensor,np.full(len(times),np.nan)),dtype=float)
        if len(values)!=len(times):
            raise ValueError('Sensor length mismatch')
        present=np.isfinite(values)
        features[f'past_{sensor}_sample_mean']=float(values[present].mean()) if present.any() else None
        features[f'past_{sensor}_observed_fraction']=float(present.mean())
    return features


def examples_for_trip(frame,split,bronze_file):
    """Caller supplies one vehicle/trip, sorted by elapsed and Bronze index."""
    if frame.vehicle_id.nunique()!=1 or frame.trip_id.nunique()!=1:
        raise ValueError('Exactly one vehicle and trip required')
    times=frame.elapsed_ms.to_numpy()
    speed=frame.speed_kmh.to_numpy(dtype=float)
    indices=eligible_indices(times,speed)
    selected=disjoint_contexts(times,indices,strict=True)
    vehicle,trip=int(frame.vehicle_id.iloc[0]),int(frame.trip_id.iloc[0])
    examples=[]
    for left,anchor,right in selected:
        past=frame.iloc[left:anchor+1]
        sensors={name:past[name].to_numpy(dtype=float) for name in SENSORS}
        feature=past_features(times[left:anchor+1],speed[left:anchor+1],sensors)
        prediction=int(times[anchor])
        examples.append({'example_id':f'{vehicle}:{trip}:{prediction}',
            'vehicle_id':vehicle,'trip_id':trip,'split':split,'engine_type':str(frame.engine_type.iloc[0]),
            'prediction_elapsed_ms':prediction,'feature_start_ms':int(times[left]),
            'feature_end_ms':prediction,'target_start_ms':prediction,'target_end_ms':int(times[right]),
            'bronze_file':bronze_file,'past_start_bronze_row_index':int(frame.bronze_row_index.iloc[left]),
            'prediction_bronze_row_index':int(frame.bronze_row_index.iloc[anchor]),
            'target_end_bronze_row_index':int(frame.bronze_row_index.iloc[right]),
            **feature,TARGET:temporal_mean(times[anchor:right+1],speed[anchor:right+1])})
    return examples,{'candidate_windows':len(indices),
        'day3_nonoverlap_pairs':len(disjoint_contexts(times,indices,strict=False)),
        'selected_windows':len(selected)}
