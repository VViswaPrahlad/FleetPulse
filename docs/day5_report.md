# FleetPulse Day 5 — causal features and fixed baselines

Date: **2026-10-09**, Asia/Calcutta. **Day 5 complete and validated locally.**
No advanced estimator training, dashboard, Day 6 work, dataset download or
system-wide setting change occurred. Git publication is performed only after
tests and index audit pass; the resulting commit/push status is reported in chat.

## Source and feasibility reconciliation

Existing Silver: **22,434,106 rows**, **32,552 trips**,
54 weekly Parquet files. Existing Bronze and Gold are used only for immutable
hash validation and the Gold source-vehicle roster. No earlier ETL is rerun.

Silver exactly reproduces the reported **34,348 candidate
windows across 318 vehicles and 6,864
trips**. Every trip agrees with both Day 3's saved Bronze `speed_paired_windows`
count and an independent invocation of its eligibility function on Silver.
Per-trip differences: **0**. Quarantining 2,702 negative offsets
did not alter usable windows under the original nonnegative-time requirement.

The historical greedy policy permits contexts touching at a single endpoint
and reproduces **11,671** contexts. Day 5 requires the next
feature start to be **strictly later** than the previous target end. This
retains **11,549 examples across 318 vehicles**,
122 fewer than the touching-endpoint count. The 22,799 other candidate anchors
are intentionally not used in any baseline evaluation: no complete contexts
share an observation within a trip. All 318 usable vehicles remain represented.
This selection is deterministic, earliest-first, independent of label magnitude
and baseline errors. All candidate counts are retained in the per-trip audit.

## Exact temporal and target contract

- Key: `(vehicle_id, trip_id, prediction_elapsed_ms)`. Timestamps are integer
  **milliseconds since that trip's origin**, not Unix/UTC timestamps.
- Prediction t is an observed elapsed offset on the exact one-second grid.
  Past input is **[t-60,000 ms, t]**; label is the temporal mean of speed
  over **[t, t+60,000 ms]**, in km/h. All three endpoints must exist exactly.
- Both sides use trapezoidal integration between observed speed endpoints.
  Mean = sum((v_previous+v_next)/2 * elapsed_seconds) / 60.
  Boundary speed at t is available at prediction and enters the first future
  trapezoid; all later readings are strictly label-only. The intervals' interiors
  are disjoint even though the anchor is shared within a single example.
- Chronological ordering is per complete trip with stable Bronze row index.
  Every recorded speed/time in the closed 120-second context must be finite,
  nonnegative and integral in time, with unique timestamps and gaps <=2 seconds.
  Duplicates invalidate continuity rather than being removed and bridged.
- Missing speed, exact endpoints and long gaps are never filled, extrapolated
  or resampled. Trapezoidal integration assumes behavior between measured
  endpoints; it does not invent a missing recorded sensor value.
- Offline future coverage determines whether a label is measurable; it is
  never exposed as a feature. Online eligibility can only inspect the past.
  Full trips currently fit a source file; cross-file trips fail explicitly.
- Strict context disjointness prevents target overlap and any observation
  reuse within each retained trip. Different windows/trips from the same vehicle
  remain correlated; they are not independent subjects.

## Frozen vehicle-held-out splits

Before computing any window, rank all **384 source vehicles** by SHA-256 of
`fleetpulse-speed-v1|<vehicle_id>`; assign 70%/15%/remainder by vehicle count.
All trips/windows of a vehicle inherit exactly one split. IDs are used for
assignment/audit, never as predictors. No stratification or reseeding occurs
after inspecting targets or scores. The split manifest records every ID and
unused source vehicles. **66 source vehicles** have no eligible window.

| Split | Assigned source vehicles | Usable vehicles | Usable trips | Candidates | Retained examples |
|---|---:|---:|---:|---:|---:|
| train | 268 | 223 | 4,607 | 21,541 | 7,509 |
| validation | 57 | 45 | 1,083 | 7,040 | 2,121 |
| test | 59 | 50 | 1,174 | 5,767 | 1,919 |

| Split | ICE vehicles | HEV vehicles | PHEV vehicles | EV vehicles |
|---|---:|---:|---:|---:|
| train | 150 | 55 | 16 | 2 |
| validation | 31 | 11 | 2 | 1 |
| test | 34 | 10 | 6 | 0 |

There is **no EV in the test split**; three source EVs cannot ensure reliable
powertrain-specific holdouts under a blind vehicle split. No claim of EV test
generalization is made. Validation/test metrics represent 45/50 held-out vehicles.

## Feature allowlist and provenance

There are **31 numeric predictors**, defined in
`src/features/speed_windows.py::FEATURES`. Only that allowlist may become X;
the saved files also include separate audit metadata and the target.

