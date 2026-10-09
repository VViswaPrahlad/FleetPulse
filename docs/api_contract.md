# FleetPulse REST API contract

Local base URL: `http://127.0.0.1:8000/api/v1`. API version: v1;
application version: 1.0.0. OpenAPI is at `/openapi.json`, interactive API docs
at `/docs` and `/redoc` (outside the versioned resource prefix).
The approved product architecture is **React + TypeScript / FastAPI**.
Day 7 implements the backend only; no React application exists yet.

## Run on Windows

Use the existing project `.venv` and local artifacts:

```powershell
.\scripts\run_backend.ps1
# Optional development reload; watches src/api only, not datasets or .venv:
.\scripts\run_backend.ps1 -Port 8000 -Reload
```

Equivalent command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --limit-concurrency 32 --timeout-keep-alive 5
```

Stop with Ctrl+C. The launcher changes Python/temp settings only for its
process. No Java, ETL, training job, Docker or external service starts.
The server binds loopback by default. Swagger UI assets may require a network
connection; the API and OpenAPI JSON use only local data.

## Resources

All paths below are relative to `/api/v1`.

| Method / path | Query parameters | Contract |
|---|---|---|
| `GET /health` | none | Process liveness; does not require artifacts |
| `GET /ready` | none | 200 if Gold, model, evaluation and model/evaluation identity are ready; otherwise 503 with component booleans |
| `GET /fleet/overview` | none | Typed Gold fleet metrics; units in column suffixes |
| `GET /vehicles` | limit, offset, powertrain | Stable vehicle-ID pagination |
| `GET /vehicles/{vehicle_id}` | none | One vehicle, 404 when absent |
| `GET /trips` | limit, offset, vehicle_id, trip_id, powertrain | Stable (vehicle_id, trip_id) pagination |
| `GET /vehicles/{vehicle_id}/trips/{trip_id}` | none | Composite trip key; trip IDs are not fleet-wide unique |
| `GET /trends/daily` | limit, offset, start_date, end_date | Inclusive date bounds on trip-start reference day |
| `GET /trends/monthly` | limit, offset, start_date, end_date | Inclusive bounds on the stored month-start date |
| `GET /fleet/powertrains` | limit, offset | Vehicle/trip/observation distribution and analytics by engine type |
| `GET /quality/summary` | none | Fleet metrics and bounded flag page; flags overlap |
| `GET /ml/metrics` | none | Frozen model selection, baseline comparisons and vehicle-cluster intervals; no private artifact metadata |
| `GET /ml/vehicle-errors` | limit, offset, split, method, vehicle_id | Per-vehicle errors; defaults to test/model |
| `GET /ml/features` | none | Exact ordered 31-feature contract, per-feature units, nullability and bounds |
| `POST /ml/predict` | none | One fully prepared past-only feature vector; no raw readings or batch inference |

Limits: default `limit=25`, maximum 100, minimum 1; offset 0–100,000.
IDs are nonnegative integers up to 2,147,483,647. Allowed powertrain filters:
`ICE`, `HEV`, `PHEV`, `EV`. Model-error splits: `validation`, `test`; methods:
`hist_gradient_boosting`, `last_observed_speed`, `past_mean_persistence`,
`training_historical_mean`. Unknown or repeated query names are rejected,
not silently ignored. Filters are parameterized; ordering/table names are
allowlisted. No endpoint accepts SQL, a file path or a model upload.

Dates use `YYYY-MM-DD`. Reversed bounds are invalid. Daily/monthly dates are
whole-trip **dataset-reference trip-start cohorts**, timezone unspecified;
they are not wall-clock traffic rates. Monthly bounds compare month-start
dates, so `start_date=2017-11-20` excludes the November 1 cohort.
Distance is the Day 4 partial measured-interval integral, not full-trip mileage.
Missing aggregate values are JSON null, never fabricated zero or JSON NaN.

Every page has the same envelope:

```json
{"items": [], "total": 384, "limit": 25, "offset": 1000}
```

This illustrative empty page uses an offset beyond the actual vehicle count.
`total` is the matching count before pagination. All records are explicitly
projected into public response schemas; raw paths/provenance are not exposed.

## Prepared prediction input

The endpoint does **not** accept a speed/time series, reconstruct missing
history, calculate a new feature window or guess sensor readings. The caller
must already have the complete Day 5 past-only feature vector. Every one of
the 31 names is required; no unknown field, vehicle ID, target or future value
is allowed. Six optional sensor means may explicitly be `null`; their matching
observed fractions must be zero. Other features cannot be null. JSON numeric
values are required; numeric strings, booleans, NaN and infinities are rejected.
No unit conversion, clipping, imputation or preprocessing change occurs.

The request envelope requires:

```json
{
  "input_kind": "prepared_past_features",
  "feature_schema_version": "ved-speed-1",
  "history_seconds": 60,
  "speed_unit": "km/h",
  "acceleration_unit": "m/s^2",
  "time_unit": "s",
  "features": {"...": "all 31 fields from /ml/features"}
}
```

The excerpt above describes structure and is intentionally not a valid request.
Use the complete, tested [request example](examples/day7_prediction_request.json)
and [actual saved-model response](examples/day7_prediction_response.json).
The request derives from one anonymous verified Day 5 training feature vector,
not synthetic or incomplete raw telemetry. It contains no ID, GPS, timestamp
or future label; its returned forecast is an actual model prediction, not an
accuracy claim or future ground truth.

```powershell
$taskBody = Get-Content -LiteralPath docs/examples/day7_prediction_request.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/ml/predict -ContentType application/json -Body $taskBody
```

Prepared-statistic consistency checks include integral observation count
(31–60,001), maximum past gap 0.001–2 seconds, ability to span 60 seconds,
speed/acceleration extrema and variability, endpoint change, stop counts,
and sensor availability/count agreement. Fractions mathematically lie in
[0,1]; upper-bound rounding up to **1e-12** is accepted without changing the
value, covering the actual stored `1.0000000000000002` interval fraction.
SOC is bounded to [0,100]; signed battery current and temperature are preserved;
manufacturer load above 100 is accepted as in Silver. Do not round measured
fractions/derived features before sending them.

The ordered feature names and units appear in OpenAPI and `GET /ml/features`.
Schema and coherence checks cannot prove the client's source history, sensor
authenticity or past-only provenance. The caller remains responsible for exact
observed t−60/t endpoints, valid chronology, no missing speed and <=2-second
gaps, using the approved feature function. The API warning states this limit.
It exposes a point estimate, not an individual forecast confidence interval.

## Errors, availability and CORS

Normal API errors have a bounded JSON envelope:

```json
{"error":{"code":"model_unavailable","message":"The forecasting model is unavailable."}}
```

| Status | Meaning |
|---|---|
| 200 | Valid read or prediction |
| 400 | Invalid content length; CORS preflight can also return its standard denial |
| 404 | Unknown route or absent vehicle/trip |
| 413 | Prediction body exceeds 65,536 bytes, including chunked bodies |
| 422 | Invalid query, date bounds, units, feature types/names/nulls or coherence |
| 503 | Required analytics, evaluation or model dependency unavailable |
| 500 | Unexpected server failure, with fixed safe message |

Validation details include at most 16 sanitized field locations/error codes.
Input values, arbitrary path-like field names, exceptions and internal
tracebacks are never returned. Readiness intentionally uses
`{"ready":false,"components":{...}}` with 503 rather than the error envelope.
Missing resources do not prevent `/health` or OpenAPI availability; independent
routes remain usable if their own dependencies exist. Metrics remain historical
evaluation even if the model is missing; readiness flags that condition.

Allowed future React origins: `http://localhost:5173` and
`http://127.0.0.1:5173`. GET/POST, Content-Type, no credential cookies or
wildcard origins. CORS is a browser policy, not authentication. This is an
unauthenticated **local portfolio demo**, not a publicly hardened deployment.

## Caching and data access

Each analytics request owns a one-thread, 128 MB in-memory DuckDB connection.
It selects existing Gold/evaluation Parquet only, with at most 100 rows in a
response and project-local temporary storage capped at 32 MB. Reusable results
use an LRU capped at 32 query entries, invalidated by file size/mtime signatures.
Evaluation JSON is bounded to 2 MB and cached; model loading is lazy and cached,
with hash/version/feature-order checks and a lock for shared CPU inference.
Readiness reads small artifact schemas/metadata, never raw/Bronze/Silver telemetry.

Import/startup creates lightweight service objects only; no ETL, full telemetry
scan or model fit occurs. Cache signatures assume locally immutable artifacts;
restart after intentional publishing/replacement. Concurrent multi-file artifact
regeneration is not supported. No network dependency is required to serve data.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_day7_api.py -q --basetemp=data/tmp/pytest-day7
.\scripts\run_day2.ps1 -Script scripts/validate_day7_actual.py
```

The second command validates all existing prepared vectors, real response
reconciliation, exact saved-model/API inference, and a temporary loopback
Uvicorn child. It terminates its own child and checks earlier artifact hashes.
It writes only Day 7 verification outputs and anonymous API examples.
