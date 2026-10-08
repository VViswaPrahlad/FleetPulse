# FleetPulse Day 2 — completed

Date: 2026-10-08 (Asia/Calcutta). **Day 2 is complete.**

## Environment and verified local execution

Python 3.12.10, Temurin Java 21.0.12.1, PySpark 4.0.3.
Installed direct/support versions: pyspark 4.0.3, pyarrow 20.0.0, pandas 2.2.3, pytest 8.3.5, py7zr 1.0.0, py4j 0.10.9.9, numpy 2.5.3.
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
`6baa4963782d515a67d32a5490bd5d11f5d9bf0d`. Sources are retained in Git-ignored `data/raw/ved/`.
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

CRC validation took 14.5945 and
17.2668 seconds respectively.
Available disk space before extraction: **41,274,220,544 bytes**.
Bounded peak estimate: **4,139,431,026 bytes**.
Archives were staged one at a time; only successfully reconciled generated
CSVs were removed. The original archives remain intact.

## Actual telemetry statistics

- Observations: **22,436,808**.
- Distinct vehicles: **384**.
- Distinct trips (VehId, Trip): **32,552**.
- CSV headers: all 54 match the inspected 22-column schema. The actual
  temperature header is `OAT[DegC]`, not the expanded name in the README.
- GPS latitude/longitude available together: **22,436,808** rows;
  out-of-range coordinates: **0**.
- Speed min/mean/max (km/h): 0 /
  40.3992 / 173.
  Approximate p01/p50/p95/p99: [0.0, 43.0, 82.0, 114.609375] km/h.
- Direct `Fuel Rate[L/hr]` available: **896,097** rows.
  Missing: **21,540,711 (96.0061%)**.
  Literal `NaN` tokens: 21,540,711.
  Missing values remain unchanged; no MAF-based estimate or imputation occurred.
- Exact raw-record duplicate groups/excess rows:
  **0 / 0**.
- Vehicle/trip/timestamp duplicate groups/excess rows:
  **0 / 0**.
  All duplicates are retained.
- Malformed records: **0**.
- Invalid/nonintegral/negative timestamps: **2,702**.
  Invalid DayNum values: **0**.
  Invalid vehicle/trip keys: **0**.
- Unrecognized/nonfinite numeric tokens beyond the source missing markers:
  **0** cells.
- Battery SOC outside 0–100: **358**;
  temperatures below absolute zero: **0**.

### Timestamp format and observed cadence

`Timestamp(ms)` is a numeric millisecond offset within a vehicle/trip, not an
ISO datetime. `DayNum` is a fractional day offset; the author defines DayNum 1
as November 1, 2017. Maximum distinct DayNum values per vehicle/trip:
**1**.
No absolute timestamp/timezone conversion is persisted in Bronze.

Within-trip intervals were calculated after ordering by timestamp, including
duplicate timestamps. Count: 22,404,256; min/mean/max:
100 / 779.3368 /
7,444,700 ms. Approximate p01/p50/p95/p99:
[100.0, 600.0, 2000.0, 2700.0] ms. Zero intervals: 0.
Most frequent intervals (ms → count):
100.0 → 3177517, 200.0 → 2274899, 1000.0 → 2204129, 600.0 → 1652269, 300.0 → 1635064, 500.0 → 1544917, 800.0 → 1530513, 1100.0 → 1442189, 400.0 → 1382121, 700.0 → 1142286.
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
| `DayNum` | 22,436,808 | 1.0029 | 375.5012 | 0 |
| `VehId` | 22,436,808 | 2 | 630 | 0 |
| `Trip` | 22,436,808 | 2 | 11,580 | 0 |
| `Timestamp(ms)` | 22,436,808 | -1,658,400 | 10,120,900 | 2,702 |
| `Latitude[deg]` | 22,436,808 | 42.2203 | 42.3258 | 0 |
| `Longitude[deg]` | 22,436,808 | -83.8043 | -83.674 | 22,436,808 |
| `Vehicle Speed[km/h]` | 22,435,412 | 0 | 173 | 0 |
| `Fuel Rate[L/hr]` | 896,097 | 0 | 83.6 | 0 |
| `Engine RPM[RPM]` | 21,954,503 | 0 | 6,605 | 0 |
| `HV Battery Current[A]` | 3,728,652 | -411.3 | 190.2 | 2,389,179 |
| `HV Battery SOC[%]` | 3,728,652 | 0 | 100 | 0 |
| `HV Battery Voltage[V]` | 3,728,652 | 0 | 397.875 | 0 |
| `MAF[g/sec]` | 18,258,138 | 0 | 259.31 | 0 |
| `Absolute Load[%]` | 16,471,596 | 0 | 22,463.5293 | 0 |
| `OAT[DegC]` | 13,068,291 | -40 | 60 | 1,526,688 |
| `Air Conditioning Power[kW]` | 894,275 | 0 | 6.36 | 0 |
| `Air Conditioning Power[Watts]` | 2,834,377 | 0 | 3,840 | 0 |
| `Heater Power[Watts]` | 878,358 | 0 | 6,500 | 0 |
| `Short Term Fuel Trim Bank 1[%]` | 17,682,728 | -100 | 89.8438 | 6,138,325 |
| `Short Term Fuel Trim Bank 2[%]` | 6,791,736 | -93.75 | 53.9062 | 3,042,182 |
| `Long Term Fuel Trim Bank 1[%]` | 15,173,315 | -32.8125 | 57.8125 | 5,674,375 |
| `Long Term Fuel Trim Bank 2[%]` | 4,310,470 | -92.9688 | 27.3438 | 1,721,542 |

