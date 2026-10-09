import json
import inspect

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from src.analytics.build_gold import sha256
from src.features.speed_windows import FEATURES,TARGET
from src.ml.train_speed import feature_matrix,select_model
from src.ml.inference import load_model,predict_features
from src.ml.evaluation import score,improvement,cluster_bootstrap,cohort_errors


def fixture_frames():
    rng=np.random.default_rng(417)
    frames=[]
    for split,vehicle in [('train',1),('validation',2),('test',3)]:
        x=rng.normal(size=(80,len(FEATURES)))
        x[:,0]=rng.uniform(0,100,size=80)
        x[:,7]=x[:,0]+rng.normal(size=80)
        x[::3,-2]=np.nan
        frame=pd.DataFrame(x,columns=FEATURES)
        frame[TARGET]=.7*x[:,0]+.3*x[:,7]
        frame['vehicle_id']=vehicle
        frame['split']=split
        frame['engine_type']='ICE'
        frames.append(frame)
    return frames


@pytest.fixture
def fitted():
    train,validation,_=fixture_frames()
    model,selection=select_model(train,validation,candidates=[{
        'max_iter':12,'max_leaf_nodes':7,'min_samples_leaf':5,'learning_rate':.1,'l2_regularization':1.}])
    return model,selection,validation


def test_feature_matrix_excludes_metadata_target_and_preserves_nan():
    train,_,_=fixture_frames()
    matrix=feature_matrix(train)
    assert list(matrix.columns)==list(FEATURES)
    assert 'vehicle_id' not in matrix and TARGET not in matrix
    assert matrix.isna().sum().sum()>0


def test_predictions_are_finite_with_missing_optional_sensors(fitted):
    model,_,frame=fitted
    output=predict_features(frame[list(FEATURES)],model)
    assert len(output)==len(frame) and np.isfinite(output).all()
    assert list(model.feature_names_in_)==list(FEATURES)
    assert model.early_stopping is False


def test_inference_rejects_id_target_and_missing_or_infinite_inputs(fitted):
    model,_,frame=fitted
    with pytest.raises(ValueError,match='approved'):
        predict_features(frame,model)
    with pytest.raises(ValueError,match='approved'):
        predict_features(frame[list(FEATURES)].drop(columns=FEATURES[0]),model)
    x=frame[list(FEATURES)].copy()
    x.iloc[0,0]=np.inf
    with pytest.raises(ValueError,match='Infinite'):
        predict_features(x,model)


def test_prediction_column_reordering_is_safe(fitted):
    model,_,frame=fitted
    first=predict_features(frame[list(FEATURES)],model)
    second=predict_features(frame[list(reversed(FEATURES))],model)
    np.testing.assert_array_equal(first,second)


def test_training_and_predictions_are_exactly_reproducible(fitted):
    model,selection,validation=fitted
    train,_,_=fixture_frames()
    repeated,_=select_model(train,validation,candidates=[selection['selected_parameters']])
    np.testing.assert_array_equal(predict_features(validation[list(FEATURES)],model),
                                  predict_features(validation[list(FEATURES)],repeated))


def test_selection_cannot_accept_test_data_or_shared_vehicles():
    train,val,test=fixture_frames()
    assert 'test' not in inspect.signature(select_model).parameters
    with pytest.raises(ValueError,match='leakage'):
        select_model(train,test)
    val['vehicle_id']=1
    with pytest.raises(ValueError,match='leakage'):
        select_model(train,val)


def test_future_metadata_mutation_does_not_change_model_inputs():
    train,_,_=fixture_frames()
    before=feature_matrix(train).copy()
    train[TARGET]+=1000
    train['vehicle_id']=999
    train['target_end_ms']=999999999
    pd.testing.assert_frame_equal(feature_matrix(train),before)


def test_model_serialization_roundtrip_and_integrity_guard(fitted,tmp_path):
    model,_,frame=fitted
    path=tmp_path/'model.joblib'
    joblib.dump(model,path)
    metadata={'model_sha256':sha256(path),'feature_order':list(FEATURES),
              'versions':{'scikit-learn':sklearn.__version__}}
    meta=tmp_path/'inference_metadata.json'
    meta.write_text(json.dumps(metadata))
    restored,_=load_model(path)
    np.testing.assert_array_equal(predict_features(frame[list(FEATURES)],model),
                                  predict_features(frame[list(FEATURES)],restored))
    metadata['model_sha256']='not-the-model-hash'
    meta.write_text(json.dumps(metadata))
    with pytest.raises(ValueError,match='integrity'):
        load_model(path)


def test_exact_metric_and_improvement_arithmetic():
    assert score([0,2],[1,1])=={'mae_kmh':1.,'rmse_kmh':1.}
    assert improvement({'mae_kmh':2,'rmse_kmh':4},{'mae_kmh':1,'rmse_kmh':3})=={
        'mae_improvement_pct':50.,'rmse_improvement_pct':25.}
    assert improvement({'mae_kmh':1,'rmse_kmh':1},{'mae_kmh':2,'rmse_kmh':2})['mae_improvement_pct']==-100


def test_paired_cluster_bootstrap_is_seeded_and_handles_unequal_vehicle_sizes():
    ids=np.array([1,1,1,2])
    actual=np.zeros(4)
    model=np.array([1,1,1,3.])
    base=model+2
    first=cluster_bootstrap(ids,actual,model,base,n_bootstrap=400,seed=7)
    assert first==cluster_bootstrap(ids,actual,model,base,n_bootstrap=400,seed=7)
    assert first['vehicles']==2
    assert first['intervals']['paired_mae_reduction_kmh']==pytest.approx([2.,2.])
    # Whole-vehicle resampling produces the extreme 1 or 3 mean errors.
    assert first['intervals']['model_mae_kmh']==pytest.approx([1.,3.])


def test_cluster_bootstrap_requires_multiple_vehicles():
    with pytest.raises(ValueError,match='clusters'):
        cluster_bootstrap([1,1],[0,0],[1,1],[2,2])


def test_cohort_metrics_reconcile_and_absent_ev_is_not_invented():
    frame=pd.DataFrame({'vehicle_id':[1,1,2,3],'engine_type':['ICE','ICE','HEV','PHEV']})
    target=np.array([0.,25.,45.,90.])
    rows=cohort_errors(frame,{'model':target+1},target)
    assert sum(row['windows'] for row in rows if row['dimension']=='powertrain')==4
    assert sum(row['windows'] for row in rows if row['dimension']=='actual_target_speed_range')==4
    assert not any(row['category']=='EV' for row in rows)
    assert all(row['mae_kmh']==1 for row in rows)
