# Render portfolio deployment — preparation only

Prepared and reviewed on **2026-10-09**. Deployment-preparation source/configuration is versioned separately from artifact publication. Nothing has been deployed, no bundle has been uploaded and no public profile has been changed. No live Render URL exists or has been verified. Existing local startup scripts, local proxy defaults, model and data outputs remain intact. See the [source review](deployment_review.md) for the publication scope and checks.

Target: **Render Static Site** for React plus **Render Free Web Service** for FastAPI. No database, persistent disk, Docker, Java, Spark, retraining or ETL is required for serving. The supplied `render.yaml` is a settings template; applying/creating services would deploy and requires a separate decision.

## Actual runtime audit

The original inference import reached training/plotting code unnecessarily. Serving now imports shared path/hash constants from `src/runtime.py` and the same feature contract without importing training modules. Model bytes and predictions are unchanged. The public app uses an explicit artifact root, whereas the local app retains its original root and localhost CORS.

`deploy/requirements-runtime.txt` contains 12 direct serving dependencies. `deploy/requirements-runtime.lock` pins their 24-package Linux/Python 3.12 closure, including numerical libraries and small required HTTP/validation/date dependencies. Spark, Py4J, Pytest, Py7zr, Matplotlib, HTTPX, training modules and feature-dataset builders are absent from actual serving imports. Tests/tools may use the existing full local environment; Render installs only the runtime lock.

Official PyPI metadata confirms suitable Linux x86-64/CPython 3.12 wheel candidates for all 24 pins. The audit checks Python requirements and actual wheel tags, excludes Windows/newer-Python ABI wheels, and assumes glibc compatibility through manylinux 2.28. Direct pins and the complete Linux dependency closure agree. Installation uses `--only-binary=:all:` to fail rather than unexpectedly compile scientific libraries. This is **wheel metadata verification, not a Linux install/run test**. The audit tool uses Packaging from the existing full development environment; Packaging is not a serving requirement. Python is explicitly pinned to **3.12.10**; Render's current default differs. [Render Python version configuration](https://render.com/docs/python-version).

## Serving-only artifact bundle

Generate locally with:

```powershell
.\.venv\Scripts\python.exe deploy/bundle.py
```

Output: `artifacts/deployment/fleetpulse-runtime.zip`, expanded under `artifacts/deployment/bundle/`. Both remain Git-ignored. The archive is deterministic across repeated runs, with fixed ZIP metadata, CRC checks, exact allowlisted members, SHA-256 manifest and the actual pinned VED source commit. The timestamp in ZIP metadata is a canonical archive value, not a claim about creation or commit dates.

| Artifact | Bytes | Purpose |
|---|---:|---|
| Seven Gold Parquet files | 2,501,660 | Fleet/vehicle/trip/date/powertrain/quality analytics |
| Existing HGB model | 171,778 | Unchanged trained inference binary |
| Existing inference metadata | 5,683 | Exact 31-feature order, versions and model hash |
| Projected reports, cohort metrics, vehicle errors, license and manifest | 51,207 | Genuine values required by existing API contracts and provenance |
| **Expanded bundle** | **2,730,328** | About 2.73 MB |
| **ZIP archive** | **2,611,636** | About 2.61 MB |

Current archive SHA-256:

```text
16acf6172c6174f7802886c2e81a032d637ed24ee1bd838af2c9a6add39d7565
```

The allowlist copies Gold, model, inference metadata, cohort metrics, vehicle errors and the original VED license byte-for-byte. It projects Day 3 quality and Day 6 evaluation JSON to the original fields consumed by the API, without recomputing/changing results. It excludes source/weekly per-file details, input-hash inventories and unused hyperparameter search payloads. Relative artifact provenance and the inference metadata's historical training hashes are metadata, not training examples.

**Excluded:** raw VED archives/CSV/workbooks, Bronze/Silver/quarantine telemetry, ML training/validation/test tables, individual forecast-evaluation prediction tables, environments, caches, secrets and development dependencies. No full ETL output is needed on Render.

