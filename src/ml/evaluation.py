"""Paired vehicle-cluster uncertainty, not row-wise bootstrap."""
import numpy as np
import pandas as pd

SEED=20261009
BOOTSTRAPS=2000


def score(actual,predicted):
    actual,predicted=np.asarray(actual,float),np.asarray(predicted,float)
    if not len(actual) or len(actual)!=len(predicted) or not np.all(np.isfinite(actual)&np.isfinite(predicted)):
        raise ValueError('Finite paired observations required')
    error=predicted-actual
    return {'mae_kmh':float(np.abs(error).mean()),'rmse_kmh':float(np.sqrt(np.mean(error**2)))}


def improvement(baseline,model):
    return {name.replace('_kmh','_improvement_pct'):float(100*(baseline[name]-model[name])/baseline[name])
            if baseline[name]>0 else None for name in ('mae_kmh','rmse_kmh')}


def vehicle_errors(frame,predictions,target):
    rows=[]
    ids=frame.vehicle_id.to_numpy()
    for name,predicted in predictions.items():
        for vehicle in sorted(set(ids)):
            selected=ids==vehicle
            rows.append({'method':name,'vehicle_id':int(vehicle),'windows':int(selected.sum()),
                         **score(target[selected],predicted[selected])})
    return pd.DataFrame(rows)


def cluster_bootstrap(ids,actual,model,baseline,n_bootstrap=BOOTSTRAPS,seed=SEED):
    """Resample whole vehicles; paired methods use identical draws.

    Pooled CI maintains each drawn vehicle's entire window count. Macro CI
    averages per-vehicle error measures. Conditional on the fitted model/split.
    """
    ids=np.asarray(ids)
    actual,model,baseline=[np.asarray(x,float) for x in (actual,model,baseline)]
    if len(set(ids))<2 or n_bootstrap<1:
        raise ValueError('At least two vehicle clusters and one bootstrap required')
    score(actual,model)
    score(actual,baseline)
    if len(ids)!=len(actual):
        raise ValueError('Vehicle length mismatch')
    clusters=[]
    for vehicle in sorted(set(ids)):
        present=ids==vehicle
        me=model[present]-actual[present]
        be=baseline[present]-actual[present]
        clusters.append([present.sum(),np.abs(me).sum(),(me**2).sum(),np.abs(be).sum(),(be**2).sum()])
    clusters=np.asarray(clusters,float)
    draws=np.random.default_rng(seed).integers(0,len(clusters),size=(n_bootstrap,len(clusters)))
    totals=clusters[draws].sum(axis=1)
    model_mae=totals[:,1]/totals[:,0]
    model_rmse=np.sqrt(totals[:,2]/totals[:,0])
    base_mae=totals[:,3]/totals[:,0]
    base_rmse=np.sqrt(totals[:,4]/totals[:,0])
    samples={'model_mae_kmh':model_mae,'model_rmse_kmh':model_rmse,
        'baseline_mae_kmh':base_mae,'baseline_rmse_kmh':base_rmse,
        'paired_mae_reduction_kmh':base_mae-model_mae,
        'paired_rmse_reduction_kmh':base_rmse-model_rmse,
        'model_vehicle_macro_mae_kmh':(clusters[:,1]/clusters[:,0])[draws].mean(axis=1),
        'model_vehicle_macro_rmse_kmh':np.sqrt(clusters[:,2]/clusters[:,0])[draws].mean(axis=1),
        'baseline_vehicle_macro_mae_kmh':(clusters[:,3]/clusters[:,0])[draws].mean(axis=1),
        'baseline_vehicle_macro_rmse_kmh':np.sqrt(clusters[:,4]/clusters[:,0])[draws].mean(axis=1),
        'paired_vehicle_macro_mae_reduction_kmh':((clusters[:,3]-clusters[:,1])/clusters[:,0])[draws].mean(axis=1),
        'paired_vehicle_macro_rmse_reduction_kmh':(np.sqrt(clusters[:,4]/clusters[:,0])-np.sqrt(clusters[:,2]/clusters[:,0]))[draws].mean(axis=1)}
    # Relative CI is undefined if the comparison baseline has zero error in a draw.
    if np.all(base_mae>0):
        samples['mae_improvement_pct']=100*(base_mae-model_mae)/base_mae
    if np.all(base_rmse>0):
        samples['rmse_improvement_pct']=100*(base_rmse-model_rmse)/base_rmse
    return {'seed':seed,'replicates':n_bootstrap,'vehicles':len(clusters),
        'confidence':0.95,'method':'paired vehicle-cluster percentile; entire vehicle retained',
        'intervals':{name:np.quantile(values,[.025,.975]).tolist() for name,values in samples.items()}}


def cohort_errors(frame,predictions,target):
    labels=['[0,20)','[20,40)','[40,60)','[60,80)','[80,infinity)']
    ranges=pd.cut(target,bins=[0,20,40,60,80,np.inf],labels=labels,right=False)
    rows=[]
    for dimension,groups in [('actual_target_speed_range',ranges),('powertrain',frame.engine_type.to_numpy())]:
        groups=np.asarray(groups)
        for category in sorted(set(groups)):
            selected=groups==category
            for name,predicted in predictions.items():
                rows.append({'dimension':dimension,'category':str(category),'method':name,
                    'windows':int(selected.sum()),'vehicles':int(frame.vehicle_id[selected].nunique()),
                    **score(target[selected],predicted[selected])})
    return rows
