"""Audit saved ML Parquet, source provenance and temporal disjointness."""
import json
import math
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.features.build_speed_dataset import OUTPUT,RESULTS,ROOT,SCHEMA,immutable_hashes,save_json
from src.features.speed_windows import FEATURES,TARGET,SENSORS


def validate():
    started=time.perf_counter()
    manifest=json.loads((RESULTS/'dataset_manifest.json').read_text())
    frames=[]
    for split in ('train','validation','test'):
        table=pq.read_table(OUTPUT/f'{split}.parquet')
        assert table.schema.remove_metadata()==SCHEMA
        frame=table.to_pandas()
        assert (frame.split==split).all()
        frames.append(frame)
    frame=pd.concat(frames,ignore_index=True)
    max_target_error=0.
    max_past_mean_error=0.
    checked=0
    for source,examples in frame.groupby('bronze_file',sort=True):
        silver=ROOT/'data/silver/ved'/source
        columns=['vehicle_id','trip_id','elapsed_ms','speed_kmh','bronze_row_index',*SENSORS]
        data=pq.read_table(silver,columns=columns).to_pandas()
        grouped=data.groupby(['vehicle_id','trip_id'],sort=False)
        for (vehicle,trip),windows in examples.groupby(['vehicle_id','trip_id'],sort=False):
            observed=grouped.get_group((vehicle,trip)).sort_values(['elapsed_ms','bronze_row_index'])
            times=observed.elapsed_ms.to_numpy()
            speed=observed.speed_kmh.to_numpy(dtype=float)
            for row in windows.itertuples(index=False):
                left,anchor,right=np.searchsorted(times,[row.feature_start_ms,row.prediction_elapsed_ms,row.target_end_ms])
                assert times[left]==row.feature_start_ms and times[anchor]==row.prediction_elapsed_ms and times[right]==row.target_end_ms
                span=times[left:right+1]
                assert np.all((np.diff(span)>0)&(np.diff(span)<=2000))
                assert np.isfinite(speed[left:right+1]).all() and (speed[left:right+1]>=0).all()
                assert int(observed.bronze_row_index.iloc[left])==row.past_start_bronze_row_index
                assert int(observed.bronze_row_index.iloc[anchor])==row.prediction_bronze_row_index
                assert int(observed.bronze_row_index.iloc[right])==row.target_end_bronze_row_index
                # Direct arithmetic on source slices, independent of feature/window helpers.
                past=observed.iloc[left:anchor+1]
                seconds=np.diff(times[anchor:right+1])/1000.
                target=float(np.dot(seconds,(speed[anchor:right]+speed[anchor+1:right+1])/2)/60)
                past_seconds=np.diff(times[left:anchor+1])/1000.
                past_mean=float(np.dot(past_seconds,(speed[left:anchor]+speed[left+1:anchor+1])/2)/60)
                max_target_error=max(max_target_error,abs(target-getattr(row,TARGET)))
                max_past_mean_error=max(max_past_mean_error,abs(past_mean-row.past_speed_time_mean_kmh))
                assert math.isclose(target,getattr(row,TARGET),abs_tol=1e-10)
                assert math.isclose(past_mean,row.past_speed_time_mean_kmh,abs_tol=1e-10)
                assert row.past_speed_last_kmh==speed[anchor]
                for sensor in SENSORS:
                    values=past[sensor].to_numpy(dtype=float)
                    present=np.isfinite(values)
                    actual=getattr(row,f'past_{sensor}_sample_mean')
                    if present.any():
                        assert math.isclose(actual,float(values[present].mean()),abs_tol=1e-10)
                    else:
                        assert math.isnan(actual)
                    assert getattr(row,f'past_{sensor}_observed_fraction')==float(present.mean())
                checked+=1
    hashes=pd.util.hash_pandas_object(frame[list(FEATURES)+[TARGET]],index=False)
    signatures=pd.DataFrame({'signature':hashes,'split':frame.split})
    duplicate=frame.duplicated(list(FEATURES)+[TARGET],keep=False)
    cross=signatures.groupby('signature').split.nunique()
    # Equal measurements at different times are legitimate stationary/steady
    # observations, not duplicate source examples; report them without filtering
    # on test labels or changing the predeclared evaluation cohort.
    diagnostics={'identical_feature_target_rows':int(duplicate.sum()),
        'identical_feature_target_extra_rows':int(frame.duplicated(list(FEATURES)+[TARGET]).sum()),
        'cross_split_identical_signature_groups':int((cross>1).sum()),
        'unique_source_examples':int(frame.example_id.nunique())}
    moving=frame[frame[TARGET]>0]
    moving_metrics={}
    train_mean=manifest['baseline_metrics']['training_historical_mean_kmh']
    for split in ('validation','test'):
        part=moving[moving.split==split]
        predictions={'last_observed_speed':part.past_speed_last_kmh.to_numpy(),
            'past_mean_persistence':part.past_speed_time_mean_kmh.to_numpy(),
            'training_historical_mean':np.full(len(part),train_mean)}
        moving_metrics[split]={'windows':len(part),'vehicles':int(part.vehicle_id.nunique()),
            'metrics':{name:{'mae_kmh':float(np.abs(pred-part[TARGET].to_numpy()).mean()),
                             'rmse_kmh':float(np.sqrt(np.mean((pred-part[TARGET].to_numpy())**2)))}
                       for name,pred in predictions.items()}}
    if immutable_hashes()!=manifest['inputs']:
        raise RuntimeError('Immutable layer hashes changed')
    result={'passed':True,'windows_independently_checked':checked,
        'max_target_absolute_error_kmh':max_target_error,'max_past_mean_absolute_error_kmh':max_past_mean_error,
        'source_provenance_verified':True,'immutable_layers_unchanged':True,
        'duplicate_content_diagnostics':diagnostics,'zero_target_windows':int((frame[TARGET]==0).sum()),
        'moving_target_sensitivity':moving_metrics,'runtime_seconds':time.perf_counter()-started}
    save_json(RESULTS/'independent_validation.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    validate()