| Runtime lookup, relative to bundle root | Source |
|---|---|
| `data/gold/ved/*.parquet` | Seven existing genuine Gold outputs |
| `models/day6/hist_gradient_boosting.joblib` | Existing trusted Day 6 model |
| `models/day6/inference_metadata.json` | Existing metadata, unchanged |
| `results/day3/silver_quality.json` | Projected existing quality report |
| `results/day6/training_run.json` | Projected existing evaluation/selected parameters/bootstrap |
| `results/day6/cohort_metrics.json` | Existing cohort errors |
| `results/day6/vehicle_errors.parquet` | Existing vehicle-level errors |
| `VED_LICENSE.txt`, `bundle_manifest.json` | Author's license and integrity/source manifest |

The archive is an **artifact supplement**, not a standalone source checkout or Python environment. Render also needs the prepared source/configuration files in the repository. Joblib deserialization is unsafe for untrusted files: use only this locally generated artifact and independently confirmed expected archive hash.

## Memory and startup

Estimate **250–350 MB RAM at low portfolio traffic**, based on Windows measurements—not a measured Linux/Render bound. The reviewed local serving-process-tree sample was **220,397,568 working-set bytes** / **228,323,328 private bytes** after warmup. Four concurrent cold-cache queries produced sampled peaks of **234,520,576 working-set bytes** / **252,010,496 private bytes**. Earlier repeats observed about 240 MB working set. Sampling can miss short peaks; Windows memory measures are not Linux cgroup accounting.

Public configuration: one worker, native pools fixed to one before import, concurrency limit **8**, query cache **16**, DuckDB **32 MB per connection**, spill cap **32 MB**, bounded lists and 64 KiB requests. These caps do not constitute a total RSS guarantee. Local defaults remain one worker/concurrency 32/cache 32/DuckDB 128 MB. Public demo traffic is unauthenticated; CORS is not abuse protection.

`python deploy/start.py` binds **0.0.0.0** to Render's **PORT** (10000 fallback). Before accepting traffic, the factory verifies all bundle hashes, loads/checks the trusted model and evaluation identity, and validates required analytics/quality/cohort resources. Invalid CORS, missing files or mismatches fail startup. No artifact download/ETL/training runs at startup. The build step downloads/unpacks the artifact once; every deployed build includes it, so no persistent disk is needed.

Reviewed local public-process startup to health: **1.753515 s**; complete bundle validation: **6.646928 s**. Free Render has less CPU and a platform spin-up delay; these are not Render timings or guarantees.

## Free-tier suitability and cost limits

