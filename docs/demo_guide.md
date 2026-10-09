# FleetPulse demo guide

## Interview demonstration: about four minutes

Start both servers and confirm `/api/v1/ready` returns 200 before presenting. Complete the visual checklist below. Do not run ETL or training during the interview.

| Time | Demonstration | Explanation |
|---|---|---|
| 0:00–0:35 | README architecture → Fleet Overview | Genuine VED telemetry: 22.4M observations, 384 inspected vehicle IDs, 32,552 trips; traceable local engineering chain. |
| 0:35–1:15 | Data Quality | Bronze = Silver + quarantine; show missingness and gap flags; explain original values, SOC precision corrections and no imputation. |
| 1:15–1:55 | Driving Analytics | Change powertrain/vehicle filters, switch trips/vehicles and paginate; explain bounded SQL, partial distance and trip-start date cohorts. |
| 1:55–2:45 | ML Intelligence | Test MAE 10.887 versus last-speed 14.056; explain past-only inputs, disjoint contexts, held-out vehicles and validation-only selection. State 16 vehicles worsen and no test EVs. |
| 2:45–3:30 | Prediction Lab | Click **Run example prediction** in Quick Demo → real API forecast about 36.62 km/h → reset. Expand **Advanced: Prepared feature vector** to inspect/edit the exact 31 features. Explain optional sensor availability and why raw GPS is insufficient. |
| 3:30–4:10 | API `/docs`, tests and Git | Typed contract, safe errors, ignored local artifacts, exact dependencies and test evidence; acknowledge visual sign-off if still pending. |

If artifacts are unavailable, demonstrate source/contracts/tests and honest unavailable states. Checked-in figures are historical measured evaluation outputs, not dashboard screenshots.

## Major engineering decisions

- **Reject unsupported fuel forecasting early:** 96.0061% fuel missingness and only one viable ICE/HEV paired window cannot support held-out-vehicle evaluation. Speed was an explicitly approved target change.
- **Spark plus bounded PyArrow IO:** inspected explicit schemas and transformations, with practical Windows writes rather than new Hadoop DLL/infrastructure dependencies.
- **Separate descriptive Gold from causal features:** whole-trip/lifetime aggregates can leak future information at intermediate prediction times; ML reads Silver histories instead.
- **Vehicle isolation and disjoint contexts:** random overlapping-window splits would inflate results; there are 50 independent test vehicles, not 1,919 independent drivers.
- **Persistence before complexity:** compare on identical examples and report worse vehicles, uncertain macro gains and missing EV coverage honestly.
- **Lightweight serving:** reuse compact Gold and saved model/reports; bounded cached queries; no ETL or fitting at startup.
- **Honest failure states:** missing resources return 503; raw GPS/incomplete features do not become fabricated inference inputs.

## Fresh Windows setup

Validated environment: Windows, Python **3.12.10**, JDK **21**, Node **24.7.0**, npm **11.5.1**, 16 GB RAM. Other patch versions are not claimed tested.

