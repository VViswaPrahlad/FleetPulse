# FleetPulse Day 7 — FastAPI backend

Date: **2026-10-09**, Asia/Calcutta. **Day 7 complete and validated locally.**
The approved architecture replaces the earlier Streamlit plan with
**React + TypeScript / FastAPI**. Day 7 implements the backend only.
No React application, dashboard, Day 8, ETL rerun or model retraining occurred.
Commit/push follows the file audit; publication status is reported in chat and
ignored local `results/day7/publication.json`.

## Backend layout and execution

`src/api/main.py` exposes an app factory and the ASGI app; `settings.py` owns
local resource/CORS/bound defaults. `routes/` separates health, analytics and
ML resources; `services/` separates parameterized artifact queries, model
loading/inference and safe evaluation projection; `schemas/` defines typed
public responses and the exact prepared-feature request contract.

The API is versioned at **`/api/v1`**, with **15 resource paths**.
OpenAPI JSON is `/openapi.json`; Swagger/Redoc are `/docs` and `/redoc`.
Neither import nor server startup processes telemetry or fits an estimator.
Resources load lazily on their first relevant request. A missing dependency
can leave other routes operational; liveness does not depend on data.

```powershell
.\scripts\run_backend.ps1
# Development reload of src/api only:
.\scripts\run_backend.ps1 -Port 8000 -Reload
```

The dedicated Windows launcher uses the existing .venv, binds **127.0.0.1**,
one worker, HTTP concurrency limit 32 and keep-alive timeout 5 seconds.
Python/temp settings change only in that process; no system setting changes.
No Spark/Java process, GPU job, cloud service, Docker, Kafka or Airflow is added.
Stop the foreground server with Ctrl+C. Validation's temporary server child
was terminated after verification; a persistent backend is not left running.

## Documented routes

Full query/payload/response contracts and examples are in
[API contracts](api_contract.md). Paths below are relative to `/api/v1`.

| Method / path | Behavior |
|---|---|
| GET `/health` | Process liveness, no artifact load |
| GET `/ready` | Gold/evaluation schemas, model integrity/version, and model/evaluation identity; 503 when not ready |
| GET `/fleet/overview` | Typed fleet observation/vehicle/trip, speed, supported-distance and quality metrics |
| GET `/vehicles` | Paginated vehicle metrics; optional powertrain filter |
| GET `/vehicles/{vehicle_id}` | One vehicle, or safe 404 |
| GET `/trips` | Pagination and vehicle/trip/powertrain filters |
| GET `/vehicles/{vehicle_id}/trips/{trip_id}` | Composite trip identity |
| GET `/trends/daily` | Inclusive trip-start reference-day cohort bounds |
| GET `/trends/monthly` | Inclusive stored month-start date bounds |
| GET `/fleet/powertrains` | Vehicle/trip/observation distribution and measured analytics |
| GET `/quality/summary` | Fleet summary plus bounded overlapping flag counts/fractions |
| GET `/ml/metrics` | Frozen model/baseline errors, selection and conditional vehicle-cluster intervals |
| GET `/ml/vehicle-errors` | Paginated per-vehicle model/baseline errors, split/method/vehicle filters |
| GET `/ml/features` | Exact 31-field order, units, nullability, bounds and prepared-input scope |
| POST `/ml/predict` | One complete prepared past-only feature vector |

Actual count reconciliation: **22,434,106** Gold source observations,
**384 vehicles**, **32,552 trips**, **375 days**, **13 months**, four powertrain
categories and five quality-flag rows. Default model-error page represents
**50 test vehicles**. Individual vehicle and composite-key trip responses
match their corresponding list records. No raw GPS, sensor trace or raw source
record endpoint exists. Stored missing aggregate values remain JSON null.

## Bounded data access, cache and public errors

Only existing small Gold Parquet and Day 6 evaluation/model artifacts are read.
No Bronze/Silver/CSV scan or analysis query recomputation occurs at API startup
or request time. Each analytics query owns a one-thread **128 MB** in-memory
DuckDB connection, with **32 MB** maximum project-local temporary spill.
SQL projects only the public schema fields, uses bound values for filters and
allowlisted tables/order keys. Query clients cannot supply SQL or file paths.

Default page size is 25, maximum 100; offset is bounded to 100,000.
Results use a **32-entry LRU**, invalidated by artifact size/mtime signatures.
Warm repeated fleet requests were verified to use the cache. Model/evaluation
are lazy caches; inference is serialized by a lock with the existing one-thread
prediction function. Evaluation JSON is size bounded to 2 MB and explicitly
projected rather than returning the private training-run record.

