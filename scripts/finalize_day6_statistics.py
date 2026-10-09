"""Finalize paired macro uncertainty from frozen predictions, without fitting."""
import json
import time

import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,sha256
from src.features.speed_windows import TARGET
from src.features.build_speed_dataset import save_json
from src.ml.evaluation import cluster_bootstrap
from src.ml.train_speed import RESULTS,MODEL_DIR


def main():
    started=time.perf_counter()
    run=json.loads((RESULTS/'training_run.json').read_text())
    predictions=pq.read_table(RESULTS/'predictions.parquet').to_pandas()
    errors=pq.read_table(RESULTS/'vehicle_errors.parquet').to_pandas()
    baseline=run['strongest_baseline']
    comparisons={}
    for split in ('validation','test'):
        frame=predictions[predictions.split==split]
        run['vehicle_cluster_bootstrap'][split]=cluster_bootstrap(frame.vehicle_id,frame[TARGET],
            frame.hist_gradient_boosting,frame[baseline])
        per=errors[errors.split==split].pivot(index='vehicle_id',columns='method',values='mae_kmh')
        delta=per[baseline]-per.hist_gradient_boosting
        comparisons[split]={'vehicles':len(per),'model_lower_mae_vehicles':int((delta>0).sum()),
            'model_higher_mae_vehicles':int((delta<0).sum()),'equal_mae_vehicles':int((delta==0).sum()),
            'worst_model_vehicle_mae_kmh':float(per.hist_gradient_boosting.max()),
            'best_model_vehicle_mae_kmh':float(per.hist_gradient_boosting.min())}
    run['vehicle_comparison']=comparisons
    run['additional_macro_statistics_seconds']=time.perf_counter()-started
    save_json(RESULTS/'training_run.json',run)
    metadata_path=MODEL_DIR/'inference_metadata.json'
    metadata=json.loads(metadata_path.read_text())
    metadata['source_sha256']={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'src/ml').glob('*.py'))}
    save_json(metadata_path,metadata)
    print(json.dumps({'vehicle_comparison':comparisons,
        'test_macro_mae_reduction_ci':run['vehicle_cluster_bootstrap']['test']['intervals']['paired_vehicle_macro_mae_reduction_kmh']},indent=2))


if __name__=='__main__':
    main()
