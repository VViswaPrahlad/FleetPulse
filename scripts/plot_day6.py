"""Static lightweight diagnostic figures from frozen validation/test predictions."""
import os
import time
from pathlib import Path

from src.analytics.build_gold import ROOT

os.environ['MPLCONFIGDIR']=str(ROOT/'data/tmp/matplotlib-day6')
Path(os.environ['MPLCONFIGDIR']).mkdir(parents=True,exist_ok=True)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.features.build_speed_dataset import save_json
from src.features.speed_windows import TARGET
from src.ml.train_speed import RESULTS

FIGURES=ROOT/'docs/figures/day6'
MODEL='hist_gradient_boosting'
BASELINE='last_observed_speed'


def render():
    started=time.perf_counter()
    FIGURES.mkdir(parents=True,exist_ok=True)
    frame=pq.read_table(RESULTS/'predictions.parquet').to_pandas()
    test=frame[frame.split=='test']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
        'figure.facecolor':'white','axes.grid':True,'grid.alpha':.2})
    fig,axes=plt.subplots(1,2,figsize=(11,4.7),layout='constrained',sharex=True,sharey=True)
    upper=float(np.ceil(max(test[TARGET].max(),test[MODEL].max(),test[BASELINE].max())/10)*10)
    for ax,column,title,color in zip(axes,(BASELINE,MODEL),('Last-observed speed','HistGradientBoosting'),('#9a5c23','#286a98')):
        ax.scatter(test[TARGET],test[column],s=10,alpha=.3,linewidths=0,color=color,rasterized=True)
        ax.plot([0,upper],[0,upper],color='#333333',lw=1.2,ls='--',label='Perfect prediction')
        ax.set(title=title,xlabel='Actual next-minute mean speed (km/h)',ylabel='Predicted speed (km/h)')
        ax.set_xlim(0,upper)
        ax.legend(loc='upper left',frameon=False)
    fig.suptitle('Vehicle-held-out test predictions · 1,919 windows / 50 vehicles',fontsize=13)
    fig.savefig(FIGURES/'predicted_vs_actual.png',dpi=150)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    residuals={name:test[name]-test[TARGET] for name in (BASELINE,MODEL)}
    edges=np.linspace(min(r.min() for r in residuals.values()),max(r.max() for r in residuals.values()),45)
    for name,label,color in ((BASELINE,'Last-observed speed','#9a5c23'),(MODEL,'HistGradientBoosting','#286a98')):
        axes[0].hist(residuals[name],bins=edges,alpha=.55,label=label,color=color,density=True)
    axes[0].axvline(0,color='#333333',ls='--',lw=1)
    axes[0].set(xlabel='Prediction minus actual (km/h)',ylabel='Density',title='Signed errors')
    axes[0].legend(frameon=False)
    vehicles=pq.read_table(RESULTS/'vehicle_errors.parquet').to_pandas()
    vehicles=vehicles[vehicles.split=='test']
    axes[1].boxplot([vehicles.loc[vehicles.method==name,'mae_kmh'].to_numpy() for name in (BASELINE,MODEL)],
                    tick_labels=['Last speed','HistGradientBoosting'],showmeans=True)
    axes[1].set(ylabel='Per-vehicle MAE (km/h)',title='50 equally weighted vehicles')
    fig.suptitle('Frozen test error diagnostics',fontsize=13)
    fig.savefig(FIGURES/'error_distribution.png',dpi=150)
    plt.close(fig)
    importance=pd.read_json(RESULTS/'permutation_importance.json').head(12).iloc[::-1]
    fig,ax=plt.subplots(figsize=(10,6),layout='constrained')
    ax.barh(importance.feature,importance.validation_mae_increase_mean_kmh,
            xerr=importance.validation_mae_increase_stddev_kmh,color='#286a98',alpha=.85,capsize=2)
    ax.axvline(0,color='#333333',lw=1)
    ax.set(xlabel='Validation MAE increase after permutation (km/h)',
        title='Validation-only permutation importance · top 12')
    fig.savefig(FIGURES/'validation_feature_importance.png',dpi=150)
    plt.close(fig)
    result={'runtime_seconds':time.perf_counter()-started,
        'figure_bytes':{p.name:p.stat().st_size for p in sorted(FIGURES.glob('*.png'))},
        'test_used_for_diagnostics_only':True,'feature_importance_split':'validation'}
    save_json(RESULTS/'figures.json',result)
    print(result)


if __name__=='__main__':
    render()
