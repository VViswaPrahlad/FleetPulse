# FleetPulse Day 9 — integration and hardening

Measured locally on 2026-10-09. Engineering, automated integration and
performance validation are complete. **Visual browser verification remains
unavailable**, as described below. No Day 10 work, ETL or production model
training was performed.

## Browser verification — explicit limitation

FastAPI and Vite were launched on **127.0.0.1:8000 / 5173**. The computer-use
inventory returned `apps: []`, `browsers: []`. Attempts to open
`http://127.0.0.1:5173` through both the in-app browser and Chrome returned
“Browser is not available.” No security controls or browser warnings were bypassed.

| Page | Real API / compiled DOM integration | Visual browser result |
|---|---|---|
| Fleet Overview | Real KPIs, powertrains and bounded monthly cohorts passed | Unverified |
| Driving Analytics | Actual 25-row trip table; filter/pagination component tests passed | Unverified |
| Data Quality | Actual input/retained/quarantine counts and flags passed | Unverified |
| ML Intelligence | Actual model metrics, cohort/error contracts and limitations passed | Unverified |
| Prediction Lab | Exact 31 inputs, measured example, saved-model prediction and reset passed | Unverified |

Desktop/mobile chart appearance, real browser layout, focus/overlay behavior,
touch interactions and cross-browser rendering are **not claimed verified**.
The three CSS structural tests at 360, 768 and 1440 px pass; jsdom cannot render
pixels. DOM/build tests are not substitutes for browser inspection. This is
the remaining verification limitation, not a reason to fabricate screenshots.

## Confirmed defects and fixes

1. **Invalid vehicle filters fetched an unfiltered fleet page.** An invalid
   suffix after a valid vehicle ID added another request. Invalid/inverted
   date ranges similarly fetched unfiltered history. The query hook now accepts
   a paused null path, aborting the prior request and issuing no replacement.
2. **Connection recovery required reloading the page.** The header now provides
   an explicit health retry after a backend restart, with no polling loop.
3. **A JSON-null error envelope raised TypeError.** Error parsing now handles
   null safely and validates message/details container types.
4. **An empty proxy error gave an unhelpful unreadable-response message.**
   Backend-down HTTP 500 from Vite now produces an actionable startup/retry
   message. All five compiled pages were exercised with the actual backend
   stopped; no guessed metrics, inference inputs or predictions appeared.
5. **Native pool initialization allocated excessive private memory.** A
   controlled process-only OMP/OpenBLAS/MKL/NumExpr thread limit of one reduced
   backend private allocation and first-inference overhead. The Windows
   launcher now initializes those values before scientific-library imports.
   The saved model and prediction remain unchanged.

Five targeted tests failed before frontend fixes; the obsolete-request abort
test already passed. The final eight regression cases also cover stable-query
rerenders and empty gateway responses. The smoke harness was corrected to wait
for each unavailable page's heading and error state and exit naturally, avoiding
an intermittent Windows Node/libuv assertion caused by forced process exit.
Validation cleanup explicitly stops only owned process trees, including Windows
venv redirectors. No unrelated process or important file is deleted.

## Actual integration and data reconciliation

`scripts/validate_day9_actual.py` checks **15 frontend-related read contracts**
against the real backend and **5,332 projected field values** against existing
Gold Parquet. Counts and dates/nulls reconcile. Saved Day 3 missingness and
pipeline counts and Day 6 baseline/cohort metrics match their source reports.
The two Day 8 endpoints retain their 4 MB / 250 KB report limits and 100-record
cohort bound; fixture tests for missing, malformed and filtered reports pass.

The actual retained fleet remains **22,434,106 observations, 384 vehicles and
32,552 trips**, from **22,436,808 Bronze observations minus 2,702 quarantined**.
No full telemetry table is sent to the browser. Tables request 25 records;
charts request at most 100 date cohorts. Null measurements remain unavailable.

