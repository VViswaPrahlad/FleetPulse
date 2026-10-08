# FleetPulse local SQL

- `gold/interval_facts.sql`: temporary within-trip adjacent observations; no imputation.
- `gold/*.sql`: seven descriptive outputs, exact percentiles and explicit NULL semantics.
- `validation/silver_totals.sql`: direct Silver reconciliation, executed by the builder.
- `analytics/*.sql`: six reusable interview/demo queries against Gold Parquet views.

From the project root:

```powershell
.\.venv\Scripts\python.exe -m src.analytics.build_gold
.\.venv\Scripts\python.exe -m src.analytics.query fleet_overview
.\.venv\Scripts\python.exe -m src.analytics.query powertrain_comparison
.\.venv\Scripts\python.exe -m src.analytics.query trip_gap_audit
```

SQL names are allowlisted to checked-in files. Connections are in process;
no server, extension download or persistent duplicate of Silver is needed.
Views are recreated from the project root, so no machine-specific database
paths are committed. The builder uses fixed one-thread execution and PyArrow
Zstandard files. `--force` explicitly regenerates; otherwise matching
input/config/output SHA-256 hashes reuse the existing outputs.

Daily/monthly tables assign each whole trip to its **trip-start dataset-reference
date**: `2017-11-01 + floor(day_number - 1)` days. The author specifies the
reference date but no timezone. These are trip-start cohorts, not event-day
traffic summaries; midnight-crossing trips are not split. Source-week file
dates and source-month partitions are separate provenance concepts.

Distance integrates measured speed between adjacent endpoints with positive
gaps <=2 seconds, never across missing speed or long gaps. It is an observed
segment estimate, not odometer distance or complete trip mileage. Entire-trip
and lifetime aggregates are descriptive and cannot serve as causal forecasting
features at a time inside the trip.
