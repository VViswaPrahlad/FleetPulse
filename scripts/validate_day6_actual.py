"""Reconcile saved predictions and train-only refit without test model selection."""
import json
import time

import numpy as np
import pyarrow.parquet as pq

from src.features.build_speed_dataset import save_json
from src.features.speed_windows import TARGET,FEATURES
from src.ml.train_speed import RESULTS,preserved_hashes,audit_saved_dataset,select_model
from src.ml.inference import load_model,predict_features
from src.ml.evaluation import score,cluster_bootstrap


def validate():
    started=time.perf_counter()
    run=json.loads((RESULTS/'training_run.json').read_text())
    frames,_,audit=audit_saved_dataset()
    model,_=load_model()
    records=pq.read_table(RESULTS/'predictions.parquet').to_pandas()
    for split in ('validation','test'):
        actual=frames[split]
        saved=records[records.split==split]
        if saved.example_id.tolist()!=actual.example_id.tolist():
            raise RuntimeError('Method example list reconciliation failed')
        if not np.array_equal(saved[TARGET],actual[TARGET]):
            raise RuntimeError('Saved labels differ from frozen dataset')
        output=predict_features(actual[list(FEATURES)],model)
        if not np.array_equal(output,saved.hist_gradient_boosting):
            raise RuntimeError('Saved model prediction reconciliation failed')
        for method in run['metrics'][split]:
            metrics=score(saved[TARGET],saved[method])
            if any(abs(metrics[key]-run['metrics'][split][method][key])>1e-12 for key in metrics):
                raise RuntimeError('Metric arithmetic reconciliation failed')
    # Refit just the already frozen training-only specification; validation
    # predictions must be identical. No alternate model/test criterion is tried.
    repeated,_=select_model(frames['train'],frames['validation'],
                           candidates=[run['selection']['selected_parameters']])
    original=predict_features(frames['validation'][list(FEATURES)],model)
    duplicate=predict_features(frames['validation'][list(FEATURES)],repeated)
    if not np.array_equal(original,duplicate):
        raise RuntimeError('Full training reproducibility failed')
    saved=records[records.split=='test']
    bootstrap=cluster_bootstrap(saved.vehicle_id,saved[TARGET],saved.hist_gradient_boosting,
                               saved[run['strongest_baseline']])
    if bootstrap!=run['vehicle_cluster_bootstrap']['test']:
        raise RuntimeError('Seeded bootstrap reproducibility failed')
    if preserved_hashes()!=run['input_sha256']:
        raise RuntimeError('Preserved earlier outputs changed')
    result={'passed':True,'audited_examples':audit['rows'],'validation_test_predictions_checked':len(records),
        'full_training_refit_validation_predictions_identical':True,
        'bootstrap_repeat_identical':True,'immutable_inputs_unchanged':True,
        'runtime_seconds':time.perf_counter()-started}
    save_json(RESULTS/'independent_validation.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    validate()
