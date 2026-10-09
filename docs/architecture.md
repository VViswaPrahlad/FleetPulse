# FleetPulse architecture — validated Bronze, Silver and Gold

```text
Author VED commit + license
           |
      download manifest (sizes, SHA-256, member CRCs)
           |
  data/raw/ved/*.7z + static XLSX (retained, Git-ignored)
           |
  data/tmp/ved/partN/ (one archive at a time; free-space/budget gate)
           |
  PySpark local[2], explicit 22-string schema + raw record provenance
           |
  bounded weekly Arrow/Pandas transfer → PyArrow Zstandard Parquet
           |
  atomic, reconciled output in data/bronze/ved/source_month=YYYY-MM/
           |
  explicit-file Spark reader → inspection-only quality statistics
```

## Source contract and retention

Both archives from pinned author commit `6baa4963782d515a67d32a5490bd5d11f5d9bf0d` pass CRC tests.
All 54 headers are verified against source field names, including `OAT[DegC]`.
Twenty-two source fields remain strings to preserve original spelling and
literal `NaN`. Additional columns hold raw_line, source_file, source_week,
is_malformed and malformed_reason. Raw records exclude line terminators;
the archives preserve canonical CSV bytes. Malformed observations and
duplicates remain in Bronze. Unexpected schemas and count mismatches fail
explicitly. During Day 2, numeric casting and the static powertrain join were
inspection views only. Day 3 adds typed Silver with the rules below; missing
measurements are never imputed.

## Local Windows execution

Python 3.12.10, Java 21.0.12.1, Spark 4.0.3.
The launcher sets Java/Python-worker settings and all current temporary
locations inside the project. It leaves system-wide settings alone.
The existing approved PyArrow package writes Parquet with Windows APIs.
Spark reads enumerated file paths; Hadoop's native Windows writer and
directory listing remain unavailable. The roundtrip and fixture tests pass
through the provided implementation. No native Hadoop binaries are installed.

## Partitioning, budget and idempotence

13 source-month partitions contain 54 weekly files. Source month comes
from the week-start filename; it is not an observation-date transformation.
No vehicle-ID partitions or per-trip files are generated. The largest weekly
CSV is 96,677,690 bytes, which bounds each Arrow/Pandas collection.
Source expansion is 3,203,555,729 bytes; only one archive is staged at once.
Generated source CSVs are removed after their file count/schema checks pass;
original archives are retained. Current output is 546,055,318
bytes and observed processing peak is 3,018,505,445 bytes against a 5 GB cap.
Full inspection monitors storage and cancels Spark jobs at 4.5 GB.

Fixed output names, source hashes and output hashes support resumable cache
validation. Fresh files are ordered by raw_line and published via atomic
replacement after validation. Output file-set and full-row reconciliation
detect stale/missing files. There is no append path or silent row dropping.
Tests use small fixtures; a full repeat invocation preserves all 54 hashes.

## Measured artifacts and scope

### Day 3 Silver and quality

The existing Bronze files feed `src/processing/silver_ved.py` without
re-extraction or Day 2 replay. Spark standardizes numeric types and applies
documented row/field quality rules; bounded PyArrow writes 54 Silver files
and 54 quarantine files in the original source-month layout. Provenance is
the immutable Bronze file and zero-based row index. Atomic replacement,
config/source/output hashes, full row-identity reconciliation and explicit
file-path Spark readers validate reproducibility on Windows.

22,436,808 input rows reconcile to 22,434,106 Silver rows and 2,702 quarantine
rows. Negative elapsed offsets are quarantined, not rebased. Tiny SOC
overshoots are normalized with original parsed SOC retained. NaN becomes
NULL; no sensor values are imputed. Irregular gaps and high load are flagged,
and signed current/temperature/fuel trims remain signed. Exact rules and
all measured counts are in [Day 3 report](day3_report.md).

Fuel feasibility runs before Silver and measures existing observations,
contiguous coverage and exact-endpoint 60+60-second windows. The original
ICE/HEV target was not viable for held-out-vehicle evaluation;
the user approved next-60-second mean speed forecasting on Day 4. Window computations
produce diagnostic counts, not a Gold training dataset. No model is trained.

22,436,808 source rows equal Bronze rows. Results JSON/XML artifacts
record per-file hashes/counts/runtime, telemetry statistics, repeat checks
and test results. [Day 2 report](day2_report.md) contains measured summaries.
Source and generated data remain Git-ignored. Day 2 ended at validated Bronze;
Day 3 adds the Silver/quarantine layers above. Day 4 adds descriptive Gold; ML training, dashboards and cloud
services remain deferred. The current cap is 10 GB, with a preference for under 5 GB.

## Day 4 Gold analytics and DuckDB

```text
Immutable Silver Parquet (54 files / 22,434,106 rows)
    -> in-process DuckDB 1.4.4 explicit-file view
    -> bounded weekly ordering after checking that no trip crosses source files
    -> temporary within-trip interval facts
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

## Day 5 leakage-safe ML dataset and baselines

```text
Gold vehicle IDs (source roster only) -> frozen hash-ranked vehicle split
Immutable Silver weekly Parquet -> complete vehicle/trip chronological groups
    -> exact observed t-60, t, t+60 boundaries and <=2s gaps
    -> Day 3 count reconciliation (34,348 candidates / 318 vehicles)
    -> strict greedy disjoint 120s contexts (11,549 examples)
    -> past-only feature function + separate future-speed target integration
    -> PyArrow train / validation / test tables in data/ml/speed/
    -> fixed last-speed / past-mean / train-only historical-mean baselines
    -> source-provenance audit, immutable hashes and reproducibility manifest
