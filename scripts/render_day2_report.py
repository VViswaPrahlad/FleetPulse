"""Write Day 2 documentation from measured artifacts, never invented metrics."""
import importlib.metadata
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from src.ingestion.ingest_ved import ROOT, RAW, OUTPUT, HEADERS, footprint
from src.ingestion.inspect_ved import NUMERIC


def number(value):
    if value is None:
        return "unavailable"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def main():
    ingestion = json.loads((ROOT / "results/day2_ingestion.json").read_text())
    stats = json.loads((ROOT / "results/day2_statistics.json").read_text())
    repeat = json.loads((ROOT / "results/day2_reproducibility.json").read_text())
    manifest = json.loads((RAW / "manifest.json").read_text())
    tests = ET.parse(ROOT / "results/day2_pytest.xml").getroot().find("testsuite")
    assert ingestion["complete"] and ingestion["source_rows"] == stats["rows"] == repeat["bronze_rows"]
    assert tests is not None and tests.attrib["failures"] == "0" and tests.attrib["errors"] == "0"
    versions = {p: importlib.metadata.version(p) for p in
                ["pyspark", "pyarrow", "pandas", "pytest", "py7zr", "py4j", "numpy"]}
    full_versions = sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())
    peak = max(ingestion["peak_project_bytes_observed"], stats["peak_project_bytes_observed"])
    intervals = stats["intervals"]
    numeric_rows = "\n".join(
        f"| `{original}` | {number(stats[alias+'_available'])} | {number(stats[alias+'_min'])} | "
        f"{number(stats[alias+'_max'])} | {number(stats[alias+'_negative'])} |"
        for alias, original in NUMERIC.items())
    powertrain_rows = "\n".join(
        f"| {r['engine_type'] or 'unmatched'} | {r['vehicles']} | {r['rows']:,} | {r['fuel_rows']:,} | "
        f"{100*r['fuel_rows']/r['rows']:.4f}% | {r['battery_current_rows']:,} |"
        for r in stats["powertrain"])
    months = len(list(OUTPUT.glob("source_month=*")))
    filesizes = [r["output_bytes"] for r in ingestion["files"]]
    (ROOT / "README.md").write_text(f"""# FleetPulse

FleetPulse is a local vehicle telemetry project. The approved primary source
is the [Vehicle Energy Dataset (VED)](https://github.com/gsoh/VED).

**Day 2 is complete:** {stats['rows']:,} actual observations, {stats['vehicles']}
vehicles and {stats['trips']:,} vehicle/trip pairs are ingested into Bronze.
All source rows reconcile. {tests.attrib['tests']} fixture tests pass; a repeat
invocation preserves all 54 output hashes. Full ingestion took
{ingestion['elapsed_seconds']:.2f} seconds. Bronze occupies
{ingestion['output_bytes']:,} bytes. See [the measured Day 2 report](docs/day2_report.md)
for fuel-rate missingness, cadence, duplicates, powertrain differences,
dependency versions, storage and limitations.

## Current architecture

Official checksummed archives → bounded archive staging → explicit-schema
PySpark parsing → PyArrow Parquet writer → `data/bronze/ved/`.
Raw values, literal `NaN`, malformed records and duplicates are retained.
Output contains 54 weekly files in {months} source-month directories.
Numeric conversions are inspection-only; no Silver/Gold layer is implemented.
See [architecture](docs/architecture.md) and [scope](docs/project_scope.md).

## Run locally

Use the existing Python 3.12 `.venv` and JDK 21. The launcher applies Java,
Python-worker and project-local temporary-directory settings only to the
current process. From the FleetPulse PowerShell terminal:

```powershell
.\\scripts\\run_day2.ps1 -Script scripts/spark_smoke.py
.\\scripts\\run_day2.ps1 -Script scripts/complete_day2.py
.\\scripts\\run_day2.ps1 -Script scripts/check_day2_reproducibility.py
```

`complete_day2.py` runs fixture tests, idempotent ingestion, then full-corpus
inspection. Existing verified sources need no new downloads. For a fresh
checkout, create `.venv` with `py -3.12 -m venv .venv`, install
`requirements.txt`, then run `scripts/acquire_ved.py` through the launcher
with authorized network access. It obtains only author-repository VED data,
checks sizes/CRCs/disk/budget, and leaves extraction to bounded ingestion.

## Windows IO and storage

Python {sys.version.split()[0]}, Java {stats['java']}, PySpark {stats['spark']}.
The approved PyArrow writer and explicit-file Spark reader avoid unavailable
Hadoop native Windows IO. Use `read_bronze()` in the ingestion module;
direct `spark.read.parquet(directory)` and Spark's native writer are not
validated on this machine.

Keep the project below **5,000,000,000 bytes**. One archive is staged at a
time and reconciled generated CSVs are removed. The original 176,386,679-byte
archives remain; their CSV expansion totals 3,203,555,729 bytes. Observed
processing peak was {peak:,} bytes. Raw data, Bronze, temporaries and results
are ignored by Git. No source data or individual GPS trace is committed.

## Deferred scope

The initial fuel-use forecasting proposal is documented in
[the ML definition](docs/ml_problem_definition.md). Sparse direct fuel-rate
coverage is now measured; no missing fuel signal is imputed on Day 2.
Silver/Gold transformations, ML, dashboard and cloud work have not started.
Work stops after Day 2; no GitHub push occurred.
""", encoding="utf-8")
    (ROOT / "docs/architecture.md").write_text(f"""# FleetPulse architecture — Day 2

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

Both archives from pinned author commit `{manifest['commit']}` pass CRC tests.
All 54 headers are verified against source field names, including `OAT[DegC]`.
Twenty-two source fields remain strings to preserve original spelling and
literal `NaN`. Additional columns hold raw_line, source_file, source_week,
is_malformed and malformed_reason. Raw records exclude line terminators;
the archives preserve canonical CSV bytes. Malformed observations and
duplicates remain in Bronze. Unexpected schemas and count mismatches fail
explicitly. Numeric casting and the static powertrain join are inspection
views; they produce no Silver tables and perform no imputation.

## Local Windows execution

Python {sys.version.split()[0]}, Java {stats['java']}, Spark {stats['spark']}.
The launcher sets Java/Python-worker settings and all current temporary
locations inside the project. It leaves system-wide settings alone.
The existing approved PyArrow package writes Parquet with Windows APIs.
Spark reads enumerated file paths; Hadoop's native Windows writer and
directory listing remain unavailable. The roundtrip and fixture tests pass
through the provided implementation. No native Hadoop binaries are installed.

## Partitioning, budget and idempotence

{months} source-month partitions contain 54 weekly files. Source month comes
from the week-start filename; it is not an observation-date transformation.
No vehicle-ID partitions or per-trip files are generated. The largest weekly
CSV is 96,677,690 bytes, which bounds each Arrow/Pandas collection.
Source expansion is 3,203,555,729 bytes; only one archive is staged at once.
Generated source CSVs are removed after their file count/schema checks pass;
original archives are retained. Current output is {ingestion['output_bytes']:,}
bytes and observed processing peak is {peak:,} bytes against a 5 GB cap.
Full inspection monitors storage and cancels Spark jobs at 4.5 GB.

Fixed output names, source hashes and output hashes support resumable cache
validation. Fresh files are ordered by raw_line and published via atomic
replacement after validation. Output file-set and full-row reconciliation
detect stale/missing files. There is no append path or silent row dropping.
Tests use small fixtures; a full repeat invocation preserves all 54 hashes.

## Measured artifacts and scope

{stats['rows']:,} source rows equal Bronze rows. Results JSON/XML artifacts
record per-file hashes/counts/runtime, telemetry statistics, repeat checks
and test results. [Day 2 report](day2_report.md) contains measured summaries.
Source and generated data remain Git-ignored. Silver/Gold, ML, dashboards
and cloud services are deferred; Day 2 ends at validated Bronze ingestion.
""", encoding="utf-8")
    text = f"""# FleetPulse Day 2 — completed

Date: 2026-10-08 (Asia/Calcutta). **Day 2 is complete.**

## Environment and verified local execution

Python {sys.version.split()[0]}, Temurin Java {stats['java']}, PySpark {stats['spark']}.
Installed direct/support versions: {', '.join(f'{p} {v}' for p,v in versions.items())}.
`pip check` passed. `requirements.txt` contains only the five Day 2 direct
dependencies; py7zr is required to read the official 7z files. No additional
technology was installed during this continuation.

The original PySpark 4.0.1 pin was replaced with 4.0.3 following its verified
Windows/Python 3.12 worker failure ([Apache SPARK-53759](https://issues.apache.org/jira/browse/SPARK-53759)).
Java, Python-worker, PATH and temporary-directory settings are process-local.
All current task temporary files stay under `data/tmp/`; no system settings
were changed. Local execution uses two workers and a 2 GB Spark driver.

The Spark DataFrame → Arrow → Parquet → Spark smoke test passed, including
count and value equality. Its measured runtime was **17.3907 seconds**.
The pipeline uses PyArrow for Parquet writes and supplies explicit file paths
to Spark readers. This resolves the task's Windows IO blocker using already
approved packages. Direct Hadoop Parquet writes and directory-based Spark
listing still require unavailable Windows Hadoop native components; no
native binaries were downloaded. Use the provided reader/launcher.

## Official sources and archive integrity

[VED author repository](https://github.com/gsoh/VED), commit
`{manifest['commit']}`. Sources are retained in Git-ignored `data/raw/ved/`.
Both dynamic downloads match the verified Content-Length and passed all
member CRC checks before extraction. Static ICE/HEV and PHEV/EV XLSX files
and the Apache-2.0 license are downloaded from that same immutable commit.
The manifest records URLs, retrieval UTC, sizes, hashes and member metadata.

| Source | Compressed bytes | CSV files | Declared/extracted CSV bytes |
| --- | ---: | ---: | ---: |
| Part 1 | 82,723,769 | 22 | 1,463,400,664 |
| Part 2 | 93,662,910 | 32 | 1,740,155,065 |
| Total | 176,386,679 | 54 | 3,203,555,729 |

SHA-256:

```text
Part 1: 44d53754fd39e196171ec09f123604375d0248d5c06a97d6695ef0e22a948c61
Part 2: a235c894e619a9e06b6c28c6e68593e26f4b168265cd2c45a0f3a43e646bc701
```

CRC validation took {manifest['sources'][0]['integrity_seconds']:.4f} and
{manifest['sources'][1]['integrity_seconds']:.4f} seconds respectively.
Available disk space before extraction: **{manifest['disk_free_before_extraction_bytes']:,} bytes**.
Bounded peak estimate: **{manifest['bounded_peak_estimate_bytes']:,} bytes**.
Archives were staged one at a time; only successfully reconciled generated
CSVs were removed. The original archives remain intact.

## Actual telemetry statistics

- Observations: **{stats['rows']:,}**.
- Distinct vehicles: **{stats['vehicles']:,}**.
- Distinct trips (VehId, Trip): **{stats['trips']:,}**.
- CSV headers: all 54 match the inspected 22-column schema. The actual
  temperature header is `OAT[DegC]`, not the expanded name in the README.
- GPS latitude/longitude available together: **{stats['gps_rows']:,}** rows;
  out-of-range coordinates: **{stats['invalid_gps']:,}**.
- Speed min/mean/max (km/h): {number(stats['speed_kmh_min'])} /
  {number(stats['speed_kmh_mean'])} / {number(stats['speed_kmh_max'])}.
  Approximate p01/p50/p95/p99: {stats['speed_quantiles']} km/h.
- Direct `Fuel Rate[L/hr]` available: **{stats['fuel_lph_available']:,}** rows.
  Missing: **{stats['fuel_missing_rows']:,} ({stats['fuel_missing_pct']:.4f}%)**.
  Literal `NaN` tokens: {stats['source_missing_tokens']['Fuel Rate[L/hr]']:,}.
  Missing values remain unchanged; no MAF-based estimate or imputation occurred.
- Exact raw-record duplicate groups/excess rows:
  **{stats['exact_record_duplicates']['groups']:,} / {stats['exact_record_duplicates']['excess_rows']:,}**.
- Vehicle/trip/timestamp duplicate groups/excess rows:
  **{stats['observation_key_duplicates']['groups']:,} / {stats['observation_key_duplicates']['excess_rows']:,}**.
  All duplicates are retained.
- Malformed records: **{stats['malformed_rows']:,}**.
- Invalid/nonintegral/negative timestamps: **{stats['invalid_timestamps']:,}**.
  Invalid DayNum values: **{stats['invalid_daynum']:,}**.
  Invalid vehicle/trip keys: **{stats['range_flags']['invalid_vehicle_trip_keys']:,}**.
- Unrecognized/nonfinite numeric tokens beyond the source missing markers:
  **{sum(stats['non_numeric_tokens'].values()):,}** cells.
- Battery SOC outside 0–100: **{stats['range_flags']['battery_soc_outside_0_100']:,}**;
  temperatures below absolute zero: **{stats['range_flags']['temperature_below_absolute_zero']:,}**.

### Timestamp format and observed cadence

`Timestamp(ms)` is a numeric millisecond offset within a vehicle/trip, not an
ISO datetime. `DayNum` is a fractional day offset; the author defines DayNum 1
as November 1, 2017. Maximum distinct DayNum values per vehicle/trip:
**{stats['trip_daynum_variability']['max_distinct_daynum_per_trip']}**.
No absolute timestamp/timezone conversion is persisted in Bronze.

Within-trip intervals were calculated after ordering by timestamp, including
duplicate timestamps. Count: {intervals['count']:,}; min/mean/max:
{number(intervals['min_ms'])} / {number(intervals['mean_ms'])} /
{number(intervals['max_ms'])} ms. Approximate p01/p50/p95/p99:
{intervals['quantiles_ms']} ms. Zero intervals: {intervals['zero_intervals']:,}.
Most frequent intervals (ms → count):
{', '.join(str(r['interval_ms'])+' → '+str(r['count']) for r in stats['interval_modes'])}.
These are row-level event intervals; repeated sensor values do not prove
that each channel was refreshed at that cadence. Long gaps are preserved.

### Availability, ranges and negative readings

Numeric views exist only for inspection; source values remain strings in Bronze.
Negative longitude, battery current (potential regeneration), outside-air
temperature and fuel trims are legitimate categories, not blanket invalids.
Negative speed, fuel, RPM, MAF, power, SOC and voltage are range flags, retained
as recorded. Approximate quantiles use Spark percentile_approx, accuracy 10,000.

| Actual source column | Finite readings | Minimum | Maximum | Negative readings |
| --- | ---: | ---: | ---: | ---: |
{numeric_rows}

### Differences identified through actual static workbooks

Static vehicle counts: {stats['static_vehicle_counts']}.
The actual dynamic/static files contain **384 vehicles, including 93 HEVs**,
whereas the repository description lists 383 vehicles and 92 HEVs. This report
uses the inspected files. Direct fuel rate is absent from all observed HEV/EV
rows and concentrated in PHEV records; ICE direct coverage is extremely sparse.
The future forecasting proposal therefore requires a separate coverage decision.
Static headers differ: ICE/HEV uses `Vehicle Type`; PHEV/EV uses `EngineType`.
The join is inspected only; it is not a Silver transformation. Duplicate
static vehicle IDs are rejected to avoid row inflation.

| Powertrain | Observed vehicles | Rows | Direct fuel-rate readings | Fuel availability | Battery-current readings |
| --- | ---: | ---: | ---: | ---: | ---: |
{powertrain_rows}

## Bronze implementation and reconciliation

Implementation: `src/ingestion/ingest_ved.py`; output: `data/bronze/ved/`.
The explicit schema uses all 22 actual field names as nullable strings so
original numeric spelling and `NaN` tokens survive. Metadata adds `raw_line`,
`source_file`, `source_week`, `is_malformed`, and `malformed_reason`.
Raw lines exclude their original line terminators; archives remain canonical.
Malformed CSV records retain their raw line and parsed fields with a flag.
Schema changes or a row reconciliation failure stop the file explicitly.

Spark parses and orders one weekly file at a time. The weekly Arrow/Pandas
collection is bounded by source file size (largest: 96,677,690 bytes), never
the full corpus. PyArrow writes deterministic Zstandard Parquet to a pending
file; schema and row count are checked before atomic replacement.
Idempotence uses fixed filenames and validated hashes, never append mode.

Partitioning: **{months} source-month directories**, with **54 weekly files**;
these describe the source week-start month, not a derived observation month.
There is no vehicle-ID partitioning. File size min/mean/max:
{min(filesizes):,} / {sum(filesizes)/len(filesizes):,.0f} / {max(filesizes):,} bytes.

Source count = Bronze count = **{ingestion['bronze_rows']:,}**.
Output footprint: **{ingestion['output_bytes']:,} bytes**.
Measured ingestion wall time: **{ingestion['elapsed_seconds']:.4f} seconds**
({ingestion['elapsed_seconds']/60:.2f} minutes), from startup through final
Spark row-count reconciliation. Part 1 was staged before this timer; Part 2
extraction is included. CRC/download/fixture-test/inspection times are separate.
Full-corpus inspection: **{stats['inspection_seconds']:.4f} seconds**.

## Validation and reproducibility

Pytest: **{tests.attrib['tests']} passed**, **{tests.attrib['failures']} failed**,
**{tests.attrib['errors']} errors**, in {float(tests.attrib['time']):.4f} seconds.
Fixtures cover actual schema, token preservation, malformed short/long/blank
records, count reconciliation, duplicate retention/identification, timestamp
validity, Spark/Arrow readability, byte-identical recomputation and explicit
failure for schema changes/repeated headers.

A full repeat invocation preserved all **{repeat['unchanged_files']}** file
hashes and the **{repeat['bronze_rows']:,}** count. Repeat runtime:
**{repeat['repeat_runtime_seconds']:.4f} seconds**. That repeat used the validated
content-hash cache; fresh byte-identical recomputation is separately tested
with fixtures. A second forced full recomputation was not run.
Measured artifacts: results/day2_ingestion.json, day2_statistics.json,
day2_reproducibility.json and day2_pytest.xml; source provenance: raw manifest.

## Storage, limitations and stopping point

Current project logical file storage: **PROJECT_BYTES bytes**; cap:
**5,000,000,000 bytes**. Observed peak during ingestion/inspection:
**{peak:,} bytes**. Includes .venv, source archives, Bronze, reports and current
task temporaries. Inspection storage is sampled once per second and cancels
Spark jobs at 4.5 GB to preserve headroom. Allocated filesystem space and
instantaneous unsampled peaks are not claimed; external Python/JDK installations
are excluded from the project footprint.

Known limits: Windows native Hadoop writer/directory listing remains unavailable;
the provided Arrow writer and explicit-file Spark reader pass validation.
Source `NaN`, sparse direct fuel-rate coverage, legitimate signed readings,
duplicates and long gaps remain intact. Absolute timestamp semantics/timezone
are not normalized. Source-month partitions need not equal event-month partitions.

No blocking issue remains for this Day 2 pipeline. No ML, dashboard,
Silver/Gold, cloud, system-setting changes or GitHub push was performed.
**Stopped after Day 2.**

### Full installed dependency record

```text
{chr(10).join(p+'=='+v for p,v in full_versions)}
```
"""
    report = ROOT / "docs/day2_report.md"
    for _ in range(3):
        report.write_text(text.replace("PROJECT_BYTES", f"{footprint():,}"), encoding="utf-8")
    print(json.dumps({"report": str(report), "project_bytes": footprint(), "peak_bytes": peak}), flush=True)


if __name__ == "__main__":
    main()