The documented prepared vector returns **36.61748855856695 km/h**, exactly
matching direct inference with the unchanged saved Day 6 model. The full
production-bundle DOM flow visits all five pages, loads all 31 prepared fields,
predicts and resets. It makes **13 API requests**: 12 GETs and one POST. Monthly
cohorts are read once on each of the two relevant pages; the API cache serves
repeats. Stable-query rerenders issue no extra requests; invalid filters now
issue none. There is no confirmed chart/rerender bottleneck to optimize without
real browser profiling, so no speculative memoization/cache system was added.

SHA-256 checks protect **192 prior files**: raw/Bronze/Silver/Gold/ML datasets,
models and Day 1–8 result artifacts. All remain unchanged. The all-Python test
suite fits only tiny synthetic fixture models and processes tiny Spark fixtures;
it does not refit the production model or reprocess VED.

## Reliability and security checks

- CORS allows only `http://127.0.0.1:5173` and `http://localhost:5173`;
  the unapproved origin is rejected and credential cookies are not enabled.
- Servers bind loopback, one API worker, concurrency limit 32. No authentication
  or public deployment is introduced. CORS is not an authentication boundary.
- Limit 101, offset 100001, unknown query names, raw GPS prediction bodies,
  invalid sampling gaps and malformed JSON return safe 422 errors.
- A 65,537-byte prediction request returns 413; the 64 KiB body cap remains.
- A missing-artifact fixture returns live health but 503 readiness, analytics,
  report, evaluation and model responses. Existing real artifacts were never
  removed/renamed to test this behavior.
- Actual backend shutdown produces HTTP 500 at the Vite proxy; all five
  compiled pages display safe actionable unavailability messages.
- API response/error checks and production-asset scans found no absolute
  project paths, tracebacks or recognized credential patterns. npm audit reports
  **zero known vulnerabilities**; dependencies were not changed/downloaded.

**Development-only path metadata remains visible:** Vite's transformed JSX
includes local source filenames, and the anonymous example import uses an
in-project source path. This is developer tooling, not a sanitized production
bundle. The existing development server must remain loopback-only. Production
assets and API responses pass the path checks. No claim that development
modules hide source locations is made.

## Performance — measured, not projected

Warm latency uses 30 sequential loopback requests per endpoint, an explicit warmup,
one worker and existing artifact caches. p95 uses nearest rank (29th sorted sample
of 30). These are local samples, not load/concurrency/browser benchmarks.

| Endpoint | Median ms | p95 ms | Response bytes |
|---|---:|---:|---:|
| Fleet overview | 3.639 | 4.326 | 1,001 |
| Trips, 25 records | 3.015 | 4.119 | 26,038 |
| Daily trends, 100 cohorts | 3.817 | 4.759 | 100,830 |
| Pipeline quality | 2.389 | 2.800 | 532 |
| ML metrics | 1.077 | 2.030 | 4,296 |
| ML cohorts | 1.697 | 2.782 | 4,014 |
| Prepared-vector prediction | 63.981 | 71.330 | 278 |

Twenty repeated warm overview requests add **zero DuckDB queries**. The cache
remains bounded to 32 query entries and the report cache to four signatures.

Memory measurements include the entire owned Windows process tree, not just
the small venv launcher. Initial launcher-only measurements were discarded.
Under the same direct-Uvicorn benchmark, before/after thread limits:

| Measurement | Default native pools | Pools limited before import |
|---|---:|---:|
| Warm backend private allocation | 1,728,249,856 bytes | 175,288,320 bytes |
| Warm backend working set | 240,955,392 bytes | 236,421,120 bytes |
| First prediction after readiness | 1,446.118 ms | 36.585 ms |

This controlled-run snapshot shows approximately a **89.9% reduction in private
allocation**, with identical predictions. A final independent repeat measured
175,681,536 private bytes and 235,806,720 working-set bytes; first inference
took 99.725 ms. Warm prediction medians varied **16.548–63.981 ms** between
the two limited runs, demonstrating local timing variability. The latency
table above uses the final repeat, not the fastest observations. No latency
guarantee or browser-performance claim is made. In the controlled limited run, private
allocation grows about 2.94 MB during warmup/210 timed requests; this finite
sample does not prove absence of every possible leak. Frontend development
process-tree working set is 210,485,248 bytes; private allocation 313,663,488.
No millions of telemetry rows are loaded into either process for these requests.

