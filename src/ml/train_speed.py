"""Audit frozen Day 5 examples, select on validation only, evaluate test once.

No refit on validation/test. All numerical training/prediction uses one CPU
thread, fixed seed, native missing-value handling, and exactly 31 causal inputs.
"""
import argparse
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import shutil
import time

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from threadpoolctl import threadpool_limits

from src.analytics.build_gold import ROOT,sha256,footprint
from src.features.speed_windows import FEATURES,TARGET
from src.features.build_speed_dataset import SCHEMA,validate_examples,save_json
from src.features.baselines import predictions
from src.ml.evaluation import SEED,score,improvement,vehicle_errors,cluster_bootstrap,cohort_errors

RESULTS=ROOT/'results/day6'
MODEL_DIR=ROOT/'models/day6'
MODEL_PATH=MODEL_DIR/'hist_gradient_boosting.joblib'
CANDIDATES=tuple({'learning_rate':lr,'max_iter':200,'max_leaf_nodes':leaves,
    'min_samples_leaf':minimum,'l2_regularization':regularization}
    for lr,leaves,minimum,regularization in (
        (.05,15,20,1.),(.05,31,20,1.),(.10,15,20,1.),(.10,31,20,1.),
        (.05,15,50,5.),(.05,31,50,5.)))
LOG=logging.getLogger('fleetpulse.ml')


def preserved_hashes():
    paths=[]
    for layer in ('bronze','silver','gold'):
        paths.extend((ROOT/f'data/{layer}/ved').rglob('*.parquet'))
    for directory in ('data/ml/speed','results/day5'):
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(paths)}


def feature_matrix(frame):
    if any(f not in frame.columns for f in FEATURES):
        raise ValueError('Missing required feature columns')
    matrix=frame.loc[:,list(FEATURES)].astype(float)
    if np.isinf(matrix.to_numpy()).any():
        raise ValueError('Infinite input; NaN missing values are allowed')
    return matrix


def audit_saved_dataset():
    manifest=json.loads((ROOT/'results/day5/dataset_manifest.json').read_text())
    splits=json.loads((ROOT/'results/day5/split_manifest.json').read_text())
    for path,digest in {**manifest['inputs'],**manifest['outputs']}.items():
        if sha256(ROOT/path)!=digest:
            raise RuntimeError(f'Day 5 manifest integrity mismatch: {path}')
    if splits['features']!=list(FEATURES) or splits['target_column']!=TARGET or manifest['selected_windows']!=11549:
        raise RuntimeError('Frozen feature/target/count contract changed')
    frames={}
    for name in ('train','validation','test'):
        table=pq.read_table(ROOT/f'data/ml/speed/{name}.parquet')
        if table.schema.remove_metadata()!=SCHEMA:
            raise RuntimeError('Saved ML schema mismatch')
        frames[name]=table.to_pandas()
        expected=splits['summary'][name]
        if len(table)!=expected['selected_windows'] or frames[name].vehicle_id.nunique()!=expected['usable_vehicles'] or not (frames[name].split==name).all():
            raise RuntimeError('Saved split count/label mismatch')
        feature_matrix(frames[name])
    combined=pd.concat(frames.values(),ignore_index=True)
    assignments={int(v):s for v,s in splits['vehicle_assignments'].items()}
    audit=validate_examples(combined,assignments)
    if len(combined)!=11549 or combined.vehicle_id.nunique()!=318:
        raise RuntimeError('Combined cohort mismatch')
    audit.update({'rows':len(combined),'vehicles':318,'manifest_hashes_verified':True,
                  'features':len(FEATURES),'test_ev_vehicles':int(frames['test'].loc[frames['test'].engine_type=='EV','vehicle_id'].nunique())})
    return frames,manifest,audit