| Feature family | Definition; past-only source |
|---|---|
| Time mean speed | Trapezoidal speed integral / 60 seconds, km/h |
| Sample mean/median/stddev/min/max | Unweighted past speed readings; population stddev (ddof=0), km/h |
| First/last/change | Past window endpoints and last minus first, km/h |
| Speed trend | OLS slope against past elapsed seconds, km/h/s |
| Stop interval fraction | Duration with both adjacent measured speeds exactly zero / 60 seconds |
| Stop sample fraction | Fraction of past observations whose speed is exactly zero |
| Acceleration mean/stddev/min/max | Adjacent speed difference / 3.6 / measured seconds, m/s²; sample weighted |
| Absolute acceleration time mean | Sum(abs(acceleration) * interval seconds) / 60, m/s² |
| Sampling | Past observation count and maximum measured past gap (seconds) |
| Optional sensors | Finite past sample mean and present-reading fraction, for each sensor below |

Engine RPM, MAF (g/s), absolute load (%), outside temperature (°C), battery SOC
(%) and signed HV battery current (A) preserve their Silver semantics. Means
remain **NULL** when no measurement exists. Missingness fractions are derived
past-only availability indicators; a zero fraction is not a fabricated sensor
value. No optional sensor is required for eligibility and no imputation occurs.
Fuel rate is deliberately not used as a pervasive predictor given structural
missingness. No full-trip or vehicle-lifetime Gold aggregate is a feature.

| Optional sensor | NULL mean features among 11,549 examples |
|---|---:|
| `engine_rpm` | 292 |
| `maf_g_s` | 2,564 |
| `absolute_load_pct` | 3,747 |
| `outside_air_temp_c` | 2,723 |
| `battery_soc_pct` | 7,978 |
| `hv_battery_current_a` | 7,978 |

Feature/target files contain audit-only vehicle/trip IDs, split, engine type,
relative boundaries, source Bronze file and three immutable Bronze row indices.
Raw GPS, absolute dates, IDs, future quality/count/availability and target
columns are excluded from the predictor list. Sensor means and sampling counts
are computed only after slicing [t-60,t]; the feature function cannot access
future arrays. A test mutating future speed and engine RPM changes the label
while leaving every feature unchanged.

## Baselines and measured held-out metrics

All three rules are fixed before evaluation, with no hyperparameter tuning:

1. **Last-observed speed:** predict speed at t for the next-minute temporal mean.
2. **Past-mean persistence:** predict the preceding 60-second temporal mean.
3. **Historical average:** one constant, the mean of selected training labels,
   **48.643499722 km/h**. Validation/test labels never
   enter fitting. This pooled training-window mean is not a per-test-vehicle mean.

No scikit-learn estimator is needed for these analytical baselines. NumPy/Pandas
and PyArrow reuse existing approved packages; no new software is installed.
NumPy 2.5.3 is now explicitly pinned because Day 5 uses it directly.
Pandas 2.2.3, PyArrow 20.0.0 and Python 3.12.10 are reused.
`pip check` passes. PySpark/DuckDB remain installed; no Spark/Java job runs today.

Pooled errors weight windows equally. Macro errors average each vehicle's own
MAE/RMSE equally; macro RMSE is the mean of per-vehicle RMSE, not a pooled root.
All three methods use exactly the same selected examples. Training metrics and
per-vehicle metrics are saved locally; below are the held-out results in km/h.

| Split | Baseline | MAE km/h | RMSE km/h | Vehicle macro MAE | Vehicle macro RMSE |
|---|---|---:|---:|---:|---:|
| validation | `last_observed_speed` | 13.702132 | 18.219851 | 13.879786 | 17.201903 |
| validation | `past_mean_persistence` | 14.632047 | 19.892806 | 13.474043 | 17.213113 |
| validation | `training_historical_mean` | 17.390852 | 24.349012 | 17.018432 | 20.873840 |
| test | `last_observed_speed` | 14.056006 | 18.802985 | 12.466133 | 15.918880 |
| test | `past_mean_persistence` | 14.186875 | 19.245332 | 16.492761 | 19.991954 |
| test | `training_historical_mean` | 17.814939 | 23.724005 | 18.551034 | 22.457076 |

Last speed has lower pooled MAE/RMSE than the two other rules on these fixed
validation/test cohorts. Validation macro MAE ranks past mean slightly better
than last speed; unequal vehicle volumes matter. No baseline is tuned or
selection policy changed in response to the published test results. Advanced
model choices must use training/validation only; the held-out vehicle split
remains fixed for later separately authorized work.

## Leakage, duplication and numerical validation

- No vehicle occurs in multiple splits; no feature accesses future rows.
- No duplicate example ID or vehicle/trip/anchor occurs. No retained contexts
  overlap or share boundary observations within a trip. Original sensor records
  and earlier layers are unchanged.
- Full saved-output audit independently checks all **11,549**
  examples against Silver, including endpoint existence, gaps, chronological
  source pointers, past sensor means/fractions and exact last speed.
  Maximum target and past-mean discrepancies are each
  **5.68e-14 km/h** (floating rounding).
