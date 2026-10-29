# FleetPulse

**Automotive Telemetry Analytics & Machine Learning Platform**

Transforming real vehicle telemetry into auditable fleet analytics and next-minute speed forecasts with **PySpark, DuckDB, scikit-learn, FastAPI, and React**.

[**🚀 Live Dashboard**](https://fleetpulse-dashboard.onrender.com) · [**API Docs**](https://fleetpulse-api-got2.onrender.com/docs) · [**Demo Walkthrough**](docs/demo_guide.md)

> **Live demo:** Visit **Prediction Lab → Run example prediction** to call the deployed model using a verified prepared feature vector. Expected output: approximately **36.62 km/h**. Render's free API may need about a minute to wake after inactivity.

## Recruiter demo — no installation required

1. Open **Live Dashboard** above.
2. Select **Prediction lab** in the sidebar, then **Run example prediction** in Quick Demo. No feature entry is needed. Expect **36.62 km/h**, the predicted mean speed for the next 60 seconds.
3. Open **API Docs** above to inspect the typed contract (optional).

If the API is asleep, wait about a minute. If an error appears, use the affected page's **Retry request**, then run the example again. Header **Retry** checks connectivity only; it does not reload page data. If loading persists, reload the dashboard root and navigate via the sidebar. A saved [request](docs/examples/day7_prediction_request.json) and [response](docs/examples/day7_prediction_response.json) are historical evidence, not a substitute for a successful live call. See the [walkthrough and current verification status](docs/demo_guide.md).

## At a glance

| Data engineering | Machine learning |
|---|---|
| **22,436,808** ingested telemetry records | **10.887 km/h** held-out test MAE |
| **22,434,106** retained Silver records | **14.091 km/h** held-out test RMSE |
| **384** vehicles · **32,552** trips | **22.55% lower test MAE** than last-observed-speed baseline |

The source is the [Vehicle Energy Dataset (VED)](https://github.com/gsoh/VED), an historical real-world telemetry dataset. The figures above reflect inspected project artifacts; the source README's reported vehicle count differs from the **384 distinct vehicle IDs** found in the ingested files.

## How it works

~~~mermaid
flowchart LR
    VED[VED telemetry] --> Spark[PySpark ETL]
    Spark --> B[Bronze]
    B --> S[Silver + quality checks]
    S --> G[Gold Parquet]
    G --> DB[DuckDB analytics]
    DB --> API[FastAPI]
    API --> UI[React dashboard]
    S --> Feat[Past-only features]
    Feat --> Eval[Vehicle-held-out ML evaluation]
    Eval --> Model[Saved forecasting model]
    Model --> API
~~~

- **Data pipeline:** Bronze retains source provenance, Silver standardizes observations and quarantines invalid records, and Gold produces queryable fleet, vehicle, trip, and quality summaries.
- **Analytics:** DuckDB and SQL power fleet overviews, driving patterns, and data-quality views without sending raw telemetry to the browser.
- **Forecasting:** A scikit-learn HistGradientBoosting model uses **31 past-only features from the preceding 60 seconds** to predict mean speed over the **next 60 seconds**.
- **Application:** FastAPI exposes versioned endpoints; the React/TypeScript dashboard provides fleet insights, ML evaluation, and predictions.

[Detailed architecture](docs/architecture.md) · [Data-quality rules](docs/day3_report.md) · [SQL examples](sql/README.md)

## ML evaluation

Vehicles are separated between training, validation, and test sets to prevent vehicle overlap. The final **1,919 test examples represent 50 held-out vehicles**.

| Model | Test MAE (km/h) | Test RMSE (km/h) |
|---|---:|---:|
| Last-observed-speed baseline | 14.056 | 18.803 |
| **HistGradientBoosting** | **10.887** | **14.091** |

**Scope matters:** These are pooled offline results, not a claim of production-ready forecasting. Performance worsens for **16 of 50** test vehicles, low/high-speed cohorts can fare worse, and EVs are absent from the test set. See the [full evaluation and uncertainty analysis](docs/day6_report.md) for vehicle-level results and confidence intervals.

## Tech stack

| Layer | Technologies |
|---|---|
| Data engineering | Python, PySpark, PyArrow, Apache Parquet |
| Analytics | DuckDB, SQL, Pandas |
| Machine learning | scikit-learn, NumPy |
| Backend | FastAPI, Pydantic, Uvicorn |
| Frontend | React, TypeScript, Vite, Tailwind CSS, Recharts |
| Quality & hosting | Pytest, Vitest, Render |

## Run locally

The validated environment uses **Python 3.12**, **Node.js 24**, and **JDK 21** for Spark reconstruction. On Windows PowerShell:

~~~powershell
git clone https://github.com/VViswaPrahlad/FleetPulse.git
cd FleetPulse
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci --prefix dashboard
~~~

With the required local data and model artifacts already prepared, start the backend and frontend in **separate terminals**:

~~~powershell
.\scripts\run_backend.ps1
~~~

~~~powershell
.\scripts\run_frontend.ps1
~~~

Open **http://127.0.0.1:5173**. **Important:** the public Git repository intentionally excludes raw data, generated Parquet outputs, and model binaries; cloning alone does **not** reproduce the live analytics or prediction results. Follow the [fresh-machine setup and artifact reconstruction guide](docs/demo_guide.md) for a complete local run.

## Documentation

| Want to explore… | Read |
|---|---|
| Architecture, data boundaries, and artifact flow | [Architecture](docs/architecture.md) |
| Dataset validation and cleaning decisions | [Data quality report](docs/day3_report.md) |
| Forecasting methodology, held-out evaluation, and limitations | [ML evaluation](docs/day6_report.md) |
| API request schemas and prediction contract | [API contract](docs/api_contract.md) |
| Local setup, live demo walkthrough, and interview talking points | [Demo guide](docs/demo_guide.md) · [Interview Q&A](docs/interview_qa.md) |
| Testing and deployment checks | [Deployment review](docs/deployment_review.md) |
| Render deployment and verified runtime-bundle setup | [Deployment guide](docs/deployment_guide.md) |

**Deployment note:** The [live dashboard](https://fleetpulse-dashboard.onrender.com) uses Render's free hosting tier. The API can sleep while idle; retry once it wakes. This is a portfolio demonstration, not a continuously available production fleet service.

**Data attribution:** [VED source and Apache-2.0 dataset license](https://github.com/gsoh/VED). FleetPulse keeps source artifacts and trained binaries out of Git; see the linked documentation for reproducibility and measurement caveats.