def select_model(training,validation,candidates=CANDIDATES):
    """No test argument exists; training fit, validation MAE selection only."""
    if (set(training.vehicle_id)&set(validation.vehicle_id)
        or not (training.split=='train').all() or not (validation.split=='validation').all()):
        raise ValueError('Training/validation split leakage')
    x_train,x_validation=feature_matrix(training),feature_matrix(validation)
    y_train=training[TARGET].to_numpy(float)
    y_validation=validation[TARGET].to_numpy(float)
    if not np.isfinite(y_train).all() or not np.isfinite(y_validation).all():
        raise ValueError('Finite targets required')
    models=[]
    trials=[]
    with threadpool_limits(limits=1):
        for i,parameters in enumerate(candidates):
            started=time.perf_counter()
            model=HistGradientBoostingRegressor(loss='squared_error',early_stopping=False,
                random_state=SEED,categorical_features=None,**parameters)
            model.fit(x_train,y_train)
            predicted=model.predict(x_validation)
            trials.append({'candidate':i,'parameters':parameters,
                'fit_rows':len(training),'fit_vehicles':int(training.vehicle_id.nunique()),
                'validation':score(y_validation,predicted),'runtime_seconds':time.perf_counter()-started})
            models.append(model)
            LOG.info('Candidate %s validation MAE %.6f RMSE %.6f',i,trials[-1]['validation']['mae_kmh'],trials[-1]['validation']['rmse_kmh'])
    best=min(range(len(trials)),key=lambda i:(trials[i]['validation']['mae_kmh'],i))
    return models[best],{'criterion':'validation pooled MAE; candidate order breaks ties',
        'selected_candidate':best,'selected_parameters':dict(candidates[best]),'trials':trials,
        'fit_split':'train only','early_stopping':False,'refit_on_validation':False,
        'loss':'squared_error','random_state':SEED,'categorical_features':None}


def evaluate_methods(frame,model,training_mean):
    target=frame[TARGET].to_numpy(float)
    methods=predictions(frame,training_mean)
    with threadpool_limits(limits=1):
        methods['hist_gradient_boosting']=model.predict(feature_matrix(frame))
    return methods,{name:score(target,predicted) for name,predicted in methods.items()}


