"""Bounded Silver-to-ML feature engineering and fixed baseline evaluation."""
import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import shutil
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,sha256,footprint,local
from src.features.speed_windows import (FEATURES,SENSORS,TARGET,SEED,HORIZON_MS,GAP_MS,
    vehicle_split,examples_for_trip)
from src.features.baselines import evaluate
from src.quality.fuel_feasibility import window_support

INPUT=ROOT/'data/silver/ved'
OUTPUT=ROOT/'data/ml/speed'
RESULTS=ROOT/'results/day5'
VERSION='ved-speed-1'
COLUMNS=['vehicle_id','trip_id','elapsed_ms','speed_kmh','engine_type',
         'bronze_file','bronze_row_index',*SENSORS]
METADATA={'example_id':pa.string(),'vehicle_id':pa.int64(),'trip_id':pa.int64(),
    'split':pa.string(),'engine_type':pa.string(),'prediction_elapsed_ms':pa.int64(),
    'feature_start_ms':pa.int64(),'feature_end_ms':pa.int64(),'target_start_ms':pa.int64(),
    'target_end_ms':pa.int64(),'bronze_file':pa.string(),'past_start_bronze_row_index':pa.int64(),
    'prediction_bronze_row_index':pa.int64(),'target_end_bronze_row_index':pa.int64()}
SCHEMA=pa.schema(list(METADATA.items())+[(f,pa.float64()) for f in FEATURES]+[(TARGET,pa.float64())])
LOG=logging.getLogger('fleetpulse.features')


def immutable_hashes():
    return {p.relative_to(ROOT).as_posix():sha256(p) for layer in ('bronze','silver','gold')
        for p in sorted((ROOT/f'data/{layer}/ved').rglob('*.parquet'))}


def validate_examples(frame,splits):
    if frame.example_id.duplicated().any():
        raise ValueError('Duplicate example ID')
    if frame[['vehicle_id','trip_id','prediction_elapsed_ms']].duplicated().any():
        raise ValueError('Duplicate prediction anchor')
    if any(frame.split!=frame.vehicle_id.map(splits)) or frame.groupby('vehicle_id').split.nunique().max()!=1:
        raise ValueError('Vehicle split leakage')
    if set(FEATURES)&(set(METADATA)|{TARGET}):
        raise ValueError('Metadata or target in feature allowlist')
    if (not (frame.feature_end_ms==frame.prediction_elapsed_ms).all()
        or not (frame.target_start_ms==frame.prediction_elapsed_ms).all()
        or not (frame.prediction_elapsed_ms-frame.feature_start_ms==HORIZON_MS).all()
        or not (frame.target_end_ms-frame.prediction_elapsed_ms==HORIZON_MS).all()):
        raise ValueError('Temporal boundary violation')
    if not np.isfinite(frame[TARGET]).all() or (frame[TARGET]<0).any():
        raise ValueError('Invalid label')
    if not np.isfinite(frame.past_speed_time_mean_kmh).all():
        raise ValueError('Invalid required speed feature')
    for _,trip in frame.groupby(['vehicle_id','trip_id']):
        ordered=trip.sort_values('prediction_elapsed_ms')
        if (ordered.feature_start_ms.to_numpy()[1:]<=ordered.target_end_ms.to_numpy()[:-1]).any():
            raise ValueError('Contexts overlap or share a boundary observation')
    return {'passed':True,'duplicate_examples':0,'vehicle_overlap':0,
        'target_overlap':0,'context_shared_observations':0,'features':list(FEATURES)}


