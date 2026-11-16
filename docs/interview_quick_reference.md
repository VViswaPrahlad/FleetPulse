# FleetPulse — interview quick reference

This is a personal preparation guide, not an additional feature or performance claim. Use your own words, and be prepared to open the linked code.

## Two-minute introduction

FleetPulse takes historical vehicle telemetry and turns it into auditable analytics plus a next-minute speed-forecasting demonstration. I used PySpark with explicit schemas to ingest 22,436,808 observations, retained 22,434,106 in Silver, and quarantined 2,702 with documented reasons. Gold Parquet tables and DuckDB provide bounded queries behind FastAPI and a React/TypeScript dashboard. For prediction, I engineered 31 past-only features from the prior minute and evaluated a HistGradientBoosting regressor on completely held-out vehicles. On 1,919 test windows from 50 vehicles the model achieved 10.887 km/h MAE against 14.056 km/h for a last-speed baseline. It is not uniformly better: 16 vehicles worsen and there are no test EVs. A compact artifact bundle powers a Render-hosted, read-only portfolio demo.

## Engineering questions

**Why Spark instead of only Pandas?** Spark offered typed, explicit-schema transformations and audit-friendly quality rules for a 22.4-million-row pipeline. Bounded PyArrow IO was used to accommodate local Windows constraints. I do not claim distributed-cluster scalability was benchmarked.

**Why Bronze, Silver, quarantine and Gold?** Bronze preserves source/provenance; Silver applies documented cleaning; rejected rows are counted and retained separately; Gold serves query-friendly summaries. The row identity is 22,436,808 = 22,434,106 + 2,702.

**Why DuckDB and FastAPI?** DuckDB queries compact Parquet outputs without a separate database service. FastAPI provides typed, versioned endpoints, bounded pagination and safe errors for the dashboard.

**What did you do in React?** The UI has fleet, driving, quality, model-intelligence and prediction pages; typed API DTOs; loading/empty/error states; filter/pagination interactions; and a quick prediction action. Review `dashboard/src/App.tsx`, `dashboard/src/api.ts` and the page components before the interview. Do not present framework familiarity beyond what you can explain.

**How do you prevent leakage?** Vehicles are assigned to disjoint training/validation/test groups before window generation. Inputs use [t−60s,t] only; targets are future [t,t+60s] mean speed; full observation contexts are kept disjoint and identifiers/future summaries excluded.

**Why gradient boosting rather than an LSTM?** HistGradientBoosting is a strong, CPU-friendly baseline for compact engineered tabular time-window features, handles missing values natively and is simpler to audit. Six prespecified configurations were selected using validation MAE. No claim is made that it beats untested sequence models.

**What does 22.55% improvement mean?** The *pooled offline test MAE* fell from 14.056 to 10.887 km/h on identical held-out examples. It is not a guaranteed per-vehicle benefit. The paired vehicle-macro improvement confidence interval crosses zero.

**Why paired whole-vehicle bootstrap?** Windows from a vehicle are correlated. Resampling whole vehicles preserves that clustering; 2,000 replicates quantify conditional uncertainty. Those intervals do not account for model retraining or new deployment environments.

**Is this live telemetry or a production system?** Neither. The deployed app presents historical data and runs inference on prepared feature vectors. Render serves a compiled React site and an API using a compact validated bundle; the free service may sleep. There is no live ingestion, authentication or production SLA.

**What would you improve?** Broader external validation, better performance for weak speed/vehicle cohorts, end-to-end trusted feature construction from raw streaming telemetry, production observability and completed responsive/accessibility testing.

## Four-minute walkthrough

1. Show the README pipeline and reconciled row counts (40 seconds).
2. Navigate dashboard quality and driving analytics (60 seconds).
3. Explain held-out vehicles, baseline, and the 16/50 regressions (70 seconds).
4. Use Prediction Lab → Run example prediction; show API docs (70 seconds).

For full methodology, use [the existing detailed Q&A](interview_qa.md), [architecture](architecture.md) and [evaluation](day6_report.md). Verify the live result yourself immediately before an interview.
