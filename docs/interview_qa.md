# FleetPulse interview questions and answers

**What problem does FleetPulse address?**
Auditable analytics over genuine vehicle telemetry and prediction of next-minute mean speed from the previous minute. It connects ingestion, quality, SQL analytics, defensible ML evaluation and local full-stack serving.

**Why report 384 vehicles when the source README says 383?**
The 54 inspected CSVs contain 384 distinct IDs and 32,552 vehicle/trip pairs. I document that discrepancy rather than discarding an ID to match prose.

**Why reject fuel forecasting?**
96.0061% of Bronze fuel rate is missing; the intended ICE/HEV population supports only one viable paired window. Held-out-vehicle evaluation is impossible. Speed was explicitly approved instead; no missing fuel or consumption proxy is fabricated.

**Why Spark plus PyArrow?**
Spark provides explicit-schema ingestion/quality expressions across 22.4M rows; bounded weekly PyArrow IO works on Windows without Hadoop DLL dependencies. Compact/window data use Pandas/NumPy where practical. Local success is not evidence of distributed-cluster scalability.

**How is silent loss prevented?**
Raw tokens/provenance are preserved in Bronze; every row reaches Silver or quarantine: 22,436,808 = 22,434,106 + 2,702. Invalid/missing sensors get flags and unavailable values, not fabricated replacements. Independent counts and hashes reconcile.

**Are distance and dates complete ground truth?**
Distance integrates only eligible observed speed intervals with gaps ≤2 seconds, so it is partial segment distance, not an odometer. Elapsed milliseconds are trip-relative; Gold groups whole trips by author reference start date without inventing a timezone.

**Define the target and leakage protection.**
At observed t, features use `[t−60,t]`; labels are trapezoidal mean speed over `[t,t+60]`, km/h. Exact endpoints and gaps ≤2s are required. Vehicle splits are frozen before windows, and complete contexts share no observations within trips. IDs/GPS/absolute dates/future coverage/whole-trip aggregates are excluded. Selection/importance use validation, never test.

**Why 34,348 candidates but 11,549 examples?**
Candidates overlap. Deterministic earliest-first selection makes full 120-second contexts strictly disjoint. Day 3's 11,671 touching contexts differ by 122 because Day 5 forbids endpoint reuse between examples. All 318 usable vehicles remain.

**Which model and parameters won?**
CPU HistGradientBoosting with native NaN: learning rate .05, 200 iterations, 15 maximum leaf nodes, minimum leaf size 20, L2 1, early stopping off, seed 20261009. Six fixed configurations were selected by validation pooled MAE. No scaling/imputation, validation refit or random-row early-stopping split.

**Did ML beat persistence?**
On identical test examples, MAE 10.886851 versus 14.056006 km/h and RMSE 14.090555 versus 18.802985: 22.55%/25.06% pooled improvements. But 16/50 vehicles worsen, low/high-speed cohorts worsen and paired macro MAE improvement's interval crosses zero. Uniform advantage is not established.

**How is uncertainty estimated?**
2,000 fixed-seed paired whole-vehicle bootstrap replicates retain all windows of each sampled vehicle. Test MAE 95% interval is 10.188–11.905 km/h; RMSE 13.194–15.304. These are conditional aggregate intervals, not prediction intervals or retraining/selection uncertainty. Only 50 independent test vehicles are represented.

**Can you claim EV performance?**
No EV appears in test, and just one in validation. Structural missingness and small powertrain cohorts constrain conclusions; no unseen-EV generalization claim is supported.

**What are the 31 features?**
Ten past speed statistics/trends, two stop fractions, five acceleration statistics, sample count/max gap, six optional sensor means and six observed fractions. All are historical. Native NaN preserves unavailable means. Validation permutation importance is descriptive, not causal with correlated features.

**Can the API predict from raw GPS?**
No. It requires the exact prepared historical feature schema with units/history and coherent sampling/availability. Model hash, library compatibility and feature order are checked. The API cannot independently prove caller provenance and never manufactures missing telemetry.

**Does startup read millions of rows or train?**
No. Existing compact Gold and bounded reports/model artifacts are reused. Queries cap at 100 rows, offsets at 100,000 and bodies at 64 KiB; bounded caches prevent repeated work. ETL/model fitting do not run at startup.

**Is it production ready?**
Modular services/schemas, safe errors, bounded IO, testing and reproducibility demonstrate engineering discipline. It remains a loopback portfolio demo without authentication/TLS/public deployment/monitoring/SLAs. CORS is not authentication. Dev modules contain source paths; production assets/API are scanned separately.

**What happens when artifacts are missing?**
Health remains live; readiness/resource endpoints return safe 503 and the frontend displays honest errors. Empty fixture roots test this without moving real artifacts. No fallback metrics or predictions are invented.

**Can a recruiter reproduce it from Git alone?**
Source, tests, SQL, contracts, lockfile/pins and lightweight measured figures are public. Archives/datasets/model/results are excluded. A fresh user installs dependencies and deliberately reconstructs artifacts from official pinned VED sources. A separate fresh-machine reconstruction was not performed during Day 10.

**What remains unverified, and what would come next?**
Automated Python/frontend/API/compiled-DOM checks pass, but actual desktop/mobile rendering is unverified because no browser surface is available. Follow the manual sign-off. Future proposals include external-region validation, low/high-speed improvement, causal raw-telemetry preparation, physical-device/accessibility checks and deployment controls; they are not implemented features.