The model checks checksum, scikit-learn version and exact feature order through
the existing trusted-local loader. Readiness additionally requires its identity
to match saved evaluation. Corrupt/missing resource schemas or model integrity
fail safely; caches do not silently substitute missing files with synthetic data.
Cached artifact signatures assume local immutability and no concurrent publishing.

Normal API errors are safe JSON: 404 not_found, 422 invalid_request,
503 analytics/model/evaluation_unavailable, and generic 500 internal_error.
Prediction bodies, including chunked bodies, are capped at **65,536 bytes**
before JSON decoding; excess returns 413. Unknown/repeated query names fail
422. At most 16 sanitized validation fields/codes are returned; neither input
values nor path-like names, filesystem paths, secrets or tracebacks are echoed.
Server operators can see local logs; logs are not a response or Git artifact.
Readiness uses its documented boolean-component response on 503.

CORS permits **http://localhost:5173** and **http://127.0.0.1:5173** only,
GET/POST and Content-Type, without credential cookies. CORS is not authentication;
this is a local unauthenticated portfolio demo, not a publicly hardened service.
Approved-origin generic errors also receive CORS headers for the future client.

## Verified prediction contract

The body requires `input_kind=prepared_past_features`,
`feature_schema_version=ved-speed-1`, history_seconds=60, speed_unit=km/h,
acceleration_unit=m/s^2, time_unit=s, and **all 31 feature names**. Extra fields,
IDs, target, raw speed/timestamp lists, incomplete vectors, strings/booleans
in numeric fields, invalid units, NaN/infinity and required nulls are rejected
before model invocation. No conversions, clipping, filling or feature extraction
are performed. Only the six optional sensor means may be null, with matching
availability fraction zero. Missing means become native NaN for the saved model.

Checks validate integral observation count, <=2-second maximum gap and ability
to span 60 seconds, speed/acceleration extrema/variability, endpoint change,
stop statistics and sensor/count coherence. Signed battery current, temperature
and manufacturer load >100 retain the approved Silver semantics.

The complete-vector audit discovered a valid Day 5 interval fraction
`1.0000000000000002`. Fractions permit only **1e-12** upper rounding tolerance
and retain the original value, without modifying older outputs. A dedicated
regression test proves it reaches the prediction service without clipping.

Every existing **11,549 prepared vector** passes this contract.
The checked-in anonymous [request example](examples/day7_prediction_request.json)
uses an actual saved Day 5 training feature vector; its
[response example](examples/day7_prediction_response.json) predicts
**36.61748855856695 km/h**, equal to direct saved Day 6 inference.
It contains no ID, GPS, absolute timestamp or future label, and is an example
forecast, not an observed outcome or claim of accuracy.

```powershell
$taskBody = Get-Content -LiteralPath docs/examples/day7_prediction_request.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/ml/predict -ContentType application/json -Body $taskBody
```

Schema/coherence checks cannot prove a caller's true source history or future
exclusion. The caller is responsible for preparing the approved [t-60,t] vector
from valid telemetry. The API explicitly states that it cannot certify that
provenance. It does not fabricate a forecast from partial raw readings and does
not present a cohort bootstrap interval as an individual prediction interval.

## Model/evaluation limitations remain visible

The API reuses Day 6 metrics without changing them. Pooled test model MAE/RMSE
are 10.886851/14.090555 km/h, versus last-speed 14.056006/18.802985.
Sixteen of 50 test vehicles worsen, low/high-speed cohorts worsen, and the
paired vehicle-macro MAE-reduction interval crosses zero. **No EV is represented
in test.** These caveats are surfaced in `/ml/metrics`; prediction does not
retrain, recalibrate or imply universal vehicle/powertrain superiority.

## Automated and real-server verification

**99 tests passed; 0 failures; 0 errors**.
This comprises **52 Day 7 API tests** plus 47 relevant Day 3/4/5 fixture
regressions; no Day 6 estimator-training tests or full data processing are run.
JUnit suite runtime: **15.236 seconds**.
One nonblocking Starlette/AnyIO TestClient deprecation warning is recorded;
it is not suppressed and does not prevent API/server validation.