Render currently lists Free Web Service as **0.1 CPU / 512 MB**, making this a plausible small portfolio workload; actual Linux memory/load remains to be checked. Static Sites are CDN-served and do not need backend compute. [Compute plans](https://render.com/docs/compute-plans), [static sites](https://render.com/docs/static-sites).

Free services sleep after 15 idle minutes and may take about one minute to wake. They share 750 free instance hours/workspace/month, have ephemeral storage and no free persistent disk/shell/one-off jobs. Build minutes/bandwidth are quota-limited; exceeding allowances can incur charges when a payment method exists. Without a payment method, Render instead suspends services/builds at relevant limits. Verify the workspace billing policy before deployment; $0 compute is **not an unconditional zero-overage-cost guarantee**. [Current free-tier rules](https://render.com/docs/free).

For zero additional cost: choose Hobby/free resources only, create no paid add-ons/disks/databases/custom domain purchases, inspect included usage/overage settings, and use a workspace without a payment method if supported and appropriate. If the account requires billing or cannot enforce your desired zero-spend policy, stop for a decision. Do not add keep-alive pings to defeat sleep. Public-mode errors explain waiting/retrying; no fallback metrics/predictions are invented.

## Exact Render settings

Use the repository root for both services (**Root Directory blank**). Setting frontend root to `dashboard` would hide its checked-in example import from `docs/`. Branch: `main`, once these prepared changes have been separately approved and published. Actual service names/assigned URLs may differ; copy URLs from Render, never assume the suggested names guarantee a domain.

| Setting | FastAPI Web Service | React Static Site |
|---|---|---|
| Suggested name | `fleetpulse-api` | `fleetpulse-dashboard` |
| Runtime/type | Python / Web Service | Static Site |
| Plan | **Free** | Free static hosting |
| Region | Singapore, if offered; otherwise choose available free region deliberately | CDN; no compute region setting |
| Build command | `python -m pip install --only-binary=:all: -r deploy/requirements-runtime.lock && python deploy/fetch_bundle.py` | `node deploy/build_frontend.mjs` |
| Start command | `python deploy/start.py` | None |
| Publish directory | N/A | `dashboard/dist` |
| Health check | `/api/v1/health` | N/A |
| Auto deploy | Off | Off |
| Persistent disk / database | None | None |
| SPA rewrite | N/A | Source `/*`, destination `/index.html`, action **Rewrite** |

Backend environment:

```text
PYTHON_VERSION=3.12.10
FLEETPULSE_FRONTEND_ORIGIN=https://<actual-static-site-host>
FLEETPULSE_BUNDLE_URL=https://<approved-public-archive-download-url>
FLEETPULSE_BUNDLE_SHA256=<current-64-character-archive-sha256>
```

Do not override platform PORT. The launcher sets OMP/OpenBLAS/MKL/NumExpr process limits itself. Frontend CORS is a single exact HTTPS origin: no path, wildcard, credentials or port. Localhost is not admitted in public mode; credentials are disabled. `deploy/fetch_bundle.py` only accepts HTTPS, caps archive/expanded size at 16 MB, checks the out-of-band hash, CRCs and file allowlist, rejects traversal/symlinks, and verifies unpacked files.

Frontend environment:

```text
NODE_VERSION=24.7.0
VITE_API_URL=https://<actual-api-host>
```

Do not append `/api/v1`; the frontend adds that prefix. This variable is public build-time configuration, **not a secret**. Changing it requires a rebuild. The Render build guard refuses an unset or malformed origin instead of silently compiling the local proxy default. Existing local `npm run build` keeps `/api/v1` relative proxy behavior unchanged when this variable is unset.

The Blueprint uses `sync: false` values you must provide; creating it still triggers initial deployment even with auto-deploy off. Treat it as a template until actual service URLs and approved bundle location exist. [Blueprint reference](https://render.com/docs/blueprint-spec), [health checks](https://render.com/docs/health-checks).

## Manual deployment steps — NOT performed

1. Source/configuration publication and **serving-only artifact publication** are separate actions. This source review authorizes only the safe preparation commit. Audit the manifest/license/Gold fields before any later artifact upload. Do not force-add ignored datasets/models to Git.
2. After separate artifact-publication approval, put **only** the verified small archive at a stable trusted HTTPS location. A public GitHub release asset under your existing repository is one possible no-additional-service-cost location; creating/uploading it needs approval. Preserve this bundle's license/provenance and record its SHA-256. No signed/private credentials belong in frontend configuration. Render service creation also remains a separate approval step.
3. In Render, verify free-plan/billing limits and connect the approved source repository. Recommended manual sequence to avoid guessing domains: create the Static Site first, record its assigned URL, and defer deployment if the UI permits. Otherwise its initial build intentionally fails the missing-API-origin guard; it never publishes a localhost-configured build.
4. Create the **Free** API with that exact assigned frontend origin, approved bundle URL/hash, Python pin and settings above. Render build downloads only the compact archive. Confirm build/start logs, health **and readiness** 200 and model identity `hgb-day6-ea8d587632fa`. If OOM/incompatible wheel/hash/download errors occur, stop; do not silently upgrade or retrain.
5. Set the frontend's `VITE_API_URL` to the actual API HTTPS origin, set Node version/rewrite, build it and verify its assigned HTTPS URL. If frontend host changes, update API CORS and redeploy. Do not apply a second Blueprint that accidentally creates duplicate services.
6. Verify the live endpoints and manual checklist below. Only then claim deployment success or consider public-profile updates. Neither is authorized/performed in this preparation.

## Verification already completed locally

- **90 relevant Python tests** passed, **16.96 s**: deployment/CORS/archive/path/integrity protection, existing API/report and model regressions; 74 known dependency deprecation warnings.
- **41 frontend tests** passed, **18.33 s**; strict TypeScript passed; local production build **2.38 s**, separate public-URL build **2.35 s**. The previously committed Quick Demo remains the default Prediction Lab experience.
- **23 API contracts** from the bundle match original local artifacts exactly: overview, details, powertrain/vehicle/date filters, pagination, empty results, quality, metrics/cohorts/error tables and feature schema.
- All five compiled production-page **DOM** flows pass with real bundle data, exact 31-feature inference/reset and public HTTPS URL construction. A reserved `.invalid` test host is explicitly remapped to loopback; it is not a live API or TLS verification. All 13 API requests use that compiled test origin. Chart data contracts/component behavior pass; actual chart pixels are not claimed verified.
- Actual saved model returns **36.61748855856695 km/h** for the documented measured example. Model/metadata/Gold bytes remain unchanged; projected report API values are identical.
- Correct-origin CORS passes; localhost/unapproved origin fail. Invalid raw GPS returns safe 422. Stopping only the owned backend produces honest public-mode unavailable/wake/retry states on all five DOM pages.
- **278 original data/model/Day 1–10 result files** remain byte-identical. No ETL/training/registry package installation/upload was performed.

Computer-use inventory still reports no enabled browsers. Therefore real chart rendering, desktop/mobile pixels, touch/keyboard interactions and **all live Render verification remain pending**. Follow [manual browser sign-off](demo_guide.md#manual-browser-sign-off), substituting the actual HTTPS frontend URL.

## Live acceptance checklist

After approval/deployment, record actual URLs, Render instance memory/logs, browser/version and observed checks:

- Health and readiness both 200; `/docs` reachable without paths/secrets leaking in error responses.
- Overview: 384 vehicles, 32,552 trips, 22,434,106 retained observations; genuine powertrain/date charts.
- Driving: vehicle/powertrain/date filters, next/previous pages, empty vehicle filter and direct-route refresh.
- Quality: 22,436,808 Bronze = 22,434,106 Silver + 2,702 quarantine; sensor missingness and SOC rules.
- ML: test model MAE/RMSE 10.886851/14.090555 versus last-speed 14.056006/18.802985; no test EVs and worse-vehicle/macro-CI limitations remain visible.
- Prediction: **Run example prediction** in Quick Demo → approximately 36.61749 km/h; reset, expand Advanced for the 31 features, and verify invalid-input rejection. No fabricated raw GPS inference or per-prediction CI.
- Network: HTTPS API requests go to the actual backend, no localhost/mixed-content/CORS failures; approved preflight succeeds and other origins fail.
- Responsive/visual: repeat five pages at 1440×900, 360×800, 768×1024; inspect charts/tables/menu/focus/loading/error states.
- Cold start: let API sleep, return and observe actual waiting/retry recovery; never advertise always-on uptime.
- Restart/redeploy: packaged artifacts survive as build contents; memory remains within Free plan under realistic low traffic. If not, document the blocker instead of upgrading automatically.

## Reproduce preparation checks

From project root, using existing approved dependencies:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe deploy/bundle.py
.\.venv\Scripts\python.exe -m pytest tests/test_deployment.py tests/test_day7_api.py `
    tests/test_day8_reports.py tests/test_day6_ml.py -q --basetemp=data/tmp/pytest-deployment
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run typecheck
npm.cmd --prefix dashboard run build
# Separate test public build; no real URL is contacted by the explicit remap harness.
$env:VITE_API_URL = 'https://fleetpulse-api.invalid'
npm.cmd --prefix dashboard run build -- --outDir ../artifacts/deployment/frontend
Remove-Item Env:VITE_API_URL
.\.venv\Scripts\python.exe deploy/validate_bundle.py
```

The harness uses only owned ports 8011/5181 and stops only its children. It reads the actual HTML entry asset even if prior generated chunks remain. It does not perform visual browser or real HTTPS/TLS checks. Runtime audit `python deploy/audit_runtime.py` also reads official PyPI metadata and therefore requires network access. All evidence is ignored under `results/deployment/`; the compact generated archive remains under `artifacts/deployment/`.
