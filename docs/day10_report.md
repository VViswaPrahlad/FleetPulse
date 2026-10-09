# FleetPulse Day 10 — portfolio release verification

Measured locally on **2026-10-09**, Windows / Asia–Calcutta. Documentation and automated release checks are prepared. **Final visual release sign-off is NOT complete:** no automated browser is available. No production ETL, model retraining, new major feature, paid service or cloud deployment occurred.

## Browser verification: unresolved

The existing FleetPulse backend/frontend were already listening on **127.0.0.1:8000 / 5173**; the health response identified FleetPulse. Their processes were not stopped. Computer-use inventory returned `apps: []`, `browsers: []`. Opening `http://127.0.0.1:5173` through both **iab** and **Chrome** returned “Browser is not available.” No rendered dashboard was observed.

All five pages pass compiled DOM integration and component/CSS checks, but desktop/mobile layout, actual chart rendering, touch/focus interactions and browser pixels remain unverified. No visual defect is claimed fixed without observation. The [manual checklist](demo_guide.md#manual-browser-sign-off) specifies desktop 1440×900, mobile 360×800 and tablet 768×1024, every page and loading/empty/invalid/backend-down states. It must be completed before claiming final visual release readiness.

Separate **owned** loopback servers on **8010 / 5180** were launched using the real PowerShell scripts, to measure startup without interrupting the existing demo. Backend health was ready after **1.252089 s**, frontend HTML after **2.732064 s**, measured from concurrent launcher spawn. Readiness and proxied fleet metrics passed. Those owned servers were stopped after the browser attempt. No system settings or unrelated processes were changed.

## Showcase and demonstration documentation

- README rewritten around the actual completed stack, genuine counts, measured model/baseline results, reproducibility, source-only versus artifact requirements, and honest limitations.
- [Architecture](architecture.md) rewritten with Mermaid: VED → Spark/PyArrow → Bronze → Silver/quarantine → Gold → DuckDB → FastAPI → React, plus frozen ML splits, selection/evaluation and inference.
- [Demo guide](demo_guide.md): approximately four-minute presentation, engineering decisions, fresh Windows setup, ordered optional artifact reconstruction and exact manual browser sign-off.
- [Interview Q&A](interview_qa.md): measurement semantics, target rejection, leakage, missingness, baselines, clustered uncertainty, API limits and remaining gaps.

Fresh-machine reconstruction is documented against existing scripts, **not executed or claimed verified on another machine**. Source-only builds/health/docs/fixture tests work with installed dependencies; populated analytics, readiness and prediction require ignored local artifacts. Four frontend saved-contract tests skip without local Day 8 contract snapshots. No raw dataset/model bundle is published.

## Automated verification

| Check | Actual result |
|---|---|
| Complete Python suite | **144 passed**, zero skipped; **178.97 s** |
| Frontend suite | **32 passed**, four files; **12.57 s** |
| Strict TypeScript | Passed |
| Production build | Passed, **2.45 s** Vite build phase |
| Real-artifact validation | Passed, **14.927521 s** |
| README Windows pytest command | Exact launcher syntax collected all 144 tests without rerunning them |
| Browser desktop/mobile | **Unverified: browser unavailable** |

Python emitted 74 dependency deprecation warnings: one Starlette/AnyIO alias and 73 Joblib/NumPy array-shape warnings in synthetic-model tests. No dependency change was made to suppress warnings. Timing varies with concurrent local workload; it is not an SLA. Test fixtures fit tiny synthetic models/process tiny Spark data, not the production model/dataset.

The existing real-data harness was reused with configurable loopback ports and redirected exclusively to `results/day10/`. It validates **15 read contracts**, **5,332 projected Gold field values**, pipeline missingness/counts, saved model/baseline/cohort results and exact inference. The documented anonymous prepared vector predicts **36.61748855856695 km/h**, identical to direct saved-model inference. Healthy compiled DOM navigation covers all five pages, 31 prediction fields, actual inference/reset and 13 API requests. Backend-unavailable flows cover all five pages against actual stopped owned backend/proxy HTTP 500. These are explicitly **DOM tests, not browser visual tests**.

Security/reliability checks pass: limits/offsets/unexpected queries/raw GPS/invalid gap/malformed JSON return safe 422; oversized body returns 413; missing-artifact fixtures return safe 503 while health stays live; CORS accepts only documented local origins without credentials. Twenty warm overview requests add zero DuckDB queries. API responses and production assets contain no project paths/tracebacks or recognized credential patterns. Development JSX still contains source filenames, so dev servers remain loopback-only.

## Actual data and ML results retained

Bronze **22,436,808** = Silver **22,434,106** + quarantine **2,702**. **384 vehicles / 32,552 trips**. Gold row counts remain **1 / 384 / 32,552 / 375 / 13 / 4 / 5** for fleet, vehicles, trips, daily, monthly, powertrains and quality.

The unchanged ML corpus has **11,549 examples / 318 vehicles**, 31 features. Train/validation/test have **7,509/2,121/1,919 rows** and **223/45/50 represented vehicles**. Frozen contexts do not share observations within trips; vehicles never cross splits. Inputs are past-only; no Gold whole-trip statistics or IDs enter inference.

Unchanged HGB test MAE/RMSE: **10.886851 / 14.090555 km/h** versus last-speed **14.056006 / 18.802985**, pooled improvements **22.55% / 25.06%**. Native missingness, validation-only selection and training-only final fit remain intact. **16 test vehicles worsen; EVs are absent from test; paired macro MAE improvement's confidence interval crosses zero.** No stronger generalization or individual-prediction uncertainty claim is introduced.

## Startup and performance measurements

Warm latency: 30 sequential loopback samples per endpoint, one worker and warm caches. p95 is nearest rank (29th sorted sample). These are local samples, not browser or concurrent load benchmarks.

| Endpoint | Median ms | p95 ms |
|---|---:|---:|
| Fleet overview | 2.550 | 3.365 |
| Trips, 25 rows | 2.791 | 3.244 |
| Daily cohorts, 100 rows | 3.730 | 4.080 |
| Pipeline quality | 2.232 | 3.980 |
| Model metrics | 1.809 | 2.187 |
| Model cohorts | 1.847 | 2.321 |
| Prepared-vector prediction | 56.593 | 59.815 |

First inference after readiness took **39.669 ms** in the direct-server validation. Direct Uvicorn/Vite startup liveness was **1.167360 / 1.170211 s** from concurrent spawn, distinct from the PowerShell launcher measurements above and browser rendering time. Native pools were limited before import; no speculative optimization was added.

Production assets total **629,855 bytes**, offline gzip **193,529 bytes** using Python gzip level 9 and fixed timestamp. This is potential compression, not a claim that the local server enables HTTP gzip. Largest JS chunk is 346,231 bytes; no bundle-size warning. The production bundle/real API checks pass independently of unavailable browser tools.

## Preservation, dependencies and repository hygiene

Pre-release SHA-256 snapshot protects **261 prior files**: raw, Bronze, Silver, quarantine, Gold, ML, models and Day 1–9 results. All remain byte-identical after tests/integration. New evidence lives only in ignored `results/day10/`; temporary fixtures/caches are project-local.

`pip check` passes. All installed direct Python requirements match exact pins; installed npm direct dependencies match package.json and package-lock.json. No package was installed, dataset downloaded, lockfile changed or system environment modified. Official README/install links were opened; local Markdown paths/anchors and documented script paths were checked. The Windows pytest syntax was verified through collection, and actual backend/frontend launcher commands ran successfully. Optional reconstruction commands were source-checked only, consistent with the prohibition on rerunning ETL/training.

GitHub's language API reports actual **Python 411,815**, **TypeScript 83,047**, **CSS 18,795**, **JavaScript 5,890**, **PowerShell 2,918**, **HTML 531** source bytes at the pre-release remote head. Twelve `.ts`/`.tsx` files, including five application TSX modules and tests/config, are tracked. `.gitattributes` only controls text/line endings; no Linguist manipulation is present.

Ignore rules cover node_modules, dist/build, raw/generated datasets, CSV/Parquet, archives, model binaries, environments, caches and secrets. Working-tree and exact-index audits check recognized credentials, forbidden paths and oversized blobs. Largest tracked file remains the measured evaluation figure **219,162 bytes**, with no >1 MB warning and no >5 MB blob. Source-only repo size is modest; generated artifacts stay local.

Measured whole-project logical storage after tests/documentation: **2,763,617,931 bytes (2.764 GB / 2.574 GiB)**, including environments, node_modules, datasets, models, builds, caches, scratch and Git. Small final report/commit additions follow this snapshot. `scripts/validate_day10_release.py finalize` records the latest exact footprint and rechecks all preservation hashes. This is file length, not NTFS allocated size, and remains below preferred 5 GB / maximum 10 GB.

## Git publication and remaining limitation

Base: clean `main` tracking `origin/main`, commit **50af523a830dd1ee8e1330fb682f08bb632552a2**. Authenticated account: **VViswaPrahlad**. Existing origin: [FleetPulse](https://github.com/VViswaPrahlad/FleetPulse). Publication uses a normal audited commit and push, without rewritten history or uploaded artifacts. Final commit hash, remote-head equality and clean status are verified after commit/push and reported in the final handoff.

**Remaining critical sign-off:** rendered desktop/mobile verification cannot be completed with the available tools. Documentation and automated verification are ready for publication, but **overall final portfolio release completion is not claimed** until the manual visual checklist is observed and signed off. No work beyond Day 10 is performed.
