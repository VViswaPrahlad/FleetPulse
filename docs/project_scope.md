# FleetPulse project scope

**Research and verification date:** 2026-10-08

## Problem statement

FleetPulse is a local automotive telemetry analytics and ML project using public naturalistic vehicle data. It will build a reproducible ingestion and quality pipeline, preserve raw-to-curated lineage in Parquet, support SQL analytics, and evaluate a narrowly defined prediction task without overstating scale or sensor truth.

## Dataset and ML decision

**Selected dataset:** VED (Vehicle Energy Dataset), approved and ingested. It has real vehicle time series, GPS coordinates, vehicle/trip IDs, speed and OBD-II signals. The pinned author archives total 176,386,679 bytes. Days 2 and 3 are validated; Day 4 adds descriptive Gold and DuckDB.

**Approved primary ML task:** predict next-60-second time-weighted mean speed (km/h) from the preceding 60 seconds of measured telemetry. Features must be available at prediction time, with evaluation held out by vehicle. The original ICE/HEV fuel task was rejected after measured feasibility supported only one usable vehicle/window. See [ML problem definition](ml_problem_definition.md).

VED's signal is ECU/OBD reported, coverage may vary by vehicle, and the corpus is geographically and temporally limited. This task is a short-horizon forecast on this dataset, not a general fleet guarantee. Do not convert it into anomaly classification without independently defensible labels.

## In scope

- Public VED data only, attribution, license notices and source provenance.
- Windows-local Python 3.12 and PySpark local ETL; Bronze/Silver/Gold Parquet.
- DuckDB SQL analytics and explicit data-quality reporting.
- Scikit-learn persistence baseline and one tree-boosting regression model.
- Vehicle-grouped validation, MAE/RMSE, and leakage controls.
- Approved local FastAPI backend and a future React + TypeScript frontend; the original Streamlit plan is superseded.
- Pytest tests for pipeline contracts and target/split correctness.
- 16 GB RAM-aware processing; maximum 10 GB storage, preferably below 5 GB.

## Out of scope

- EPA vehicle ratings as a substitute for time-series telemetry.
- Proprietary/company/owner data, re-identification, or claims about named drivers.
- Fabricated/synthetic supervised labels, fabricated results, or unsupported production-scale claims.
- Publishing raw VED archives, individual trip traces or sensitive locations in the project repository/dashboard.
- Kafka, Airflow, Kubernetes, cloud services, added infrastructure or expanding the current technology stack.
- No ML training, dashboard development or Day 5 work during Day 4. External downloads/installations and system changes require the configured approval mechanism.

## Evaluation strategy

1. Audit speed coverage by vehicle/powertrain; report eligible/excluded vehicles, trips and windows with reasons.
2. Validate timestamp cadence, trip keys, duplicate handling, gaps, zero/negative values and integration boundaries before generating targets.
3. Split by vehicle ID before creating windows. Do not allow overlapping windows, trips, or vehicle records to cross train/validation/test.
4. In a future authorized ML phase, compare persistence of past mean speed with a proposed `HistGradientBoostingRegressor`.
5. Report MAE and RMSE in km/h, eligible counts, coverage, held-out-vehicle splits and powertrain-specific metrics. No fabricated or pre-claimed performance.
6. Keep future speed observations exclusively in the target; features must use only information available by prediction time.

## Original Day 1 plan (historical; actual checkpoints supersede it)

| Day | Deliverable |
|---|---|
| 1 | Dataset research, decision documents and scaffold. Complete. |
| 2 | After approval: download within the size restriction, verify archives/hash, inspect a small sample, exact schema/cadence/target coverage, storage projection and license attribution. No full run until the 5 GB budget is checked. |
| 3 | Implement ingestion and provenance manifest; add schema and input-contract tests. |
| 4 | Implement PySpark Bronze/Silver transformations, checks and explicit reject reporting. |
| 5 | Generate Gold trip/window tables and DuckDB SQL summaries; verify data grain and file sizes. |
| 6 | Implement target-window logic, grouped-by-vehicle split, persistence baseline, and scikit-learn evaluation. |
| 7 | Error analysis, coverage/limitations reporting, repeatability checks; optional model tuning only if justified. |
| 8 | Build a modest Streamlit/Plotly view over verified aggregates and evaluation outputs. |
| 9 | Run tests, document clean setup/license, review storage and publishability. No GitHub push unless separately approved. |

## Current checkpoint

Validated Days 1–6 are complete. The user approved replacing the earlier Streamlit plan with React + TypeScript / FastAPI, and authorized Day 7 backend-only development plus an audited commit/push. Reuse existing Gold/model/evaluation artifacts without ETL or retraining. Stop after Day 7; React and Day 8 work remain unstarted. Historical reports retain the decisions applicable at their checkpoints.

## Sources

- [VED author repository](https://github.com/gsoh/VED)
- [VED paper](https://arxiv.org/abs/1905.02081)
- [VED dataset comparison and verification notes](dataset_comparison.md)
- [Dataset selection decision](dataset_selection_decision.md)
- [ML problem definition](ml_problem_definition.md)