The **actual PowerShell backend launcher** also passed health/readiness and
saved-model inference with inherited thread settings removed from the test
environment. It sets limits itself, without execution-policy overrides or
system-wide environment changes. Verification took **2.263272 s**; including
the PowerShell process, its tree used 298,094,592 working-set bytes and
222,683,136 private bytes in that separate run.

Final production-build assets:

| Asset | Bytes | Offline gzip bytes |
|---|---:|---:|
| Chart JS | 346,231 | 102,780 |
| Framework JS | 49,358 | 17,462 |
| Application JS | 213,570 | 67,426 |
| CSS | 19,910 | 5,440 |
| HTML | 786 | 421 |
| **Total** | **629,855** | **193,529** |

Gzip values use Python gzip level 9 with fixed timestamp; they are potential
compressed sizes, not claims that the local server enables network compression.
The warm-cache Vite build took **2.30 s**. No bundle-size warning remains.

The final real-data validation completed in **15.312311 s**, including artifact
hashes, source reconciliation, HTTP/security checks, benchmarks, memory checks
and both healthy/unavailable compiled DOM flows. The earlier controlled run took
8.481422 s, with healthy compiled DOM execution 0.421800 s and child liveness
0.907068 s backend / 0.929413 s frontend from concurrent spawn. DOM execution
is distinct from real browser rendering; repeats vary with local scheduling.

## Automated tests and storage

| Check | Result |
|---|---|
| All Python tests | **144 passed**, 69.02 s; no skipped tests |
| Frontend tests | **32 passed**, 4.91 s; 8 new regression tests |
| TypeScript strict check | Passed |
| Production build | Passed |
| Real source/API and compiled DOM validation | Passed |
| Actual Windows launcher | Passed |
| Browser desktop/mobile rendering | Unverified: browser unavailable |

Python tests emit 74 dependency deprecation warnings: one Starlette/AnyIO alias
and 73 Joblib/NumPy array-shape warnings in synthetic-model tests. No test failed
after fixes. No dependency upgrade was needed or performed.

The full pre-publication footprint is **2,755,924,066 bytes (2.756 GB / 2.567 GiB)**,
including datasets, model, virtual environment, node_modules, build, caches,
temporary fixture outputs and Git metadata. Small documentation/commit additions
follow this snapshot. `scripts/finalize_day9_statistics.py` reproduces the latest
measurement and artifact hashes into ignored `results/day9/storage.json`.
Storage remains below the preferred 5 GB target and 10 GB maximum.

## Reproduce and Git publication

Use the unchanged two-terminal startup workflow in README. For integration:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe scripts/validate_day9_actual.py
.\.venv\Scripts\python.exe scripts/verify_day9_launcher.py
.\.venv\Scripts\python.exe scripts/finalize_day9_statistics.py
npm.cmd --prefix dashboard run typecheck
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run build
```

`--serve` retains only the validator's own loopback children for up to 20 minutes,
or until `results/day9/stop_serving` exists. Port conflicts cause an explicit
failure without stopping unrelated processes. Prior results are never rewritten.
Generated validation/test/benchmark files stay ignored. Source, regression
tests, launcher changes and documentation are audited before staging and again
against exact index blobs. Datasets, CSV/Parquet, archives, environments, secrets,
model binaries, node_modules, dist and large generated files are excluded.

Publication target is the existing **origin/main**, preserving all history.
Base commit: **83c8a5b** (Day 8). Exact Day 9 commit, successful remote-head match
and clean working-tree status are verified after publication and reported to
the user. Browser availability and development source-location metadata are the
remaining limitations. No Day 10 work was started.