If missing, install prerequisites manually from official sources: [Python 3.12.10](https://www.python.org/downloads/release/python-31210/), [Temurin JDK 21](https://adoptium.net/temurin/releases/?version=21), [Node.js](https://nodejs.org/en/download) (24.x for this environment), and Git. JDK is required for Spark/reconstruction and the full fixture suite, not API/dashboard startup. No launcher silently installs software or changes system-wide settings; respect your machine's execution/security policies.

```powershell
git clone https://github.com/VViswaPrahlad/FleetPulse.git
Set-Location FleetPulse
py -3.12 --version
node --version
npm.cmd --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
$env:npm_config_cache = Join-Path (Get-Location) 'data/tmp/npm-cache'
npm.cmd ci --prefix dashboard
npm.cmd --prefix dashboard run typecheck
npm.cmd --prefix dashboard run build
```

For Spark, set `$taskJdk = 'C:\your\actual\jdk-21-folder'` and confirm `& "$taskJdk\bin\java.exe" -version`. Pass `-JavaHome $taskJdk` to `scripts/run_day2.ps1`; its default is the original developer's installation path, not a portable assumption. JAVA_HOME/PATH and scratch settings apply only within that process.

| Capability | Source + installed dependencies | Required local artifacts |
|---|---|---|
| Frontend build/component tests | Yes; four saved-contract tests skip without snapshots | `results/day8/contracts.json` for those four checks |
| All Python fixture tests | Yes, with JDK and project-local pytest basetemp | Tiny generated fixtures, no full VED |
| API health/OpenAPI/form schema | Yes | None |
| Fleet/trip/quality dashboard | Honest unavailable states only | Gold and Day 3 quality report |
| Model metrics/cohorts/vehicle errors | Unavailable states only | Day 6 evaluation JSON/Parquet |
| Prediction | Validation only; model unavailable | Saved model, inference metadata and compatible libraries |
| Real-data release harness | No | Complete prior artifacts plus frontend build |

A clone is not a bundled dataset/model demo. Health is 200 but readiness is 503 without artifacts. Installation/reconstruction on a separate fresh machine was **not** performed during Day 10: commands were checked against project code, and the current local environment was validated.

## Artifact reconstruction: source-only checkout

**Instructions for a deliberate separate reconstruction, not a Day 10 action.** These commands download official VED sources and rebuild/train the established recipe. Do not rerun them on a completed demo or use `--force` casually. Acquisition checks archive sizes, integrity, disk space and its original 5 GB cap; later pipelines enforce the 10 GB maximum.

Run one line at a time, stopping immediately on any nonzero exit or storage/dependency failure:

```powershell
$taskJdk = 'C:\your\actual\jdk-21-folder'
$env:PYTHONPATH = (Get-Location).Path
# External download: official pinned dynamic archives, static workbooks, license.
.\.venv\Scripts\python.exe scripts/acquire_ved.py
# Bronze and source inspection.
.\scripts\run_day2.ps1 -JavaHome $taskJdk -Script scripts/complete_day2.py
# Required feasibility manifest precedes Silver.
.\.venv\Scripts\python.exe -m src.quality.fuel_feasibility
.\scripts\run_day2.ps1 -JavaHome $taskJdk -Script scripts/complete_day3.py
# Gold, strict features/splits and established training/evaluation recipe.
.\.venv\Scripts\python.exe scripts/complete_day4.py
.\.venv\Scripts\python.exe scripts/complete_day5.py
.\.venv\Scripts\python.exe -m src.ml.train_speed
```

The initial reconstruction can take substantial time and staging space. No timing guarantee or separate-machine reproduction is claimed. The training recipe writes frozen metrics/bootstrap/cohorts and a model; checked-in PNGs already exist and need not be regenerated to serve the app. Day 8 contract snapshots are optional test evidence, not a serving dependency.

Core serving artifacts:

- `data/gold/ved/`: seven Parquet tables listed in README.
- `results/day3/silver_quality.json`: pipeline and quality summaries.
- `results/day6/training_run.json`, `cohort_metrics.json`, `vehicle_errors.parquet`: saved evaluation.
- `models/day6/hist_gradient_boosting.joblib`, `inference_metadata.json`: trusted model and exact schema/version/hash metadata.

Keep these excluded from Git. Never deserialize an untrusted Joblib model; it can execute Python objects.

## Launch and readiness

In two PowerShell terminals at the project root:

```powershell
# Terminal 1
.\scripts\run_backend.ps1
```

```powershell
# Terminal 2
.\scripts\run_frontend.ps1
```

Open `http://127.0.0.1:5173`, API docs `http://127.0.0.1:8000/docs`, and check `Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready`. Stop only your own terminal's server with Ctrl+C. If ports are occupied, do not stop unrelated processes. Alternate: backend `-Port 8010`, frontend `-Port 5180 -BackendPort 8010`; the same-origin proxy requires no expanded direct-browser CORS origins.

Production preview: build first, then `.\scripts\run_frontend.ps1 -Preview -Port 4173`. It is a local preview, not public deployment.

## Manual browser sign-off

**Pending: automated tools did not observe rendered UI.** Inventory reports no browsers; in-app and Chrome attempts both fail. Before claiming final visual release readiness, record browser/version, date, viewport and pass/fail notes. Leave these boxes unchecked until observed.

1. Start servers and confirm readiness. Open `http://127.0.0.1:5173` in Chrome/Edge. Open DevTools Console/Network; use **1440×900**, 100% zoom.
2. Visit five routes via sidebar and direct URL; test Back/Forward and route reload. Check active navigation, readable headings and no blank/clipped UI or console errors.
3. Repeat in DevTools device emulation at **360×800** and **768×1024**. Open/close mobile menu, use backdrop and navigate. Cards/charts fit; tables scroll inside their container rather than overflowing the entire page. Record emulation versus physical-device testing separately.
4. Use Tab/Shift+Tab/Enter and Escape where supported. Check skip-to-content, visible focus, form labels, contrast, chart legends/axes and hover/touch interactions.

| Page | Checks at each viewport | Sign-off |
|---|---|---|
| `/` Fleet Overview | 384 vehicles, 32,552 trips, 22,434,106 retained rows; powertrain chart; daily/monthly toggle; tooltips; partial-distance label | [ ] |
| `/driving` Driving Analytics | Trip/vehicle toggle; valid vehicle/powertrain filters; dates; Next/Previous; bounded tables; readable charts | [ ] |
| `/quality` Data Quality | Bronze/Silver/quarantine reconciliation; missingness/gaps; SOC explanation; no invented complete sensors | [ ] |
| `/ml` ML Intelligence | Validation/test and baseline controls; vehicle errors/pagination; speed/powertrain cohorts; CI meaning; EV/worse-vehicle limitations | [ ] |
| `/prediction` Prediction Lab | Quick Demo defaults; Run example prediction → actual ≈36.61749 km/h; reset; expand Advanced for 31 features/units and optional-null coverage; raw-GPS warning | [ ] |

Additional states:

- [ ] **Loading:** DevTools Slow 3G + disabled cache; reload/navigate all pages and observe loading without stale results posing as new ones. Restore normal network afterward.
- [ ] **Empty:** Driving trip filter vehicle `2147483647` (valid ID absent from VED); clear empty state, no stuck pagination; reset.
- [ ] **Invalid filters:** invalid vehicle or inverted dates show validation and issue no unfiltered replacement request in Network.
- [ ] **Invalid prediction:** expand Advanced; required fields blank, negative speed or gap >2 seconds; validation without stale predictions, paths or tracebacks. Run the verified example afterward.
- [ ] **Backend unavailable:** Ctrl+C only your backend terminal; reload/navigate all pages and confirm actionable errors with no invented values. Restart and use page/header Retry.
- [ ] **Production preview:** repeat navigation, charts and form at `http://127.0.0.1:4173` after build. Development modules expose source filenames; production assets/API are scanned separately.

No confirmed visual defect can be fixed without observing it. Retain screenshots/steps for any failing item and resolve it before final sign-off. Current status is **automatically validated, visually unverified**.

## Repeat automated checks without rebuilding telemetry

```powershell
.\scripts\run_day2.ps1 -JavaHome $taskJdk -Script '-m' pytest -q `
    --basetemp=data/tmp/pytest-release
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run typecheck
npm.cmd --prefix dashboard run build
```

The Day 10 harness's positional actions are `snapshot`, `browser-session`, `validate`, `finalize`. It snapshots prior artifacts, redirects reused integration checks to `results/day10/`, and uses ports 8010/5180. `snapshot` cannot overwrite its original baseline. `browser-session` waits up to 20 minutes or its disposable `results/day10/stop_browser_session` marker, stopping only its owned processes. Generated reports stay ignored. Do not use the Day 9 validator on ports occupied by the existing demo or rewrite earlier reports during release checks.
