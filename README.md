# FleetPulse

FleetPulse is a local vehicle telemetry project. The approved primary source
is the [Vehicle Energy Dataset (VED)](https://github.com/gsoh/VED).

**Day 5 is complete:** the Silver audit reproduces all 34,348 eligible speed
windows across 318 vehicles. The ML dataset retains 11,549 examples whose
complete contexts share no observations. Vehicle-held-out splits contain
223 training, 45 validation and 50 test vehicles. Three fixed baselines are
evaluated; no advanced model is trained. See [Day 5 report](docs/day5_report.md).

**Day 4 is complete:** seven reproducible Gold Parquet tables, local DuckDB
SQL demos, and 18 passing tests. All 22,434,106 Silver observations reconcile;
Bronze and Silver are unchanged. The approved ML target is next-60-second
mean speed with causal inputs and vehicle-held-out evaluation. No model is
trained. See [the measured Day 4 report](docs/day4_report.md).

**Day 3 is complete:** 22,434,106 typed Silver rows and 2,702 quarantined
negative-timestamp rows reconcile to all 22,436,808 Bronze observations.
Bronze is unchanged. The original ICE/HEV fuel target has only one usable
paired training window; the approved primary ML target is now next-60-second mean speed. See
[the Day 3 quality and feasibility report](docs/day3_report.md).

**Day 2 is complete:** 22,436,808 actual observations, 384
vehicles and 32,552 vehicle/trip pairs are ingested into Bronze.
All source rows reconcile. 11 fixture tests pass; a repeat
invocation preserves all 54 output hashes. Full ingestion took
525.23 seconds. Bronze occupies
546,055,318 bytes. See [the measured Day 2 report](docs/day2_report.md)
for fuel-rate missingness, cadence, duplicates, powertrain differences,
dependency versions, storage and limitations.

## Current architecture

Official checksummed archives → bounded archive staging → explicit-schema
PySpark parsing → PyArrow Parquet writer → `data/bronze/ved/`.
Raw values, literal `NaN`, malformed records and duplicates are retained.
Output contains 54 weekly files in 13 source-month directories.
Existing Bronze now feeds reproducible PySpark type/quality processing and
bounded PyArrow output to `data/silver/ved/` and `data/quarantine/ved/`.
Every row has a Bronze file/index pointer. Missing sensors remain missing;
DuckDB SQL now produces descriptive Gold analytics; no model is trained.
See [architecture](docs/architecture.md) and [scope](docs/project_scope.md).

## Run locally

Use the existing Python 3.12 `.venv` and JDK 21. The launcher applies Java,
Python-worker and project-local temporary-directory settings only to the
current process. From the FleetPulse PowerShell terminal:

```powershell
.\scripts\run_day2.ps1 -Script scripts/spark_smoke.py
.\scripts\run_day2.ps1 -Script scripts/complete_day2.py
.\scripts\run_day2.ps1 -Script scripts/check_day2_reproducibility.py
```

`complete_day2.py` runs fixture tests, idempotent ingestion, then full-corpus
inspection. Existing verified sources need no new downloads. For a fresh
checkout, create `.venv` with `py -3.12 -m venv .venv`, install
`requirements.txt`, then run `scripts/acquire_ved.py` through the launcher
with authorized network access. It obtains only author-repository VED data,
checks sizes/CRCs/disk/budget, and leaves extraction to bounded ingestion.

## Windows IO and storage

Python 3.12.10, Java 21.0.12.1, PySpark 4.0.3.
The approved PyArrow writer and explicit-file Spark reader avoid unavailable
Hadoop native Windows IO. Use `read_bronze()` in the ingestion module;
direct `spark.read.parquet(directory)` and Spark's native writer are not
validated on this machine.

The current maximum is **10,000,000,000 bytes**, with a preference for staying
under **5,000,000,000 bytes**. For Bronze acquisition, one archive is staged at a
time and reconciled generated CSVs are removed. The original 176,386,679-byte
archives remain; their CSV expansion totals 3,203,555,729 bytes. Observed
processing peak was 3,018,505,445 bytes. Raw data, Bronze, temporaries and results
are ignored by Git. No source data or individual GPS trace is committed.

## Deferred scope

The initial fuel-use forecasting proposal is documented in
[the ML definition](docs/ml_problem_definition.md). Sparse direct fuel-rate
coverage is now measured; no missing fuel signal is imputed on Day 2.
Silver and feasibility analysis are complete. Day 4 adds Gold and DuckDB.
Advanced ML training, dashboards and cloud services remain deferred. Day 5 adds
feature engineering and baselines; work stops after Day 5.

## Repeat Day 3 using validated caches

The existing launcher only sets process-local Java/Python/temporary paths;
its filename does not cause Day 2 work to rerun.

```powershell
.\scripts\run_day2.ps1 -Script src/processing/silver_ved.py
.\scripts\run_day2.ps1 -Script scripts/check_day3_repeat.py
```

`scripts/complete_day3.py` runs the 20 Day 3 fixture tests before Silver.
Silver uses the measured feasibility checkpoint and verified Bronze hashes;
it never downloads or re-ingests sources. The current storage cap is 10 GB,
with a preference for remaining under 5 GB. The user approved the speed target on Day 4.

## Day 4 Gold and local SQL

The approved target is next-60-second time-weighted mean speed in km/h, with
past-only inputs and vehicle-held-out evaluation. Fuel forecasting was rejected
because the original ICE/HEV cohort supports just one usable vehicle/window.
See [ML definition](docs/ml_problem_definition.md) and [Day 4 report](docs/day4_report.md).

```powershell
.\.venv\Scripts\python.exe -m src.analytics.build_gold
.\.venv\Scripts\python.exe -m src.analytics.query fleet_overview
.\.venv\Scripts\python.exe -m src.analytics.query powertrain_comparison
.\.venv\Scripts\python.exe -m pytest tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day4
```

DuckDB 1.4.4 reads existing Silver locally; PyArrow 20.0.0 writes seven Gold
tables under `data/gold/ved/`. No Java process is needed for these SQL jobs.
The builder verifies input/output/config hashes and reconciles aggregates
against Silver. SQL lives in [sql/](sql/README.md). Trip-start day/month cohorts
use the author's reference date with unspecified timezone. Distance covers
measured adjacent speed intervals <=2 seconds; gaps and missing endpoints
are excluded from integration, never from observation counts. Whole-trip
Gold summaries are descriptive and cannot become causal forecasting features.

## Day 5 causal features and baselines

```powershell
.\.venv\Scripts\python.exe -m src.features.build_speed_dataset
.\scripts\run_day2.ps1 -Script scripts/complete_day5.py
.\scripts\run_day2.ps1 -Script scripts/validate_day5_actual.py
.\.venv\Scripts\python.exe -m pytest tests/test_day5_features.py -q --basetemp=data/tmp/pytest-day5
```

The first command creates or verifies cached `data/ml/speed/train.parquet`,
`validation.parquet` and `test.parquet`. It reads existing Silver; Bronze,
Silver and Gold remain unchanged. No Spark job or Java process is needed by
feature code; the existing launcher is an optional process-settings convenience.
`scripts/complete_day5.py --verify-fresh` explicitly verifies a fresh repeat;
ordinary repeat invocations use hashes instead of processing telemetry again.

The feature allowlist is `src.features.speed_windows.FEATURES` (31 numeric
columns). All predictive inputs use only [t-60s,t]; target mean speed integrates
observed endpoints over [t,t+60s]. Vehicle/trip IDs, absolute timestamps, source
pointers, split labels and targets are audit metadata and must not be passed
to a model. Optional sensor means retain NULL when absent; no sensor is filled.
Missingness fractions are past-only. The SHA-256-ranked vehicle assignment is
frozen before window generation. Strict greedy selection prevents any source
observation from being shared between retained contexts in a trip.

Split assignments, per-trip coverage audit, train-only historical constant,
baseline metrics and reproducibility metadata live under ignored `results/day5/`.
Only implementation, tests and measured text reports are committed to GitHub;
ML-ready Parquet and generated metrics remain local. Stop after Day 5.