API fixtures cover all reads, typed OpenAPI, null semantics, pagination,
filtering/composite keys/dates, SQL-injection rejection, complete/invalid/raw
prediction requests, signed sensors, body limits including chunking, bounded
cache and invalidation, missing/corrupt resources, model/evaluation mismatch,
private-path/error redaction, approved/denied CORS, concurrent independent
connections, unknown/repeated queries and measured fraction rounding.

`scripts/validate_day7_actual.py` independently validates all saved feature
vectors, exercises all 15 resource paths against real artifacts, reconciles
counts and detail/list consistency, and checks direct-model/API equality.
It starts a real Uvicorn process on a free loopback port, verifies health,
readiness, overview, model metrics and prediction via HTTP, and terminates
only its own child. Live verification passed; no process is left running.

Every earlier raw/archive, Bronze, Silver, Gold, ML dataset, Day 1–6 result
and model artifact fingerprint matches before/after. Protected files are
enumerated in ignored `results/day7/actual_validation.json`; no hash map
or private path is returned by the REST API.

## Actual runtime, response sizes and storage

The following are single local TestClient requests in the final artifact check,
not load-test benchmarks. Some dependencies were warm; each list below explicitly
requests three rows, while the contract permits up to 100.

| Resource request | Status | Measured seconds | Response bytes |
|---|---:|---:|---:|
| `/health` | 200 | 0.001450 | 60 |
| `/ready` | 200 | 0.017931 | 107 |
| `/fleet/overview` | 200 | 0.015645 | 1,001 |
| `/vehicles?limit=3` | 200 | 0.014976 | 3,005 |
| `/trips?limit=3` | 200 | 0.018611 | 3,143 |
| `/trends/daily?limit=3` | 200 | 0.014672 | 3,063 |
| `/trends/monthly?limit=3` | 200 | 0.013406 | 3,155 |
| `/fleet/powertrains` | 200 | 0.013651 | 4,104 |
| `/quality/summary` | 200 | 0.011963 | 1,692 |
| `/ml/metrics` | 200 | 0.001495 | 4,296 |
| `/ml/vehicle-errors?limit=3` | 200 | 0.012857 | 459 |
| `/ml/features` | 200 | 0.001173 | 4,400 |
| `/ml/predict` | 200 | 0.018681 | 278 |

Full saved-vector/API/live-server verification runtime:
**7.755398 seconds**, excluding package installation,
Pytest and documentation rendering. Fresh loopback process to successful
health: **1.230589 seconds**. No fabricated
throughput, p95, concurrency-capacity or production-scale claim is made.

Logical total project storage at validated pre-commit snapshot:
**2,192,413,911 bytes (2.192414 GB decimal)**, including .venv, original
data, model, all results, scratch and Git. This is below preferred 5 GB and
maximum 10 GB. File length is not NTFS allocation. Final post-commit storage
and public remote hash are recorded in ignored publication metadata.

| Dependency | Installed version |
|---|---|
| fastapi | 0.115.12 |
| starlette | 0.46.2 |
| pydantic | 2.11.7 |
| uvicorn | 0.34.3 |
| httpx | 0.28.1 |
| duckdb | 1.4.4 |
| scikit-learn | 1.7.2 |
| anyio | 4.15.1 |

FastAPI/Starlette/Pydantic/Uvicorn and HTTPX test support were installed only
inside the project .venv through the configured approval mechanism; direct
versions are pinned. `pip check` passes. NumPy/model library versions and prior
model artifacts are preserved. No Node/React dependencies or system software
are installed. HTTP API serving does not require an external service; Swagger
UI assets may load from its default CDN while OpenAPI JSON remains local.

## Publication and scope boundary

Public deliverables: backend source, tests, pinned dependencies, Windows launcher,
API contract, two small anonymous request/response examples, README/architecture/
scope updates and this measured report. All data/Parquet/archives, .venv, caches,
secrets, logs, model binaries and generated evaluation results remain ignored.
Pre-stage and exact-index audits precede the authorized ordinary origin/main
push; no history rewrite, force push or dataset/model upload is permitted.

Limitations: this is loopback-only and unauthenticated; CORS is not an access
control system. Requests require prepared features whose caller provenance
cannot be verified. Source/reference dates have no verified timezone. Cache
signatures assume immutable artifacts; concurrent multi-file regeneration is
unsupported. The model's Day 6 coverage/EV/subgroup caveats remain. Swagger UI
may need CDN access. No frontend or public deployment is supplied.

**No unresolved Day 7 blocker. Stop after Day 7.** No React or Day 8 development
started. Publication status and final commit are confirmed after the audit.
