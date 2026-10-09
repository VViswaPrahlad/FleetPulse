# ML problem definition

Approved on 2026-10-08: **next-60-second mean speed forecasting** using VED.
This replaces the rejected ICE/HEV fuel-consumption task. No model, training
windows or feature matrix is produced on Day 4.

Day 5 (2026-10-09) implements the approved windows and three fixed baselines.
Silver reproduces 34,348 candidates / 318 vehicles / 6,864 trips exactly.
Primary baseline evaluation uses 11,549 strict disjoint contexts, with next
feature start > prior target end, so not even an endpoint observation is reused.
The Day 3 11,671-context count allowed touching endpoints; its 122-example
difference is policy-driven. All 318 usable vehicles remain. A deterministic
SHA-256 split of all 384 source vehicles is frozen before window generation.
See [Day 5 report](day5_report.md) for definitions, held-out counts and metrics.

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

Day 5 implements last-speed, past-mean persistence, and training-only global
historical-mean baselines. Day 6 fits HistGradientBoostingRegressor using native
NaN handling and six fixed validation-only configurations. No imputation/scaling
or internal random-row early stopping is used; the model stays training-only.
Neither permutation importance nor test diagnostics change the 31-feature list.

Report held-out **MAE and RMSE in km/h**, per-vehicle errors and macro averages,
powertrain coverage, eligible/excluded windows and overlap policy. Compare
with persistence on identical test windows; keep final test vehicles untouched
until the definition and choices are frozen. Day 6 publishes actual pooled and
vehicle-macro errors with paired vehicle-cluster confidence intervals in the
[Day 6 report](day6_report.md); no regression accuracy claim is made.
VED is geographically/temporally limited and
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
