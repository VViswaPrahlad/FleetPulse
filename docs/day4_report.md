# FleetPulse Day 4 — Gold analytics and DuckDB SQL

Date: 2026-10-08 (Asia/Calcutta). **Day 4 complete.** No model training,
dashboard, new dataset download, cloud service or Day 5 work occurred.

## Approved ML decision

The user approved replacing ICE/HEV next-minute fuel consumption with
**next-60-second mean speed forecasting**. The definition uses a temporal
mean of measured speed, trapezoidal integration / 60 seconds, in km/h,
with past-60-second inputs and vehicle-held-out evaluation. Future speed,
future coverage and entire-trip/lifetime Gold summaries cannot be features.
The ML definition, README, scope and architecture now record this decision.

Measured Day 3 fuel feasibility rejected the old task: 896,097 fuel-rate
observations across 13 vehicles/1,357 trips, with 96.0061% Bronze missingness.
Twelve vehicles are PHEVs, one ICE; HEV/EV direct fuel rate is absent.
The original ICE/HEV population supports **1 vehicle, 1 trip, 1 paired window**
at <=2-second gaps; even <=10 seconds permits just 1 vehicle/5 windows.
Vehicle-held-out evaluation therefore cannot be performed for that task.
Speed feasibility measured **318 vehicles, 6,864 trips, 34,348 overlapping
paired windows**, and **11,671 disjoint 120-second contexts**. These are
historical feasibility counts, not regenerated training data or model scores.
Silver eligibility must be revalidated in a future authorized ML phase.

## Inputs and reproducible execution

Read existing 54 Silver Parquet files directly: **22,434,106 observations**,
384 vehicles, 32,552 (vehicle_id, trip_id) pairs. No Bronze/Silver ETL was rerun.
Before and after generation, all 54 Bronze and 54 Silver SHA-256 hashes match.
The source schema/provenance and quality flags remain unchanged.

DuckDB **1.4.4** is the only new dependency, installed through
the configured approval mechanism and pinned in requirements.txt. Existing
Python 3.12.10, PyArrow 20.0.0, Pandas 2.2.3, Pytest 8.3.5,
PySpark 4.0.3 and Java 21.0.12.1 remain. No Spark/Java process is needed for Gold.
`pip check` passed. DuckDB is an in-process SQL engine, not a server.

The CLI uses project-root paths, one thread, a 4 GB memory limit and a 1.5 GB
logical spill limit in project-local scratch. No external extension install or
autoload is enabled. Window ordering is bounded to weekly files after checking
that no trip crosses source files (actual maximum = 1 file per trip).
Temporary facts are reused for the six aggregate queries; no duplicate Silver
dataset/database is persisted. PyArrow writes stable ordered Zstandard Parquet.
All summaries are validated before file replacement; the manifest is written
last. Concurrent readers during the seven-file publication are unsupported.

```powershell
.\.venv\Scripts\python.exe -m src.analytics.build_gold
.\.venv\Scripts\python.exe -m src.analytics.query fleet_overview
.\.venv\Scripts\python.exe -m src.analytics.query trip_gap_audit
.\.venv\Scripts\python.exe -m pytest tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day4
```

The builder verifies config/SQL/input/output hashes and reuses valid outputs.
`--force` explicitly regenerates. `scripts/complete_day4.py` builds and checks
the cache repeat; `scripts/validate_day4_actual.py` independently validates
interval integration and runs all six demo queries. Run these scripts with
project-root PYTHONPATH, or use the existing process-only launcher.

## Gold outputs

Location: `data/gold/ved/`, one file per table; **2,501,660 bytes total**.
No vehicle/trip partitions or thousands of small files are created.

| Table | Rows | Parquet bytes |
|---|---:|---:|
| `trip_analytics` | 32,552 | 2,363,550 |
| `vehicle_analytics` | 384 | 50,165 |
| `daily_fleet` | 375 | 51,618 |
| `monthly_fleet` | 13 | 12,850 |
| `powertrain_fleet` | 4 | 11,451 |
| `fleet_overview` | 1 | 10,630 |
| `quality_metrics` | 5 | 1,396 |

