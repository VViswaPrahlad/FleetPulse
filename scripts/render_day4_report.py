"""Generate measured Day 4 report from successful local artifacts."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import duckdb
import pyarrow as pa
import pandas as pd
import pytest
import pyarrow.parquet as pq

from src.analytics.build_gold import ROOT,RESULTS,OUTPUT,TABLES,sha256,footprint


def render():
    run=json.loads((RESULTS/'gold_full_run.json').read_text())
    repeat=json.loads((RESULTS/'reproducibility.json').read_text())
    independent=json.loads((RESULTS/'independent_validation.json').read_text())
    previous=json.loads((RESULTS/'gold_previous_run.json').read_text())
    hashes={n:sha256(OUTPUT/f'{n}.parquet') for n in TABLES}
    if hashes!={n:v['sha256'] for n,v in run['tables'].items()}:
        raise RuntimeError('Gold output differs from full-run manifest')
    fresh_same=hashes=={n:v['sha256'] for n,v in previous['tables'].items()}
    if not fresh_same:
        raise RuntimeError('Full fresh-run byte reproducibility failed')
    test=ET.parse(RESULTS/'day4_pytest.xml').getroot().find('testsuite')
    overview=pq.read_table(OUTPUT/'fleet_overview.parquet').to_pylist()[0]
    trips=pq.read_table(OUTPUT/'trip_analytics.parquet')
    dates=pq.read_table(OUTPUT/'daily_fleet.parquet')['trip_start_reference_day'].to_pylist()
    unsupported=sum(x is None for x in trips['observed_distance_km'].to_pylist())
    outputs='\n'.join(f"| `{n}` | {m['rows']:,} | {m['bytes']:,} |" for n,m in run['tables'].items())
    queries='\n'.join(f"| `{n}.sql` | {m['rows']:,} | {m['runtime_seconds']:.4f} |" for n,m in independent['sql_queries'].items())
    flags=pq.read_table(OUTPUT/'quality_metrics.parquet').to_pylist()
    quality='\n'.join(f"| `{x['quality_flag']}` | {x['observation_count']:,} | {100*x['observation_fraction']:.6f}% |" for x in flags)
    cohorts=pq.read_table(OUTPUT/'powertrain_fleet.parquet').to_pylist()
    powertrains='\n'.join(f"| {x['engine_type']} | {x['vehicle_count']:,} | {x['trip_count']:,} | {x['observation_count']:,} | {x['observed_distance_km']:,.3f} |" for x in cohorts)
    storage={name:sum(p.stat().st_size for p in (ROOT/path).rglob('*') if p.is_file()) for name,path in {
        'Raw':'data/raw/ved','Bronze':'data/bronze/ved','Silver':'data/silver/ved',
        'Quarantine':'data/quarantine/ved','Gold':'data/gold/ved','Virtual environment':'.venv','Temporary':'data/tmp'}.items()}
    # Complete footprint accounting raises on inaccessible directories; run under
    # configured approval when the sandbox restricts its own pytest folders.
    measured=footprint()
    final={'project_bytes':measured,'categories_bytes':storage,
        'full_fresh_runs_identical':fresh_same,'gold_sha256':hashes,
        'tests':dict(test.attrib),'bronze_silver_unchanged':run['bronze_silver_unchanged']}
    (RESULTS/'final_validation.json').write_text(json.dumps(final,indent=2)+'\n',encoding='utf-8')
    storage_rows='\n'.join(f'| {n} | {size:,} |' for n,size in storage.items())
    text=f'''# FleetPulse Day 4 — Gold analytics and DuckDB SQL

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

DuckDB **{duckdb.__version__}** is the only new dependency, installed through
the configured approval mechanism and pinned in requirements.txt. Existing
Python 3.12.10, PyArrow {pa.__version__}, Pandas {pd.__version__}, Pytest {pytest.__version__},
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
.\\.venv\\Scripts\\python.exe -m src.analytics.build_gold
.\\.venv\\Scripts\\python.exe -m src.analytics.query fleet_overview
.\\.venv\\Scripts\\python.exe -m src.analytics.query trip_gap_audit
.\\.venv\\Scripts\\python.exe -m pytest tests/test_day4_gold.py -q --basetemp=data/tmp/pytest-day4
```

The builder verifies config/SQL/input/output hashes and reuses valid outputs.
`--force` explicitly regenerates. `scripts/complete_day4.py` builds and checks
the cache repeat; `scripts/validate_day4_actual.py` independently validates
interval integration and runs all six demo queries. Run these scripts with
project-root PYTHONPATH, or use the existing process-only launcher.

## Gold outputs

Location: `data/gold/ved/`, one file per table; **{run['gold_bytes']:,} bytes total**.
No vehicle/trip partitions or thousands of small files are created.

| Table | Rows | Parquet bytes |
|---|---:|---:|
{outputs}

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

- Speed present: **{overview['speed_observation_count']:,}** rows; missing:
  **{overview['missing_speed_count']:,}** ({100*overview['missing_speed_count']/overview['observation_count']:.6f}%).
- Fuel rate present: **{overview['fuel_rate_observation_count']:,}** rows; missing:
  **{overview['missing_fuel_rate_count']:,}** ({100*overview['missing_fuel_rate_count']/overview['observation_count']:.6f}% of Silver).
- Sample mean speed: **{overview['speed_sample_mean_kmh']:.6f} km/h**;
  eligible-interval time-weighted mean: **{overview['speed_time_weighted_mean_kmh']:.6f} km/h**.
- Eligible intervals: **{overview['eligible_speed_interval_count']:,}**;
  supported duration: **{overview['observed_speed_interval_s']:,.6f} seconds**;
  partial measured-segment distance: **{overview['observed_distance_km']:,.6f} km**.
- Trips without any eligible speed interval: **{unsupported:,}**; distance is NULL.
- Gaps >2s: **{overview['gap_gt_2s_count']:,}**; gaps >10s:
  **{overview['gap_gt_10s_count']:,}**; max gap:
  **{overview['max_sampling_gap_s']:,.3f} seconds**; duplicate timestamps:
  **{overview['duplicate_timestamp_count']:,}**.
- Trip-start date range: **{min(dates)} to {max(dates)}**, with {len(dates)} observed dates.

| Powertrain | Vehicles | Trips | Observations | Partial distance km |
|---|---:|---:|---:|---:|
{powertrains}

Powertrain counts derive from existing author static-workbook mappings;
93 HEVs are observed, rather than assuming the README's 92. Direct fuel
missingness remains distinct from electric consumption; no proxy is substituted.

| Quality flag | Occurrences | Fraction of Silver observations |
|---|---:|---:|
{quality}

**{overview['flagged_observation_count']:,} rows** carry one or more flags;
**{overview['quality_flag_occurrence_count']:,} flag occurrences** overlap and
must not be interpreted as excluded rows. All are retained in Gold counts.

## SQL demonstrations

Reviewable build SQL lives in `sql/gold/`, direct-source validation in
`sql/validation/`, and named reusable queries in `sql/analytics/`.
The query CLI recreates views from project-local Parquet, so no absolute-path
database file or duplicate sensor table is committed.

| SQL demonstration | Actual result rows | Measured seconds |
|---|---:|---:|
{queries}

Query timings are single local executions, not performance benchmarks.
Vehicle/trip audit examples limit output to 20 rows.

## Validation and reproducibility

- **{test.attrib['tests']} tests passed**, {test.attrib['failures']} failed,
  {test.attrib['errors']} errors; Pytest runtime **{float(test.attrib['time']):.3f} seconds**.
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
  absolute discrepancy: **{independent['max_trip_distance_absolute_error_km']:.3g} km**.
  It also verifies NULL distance when no interval qualifies.
- Two full fresh successful runs produce **identical SHA-256 bytes for all
  seven Gold files**. The second includes stricter storage-accounting guards;
  aggregate SQL and sensor semantics are identical. Fixture fresh runs are
  also byte-identical. Cache repeat preserves every output hash.
- All 54 Bronze and 54 Silver hashes remain unchanged. No raw data is committed
  or pushed; Parquet, results and scratch remain Git-ignored.

## Runtime and storage

- First successful bounded build: **{previous['runtime_seconds']:.4f} s** end to end.
- Final fresh build with complete storage accounting: **{run['runtime_seconds']:.4f} s**
  end to end, including immutable source hashing and aggregate validation.
  SQL generation/writes: **{run['compute_seconds']:.4f} s**;
  direct-source aggregate validation: **{run['validation_seconds']:.4f} s**.
- Verified cached repeat: **{repeat['runtime_seconds']:.4f} s**; it does not
  recompute the dataset. Independent validation plus six demos:
  **{independent['runtime_seconds']:.4f} s**.
- Initial global window attempts exceeded 2 GB and 4 GB DuckDB limits.
  They published no Gold. Weekly bounded ordering resolved the memory issue.
  A slow correlated UNNEST query was replaced with projected UNNEST; the
  stopped attempt's disposable spill files were removed within project scratch.
  Timings above are successful runs, not all development/failed-attempt time.
- Final logical project storage (including .venv, archives, all data layers,
  results and remaining scratch): **{measured:,} bytes**
  (**{measured/1e9:.6f} GB decimal**). This is below the preferred 5 GB and
  mandatory 10 GB limits. It is file-length accounting, not NTFS allocated size.

| Storage category | Bytes |
|---|---:|
{storage_rows}

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
'''
    report=ROOT/'docs/day4_report.md'
    report.write_text(text,encoding='utf-8')
    # Account for this report and the final JSON itself; same-length replacements converge.
    for _ in range(4):
        total=footprint()
        text=text.replace(f'{measured:,} bytes',f'{total:,} bytes').replace(
            f'{measured/1e9:.6f} GB decimal',f'{total/1e9:.6f} GB decimal')
        measured=total
        final['project_bytes']=total
        (RESULTS/'final_validation.json').write_text(json.dumps(final,indent=2)+'\n',encoding='utf-8')
        report.write_text(text,encoding='utf-8')
    print(json.dumps(final,indent=2))


if __name__=='__main__':
    render()