- Identical feature+target rows: **0**;
  cross-split identical signature groups: **0**.
  Distinct source observations with coincident measurements would not be
  silently removed based on test labels; this audit reports the actual zero counts.
- Only **25** labels are exactly zero. As a descriptive robustness
  check, excluding zero-target validation/test examples produces similar last-speed
  errors below. This does not replace the fixed primary cohort or tune a model.

| Moving-target diagnostic split | Examples | Last-speed MAE | Last-speed RMSE |
|---|---:|---:|---:|
| validation | 2,116 | 13.734510 | 18.241365 |
| test | 1,916 | 14.078014 | 18.817700 |

## Tests and reproducibility

**47 tests passed, 0 failures, 0 errors**,
including 21 Day 5 tests, 8 Day 3 eligibility regressions and 18 Day 4 Gold
regressions. JUnit suite runtime: **4.467 seconds**.
Fixtures test exact endpoints and units, gap==2s versus >2s, missing readings,
duplicates/negative times, strict boundary disjointness, temporal arithmetic,
future-mutation invariance, no trip mixing, deterministic held-out IDs,
training-only fitting, incorrect split/duplicate/overlap rejection, cross-file
guards, Parquet schema/readability and fresh byte reproducibility.

Two full successful fresh runs produce identical bytes for **seven** artifacts:
three ML Parquet tables, per-trip audit Parquet, per-vehicle baseline Parquet,
baseline JSON and split JSON. Source/config/output SHA-256 hashes, package
versions, feature allowlist, seed and selection policy are recorded.
The second run also verifies matching code/reference-input guards. Verified
cache repeat skips telemetry computation. All Bronze/Silver/Gold hashes match
before/after (54/54/7 files respectively).

## Local outputs and execution

`data/ml/speed/` contains the three ML-ready, split-specific Parquet files.
Total feature Parquet storage: **1,749,827 bytes**.
Generated outputs remain Git-ignored; only source/tests/text reports are published.

| File | Bytes |
|---|---:|
| `test.parquet` | 296,073 |
| `train.parquet` | 1,126,979 |
| `validation.parquet` | 326,775 |

`results/day5/` contains `split_manifest.json`, `baseline_metrics.json`,
`baseline_by_vehicle.parquet`, `window_audit_by_trip.parquet`,
`dataset_manifest.json`, `first_run.json`, `full_run.json`,
`independent_validation.json`, `reproducibility.json`, and `day5_pytest.xml`.

```powershell
.\.venv\Scripts\python.exe -m src.features.build_speed_dataset
.\scripts\run_day2.ps1 -Script scripts/complete_day5.py
.\scripts\run_day2.ps1 -Script scripts/validate_day5_actual.py
.\.venv\Scripts\python.exe -m pytest tests/test_day5_features.py tests/test_day3_feasibility.py tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day5
```

The launcher only supplies process settings; it does not repeat Day 2 work.
Direct script execution requires project-root PYTHONPATH. To explicitly verify
a new full fresh run, pass `--verify-fresh` to `scripts/complete_day5.py`;
ordinary runs verify cached hashes. Multi-file publication assumes no concurrent
readers. Source files must contain complete trips or the guard fails.

## Actual runtime and storage

- First end-to-end generation and baseline evaluation: **164.3836 seconds**.
- Final fresh reproducibility run: **107.7506 seconds**;
  window/features/output computation: **106.8886 seconds**;
  baseline fitting/evaluation: **0.0178 seconds** (included).
- Cache repeat: **0.8449 seconds**.
- Independent full source audit: **60.2536 seconds**.
- Complete logical project storage including .venv, existing datasets, results,
  scratch and Git: **1,919,686,591 bytes (1.919687 GB decimal)**,
  below preferred 5 GB and maximum 10 GB. This is file length, not NTFS allocated
  size. Storage/free-space gates run before generation; staging is small.

Runtime figures are actual individual executions, not a performance benchmark.

## Risks and scope boundary

Coverage selection favors trips with reliable exact endpoints and short gaps;
the 318-vehicle eligible cohort is not representative of every VED vehicle or
future fleet. Repeated windows/trips within vehicles remain correlated despite
context disjointness; 45/50 validation/test vehicles are the independent subject
counts, not 2,121/1,919 independent drivers. Pooled and macro metrics differ.
No EV appears in test; powertrain sample sizes are small. Speed measurements
and speed-derived acceleration inherit ECU reporting and integration assumptions.
Optional sensor missingness is structural and may encode vehicle type; no
imputation/scaling/feature selection is fitted today. Future label availability
is an offline audit condition and cannot be known at deployment. VED's
geographic/temporal limits preclude broad fleet-performance claims.

No model binaries are produced. No Day 6 or dashboard work is started.
**No unresolved Day 5 data/environment blocker.** Publication uses the existing
`origin/main` through the configured security approval mechanism, without force
push or history rewriting, after the staged tracked-file audit passes.