Trip keys are (vehicle_id, trip_id), vehicle keys (vehicle_id, engine_type).
Trip/vehicle/cohort summaries include observation and sensor availability
counts, sample mean/population stddev/min/max/exact p50/p95 speed,
stationary-observation counts, interval-weighted speed, partial distance,
positive-gap p50/p95/max, gap >2s/>10s counts, duplicate-timestamp indicators,
flagged-row/flag-occurrence counts, distinct source-file counts and reference
date coverage. Trip elapsed span is explicitly different from supported
observed duration. Full raw measurement provenance stays in Silver/Bronze.

## Metric and missing-value semantics

- Every Silver row contributes to observation counts; there is no Gold row
  filter. Missing speed/fuel rates remain missing. `count(sensor)` and its
  complementary missing count are explicit; SQL aggregates ignore NULL.
- Sample means and percentiles weight observations equally. Time-weighted
  speed weights only defensible measured intervals; they are separate metrics.
- Within each complete trip, order by elapsed_ms and stable Bronze provenance.
  Eligible speed intervals have **0 < gap <= 2,000 ms**, finite nonnegative
  endpoints, and no missing speed. Duplicate timestamps have zero duration
  and contribute no distance; no deduplication drops an observation.
- Partial distance = sum((previous_speed+speed)/2 * gap_ms / 3,600,000) km.
  No interval bridges a long gap or missing endpoint. Supported duration is
  the sum of eligible gaps. Time-weighted mean = distance * 3600 / duration.
  No eligible interval means NULL distance/duration/weighted mean, while
  measured stationary intervals produce genuine zero distance.
- This is an observed-segment speed integral, **not full-trip mileage,
  odometer truth or GPS route distance**. Trapezoidal interpolation between
  measured endpoints is stated, not a fabricated sensor observation.
- Trip-start reference date = 2017-11-01 + floor(DayNum-1) days. DayNum is
  constant within every observed vehicle/trip. The timezone is unspecified.
  Daily/monthly summaries assign each entire trip to that date/month, without
  splitting midnight-crossing trips. They are trip-start cohorts, not
  wall-clock traffic counts or source-week/month provenance summaries.

## Actual aggregate results

- Speed present: **22,432,710** rows; missing:
  **1,396** (0.006223%).
- Fuel rate present: **896,097** rows; missing:
  **21,538,009** (96.005649% of Silver).
- Sample mean speed: **40.399944 km/h**;
  eligible-interval time-weighted mean: **40.101681 km/h**.
- Eligible intervals: **21,624,227**;
  supported duration: **14,313,930.799049 seconds**;
  partial measured-segment distance: **159,447.967412 km**.
- Trips without any eligible speed interval: **10**; distance is NULL.
- Gaps >2s: **777,320**; gaps >10s:
  **38,264**; max gap:
  **7,444.700 seconds**; duplicate timestamps:
  **0**.
- Trip-start date range: **2017-11-01 to 2018-11-10**, with 375 observed dates.

| Powertrain | Vehicles | Trips | Observations | Partial distance km |
|---|---:|---:|---:|---:|
| EV | 3 | 504 | 476,308 | 2,335.741 |
| HEV | 93 | 9,507 | 5,587,565 | 45,711.426 |
| ICE | 264 | 18,936 | 13,126,861 | 90,802.474 |
| PHEV | 24 | 3,605 | 3,243,372 | 20,598.326 |

Powertrain counts derive from existing author static-workbook mappings;
93 HEVs are observed, rather than assuming the README's 92. Direct fuel
missingness remains distinct from electric consumption; no proxy is substituted.

| Quality flag | Occurrences | Fraction of Silver observations |
|---|---:|---:|
| `irregular_gap_gt_2s` | 777,320 | 3.464903% |
| `load_above_100_advisory` | 29,219 | 0.130244% |
| `missing_fuel_rate_lph` | 21,538,009 | 96.005649% |
| `missing_speed_kmh` | 1,396 | 0.006223% |
| `soc_precision_clipped` | 358 | 0.001596% |

**21,560,975 rows** carry one or more flags;
**22,346,302 flag occurrences** overlap and
must not be interpreted as excluded rows. All are retained in Gold counts.

## SQL demonstrations

Reviewable build SQL lives in `sql/gold/`, direct-source validation in
`sql/validation/`, and named reusable queries in `sql/analytics/`.
The query CLI recreates views from project-local Parquet, so no absolute-path
database file or duplicate sensor table is committed.

