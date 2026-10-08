"""Apply the approved Day 4 target and architecture documentation."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root/'docs/ml_problem_definition.md').write_text('''# ML problem definition

Approved on 2026-10-08: **next-60-second mean speed forecasting** using VED.
This replaces the rejected ICE/HEV fuel-consumption task. No model, training
windows or feature matrix is produced on Day 4.

## Target and measurement contract

At an observed prediction time t, predict the time-weighted mean measured
speed in [t,t+60 seconds], in km/h, from telemetry in [t-60 seconds,t].
Use trapezoidal integration of adjacent observed speed endpoints, divided by
60 seconds. This temporal mean avoids giving dense samples extra weight.
It is a derived label from reported speed, not a synthetic sensor reading.
The endpoint at t is available at prediction time and participates in both
integration boundaries; every later speed belongs exclusively to the label.

The conservative Day 3 eligibility contract requires observed endpoints at
t-60, t, t+60 seconds; anchors on a one-second trip grid; finite nonnegative
speed throughout the span; unique valid nonnegative integer timestamps;
and adjacent gaps <=2 seconds. No missing speed, boundary or long gap is
filled. Trapezoidal interpolation is an integration assumption between
measured samples, not a claim of continuous sensor observation. Eligibility
of the future is used only to determine whether an offline label can be
evaluated, never as an input feature. At deployment, future availability is
unknown; report offline selection bias and past-only prediction eligibility.

Day 3 measured **318 vehicles, 6,864 trips, 34,348 overlapping paired windows**,
and **11,671 greedily disjoint 120-second contexts**. These are Bronze-based
feasibility counts, not a Day 4 training corpus. Future window construction
must revalidate them against Silver and the frozen policy before training.

## Causal features and evaluation

- Use past speed levels, time-weighted mean, variability, stopped duration,
  recent trends, and speed-derived acceleration only from [t-60,t].
- Other valid sensor measurements and approved static powertrain descriptors
  may be used if available by t. Preserve missingness; do not fabricate sensors.
- Exclude future telemetry, future coverage/quality flags, whole-trip and
  lifetime Gold aggregates, and anything calculated using rows after t.
  Day 4 Gold is descriptive analytics, not a forecasting feature source.
- Vehicle/trip IDs and row provenance are for grouping/audit, not predictors.
  Exclude raw GPS coordinates and absolute date/time by default to avoid route
  memorization. Timestamp differences may support causal interval features.
- Freeze a deterministic **vehicle-held-out** train/validation/test split
  before generating windows. All trips/windows of each vehicle stay together.
  Never randomly split overlapping windows. Fit preprocessing, normalization,
  optional feature imputation and selection only on training vehicles.

Future baseline: persistence of the preceding 60-second time-weighted mean
speed. A training-only median reference may also be reported. A future
HistGradientBoostingRegressor is a candidate after split/feature checks;
no new ML package is installed and no fitting happens today.

Report held-out **MAE and RMSE in km/h**, per-vehicle errors and macro averages,
powertrain coverage, eligible/excluded windows and overlap policy. Compare
with persistence on identical test windows; keep final test vehicles untouched
until the definition and choices are frozen. No regression accuracy claim or
performance number exists yet. VED is geographically/temporally limited and
reported speed is not independently calibrated ground truth.

## Why fuel forecasting was rejected

Direct fuel rate is missing in **96.0061% of Bronze observations**. Its 896,097
nonmissing readings cover only 13 vehicles and 1,357 trips: 12 PHEVs and one ICE;
all HEV/EV fuel-rate signals are absent. Missingness is structural by vehicle.
The original ICE/HEV population supports only **one vehicle, one trip and one
paired window** under the two-second policy. Even a ten-second gap permits
only one vehicle and five paired windows, so vehicle-held-out evaluation is
impossible. Broadening to PHEVs would change the original population and
still yields just 12 usable vehicles, 527 trips and 2,187 paired windows,
73.25% with zero fuel labels. The user approved the speed target instead.
See [Day 3 measured feasibility](day3_report.md) for exact rules and artifacts.

No fuel value is imputed and no alternative fuel proxy is treated as measured
fuel consumption. The historical Day 3 approval-pending report remains an
accurate record of that checkpoint; this document records the subsequent decision.
''',encoding='utf-8')

p = root/'README.md'
text = p.read_text(encoding='utf-8')
text = text.replace('paired training window; alternative target approval is pending.',
                    'paired training window; the approved primary ML target is now next-60-second mean speed.')
text = text.replace('Gold and model work have not started.',
                    'DuckDB SQL now produces descriptive Gold analytics; no model is trained.')
text = text.replace('Silver and feasibility analysis are complete. Gold, ML, dashboard and cloud\nwork have not started. Work stops after Day 3; no GitHub push occurred.',
                    'Silver and feasibility analysis are complete. Day 4 adds Gold and DuckDB.\nML training, dashboards and cloud services remain deferred. Work stops after Day 4; no GitHub push occurs.')
text = text.replace('with a preference for remaining under 5 GB. Choose a replacement ML target\nonly after approval.',
                    'with a preference for remaining under 5 GB. The user approved the speed target on Day 4.')
text += '''
## Day 4 Gold and local SQL

The approved target is next-60-second time-weighted mean speed in km/h, with
past-only inputs and vehicle-held-out evaluation. Fuel forecasting was rejected
because the original ICE/HEV cohort supports just one usable vehicle/window.
See [ML definition](docs/ml_problem_definition.md) and [Day 4 report](docs/day4_report.md).

```powershell
.\\.venv\\Scripts\\python.exe -m src.analytics.build_gold
.\\.venv\\Scripts\\python.exe -m src.analytics.query fleet_overview
.\\.venv\\Scripts\\python.exe -m src.analytics.query powertrain_comparison
.\\.venv\\Scripts\\python.exe -m pytest tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day4
```

DuckDB 1.4.4 reads existing Silver locally; PyArrow 20.0.0 writes seven Gold
tables under `data/gold/ved/`. No Java process is needed for these SQL jobs.
The builder verifies input/output/config hashes and reconciles aggregates
against Silver. SQL lives in [sql/](sql/README.md). Trip-start day/month cohorts
use the author's reference date with unspecified timezone. Distance covers
measured adjacent speed intervals <=2 seconds; gaps and missing endpoints
are excluded from integration, never from observation counts. Whole-trip
Gold summaries are descriptive and cannot become causal forecasting features.
'''
p.write_text(text,encoding='utf-8')

p = root/'docs/architecture.md'
text = p.read_text(encoding='utf-8').replace('validated Bronze and Silver','validated Bronze, Silver and Gold')
text = text.replace('ICE/HEV target is retained but is not viable for held-out-vehicle evaluation;\nreplacement target/cohort selection awaits approval.',
                    'ICE/HEV target was not viable for held-out-vehicle evaluation;\nthe user approved next-60-second mean speed forecasting on Day 4.')
text = text.replace('Gold, ML, dashboards and cloud\nservices remain deferred.',
                    'Day 4 adds descriptive Gold; ML training, dashboards and cloud\nservices remain deferred.')
text += '''
## Day 4 Gold analytics and DuckDB

```text
Immutable Silver Parquet (54 files / 22,434,106 rows)
    -> in-process DuckDB 1.4.4 explicit-file view
    -> temporary ordered within-trip interval facts
    -> checked-in SQL: trip / vehicle / trip-start day / month / powertrain
    -> fleet overview and quality-flag summaries
    -> PyArrow Zstandard Gold Parquet (7 small tables)
    -> direct Silver aggregate checks + independent interval integration
    -> SHA-256 source/output/config manifest and named SQL demo CLI
```

Gold uses one thread, a 4 GB process memory limit and a 1.5 GB project-local
spill cap. SQL output has explicit stable ordering. Each file is staged,
readability/count checked, all summaries reconciled, then atomically replaced;
the manifest is written last. Consumers should run the builder successfully
before querying; simultaneous readers during multi-file publication are not
supported. No persistent copy of Silver or database server is introduced.

Each trip is keyed by (vehicle_id,trip_id). Distance is trapezoidal integration
of adjacent nonmissing nonnegative speed with 0<gap<=2000 ms. Invalid intervals
contribute no distance, while their observations still contribute to counts.
No eligible interval produces NULL distance; measured stationary intervals
produce zero. Sample speed means/percentiles are separate from time-weighted
interval means. No manufacturer-independent odometer/GPS mileage claim is made.

Daily/monthly outputs group **whole trips by trip-start reference date**:
2017-11-01 + floor(day_number-1). DayNum is constant per observed vehicle/trip;
the timezone is unspecified. These cohort summaries do not assert event-day
traffic rates, do not split midnight-crossing trips, and differ from source
week/month provenance. Gold retains cohort keys, count/coverage semantics and
source-file counts; full row-level provenance remains in immutable Silver.

The approved forecasting label is next-60-second time-weighted mean speed;
features may use only records available at the anchor. Split by vehicle before
window creation. Gold whole-trip/lifetime summaries are not causal features.
No ML training/windows or dashboard is created on Day 4. See the updated
[ML definition](ml_problem_definition.md) for fuel rejection evidence and
[Day 4 report](day4_report.md) for measured reconciliation/runtime/storage.
'''
p.write_text(text,encoding='utf-8')