def save_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def build_tables(paths,vehicles,day3_by_trip=None):
    splits=vehicle_split(vehicles)  # Frozen before seeing any window or label.
    seen=set()
    records=[]
    trip_audit=[]
    source_rows=0
    for i,path in enumerate(paths):
        frame=pq.read_table(local(path),columns=COLUMNS).to_pandas()
        frame.sort_values(['vehicle_id','trip_id','elapsed_ms','bronze_row_index'],
                          kind='stable',inplace=True)
        source_rows+=len(frame)
        for (vehicle,trip),group in frame.groupby(['vehicle_id','trip_id'],sort=False):
            key=int(vehicle),int(trip)
            if key in seen:
                raise ValueError('A trip crosses input files; bounded scheduling must change')
            seen.add(key)
            if int(vehicle) not in splits or group.bronze_file.nunique()!=1:
                raise ValueError('Vehicle/provenance does not match frozen source contract')
            examples,counts=examples_for_trip(group,splits[int(vehicle)],str(group.bronze_file.iloc[0]))
            reference=window_support(group.elapsed_ms.to_numpy(),group.speed_kmh.to_numpy(),2000)
            if counts['candidate_windows']!=reference['paired_windows'] or counts['day3_nonoverlap_pairs']!=reference['nonoverlap_pairs']:
                raise ValueError('Independent Day 3 window-support reconciliation failed')
            records.extend(examples)
            previous=int(day3_by_trip.get(key,0)) if day3_by_trip is not None else counts['candidate_windows']
            trip_audit.append({'vehicle_id':int(vehicle),'trip_id':int(trip),
                'source_rows':len(group),'silver_file':str(path.relative_to(ROOT)),
                'day3_bronze_candidate_windows':previous,**counts,
                'candidate_difference':counts['candidate_windows']-previous})
        if i%5==0 or i==len(paths)-1:
            LOG.info('Processed %s/%s files, %s trips, %s disjoint examples',i+1,len(paths),len(seen),len(records))
    table=pa.Table.from_pylist(records,schema=SCHEMA)
    frame=table.to_pandas().sort_values(['vehicle_id','trip_id','prediction_elapsed_ms']).reset_index(drop=True)
    validation=validate_examples(frame,splits)
    if set(frame.vehicle_id)-set(vehicles):
        raise ValueError('Unknown source vehicle')
    return frame,pd.DataFrame(trip_audit),splits,source_rows,validation