| SQL demonstration | Actual result rows | Measured seconds |
|---|---:|---:|
| `fleet_overview.sql` | 1 | 0.0167 |
| `powertrain_comparison.sql` | 4 | 0.0170 |
| `quality_flags.sql` | 5 | 0.0144 |
| `trip_gap_audit.sql` | 20 | 0.0212 |
| `trip_start_daily_trend.sql` | 375 | 0.0158 |
| `vehicle_coverage.sql` | 20 | 0.0170 |

Query timings are single local executions, not performance benchmarks.
Vehicle/trip audit examples limit output to 20 rows.

## Validation and reproducibility

- **18 tests passed**, 0 failed,
  0 errors; Pytest runtime **5.765 seconds**.
  Tests cover exact fixture arithmetic, missing versus stationary zero,
  irregular sampling, gap/missing-endpoint exclusion, duplicates, reference
  dates, schema/readability, primary keys, direct aggregate reconciliation,
  path restrictions, corrupted gaps, all demo SQL, fresh-byte reproducibility,
  bounded-batch equivalence, and cross-file-trip rejection.
- Trip, vehicle, daily, monthly and powertrain observation counts all sum to
  **22,434,106**, with exact speed/fuel/gap/quality count reconciliation.
  Sample means reconcile to direct Silver within 1e-9 km/h. Fleet distinct
  counts equal **384 vehicles / 32,552 trips**. Gap mismatches: **0**.
- Independent PyArrow/NumPy integration checks **all 32,552 trip distances**,
  eligible interval counts and supported durations. Maximum trip distance
  absolute discrepancy: **1.85e-13 km**.
  It also verifies NULL distance when no interval qualifies.
- Two full fresh successful runs produce **identical SHA-256 bytes for all
  seven Gold files**. The second includes stricter storage-accounting guards;
  aggregate SQL and sensor semantics are identical. Fixture fresh runs are
  also byte-identical. Cache repeat preserves every output hash.
- All 54 Bronze and 54 Silver hashes remain unchanged. No raw data is committed
  or pushed; Parquet, results and scratch remain Git-ignored.

## Runtime and storage

- First successful bounded build: **58.6702 s** end to end.
- Final fresh build with complete storage accounting: **146.6017 s**
  end to end, including immutable source hashing and aggregate validation.
  SQL generation/writes: **136.0644 s**;
  direct-source aggregate validation: **6.5359 s**.
- Verified cached repeat: **2.4554 s**; it does not
  recompute the dataset. Independent validation plus six demos:
  **4.3622 s**.
- Initial global window attempts exceeded 2 GB and 4 GB DuckDB limits.
  They published no Gold. Weekly bounded ordering resolved the memory issue.
  A slow correlated UNNEST query was replaced with projected UNNEST; the
  stopped attempt's disposable spill files were removed within project scratch.
  Timings above are successful runs, not all development/failed-attempt time.
- Final logical project storage (including .venv, archives, all data layers,
  results and remaining scratch): **1,915,877,101 bytes**
  (**1.915877 GB decimal**). This is below the preferred 5 GB and
  mandatory 10 GB limits. It is file-length accounting, not NTFS allocated size.

| Storage category | Bytes |
|---|---:|
| Raw | 176,437,885 |
| Bronze | 546,055,318 |
| Silver | 316,579,302 |
| Quarantine | 916,021 |
| Gold | 2,501,660 |
| Virtual environment | 758,762,453 |
| Temporary | 106,028,274 |

Artifacts: `results/day4/gold_full_run.json`, `gold_previous_run.json`,
`gold_manifest.json`, `reproducibility.json`, `independent_validation.json`,
`final_validation.json`, `day4_pytest.xml`, and six query-result JSON files.

## Limitations and completion

Only observed segments support distance; irregular cadence and ECU update
behavior limit interpretation. Reference dates have no verified timezone.
Fuel missingness is structural and not imputed. Gold summaries are descriptive,
not causal features or a training corpus. Multi-file publication assumes no
concurrent consumers. A future dataset with cross-file trips fails the batching
guard and needs an explicit batching policy change. DuckDB spill's configured
logical limit is not a physical allocated-file-size guarantee; available space
and total project storage are checked before execution.

**No remaining Day 4 blocker. Stop after Day 4.** No model, dashboard or Day 5
implementation was started. No system-wide setting was changed.