```

Assign all 384 source vehicles before inspecting their windows/labels, using
SHA-256 of a fixed seed plus ID, then 70/15/remainder percent by ranked vehicle
count. Usable vehicles are 223/45/50; all windows of each vehicle stay together.
Within a trip, the next retained feature start is strictly later than the
previous target end. This removes shared endpoints as well as target/context
interval overlap; it does not establish statistical independence between a
vehicle's different trips. Macro metrics expose unequal per-vehicle volumes.

31 numeric predictors come exclusively from [t-60s,t]. The target uses the
observed anchor speed at t and future measured speeds through t+60s. The
anchor boundary is shared only within an example as explicitly approved;
future rows/coverage cannot become features. No full-trip/lifetime Gold
statistic, ID or absolute timestamp is a predictor. Sensor NULL semantics and
Bronze row pointers are preserved. New ML files/JSON/Parquet results remain
Git-ignored; no raw traces, trained estimator or model binary is published.

NumPy/Pandas perform bounded local window calculations; PyArrow performs
Windows-compatible writes. No new framework/package installation is needed.
Whole trips must fit in one source file; cross-file trips fail explicitly.
The final dataset manifest is written after validated staged files replace
fixed outputs; consumers must not query during multi-file publication.
The historical baseline fits just one mean from training labels. No estimator
training, dashboard or Day 6 work is performed. See [Day 5 report](day5_report.md).

## Day 6 training and conditional uncertainty

```text
Frozen Day 5 Parquet + manifests -> checksum/schema/vehicle/temporal audit
    -> exactly 31 past-only numeric columns (native NaN preserved)
    -> six CPU HistGradientBoosting fits on train only, fixed seed/one thread
    -> pooled validation MAE selection, no internal early-stopping split
    -> persist frozen selection before test metrics, no train+validation refit
    -> validation-only permutation importance (no feature deletion/retraining)
    -> identical-example baseline/test evaluation
    -> vehicle errors + paired whole-vehicle bootstrap + cohort diagnostics
    -> local ignored model/metadata/results and three lightweight public figures
```

All prior data and Day 5 outputs are hash-checked before/after. The selected
model is serialized under `models/day6/`; metadata fixes feature order, versions,
training-input hash, forecast units, missing-value policy and selected parameters.
Inference accepts exactly the allowlisted predictors, checks model integrity and
preserves NaN. Joblib is a trusted-local artifact format, not an untrusted upload
format. Native missing-value branches learn only from training data; IDs, target,
future telemetry and absolute time never enter the predictor matrix.

Bootstrap uses 2,000 seeded paired draws of whole vehicles, preserving each
vehicle's window count for pooled metrics and equal vehicle weighting for macro
metrics. It is conditional on the fixed fitted model/split, not retraining
uncertainty or population representativeness. Target speed bins are diagnostic
labels only. No EV appears in test, no new test-driven hyperparameter is tried,
and negative subgroup/vehicle results are reported. No dashboard/Day 7 is begun.
See [Day 6 report](day6_report.md) for actual outcomes and lightweight figures.

## Approved Day 7 architecture: FastAPI now, React + TypeScript later

The earlier Streamlit plan is superseded. Day 7 implements only the local API;
the future React + TypeScript client will consume typed versioned contracts.

```text
Future React + TypeScript development client (localhost:5173)
      -> loopback Uvicorn / FastAPI /api/v1
      -> routes / public schemas / services
         -> bounded parameterized DuckDB -> existing Gold Parquet
         -> allowlisted saved Day 6 evaluation -> metrics / vehicle errors
         -> strict 31-feature prepared input -> cached trusted saved model
      -> bounded typed JSON and sanitized errors, no raw telemetry processing
```

Source layout is `src/api/{routes,services,schemas}` with an app factory/settings.
No frontend, cloud, auth system or additional pipeline technology is introduced.
API startup performs no ETL, telemetry scan or training. Model cache uses the
existing inference loader, artifact checksum, library version and feature order.
Only six optional sensor means can be null; NaN handling remains native.
Prepared-vector declarations/coherence cannot establish caller provenance.

Analytics reads only the small Gold/evaluation tables, owns one DuckDB connection
per query and caches at most 32 pages by artifact signature. Response projections
are explicit and cannot include private paths. Pagination maxes at 100; request
bodies at 64 KiB. Unknown fields/queries and invalid unit/null policies fail.
Readiness covers schemas, model loading and model/evaluation identity. Individual
routes can remain available during partial dependency loss; liveness stays up.
The launcher binds 127.0.0.1, one worker, with local React CORS and process-only
settings. Earlier data, model and evaluation artifacts remain immutable.
See [API contracts](api_contract.md) and [Day 7 measured report](day7_report.md).
