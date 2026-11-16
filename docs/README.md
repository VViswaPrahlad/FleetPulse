# FleetPulse documentation guide

**Start here for the current project.** FleetPulse is a historical telemetry analytics and next-minute speed-forecasting portfolio project. The [live dashboard](https://fleetpulse-dashboard.onrender.com) and [API documentation](https://fleetpulse-api-got2.onrender.com/docs) are hosted on Render. This is a read-only portfolio demonstration, not an always-on production service.

## Recommended reading order

1. [Project overview and measured results](../README.md) — problem, metrics, architecture, demo and limits.
2. [Architecture](architecture.md) — data contracts, Bronze/Silver/quarantine/Gold flow, held-out ML split, and serving boundaries.
3. [Demo guide](demo_guide.md) — recruiter walkthrough, verified historic browser observations, current manual acceptance checklist, and reconstruction.
4. [ML evaluation](day6_report.md) — experiment methodology, baseline, clustered uncertainty and failure cohorts (**dated technical evidence**).
5. [API contract](api_contract.md) — endpoints, errors, schemas and prepared-feature inference.
6. [Technical Q&A](interview_qa.md) — project design choices and limitations.
7. [Deployment guide](deployment_guide.md) — current hosting pointers plus dated rebuild and deployment checkpoints.

## Historical engineering checkpoints

These files are retained as an audit trail, **not as a description of the current deployed state**:

- [Day 3 data-quality report](day3_report.md): cleaning rules and original reconciliation.
- [Day 6 model report](day6_report.md): frozen offline performance and confidence intervals.
- [Day 10 release report](day10_report.md): local automated tests and visual-verification limits **at that earlier checkpoint**.
- [Original pre-deployment review](deployment_review.md): pre-Render preparation; the stated blockers were historical and should not be read as today's deployment status.

**Reproducibility:** This repository intentionally excludes raw VED archives, generated Parquet tables, trained binaries and some evaluation artifacts. You can inspect source, run fixture-based tests, and build the frontend after installing dependencies. Recreating populated analytics and predictions locally requires the separately documented dataset/model reconstruction steps. The hosted instance serves a prebuilt validated bundle; no training or ETL occurs on request.

**Verification:** The 2026-10-29 browser review verified representative routes and the 36.62 km/h example result, but did not establish perpetual uptime or full desktop/mobile/keyboard/chart/error-state acceptance. Recheck the live apps when demonstrating them.
