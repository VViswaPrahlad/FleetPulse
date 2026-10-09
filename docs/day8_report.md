# FleetPulse Day 8 — React dashboard

Measured locally on 2026-10-09. Day 8 implementation and automated validation
are complete. Visual browser inspection remains unavailable in this session.
No Day 9 work, telemetry reprocessing or model training was performed.

## Delivered frontend

| Route | Working capabilities |
|---|---|
| `/` Fleet Overview | Vehicle/trip/observation/speed KPIs; bounded activity charts; real powertrain counts; partial-distance and percentile metrics |
| `/driving` Driving Analytics | Trip/vehicle tabs; powertrain and trip vehicle-ID filters; 25-row pages; daily/monthly charts and inclusive date filters |
| `/quality` Data Quality | Bronze/Silver/quarantine reconciliation; Gold aggregation semantics; missing-sensor percentages/counts; sampling/SOC flags; cleaning rules |
| `/ml` ML Intelligence | Validation/test toggle; model plus three baselines; cluster intervals; speed/powertrain cohorts; paginated vehicle errors; negative-result limitations |
| `/prediction` Prediction Lab | Exact 31-field prepared-input form; units/bounds/null policy; opt-in measured example; backend coherence errors; real inference and reset |

The design uses dark navy/charcoal surfaces, mint accents, Lucide navigation,
KPI cards, Recharts, local professional system fonts and responsive layouts.
Mobile navigation, semantic labels, keyboard focus, skip link, reduced-motion
support, horizontal table scrolling and chart-data alternatives are included.
Every API-driven section has loading, empty and retryable error states.
No locations, live fleet activity, invented trends or fallback metrics exist.

## Contracts and measurement provenance

`docs/api_contract.md` and actual Pydantic/OpenAPI responses were inspected
before implementation. The API client uses relative `/api/v1` requests through
a loopback Vite proxy. Chart requests contain at most 100 aggregate rows;
tables contain 25. Vehicle/trip filters and pagination execute server-side.
In-flight requests are aborted when the route/filter changes.

The two small added API endpoints, `/quality/pipeline` and `/ml/cohorts`,
project saved Day 3/6 reports, never raw telemetry. Bounded JSON reads and a
four-entry signature cache prevent unbounded report loading. Existing endpoint
contracts remain unchanged. New adapter tests cover reconciliation, safe
projection, filtering, empty/missing/invalid reports and strict query validation.

Actual dashboard source values: **384 vehicles, 32,552 trips, 22,434,106 retained
observations**. Pipeline input is **22,436,808**, with **2,702** quarantined negative
elapsed observations. Gold source observations reconcile to Silver. Missing fuel
rate is **21,538,009 retained rows**; sampling gaps >2s are **777,320** flag
occurrences and SOC precision corrections **358**. Flags overlap.

Distance is an explicitly partial estimate from eligible ≤2s speed intervals,
not odometer mileage. Trend dates are whole-trip start-reference cohorts with
unspecified timezone, not time-aligned live traffic. Missing metrics remain
null and display as a dash; unavailable sensor readings are never fabricated.

ML reports expose the unchanged saved evaluation: test MAE **10.886851 km/h**,
RMSE **14.090555 km/h**, versus last observed speed **14.056006 / 18.802985**.
Pooled MAE improvement is **22.546625%**. The test cohort contains **1,919 examples
across 50 held-out vehicles** and **no EVs**. Low/high-speed cohorts and 16 of 50
vehicles worsen; the vehicle-macro improvement interval crosses zero. These
limitations are visible, and bootstrap intervals are not represented as
individual prediction intervals.

Prediction Lab starts blank. All 31 prepared features must be present in the
request; six optional sensor means may be null only with zero availability.
No IDs, future measurements, raw GPS or fabricated features are accepted.
The measured anonymous Day 7 example returns **36.61748855856695 km/h** with
model identity **hgb-day6-ea8d587632fa** through both the API and production UI.
Client bounds are preliminary; backend statistical coherence remains authority.
Caller-supplied provenance cannot be independently certified by this API.

## Environment and reproducibility

Existing Python 3.12.10 environment and FastAPI/DuckDB/model dependencies were
reused unchanged. Node **24.7.0**, npm **11.5.1** were verified. Only local
frontend dependencies were installed; no system-wide settings changed.

| Package | Pinned version |
|---|---|
| React / React DOM | 19.1.1 |
| React Router DOM | 7.18.4 |
| Vite | 7.3.7 |
| TypeScript | 5.9.3 |
| Tailwind CSS / Vite plugin | 4.1.14 |
| Recharts | 3.2.1 |
| Lucide React | 0.468.0 |
| Vitest | 5.0.3 |
| jsdom | 26.1.0 |
| Testing Library React / jest-dom / user-event | 16.3.0 / 6.8.0 / 14.6.1 |
| PostCSS (responsive CSS test parser) | 8.5.29 |

