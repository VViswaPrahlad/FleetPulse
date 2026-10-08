"""Fixed analytical baselines; learn one constant from training vehicles only."""
import numpy as np

from src.features.speed_windows import TARGET

BASELINES=('last_observed_speed','past_mean_persistence','training_historical_mean')


def fit_historical_mean(frame):
    training=frame.loc[frame.split=='train',TARGET].to_numpy(dtype=float)
    if not len(training) or not np.all(np.isfinite(training)):
        raise ValueError('Finite training targets required')
    return float(training.mean())


def predictions(frame,training_mean):
    return {'last_observed_speed':frame.past_speed_last_kmh.to_numpy(dtype=float),
        'past_mean_persistence':frame.past_speed_time_mean_kmh.to_numpy(dtype=float),
        'training_historical_mean':np.full(len(frame),training_mean)}


def evaluate(frame):
    mean=fit_historical_mean(frame)
    scores={}
    details=[]
    for split in ('train','validation','test'):
        subset=frame[frame.split==split]
        if subset.empty:
            raise ValueError(f'No eligible examples in {split}')
        target=subset[TARGET].to_numpy(dtype=float)
        vehicles=subset.vehicle_id.to_numpy()
        result={}
        for name,predicted in predictions(subset,mean).items():
            error=predicted-target
            absolute=np.abs(error)
            squared=error**2
            per_vehicle=[]
            for vehicle in sorted(set(vehicles)):
                selected=vehicles==vehicle
                metrics={'split':split,'baseline':name,'vehicle_id':int(vehicle),
                    'windows':int(selected.sum()),'mae_kmh':float(absolute[selected].mean()),
                    'rmse_kmh':float(np.sqrt(squared[selected].mean()))}
                per_vehicle.append(metrics)
                details.append(metrics)
            result[name]={'windows':len(subset),'vehicles':len(per_vehicle),
                'mae_kmh':float(absolute.mean()),'rmse_kmh':float(np.sqrt(squared.mean())),
                'vehicle_macro_mae_kmh':float(np.mean([x['mae_kmh'] for x in per_vehicle])),
                'vehicle_macro_rmse_kmh':float(np.mean([x['rmse_kmh'] for x in per_vehicle]))}
        scores[split]=result
    return {'training_historical_mean_kmh':mean,'metrics':scores,
            'per_vehicle_metrics':details,'policy':'fixed before evaluation; no validation/test tuning'}