def run():
    started=time.perf_counter()
    if footprint()+200_000_000>=10_000_000_000 or shutil.disk_usage(ROOT).free<300_000_000:
        raise RuntimeError('Day 6 storage/free-space gate failed')
    RESULTS.mkdir(parents=True,exist_ok=True)
    before=preserved_hashes()
    frames,day5,audit=audit_saved_dataset()
    audit_seconds=time.perf_counter()-started
    training,validation=frames['train'],frames['validation']
    train_mean=day5['baseline_metrics']['training_historical_mean_kmh']
    if not np.isclose(train_mean,training[TARGET].mean(),rtol=0,atol=1e-12):
        raise RuntimeError('Historical baseline constant differs from training-only mean')
    selection_started=time.perf_counter()
    model,selection=select_model(training,validation)
    # Persist the frozen decision before computing any test predictions/errors.
    save_json(RESULTS/'selection.json',selection)
    selection_seconds=time.perf_counter()-selection_started
    validation_methods,validation_scores=evaluate_methods(validation,model,train_mean)
    baselines=tuple(predictions(validation,train_mean))
    strongest=min(baselines,key=lambda name:(validation_scores[name]['mae_kmh'],name))
    save_json(RESULTS/'evaluation_policy.json',{'baseline':strongest,'choice':'validation pooled MAE only',
        'speed_range_bins':[0,20,40,60,80,'infinity'],'bootstrap_replicates':2000,'seed':SEED})
    importance_started=time.perf_counter()
    with threadpool_limits(limits=1):
        permuted=permutation_importance(model,feature_matrix(validation),validation[TARGET],
            scoring='neg_mean_absolute_error',n_repeats=5,random_state=SEED,n_jobs=1)
    importance=pd.DataFrame({'feature':FEATURES,'validation_mae_increase_mean_kmh':permuted.importances_mean,
        'validation_mae_increase_stddev_kmh':permuted.importances_std}).sort_values(
            ['validation_mae_increase_mean_kmh','feature'],ascending=[False,True])
    save_json(RESULTS/'permutation_importance.json',importance.to_dict('records'))
    importance_seconds=time.perf_counter()-importance_started
    evaluation_started=time.perf_counter()
    # The selected model stays training-only. Test is evaluated after both choices are frozen.
    metrics={}
    confidence={}
    improvements={}
    vehicle_tables=[]
    cohorts=[]
    prediction_tables=[]
    for split in ('validation','test'):
        frame=frames[split]
        methods,scores=(validation_methods,validation_scores) if split=='validation' else evaluate_methods(frame,model,train_mean)
        for name in baselines:
            expected=day5['baseline_metrics']['metrics'][split][name]
            if any(abs(scores[name][key]-expected[key])>1e-10 for key in ('mae_kmh','rmse_kmh')):
                raise RuntimeError('Baseline/identical-example reconciliation failed')
        metrics[split]=scores
        improvements[split]=improvement(scores[strongest],scores['hist_gradient_boosting'])
        errors=vehicle_errors(frame,methods,frame[TARGET].to_numpy(float))
        errors['split']=split
        vehicle_tables.append(errors)
        for name in methods:
            own=errors[errors.method==name]
            metrics[split][name].update({'vehicle_macro_mae_kmh':float(own.mae_kmh.mean()),
                'vehicle_macro_rmse_kmh':float(own.rmse_kmh.mean())})
        confidence[split]=cluster_bootstrap(frame.vehicle_id.to_numpy(),frame[TARGET].to_numpy(float),
            methods['hist_gradient_boosting'],methods[strongest])
        cohort=cohort_errors(frame,methods,frame[TARGET].to_numpy(float))
        cohorts.extend({'split':split,**row} for row in cohort)
        predictions_frame=frame[['example_id','vehicle_id','trip_id','engine_type',TARGET]].copy()
        predictions_frame['split']=split
        for name,predicted in methods.items():
            predictions_frame[name]=predicted
        prediction_tables.append(predictions_frame)
    evaluation_seconds=time.perf_counter()-evaluation_started
    saved_predictions=pd.concat(prediction_tables,ignore_index=True)
    pq.write_table(pa.Table.from_pandas(saved_predictions,preserve_index=False),RESULTS/'predictions.parquet',compression='zstd')
    pq.write_table(pa.Table.from_pandas(pd.concat(vehicle_tables),preserve_index=False),RESULTS/'vehicle_errors.parquet',compression='zstd')
    save_json(RESULTS/'cohort_metrics.json',cohorts)
    MODEL_DIR.mkdir(parents=True,exist_ok=True)
    temporary=MODEL_PATH.with_suffix('.joblib.pending')
    joblib.dump(model,temporary,compress=3)
    os.replace(temporary,MODEL_PATH)
    versions={name:importlib.metadata.version(name) for name in (
        'scikit-learn','numpy','scipy','pandas','pyarrow','joblib','threadpoolctl','matplotlib')}
    metadata={'model_sha256':sha256(MODEL_PATH),'feature_order':list(FEATURES),'target':TARGET,
        'forecast_seconds':60,'history_seconds':60,'max_sampling_gap_ms':2000,
        'units':'km/h','missing_policy':'native NaN handling; no imputation/scaling',
        'selection':selection,'versions':versions,'fit_rows':len(training),
        'fit_vehicles':int(training.vehicle_id.nunique()),'training_input_sha256':sha256(ROOT/'data/ml/speed/train.parquet'),
        'trusted_local_artifact_only':True,'cpu_threads':1,'prediction_postprocessing':'none; no clipping'}
    save_json(MODEL_DIR/'inference_metadata.json',metadata)
    with threadpool_limits(limits=1):
        loaded=joblib.load(MODEL_PATH)
        if not np.array_equal(loaded.predict(feature_matrix(validation)),validation_methods['hist_gradient_boosting']):
            raise RuntimeError('Model save/load prediction roundtrip failed')
    if preserved_hashes()!=before:
        raise RuntimeError('Preserved data or Day 5 artifacts changed')
    result={'complete':True,'dataset_audit':audit,'input_sha256':before,'selection':selection,
        'strongest_baseline':strongest,'metrics':metrics,'improvement_vs_strongest_baseline':improvements,
        'vehicle_cluster_bootstrap':confidence,'versions':versions,'model_bytes':MODEL_PATH.stat().st_size,
        'model_sha256':metadata['model_sha256'],'model_roundtrip_predictions_identical':True,
        'immutable_inputs_unchanged':True,'audit_seconds':audit_seconds,'selection_seconds':selection_seconds,
        'permutation_importance_seconds':importance_seconds,'evaluation_seconds':evaluation_seconds,
        'runtime_seconds':time.perf_counter()-started,'project_bytes':footprint(),
        'prediction_range_kmh':{split:{'min':float(saved_predictions.loc[saved_predictions.split==split,'hist_gradient_boosting'].min()),
            'max':float(saved_predictions.loc[saved_predictions.split==split,'hist_gradient_boosting'].max()),
            'negative_count':int((saved_predictions.loc[saved_predictions.split==split,'hist_gradient_boosting']<0).sum())}
            for split in ('validation','test')}}
    save_json(RESULTS/'training_run.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2))
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    run()


if __name__=='__main__':
    main()