### Differences identified through actual static workbooks

Static vehicle counts: {'EV': 3, 'HEV': 93, 'ICE': 264, 'PHEV': 24}.
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
| EV | 3 | 476,308 | 0 | 0.0000% | 476,308 |
| HEV | 93 | 5,587,565 | 0 | 0.0000% | 9,946 |
| ICE | 264 | 13,129,563 | 1,822 | 0.0139% | 0 |
| PHEV | 24 | 3,243,372 | 894,275 | 27.5724% | 3,242,398 |

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

Partitioning: **13 source-month directories**, with **54 weekly files**;
these describe the source week-start month, not a derived observation month.
There is no vehicle-ID partitioning. File size min/mean/max:
2,805,034 / 10,112,136 / 16,586,109 bytes.

Source count = Bronze count = **22,436,808**.
Output footprint: **546,055,318 bytes**.
Measured ingestion wall time: **525.2299 seconds**
(8.75 minutes), from startup through final
Spark row-count reconciliation. Part 1 was staged before this timer; Part 2
extraction is included. CRC/download/fixture-test/inspection times are separate.
Full-corpus inspection: **576.2758 seconds**.

## Validation and reproducibility

Pytest: **11 passed**, **0 failed**,
**0 errors**, in 30.8440 seconds.
Fixtures cover actual schema, token preservation, malformed short/long/blank
records, count reconciliation, duplicate retention/identification, timestamp
validity, Spark/Arrow readability, byte-identical recomputation and explicit
failure for schema changes/repeated headers.

A full repeat invocation preserved all **54** file
hashes and the **22,436,808** count. Repeat runtime:
**20.6744 seconds**. That repeat used the validated
content-hash cache; fresh byte-identical recomputation is separately tested
with fixtures. A second forced full recomputation was not run.
Measured artifacts: results/day2_ingestion.json, day2_statistics.json,
day2_reproducibility.json and day2_pytest.xml; source provenance: raw manifest.

## Storage, limitations and stopping point

Current project logical file storage: **1,450,126,664 bytes**; cap:
**5,000,000,000 bytes**. Observed peak during ingestion/inspection:
**3,018,505,445 bytes**. Includes .venv, source archives, Bronze, reports and current
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
backports.zstd==1.7.0
brotli==1.2.0
colorama==0.4.6
inflate64==1.0.4
iniconfig==2.3.1
multivolumefile==0.2.3
numpy==2.5.3
packaging==26.3
pandas==2.2.3
pip==25.0.1
pluggy==1.6.0
psutil==7.2.2
py4j==0.10.9.9
py7zr==1.0.0
pyarrow==20.0.0
pybcj==1.0.8
pycryptodomex==3.24.0
pyppmd==1.2.0
pyspark==4.0.3
pytest==8.3.5
python-dateutil==2.9.0.post0
pytz==2026.5
pyzstd==0.19.1
six==1.17.0
texttable==1.7.0
typing_extensions==4.16.0
tzdata==2026.5
```