Remaining build/type support pins are in `dashboard/package.json`; the complete
resolution is committed in `package-lock.json`. Prettier 3.6.2 was used only from the
project-local temporary npm cache to format source, without a global install
or runtime dependency. Initial pins were updated to patched releases after
npm audit. The patched lockfile reports **zero known
vulnerabilities**. npm 11.5.1's peer-resolution error on an intermediate Vitest
version was resolved with a current compatible release and a fresh lockfile.
`npm ci` succeeded after stopping only the validator's own preview server,
which held a Windows native-module file lock. No security controls were bypassed.

## Verification and measured execution

| Check | Actual result |
|---|---|
| TypeScript strict compilation | Passed, no errors |
| Frontend unit/component tests | 17 passed |
| Actual API response contract tests | 4 passed, none skipped in measured run |
| Responsive CSS structural checks | 3 passed, widths 360 / 768 / 1440 px |
| Frontend suite total | **24 passed**, final single-thread run **5.99 s** |
| Backend and prior fixture regression suite | **109 passed**, **8.17 s** |
| Production build | Passed, final warm-cache Vite build **2.30 s** (earlier build 17.17 s) |
| Real API/proxy reconciliation | 13 read contracts, inference, filters, pagination and route fallbacks passed |
| Vite development launch mode | Source/TSX/CSS and measured-example JSON imports, plus real API proxy, passed |
| Built production bundle + real API DOM smoke | All five pages, 31 inputs, example prediction and reset passed |
| Earlier artifacts protected | SHA-256 verified **183 files unchanged**, including Bronze/Silver/Gold/ML, models and Day 1–7 results |
| Browser visual smoke | Unavailable: enabled-surface inventory empty; in-app browser and Chrome unavailable |

The production-bundle smoke runs jsdom against temporary loopback servers; it
executes compiled JS and verifies actual rendered text/forms and real API
inference. It is **not** pixel rendering or a browser-engine test. Responsive
tests apply matching CSS rules and verify structural computed styles. Rendered
chart sizing, mobile appearance and cross-browser visual QA remain unverified.
No browser or screenshot result is invented.

`scripts/validate_day8_actual.py` completed in **18.647500 s**, including artifact
hash checks, both launch modes, and real HTTP/DOM verification. Loopback liveness
times measured from child spawn were **1.243347 s backend** and **1.234289 s
frontend preview**; children start concurrently. The development server was
checked later at **4.734582 s** from spawn (including earlier verification
work), while Vite's own readiness log reported **368 ms**. Built-DOM subprocess
took **6.544167 s** (its own reported execution **0.573935 s**). These are local single-run measurements,
not production benchmarks. One existing Starlette/AnyIO deprecation warning
appeared in Python tests; no failing tests remained.

Built assets: HTML **0.79 kB**, CSS **19.91 kB**, framework JS **49.36 kB**, app
JS **213.24 kB**, chart JS **346.23 kB** (Vite decimal sizes). No bundle-size
warning remained after chunk splitting. Generated build/test/contract outputs
are ignored and stay local.

The verification footprint was **2,748,665,912 bytes (2.749 GB / 2.560 GiB)**,
including dependency folders, npm cache, datasets, model, temporary tests and
build output. The subsequent full measurement was **2,748,665,911 bytes** before
the commit and minor report/index additions. `results/day8/storage.json` records
the latest measurement; `scripts/finalize_day8_statistics.py` reproduces it.
This remains comfortably below the preferred 5 GB target and 10 GB cap.

Storage includes 1,536,036,134 bytes under `data/` (including the project-local
npm cache), 1,023,210,932 bytes in `.venv`, 177,045,459 bytes in frontend
node_modules, and 629,525 bytes of production build output. No duplicate
telemetry dataset was downloaded or processed.

## Windows launch and checks

```powershell
# Project terminal; one-time install on a checkout:
$env:npm_config_cache = Join-Path (Get-Location) 'data/tmp/npm-day8'
npm.cmd ci --prefix dashboard
# Terminal 1:
.\scripts\run_backend.ps1
# Terminal 2:
.\scripts\run_frontend.ps1
# Open http://127.0.0.1:5173

npm.cmd --prefix dashboard run typecheck
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run build
.\scripts\run_frontend.ps1 -Preview -Port 4173
```

Use `-BackendPort` for an alternate local API port; settings apply only to that
terminal process. Source-only GitHub clones intentionally lack private/local
datasets and model artifacts, and show explicit unavailable states until those
existing reproducible outputs are supplied.

## Git publication

Source, tests, dependency lockfile, Windows launcher and documentation are
included. Dataset/CSV/Parquet/archive/model/environment/generated-output paths
are excluded, as are node_modules, dist, coverage, caches and TypeScript build
metadata. The index audit additionally rejects these paths, oversized blobs
and recognized credential patterns. Existing origin/main is the publication
target, without rewriting history. Exact
commit/push/clean-state verification is reported after the commit. No Day 9
work is included.
