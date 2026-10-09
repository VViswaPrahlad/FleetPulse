import json
import re
from threading import RLock
import pyarrow.parquet as pq

from src.api.errors import unavailable
from src.api.schemas.analytics import ModelMetrics,VehicleError

METHODS=('hist_gradient_boosting','last_observed_speed','past_mean_persistence','training_historical_mean')
ERROR_FIELDS=('mae_kmh','rmse_kmh','vehicle_macro_mae_kmh','vehicle_macro_rmse_kmh')
CI_FIELDS=('model_mae_kmh','model_rmse_kmh','baseline_mae_kmh','baseline_rmse_kmh',
    'paired_mae_reduction_kmh','paired_rmse_reduction_kmh','mae_improvement_pct','rmse_improvement_pct',
    'model_vehicle_macro_mae_kmh','model_vehicle_macro_rmse_kmh','baseline_vehicle_macro_mae_kmh',
    'baseline_vehicle_macro_rmse_kmh','paired_vehicle_macro_mae_reduction_kmh','paired_vehicle_macro_rmse_reduction_kmh')


class EvaluationService:
    def __init__(self,settings):
        self.settings=settings
        self._signature=None
        self._cached=None
        self._lock=RLock()

    def metrics(self):
        try:
            path=self.settings.evaluation/'training_run.json'
            stat=path.stat()
            if stat.st_size>2_000_000:
                raise ValueError('Evaluation JSON too large')
            signature=(stat.st_mtime_ns,stat.st_size)
            with self._lock:
                if signature==self._signature:
                    return self._cached
                run=json.loads(path.read_text(encoding='utf-8'))
                if not re.fullmatch('[0-9a-f]{64}',run['model_sha256']):
                    raise ValueError('Invalid model identity')
                selected=run['selection']
                numeric=('learning_rate','max_iter','max_leaf_nodes','min_samples_leaf','l2_regularization')
                parameters={name:float(selected['selected_parameters'][name]) for name in numeric}
                metrics={split:{method:{field:float(run['metrics'][split][method][field]) for field in ERROR_FIELDS}
                                for method in METHODS} for split in ('validation','test')}
                confidence={split:{'seed':int(run['vehicle_cluster_bootstrap'][split]['seed']),
                    'replicates':int(run['vehicle_cluster_bootstrap'][split]['replicates']),
                    'vehicles':int(run['vehicle_cluster_bootstrap'][split]['vehicles']),
                    'confidence':float(run['vehicle_cluster_bootstrap'][split]['confidence']),
                    'intervals':{name:[float(x) for x in run['vehicle_cluster_bootstrap'][split]['intervals'][name]] for name in CI_FIELDS}}
                    for split in ('validation','test')}
                result=ModelMetrics(model_id='hgb-day6-'+run['model_sha256'][:12],
                    target='next-60-second time-weighted mean speed',selection={
                        'candidate':int(selected['selected_candidate']),'parameters':parameters,
                        'criterion':'validation pooled MAE','fit_split':'train only',
                        'early_stopping':False,'random_state':int(selected['random_state'])},
                    metrics=metrics,strongest_baseline=run['strongest_baseline'],
                    improvements={split:{field:float(run['improvement_vs_strongest_baseline'][split][field])
                                  for field in ('mae_improvement_pct','rmse_improvement_pct')}
                                  for split in ('validation','test')},vehicle_cluster_bootstrap=confidence,
                    limitations=['No EV is represented in test.','16 of 50 test vehicles have higher model MAE.',
                        'Low/high-speed cohorts worsen; vehicle-macro MAE reduction interval crosses zero.'])
                self._cached,self._signature=result,signature
                return result
        except Exception:
            raise unavailable('evaluation') from None

    def ready(self):
        try:
            self.metrics()
            schema=pq.read_schema(self.settings.evaluation/'vehicle_errors.parquet')
            return set(VehicleError.model_fields)<=set(schema.names)
        except Exception:
            return False
