"""Small measured-style fixtures; no real sensor dataset needed."""
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.analytics.build_gold import ROOT,sha256
from src.features.speed_windows import (FEATURES,SENSORS,TARGET,vehicle_split,
    eligible_indices,disjoint_contexts,past_features,temporal_mean,examples_for_trip)
from src.features.baselines import fit_historical_mean,evaluate
from src.features.build_speed_dataset import SCHEMA,build_tables,validate_examples


def trip(vehicle=1,trip_id=1,end=240):
    times=np.arange(end+1,dtype=np.int64)*1000
    frame=pd.DataFrame({'vehicle_id':vehicle,'trip_id':trip_id,'elapsed_ms':times,
        'speed_kmh':np.full(len(times),60.),'engine_type':'ICE',
        'bronze_file':'fixture.parquet','bronze_row_index':np.arange(len(times),dtype=np.int64)})
    for sensor in SENSORS:
        frame[sensor]=np.nan
    return frame


def test_exact_endpoints_anchor_grid_and_candidate_count():
    frame=trip()
    rows=eligible_indices(frame.elapsed_ms.to_numpy(),frame.speed_kmh.to_numpy())
    assert len(rows)==121
    assert tuple(rows[0])==(0,60,120)
    assert tuple(rows[-1])==(120,180,240)
    assert (frame.elapsed_ms.to_numpy()[rows[:,1]]%1000==0).all()


def test_strict_contexts_share_no_endpoints():
    frame=trip()
    times=frame.elapsed_ms.to_numpy()
    rows=eligible_indices(times,frame.speed_kmh.to_numpy())
    assert len(disjoint_contexts(times,rows,strict=False))==2
    assert len(disjoint_contexts(times,rows,strict=True))==1


@pytest.mark.parametrize('kind',['gap','missing_speed','duplicate','missing_endpoint'])
def test_invalid_future_context_is_not_bridged(kind):
    frame=trip()
    if kind=='gap':
        frame=frame[~frame.elapsed_ms.isin([100000,101000])]
    elif kind=='missing_speed':
        frame.loc[frame.elapsed_ms==90000,'speed_kmh']=np.nan
    elif kind=='duplicate':
        frame=pd.concat([frame,frame[frame.elapsed_ms==90000]]).sort_values('elapsed_ms',kind='stable')
    else:
        frame=frame[frame.elapsed_ms!=120000]
    rows=eligible_indices(frame.elapsed_ms.to_numpy(),frame.speed_kmh.to_numpy())
    assert 60000 not in frame.elapsed_ms.to_numpy()[rows[:,1]]


def test_exact_two_second_gap_is_allowed():
    frame=trip()
    frame=frame[frame.elapsed_ms!=100000]
    rows=eligible_indices(frame.elapsed_ms.to_numpy(),frame.speed_kmh.to_numpy())
    assert 60000 in frame.elapsed_ms.to_numpy()[rows[:,1]]


def test_negative_timestamps_cannot_enter_context():
    times=np.arange(-1000,121000,1000)
    rows=eligible_indices(times,np.full(len(times),60.))
    assert np.all(times[rows[:,0]]>=0)


def test_unsorted_trip_is_rejected():
    with pytest.raises(ValueError,match='sorted'):
        eligible_indices(np.array([0,2000,1000]),np.array([60.,60.,60.]))


def test_constant_speed_feature_arithmetic_and_missing_sensor_semantics():
    frame=trip(end=60)
    result=past_features(frame.elapsed_ms.to_numpy(),frame.speed_kmh.to_numpy())
    assert result['past_speed_time_mean_kmh']==60
    assert result['past_speed_median_kmh']==60
    assert result['past_speed_stddev_kmh']==0
    assert result['past_accel_abs_time_mean_m_s2']==0
    assert result['past_stop_interval_fraction']==0
    for sensor in SENSORS:
        assert result[f'past_{sensor}_sample_mean'] is None
        assert result[f'past_{sensor}_observed_fraction']==0


def test_ramp_acceleration_and_target_units():
    times=np.arange(61)*1000
    speed=np.arange(61)*3.6
    result=past_features(times,speed)
    assert result['past_speed_time_mean_kmh']==pytest.approx(108)
    assert result['past_accel_mean_m_s2']==pytest.approx(1.)
    assert result['past_accel_abs_time_mean_m_s2']==pytest.approx(1.)
    assert result['past_speed_slope_kmh_per_s']==pytest.approx(3.6)
    assert temporal_mean(times,speed)==pytest.approx(108)


def test_stationary_fraction_is_measured_zero_not_missing():
    times=np.arange(61)*1000
    result=past_features(times,np.zeros(61))
    assert result['past_stop_interval_fraction']==1
    assert result['past_stop_sample_fraction']==1
    assert result['past_speed_time_mean_kmh']==0