def run(force=False):
    started=time.perf_counter()
    RESULTS.mkdir(parents=True,exist_ok=True)
    used=footprint()
    if used+150_000_000>=10_000_000_000 or shutil.disk_usage(ROOT).free<250_000_000:
        raise RuntimeError('ML storage/free-space gate failed')
    before=immutable_hashes()
    paths=sorted(INPUT.rglob('*.parquet'))
    vehicles=pq.read_table(ROOT/'data/gold/ved/vehicle_analytics.parquet',columns=['vehicle_id'])['vehicle_id'].to_pylist()
    day3_path=ROOT/'results/day3/fuel_by_trip.csv'
    day3_summary=json.loads((ROOT/'results/day3/fuel_feasibility.json').read_text())
    reference=pd.read_csv(day3_path,usecols=['vehicle_id','trip_id','speed_paired_windows'])
    day3_by_trip={(int(r.vehicle_id),int(r.trip_id)):int(r.speed_paired_windows) for r in reference.itertuples()}
    code={p.name:sha256(p) for p in (Path(__file__),Path(__file__).with_name('speed_windows.py'),
        Path(__file__).with_name('baselines.py'),ROOT/'src/quality/fuel_feasibility.py')}
    config={'version':VERSION,'seed':SEED,'split_policy':'hash-ranked all source vehicles 70/15/remainder',
        'max_gap_ms':GAP_MS,'horizon_ms':HORIZON_MS,'anchor_grid_ms':1000,
        'selection':'greedy earliest complete context; next feature start strictly after prior target end',
        'features':list(FEATURES),'code_sha256':code,
        'day3_reference_sha256':{p.name:sha256(p) for p in (
            day3_path,ROOT/'results/day3/fuel_feasibility.json')},'numpy':np.__version__,
        'pandas':pd.__version__,'pyarrow':pa.__version__}
    manifest_path=RESULTS/'dataset_manifest.json'
    if manifest_path.exists() and not force:
        previous=json.loads(manifest_path.read_text())
        if previous['inputs']==before and previous['config']==config and all(
            (ROOT/p).exists() and sha256(ROOT/p)==digest for p,digest in previous['outputs'].items()):
            return {'cached':True,'runtime_seconds':time.perf_counter()-started,'windows':previous['selected_windows']}
    compute_start=time.perf_counter()
    frame,audit,splits,rows,validation=build_tables(paths,vehicles,day3_by_trip)
    baseline_start=time.perf_counter()
    metrics=evaluate(frame)
    baseline_seconds=time.perf_counter()-baseline_start
    support=day3_summary['alternative_support']['speed']
    candidate_vehicles=audit.loc[audit.candidate_windows>0,'vehicle_id'].nunique()
    if rows!=22_434_106 or len(audit)!=32_552:
        raise ValueError('Silver row/trip reconciliation failed')
    differences=audit[audit.candidate_difference!=0].to_dict('records')
    split_summary={}
    for split in ('train','validation','test'):
        subset=frame[frame.split==split]
        split_summary[split]={'assigned_source_vehicles':sum(v==split for v in splits.values()),
            'usable_vehicles':int(subset.vehicle_id.nunique()),'usable_trips':int(subset[['vehicle_id','trip_id']].drop_duplicates().shape[0]),
            'selected_windows':len(subset),'candidate_windows':int(audit[audit.vehicle_id.map(splits)==split].candidate_windows.sum()),
            'powertrain_vehicles':subset[['vehicle_id','engine_type']].drop_duplicates().engine_type.value_counts().to_dict()}
    stage=ROOT/'data/tmp/ml-speed-stage'
    stage.mkdir(parents=True,exist_ok=True)
    output_paths=[]
    for split in ('train','validation','test'):
        destination=stage/f'{split}.parquet'
        subset=frame[frame.split==split]
        pq.write_table(pa.Table.from_pandas(subset,schema=SCHEMA,preserve_index=False),destination,
                       compression='zstd',row_group_size=65536)
        reread=pq.read_table(destination)
        if len(reread)!=len(subset) or reread.schema.remove_metadata()!=SCHEMA:
            raise RuntimeError('ML output readability/schema/count mismatch')
        output_paths.append(destination)
    if immutable_hashes()!=before:
        raise RuntimeError('Bronze/Silver/Gold changed during feature processing')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for path in output_paths:
        os.replace(path,OUTPUT/path.name)
    stage.rmdir()
    pq.write_table(pa.Table.from_pandas(audit,preserve_index=False),RESULTS/'window_audit_by_trip.parquet',compression='zstd')
    pq.write_table(pa.Table.from_pylist(metrics.pop('per_vehicle_metrics')),RESULTS/'baseline_by_vehicle.parquet',compression='zstd')
    save_json(RESULTS/'baseline_metrics.json',metrics)
    split_manifest={'seed':SEED,'policy':config['split_policy'],
        'vehicle_assignments':{str(v):s for v,s in sorted(splits.items())},'summary':split_summary,
        'features':list(FEATURES),'metadata_columns':list(METADATA),'target_column':TARGET,
        'fit_policy':'historical mean from selected training labels only; no tuning'}
    save_json(RESULTS/'split_manifest.json',split_manifest)
    compute_seconds=time.perf_counter()-compute_start
    result={'cached':False,'inputs':before,'config':config,'source_rows':rows,'source_trips':len(audit),
        'candidate_windows':int(audit.candidate_windows.sum()),'candidate_vehicles':int(candidate_vehicles),
        'candidate_trips':int((audit.candidate_windows>0).sum()),
        'day3_reference_windows':int(support['paired_windows']),
        'day3_reference_vehicles':len(support['vehicles']),
        'day3_boundary_touching_contexts':int(audit.day3_nonoverlap_pairs.sum()),
        'day3_count_differences':differences,'selected_windows':len(frame),
        'selected_vehicles':int(frame.vehicle_id.nunique()),'splits':split_summary,
        'validation':validation,'baseline_metrics':metrics,'baseline_seconds':baseline_seconds,
        'compute_seconds':compute_seconds,'runtime_seconds':time.perf_counter()-started,
        'immutable_layers_unchanged':True,'ml_parquet_bytes':sum(p.stat().st_size for p in OUTPUT.glob('*.parquet')),
        'feature_missing_counts':{f:int(frame[f].isna().sum()) for f in FEATURES},
        'project_bytes':footprint()}
    outputs=[*OUTPUT.glob('*.parquet'),RESULTS/'window_audit_by_trip.parquet',
        RESULTS/'baseline_by_vehicle.parquet',RESULTS/'baseline_metrics.json',RESULTS/'split_manifest.json']
    result['outputs']={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(outputs)}
    save_json(manifest_path,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    result=run(args.force)
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','outputs','config')},indent=2))


if __name__=='__main__':
    main()
