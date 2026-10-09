"""Measured report including negative cohorts and conditional cluster uncertainty."""
import json
import xml.etree.ElementTree as ET

import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,footprint,sha256
from src.features.build_speed_dataset import save_json
from src.ml.train_speed import RESULTS,MODEL_PATH,preserved_hashes


def render():
    run=json.loads((RESULTS/'training_run.json').read_text())
    audited=json.loads((RESULTS/'independent_validation.json').read_text())
    figures=json.loads((RESULTS/'figures.json').read_text())
    importance=json.loads((RESULTS/'permutation_importance.json').read_text())
    cohorts=json.loads((RESULTS/'cohort_metrics.json').read_text())
    suite=ET.parse(RESULTS/'day6_pytest.xml').getroot().find('testsuite')
    if int(suite.attrib['failures']) or int(suite.attrib['errors']) or not audited['passed']:
        raise RuntimeError('Completion report requires passing validation')
    if preserved_hashes()!=run['input_sha256'] or sha256(MODEL_PATH)!=run['model_sha256']:
        raise RuntimeError('Preserved data/model integrity changed')
    baseline=run['strongest_baseline']
    trials='\n'.join(f"| {t['candidate']} | {t['parameters']['learning_rate']} | {t['parameters']['max_leaf_nodes']} | {t['parameters']['min_samples_leaf']} | {t['parameters']['l2_regularization']} | {t['validation']['mae_kmh']:.6f} | {t['validation']['rmse_kmh']:.6f} |"
                     for t in run['selection']['trials'])
    metrics='\n'.join(f"| {split} | `{name}` | {m['mae_kmh']:.6f} | {m['rmse_kmh']:.6f} | {m['vehicle_macro_mae_kmh']:.6f} | {m['vehicle_macro_rmse_kmh']:.6f} |"
                     for split,methods in run['metrics'].items() for name,m in methods.items())
    improvements='\n'.join(f"| {split} | {r['mae_improvement_pct']:.6f}% | {r['rmse_improvement_pct']:.6f}% |"
                          for split,r in run['improvement_vs_strongest_baseline'].items())
    ci_names=('model_mae_kmh','model_rmse_kmh','baseline_mae_kmh','baseline_rmse_kmh',
        'paired_mae_reduction_kmh','paired_rmse_reduction_kmh','mae_improvement_pct','rmse_improvement_pct',
        'model_vehicle_macro_mae_kmh','model_vehicle_macro_rmse_kmh',
        'baseline_vehicle_macro_mae_kmh','baseline_vehicle_macro_rmse_kmh',
        'paired_vehicle_macro_mae_reduction_kmh','paired_vehicle_macro_rmse_reduction_kmh')
    ci='\n'.join(f"| `{name}` | {run['vehicle_cluster_bootstrap']['validation']['intervals'][name][0]:.6f}, {run['vehicle_cluster_bootstrap']['validation']['intervals'][name][1]:.6f} | {run['vehicle_cluster_bootstrap']['test']['intervals'][name][0]:.6f}, {run['vehicle_cluster_bootstrap']['test']['intervals'][name][1]:.6f} |"
                 for name in ci_names)
    by_vehicle='\n'.join(f"| {split} | {c['vehicles']} | {c['model_lower_mae_vehicles']} | {c['model_higher_mae_vehicles']} | {c['best_model_vehicle_mae_kmh']:.6f} | {c['worst_model_vehicle_mae_kmh']:.6f} |"
                         for split,c in run['vehicle_comparison'].items())
    importance_table='\n'.join(f"| `{row['feature']}` | {row['validation_mae_increase_mean_kmh']:.6f} | {row['validation_mae_increase_stddev_kmh']:.6f} |" for row in importance[:12])
    cohort_rows={}
    negative=[]
    for dimension in ('actual_target_speed_range','powertrain'):
        lines=[]
        for row in cohorts:
            if row['dimension']!=dimension or row['method']!='hist_gradient_boosting':
                continue
            comparison=next(c for c in cohorts if c['split']==row['split'] and c['dimension']==dimension
                            and c['category']==row['category'] and c['method']==baseline)
            percent=100*(comparison['mae_kmh']-row['mae_kmh'])/comparison['mae_kmh']
            lines.append(f"| {row['split']} | {row['category']} | {row['windows']} | {row['vehicles']} | {row['mae_kmh']:.6f} / {row['rmse_kmh']:.6f} | {comparison['mae_kmh']:.6f} / {comparison['rmse_kmh']:.6f} | {percent:.3f}% |")
            if row['split']=='test' and percent<0:
                negative.append(f"{row['category']} ({percent:.2f}% MAE improvement, meaning degradation)")
        cohort_rows[dimension]='\n'.join(lines)
    versions='\n'.join(f'| {name} | {version} |' for name,version in run['versions'].items())
    measured=footprint()
    params=run['selection']['selected_parameters']
    text=f'''# FleetPulse Day 6 — CPU training and vehicle-held-out evaluation

Date: **2026-10-09**, Asia/Calcutta. **Day 6 completed and validated locally.**
The selected model improves pooled errors but not every vehicle/speed cohort.
Publication follows tests and the tracked-file audit; final commit/push status
is reported in chat and ignored local `results/day6/publication.json`.
No dashboard, cloud service, GPU training or Day 7 work occurred.

## Frozen inputs and leakage audit

Reuse exactly **11,549 examples and 31 features** from Day 5:

| Split | Examples | Independent vehicle clusters |
|---|---:|---:|
| Train | 7,509 | 223 |
| Validation | 2,121 | 45 |
| Test | 1,919 | 50 |

The saved schema, feature allowlist, target, per-split counts/labels, source
provenance hashes and vehicle assignment manifest are verified before fitting.
Combined rows/vehicles are 11,549/318. No vehicle occurs in multiple splits,
no retained trip contexts overlap or share source observations, and no duplicate
prediction anchors are present. The original exact 60-second endpoints and
<=2-second gaps remain unchanged; no Day 5 window is regenerated or excluded.

Predictor X contains exactly the ordered 31 **past-only** feature names, never
vehicle/trip IDs, engine type, split label, future values/coverage, absolute
timestamps, provenance or target. Feature matrix NaNs remain NaN. The regressor
learns its native missing-value routing on training data; no imputation, scaling
or feature-selection estimator is fitted on validation/test. Optional sensor
absence may still proxy powertrain/measurement availability; held-out IDs do not
eliminate that cohort limitation.

Bronze/Silver/Gold and every existing file in `data/ml/speed/` and
`results/day5/` are SHA-256 checked before/after, **unchanged**. Training/validation
audit can read test schema/labels for integrity; test values never enter model
fitting, model selection or permutation importance. Day 5 previously published
baseline test scores; Day 6 does not claim those labels have never been viewed.
Its model/hyperparameter choices use only training and validation data.

## Limited selection and final model

Estimator: scikit-learn **HistGradientBoostingRegressor**, CPU with threadpool
limit **1**, seed **20261009**, squared-error loss and native NaN handling.
Six configurations are fixed in source before any test model score. Select
lowest **pooled validation MAE**, breaking ties by candidate order. There is no
additional search prompted by test results. All candidates fit train only;
internal random-row early stopping is disabled. The final model is the already
fitted winning candidate, not a train+validation refit.

All candidates use 200 iterations. The inspected specifications/results are:

| Candidate | Learning rate | Max leaves | Min leaf samples | L2 | Validation MAE | Validation RMSE |
|---|---:|---:|---:|---:|---:|---:|
{trials}

Winner: **candidate {run['selection']['selected_candidate']}**, learning_rate={params['learning_rate']},
max_iter={params['max_iter']}, max_leaf_nodes={params['max_leaf_nodes']},
min_samples_leaf={params['min_samples_leaf']}, l2_regularization={params['l2_regularization']},
early_stopping=False, random_state=20261009, categorical_features=None.
No maximum depth constraint is added; remaining estimator defaults use the pinned
1.7.2 release (including max_bins=255). Continuous speed and sensor summaries
are numeric; IDs/powertrain are not predictive categorical columns.

The frozen selection is saved before any test prediction/errors, and the
comparison baseline is also chosen by validation pooled MAE. No target clipping,
prediction clipping, calibration, retraining or feature deletion follows test
inspection. Raw test model predictions range from
**{run['prediction_range_kmh']['test']['min']:.6f} to {run['prediction_range_kmh']['test']['max']:.6f} km/h**;
negative predictions: **{run['prediction_range_kmh']['test']['negative_count']}**.

## Identical-example baseline comparison

The three existing rules are unchanged: last observed speed at t, past-minute
time-weighted speed, and a global training-label historical mean. Their scores
reconcile to Day 5 within 1e-10 km/h. The historical constant is not fitted on
validation/test. The strongest comparison baseline is **`{baseline}`**, selected
by validation pooled MAE before test evaluation. It is also best by pooled
test MAE among the three, but that fact does not determine the comparison.

Errors are km/h. Pooled metrics weight examples; macro metrics weight vehicles
equally. Macro RMSE is mean per-vehicle RMSE, not root mean of vehicle MSE.

| Split | Method | Pooled MAE | Pooled RMSE | Vehicle macro MAE | Vehicle macro RMSE |
|---|---|---:|---:|---:|---:|
{metrics}

Improvement = 100 * (baseline error - model error) / baseline error.
Negative values mean worse performance, not an absolute reduction.

| Split | Pooled MAE improvement | Pooled RMSE improvement |
|---|---:|---:|
{improvements}

## Vehicle errors and fixed-seed confidence intervals

Use **2,000 paired whole-vehicle bootstrap replicates**, seed **20261009**,
95% percentile intervals. Validation draws 45 vehicles with replacement and
test draws 50; a drawn vehicle contributes all its windows, including repeated
draws. Model and baseline use identical draws. Pooled metrics retain each
vehicle's observed window count; macro metrics give each drawn vehicle equal
weight. Window-wise bootstrap would understate correlation and is not used.

Intervals are conditional on the chosen model, split and observed cohort.
They do not include uncertainty from retraining, hyperparameter selection,
multiple subgroup comparisons, different routes/drivers or fleet composition.
Vehicle is the cluster unit, not a claim of independent identified drivers.
Validation uncertainty is optimistic after selecting on validation scores;
test uncertainty is evaluated only after freezing the model.

| Quantity (km/h unless percentage) | Validation 95% interval | Test 95% interval |
|---|---:|---:|
{ci}

Pooled test MAE reduction and its interval are positive. However, the **paired
vehicle-macro MAE reduction interval crosses zero**, so an equal-weighted
average-vehicle advantage is not resolved at this confidence level.
Improvement is not universal:

| Split | Vehicles | Model lower MAE | Model higher MAE | Best model vehicle MAE | Worst model vehicle MAE |
|---|---:|---:|---:|---:|---:|
{by_vehicle}

Per-vehicle errors for model and all three baselines are saved locally in
`results/day6/vehicle_errors.parquet`; no individual traces/GPS are published.

## Speed-range and powertrain diagnostics

Bins use **actual future mean speed**, strictly for post-selection diagnostics,
never as a feature or selection criterion. Intervals are [0,20), [20,40),
[40,60), [60,80), [80,infinity) km/h. Vehicle counts can repeat between bins.
All methods retain exactly the same examples in each group. Subgroup metrics
are descriptive, not independently optimized models or multiplicity-adjusted claims.

| Split | Actual target range | Examples | Vehicles | Model MAE / RMSE | Last-speed MAE / RMSE | MAE improvement |
|---|---|---:|---:|---:|---:|---:|
{cohort_rows['actual_target_speed_range']}

**Negative test results:** {('; '.join(negative)) if negative else 'none among reported cohorts'}.
Regression toward central speeds hurts low and high-speed predictions. This
model is not modified after seeing those test failures. Prediction scatter
and vehicle outliers below show the tradeoff rather than only pooled averages.

| Split | Powertrain | Examples | Vehicles | Model MAE / RMSE | Last-speed MAE / RMSE | MAE improvement |
|---|---|---:|---:|---:|---:|---:|
{cohort_rows['powertrain']}

**EVs are absent from test.** Validation includes one EV vehicle, too small
for reliable EV generalization claims. ICE/HEV/PHEV test groups contain 34/10/6
vehicles; their uncertainty differs and none implies broader fleet coverage.
Powertrain is static author-workbook metadata used only for grouping diagnostics.

## Validation-only feature importance

Permutation importance uses the frozen model on validation only, five shuffles
per feature, seed 20261009, negative MAE scoring, one job. Values are increases
in validation MAE after permutation; standard deviation is across five shuffles,
not a 95% confidence interval. No test observation or error enters this step.
All 31 features remain in the final estimator. Correlated speed statistics can
share attribution; marginal permutation is not a causal effect and can produce
unrealistic sensor combinations. Small or negative values are not silently pruned.

| Feature (top 12) | Mean MAE increase km/h | Shuffle stddev km/h |
|---|---:|---:|
{importance_table}

Last measured speed dominates, supporting the need to benchmark persistence.
Other speed/acceleration and engine measurements add less marginal information.

## Lightweight figures

All PNGs were visually inspected for readable labels and complete axes.
Combined size: **{sum(figures['figure_bytes'].values()):,} bytes**; largest:
**{max(figures['figure_bytes'].values()):,} bytes**. They show only anonymized
speed/prediction/error summaries, no vehicle IDs, GPS, raw rows or sensor traces.

![Actual versus predicted speed](figures/day6/predicted_vs_actual.png)

![Signed errors and per-vehicle MAE](figures/day6/error_distribution.png)

![Validation-only feature importance](figures/day6/validation_feature_importance.png)

## Tests, reproducibility and local inference

**{suite.attrib['tests']} tests passed; {suite.attrib['failures']} failed; {suite.attrib['errors']} errors**.
This is 12 new Day 6 fixtures plus 47 relevant earlier feature, continuity and
Gold regressions. JUnit suite runtime: **{float(suite.attrib['time']):.3f} seconds**.
Tests cover NaN prediction, predictor/metadata separation, strict inference
schema, reordered-column safety, seeded training, test/shared-vehicle rejection,
future metadata mutation, serialization/integrity, exact metrics, negative
improvements, whole-cluster paired resampling and absent-EV cohort reconciliation.

The actual 11,549-example dataset audit passes. All **4,040** validation/test
saved predictions match the loaded model exactly on the same IDs and labels;
all metric arithmetic reconciles. A fresh fit of only the frozen selected
specification on training data produces bit-identical validation predictions.
This is a reproducibility check, not another search or test-driven model choice.
The seeded full test bootstrap repeats exactly. Native NaNs are not filled.

The saved model occupies **{run['model_bytes']:,} bytes** under
`models/day6/hist_gradient_boosting.joblib`. Adjacent `inference_metadata.json`
records feature order, horizon/history/gap/units, source/fit-input/model hashes,
versions, seed, one CPU thread and selection policy. `load_model()` checks
model hash, feature contract and scikit-learn version; `predict_features()`
requires exactly the 31 predictive columns, retains NaNs, rejects infinities,
and safely reorders columns. Joblib loading is for trusted local artifacts;
hash checking detects corruption, not maliciously substituted model+metadata.

The test suite reports **73 Joblib/NumPy deprecation warnings** about array.shape
assignment in NumPy 2.5. These are not suppressed; all saved-model roundtrip
and prediction checks pass under the pinned environment. A future upgrade
should rerun compatibility tests. No existing NumPy dependency was upgraded.

| Package | Installed version |
|---|---|
{versions}

New CPU/plotting dependencies were installed only in project .venv using the
configured approval mechanism. Pip scratch and Matplotlib cache stay inside
the project. `pip check` passes. Supporting Matplotlib transitive versions are
reported by the installation log; the direct dependencies above are pinned.

Reference behavior: [scikit-learn 1.7 HistGradientBoostingRegressor](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).

## Commands, artifacts and actual runtime

```powershell
.\\.venv\\Scripts\\python.exe -m src.ml.train_speed
.\\scripts\\run_day2.ps1 -Script scripts/finalize_day6_statistics.py
.\\scripts\\run_day2.ps1 -Script scripts/validate_day6_actual.py
.\\scripts\\run_day2.ps1 -Script scripts/plot_day6.py
.\\.venv\\Scripts\\python.exe -m pytest tests/test_day6_ml.py tests/test_day5_features.py tests/test_day3_feasibility.py tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day6
```

The optional launcher changes only process settings; this code does not run
Spark/Java or repeat Day 2 processing. Direct script execution needs project-root
PYTHONPATH. The fixed training script can regenerate the same model and numerical
results; timing and serialization bytes are not promised across different package
versions/platforms. No alternative test-tuned configuration is introduced.

Local ignored artifacts: model/metadata plus `results/day6/selection.json`,
`evaluation_policy.json`, `training_run.json`, `predictions.parquet`,
`vehicle_errors.parquet`, `cohort_metrics.json`, `permutation_importance.json`,
`independent_validation.json`, `figures.json`, and `day6_pytest.xml`.
Only implementation/tests/documentation and the three lightweight PNGs are staged.
No dataset, model binary, secrets, environment or large generated output is published.

- Audit + search + inference/evaluation + persistence runtime:
  **{run['runtime_seconds']:.4f} seconds** (excluding package installation/plots/tests).
- Initial source/manifest audit: **{run['audit_seconds']:.4f} s**;
  six-candidate selection: **{run['selection_seconds']:.4f} s**;
  validation permutation importance: **{run['permutation_importance_seconds']:.4f} s**;
  frozen evaluation/bootstrap/cohorts: **{run['evaluation_seconds']:.4f} s**.
- Additional paired macro/bootstrap statistics: **{run['additional_macro_statistics_seconds']:.4f} s**;
  independent actual-model/reproducibility checks: **{audited['runtime_seconds']:.4f} s**;
  figure rendering: **{figures['runtime_seconds']:.4f} s**.
- Logical complete project storage at validated pre-commit snapshot:
  **{measured:,} bytes ({measured/1e9:.6f} GB decimal)**, including .venv, all
  preserved data, results, scratch and Git. This remains below preferred 5 GB
  and maximum 10 GB; file length is not NTFS allocated size.

The separate timings are actual stage executions, not a cumulative wall-clock
benchmark; some checks ran concurrently. Publication metadata records the final
post-commit storage and remote hash. All earlier outputs remain unchanged.

## Conclusion and remaining limitations

Positive pooled result: test MAE/RMSE are lower than persistence on the same
50 held-out vehicles, with positive paired pooled error-reduction intervals.
Negative/uncertain result: 16 test vehicles worsen, low/high-speed bins worsen,
and macro MAE superiority is not resolved by its cluster interval. The selected
model should not be described as better for every vehicle or powertrain.

The dataset's exact-endpoint/gap selection and structural sensor missingness
limit representativeness. Model and bootstrap results inherit ECU speed and
trapezoidal mean assumptions, correlated routes/trips and finite vehicle counts.
Validation selection and correlated feature permutation have stated caveats.
Published test diagnostics cannot be used to tune another Day 6 model; any
future selection must preserve a separately justified evaluation protocol.

**No unresolved Day 6 blocker. Stop after Day 6.** No dashboard or Day 7 work
started. Commit/push uses existing origin/main without rewriting history,
after the tracked-file audit and passing tests.
'''
    report=ROOT/'docs/day6_report.md'
    report.write_text(text,encoding='utf-8')
    for _ in range(4):
        total=footprint()
        text=text.replace(f'{measured:,} bytes ({measured/1e9:.6f} GB decimal)',
                          f'{total:,} bytes ({total/1e9:.6f} GB decimal)')
        measured=total
        report.write_text(text,encoding='utf-8')
    print(json.dumps({'report':str(report),'project_bytes':measured,
                      'tests':suite.attrib['tests'],'model_bytes':run['model_bytes']},indent=2))


if __name__=='__main__':
    render()