def test_future_changes_labels_but_cannot_change_features():
    frame=trip()
    before,_=examples_for_trip(frame,'train','fixture.parquet')
    frame.loc[frame.elapsed_ms>60000,'speed_kmh']=100.
    frame.loc[frame.elapsed_ms>60000,'engine_rpm']=9999.
    after,_=examples_for_trip(frame,'train','fixture.parquet')
    assert {f:before[0][f] for f in FEATURES}=={f:after[0][f] for f in FEATURES}
    assert before[0][TARGET]!=after[0][TARGET]
    assert before[0]['feature_end_ms']==before[0]['target_start_ms']==60000


def test_trip_boundaries_cannot_be_combined():
    with pytest.raises(ValueError,match='one vehicle and trip'):
        examples_for_trip(pd.concat([trip(),trip(trip_id=2)]),'train','fixture.parquet')


def test_deterministic_disjoint_vehicle_split():
    vehicles=list(range(384))
    result=vehicle_split(vehicles)
    assert result==vehicle_split(vehicles[::-1])
    assert list(result.values()).count('train')==268
    assert list(result.values()).count('validation')==57
    assert list(result.values()).count('test')==59
    ids=[{v for v,s in result.items() if s==split} for split in ('train','validation','test')]
    assert not (ids[0]&ids[1] or ids[0]&ids[2] or ids[1]&ids[2])
    assert 'vehicle_id' not in FEATURES and TARGET not in FEATURES


def test_three_vehicle_fixture_has_three_nonempty_splits():
    assert set(vehicle_split([1,2,3]).values())=={'train','validation','test'}


def baseline_fixture():
    return pd.DataFrame({'vehicle_id':[1,1,2,3],'split':['train','train','validation','test'],
        TARGET:[10.,30.,50.,70.],'past_speed_last_kmh':[10.,30.,40.,80.],
        'past_speed_time_mean_kmh':[0.,20.,30.,60.]})


def test_historical_baseline_uses_training_only_and_metrics_have_correct_units():
    frame=baseline_fixture()
    result=evaluate(frame)
    assert result['training_historical_mean_kmh']==20
    assert result['metrics']['validation']['last_observed_speed']['mae_kmh']==10
    assert result['metrics']['test']['last_observed_speed']['rmse_kmh']==10
    frame.loc[frame.split!='train',TARGET]=9999.
    assert fit_historical_mean(frame)==20


def test_baseline_requires_training_targets():
    with pytest.raises(ValueError,match='training'):
        fit_historical_mean(baseline_fixture().query('split != "train"'))


def test_leakage_audit_rejects_wrong_split_duplicate_and_overlap():
    examples,_=examples_for_trip(trip(),'train','fixture.parquet')
    frame=pd.DataFrame(examples)
    assert validate_examples(frame,{1:'train'})['passed']
    with pytest.raises(ValueError,match='split'):
        validate_examples(frame,{1:'test'})
    with pytest.raises(ValueError,match='Duplicate'):
        validate_examples(pd.concat([frame,frame]),{1:'train'})
    other=frame.copy()
    other['example_id']='different'
    other['prediction_elapsed_ms']+=1000
    other['feature_start_ms']+=1000
    other['feature_end_ms']+=1000
    other['target_start_ms']+=1000
    other['target_end_ms']+=1000
    with pytest.raises(ValueError,match='overlap'):
        validate_examples(pd.concat([frame,other]),{1:'train'})


def test_fixture_parquet_pipeline_readability_reproducibility_and_immutability(tmp_path):
    path=tmp_path/'silver.parquet'
    frames=[trip(vehicle=v) for v in range(1,11)]
    pq.write_table(pa.Table.from_pandas(pd.concat(frames),preserve_index=False),path)
    before=sha256(path)
    hashes=[]
    for i in range(2):
        frame,audit,splits,rows,validation=build_tables([path],range(1,11))
        assert len(frame)==10 and rows==2410
        assert audit.candidate_windows.sum()==1210 and validation['passed']
        assert evaluate(frame)['training_historical_mean_kmh']==60
        output=tmp_path/f'ml{i}.parquet'
        pq.write_table(pa.Table.from_pandas(frame,schema=SCHEMA,preserve_index=False),output,compression='zstd')
        assert pq.read_table(output).schema.remove_metadata()==SCHEMA
        hashes.append(sha256(output))
    assert hashes[0]==hashes[1] and sha256(path)==before


def test_cross_file_trip_cannot_be_silently_split(tmp_path):
    a,b=tmp_path/'a.parquet',tmp_path/'b.parquet'
    table=pa.Table.from_pandas(trip(),preserve_index=False)
    pq.write_table(table,a)
    pq.write_table(table,b)
    with pytest.raises(ValueError,match='crosses input files'):
        build_tables([a,b],range(1,11))
