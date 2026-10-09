# Deployment-preparation source review

**Historical checkpoint:** this review preceded the owner's successful Render deployment. Current [live links and project status](../README.md#live-deployment) are in the README; the pre-deployment blockers below describe the original checkpoint.

Reviewed locally on **2026-10-09**, from `main` at **2dc4fa1**. This review covers source/configuration publication only. No Render service, release asset, deployment bundle or public-profile update is published. The generated bundle stays local and ignored.

## Files reviewed for the preparation commit

The starting working tree contained seven modified files and sixteen untracked files, all belonging to deployment preparation. The review adds this document.

| Area | Files |
|---|---|
| Platform configuration | `render.yaml` |
| Deployment tooling | `deploy/__init__.py`, `deploy/app.py`, `deploy/audit_runtime.py`, `deploy/build_frontend.mjs`, `deploy/bundle.py`, `deploy/fetch_bundle.py`, `deploy/start.py`, `deploy/validate_bundle.py` |
| Runtime dependencies | `deploy/requirements-runtime.txt`, `deploy/requirements-runtime.lock` |
| Backend runtime separation | `src/runtime.py`, `src/api/settings.py`, `src/api/services/analytics.py`, `src/ml/inference.py` |
| Frontend public configuration | `dashboard/src/api.ts`, `dashboard/src/App.tsx`, `dashboard/src/vite-env.d.ts` |
| Validation | `dashboard/scripts/smoke-built.mjs`, `dashboard/src/test/deployment.test.ts`, `tests/test_deployment.py` |
| Documentation | `README.md`, `docs/deployment_guide.md`, `docs/deployment_review.md` |

No CSV, Parquet, archive, model binary, environment, cache, private configuration or generated result file is part of the commit. Existing lightweight evaluation figures are unchanged. Ignore rules and both working-file/index audits guard the publication boundary.

## Consistency and review fixes

- Render configuration was reviewed against the [official Blueprint reference](https://render.com/docs/blueprint-spec): Python Free Web Service, Static Site, explicit runtime versions, root-level commands, SPA rewrite, HTTP health check, no disk/database and both automatic deploy triggers off. No remote Blueprint validation/application or service creation was invoked.
- The backend start script binds `0.0.0.0:$PORT`, limits native pools before import, uses one worker and validates bundle/model/evaluation resources before serving. Artifact download happens during build only.
- The twelve direct serving dependencies match the twenty-four-package Linux lock and its dependency closure. Actual imports exclude Spark, training, plotting and test packages. Wheel checks now use concrete CPython 3.12/Linux tags and Python requirements, excluding incompatible Windows or newer-Python ABI wheels. This is metadata validation, not Linux execution.
- Local settings retain the original root, CORS, cache and 128 MB DuckDB budget, including their prior positional constructor order. Public settings use an isolated bundle root, one strict HTTPS frontend origin, cache 16 and 32 MB DuckDB budget.
- Bundle paths are confined to the dedicated generated root, preventing traversal or resolved junction paths from reaching original artifacts. Missing/invalid expected SHA-256 fails before a download; archive CRC/member/hash checks remain enforced. Integrity/path tests cover these boundaries.
- Frontend production configuration requires an explicit HTTPS API origin. The local relative `/api/v1` default, page behavior and previously committed one-click Prediction Lab remain unchanged. Public-only labels/errors describe historical analytics and wake/retry behavior.
- Documentation was refreshed for the approved source-only publication boundary, current Quick Demo and the latest measured checks. Actual service URLs, bundle upload and live acceptance remain future manual steps.

## Actual validation

| Check | Result |
|---|---|
| Relevant Python suites | **90 passed**, 16.96 s, zero skipped |
| Complete frontend suite | **41 passed**, 18.33 s |
| Strict TypeScript | Passed |
| Local production build | Passed, Vite phase **2.38 s** |
| Separate public-URL production build | Passed, Vite phase **2.35 s** |
| Runtime lock/import/official wheel audit | Passed, **24 packages** |
| Installed dependency check | `pip check` passed |
| Original-source versus bundle API | **23 contracts identical** |
| Saved-model inference | **36.61748855856695 km/h**, unchanged |
| Compiled-page healthy / unavailable flows | All **five pages** passed; Quick Demo sends the verified example to the real local API |
| Prior artifact preservation | **278 files byte-identical**, including data/model/Day 1–10 results |

Python emitted 74 known dependency deprecation warnings. Model tests fit only tiny synthetic fixtures, not the production model. Vite reports that the separate generated public outDir is not emptied; the smoke helper selects the actual current HTML entry rather than an old chunk. No important generated data was deleted to suppress that warning.

The artifact archive remains **2,611,636 bytes**, expanded **2,730,328 bytes**, with unchanged SHA-256 **16acf6172c6174f7802886c2e81a032d637ed24ee1bd838af2c9a6add39d7565**. Repeated builds produce identical bytes; original Gold/model files are copied without alteration and reports select genuine existing values.

The review's local serving-process startup reached health in **1.753515 s**; end-to-end bundle validation took **6.646928 s**. Warm process-tree working set was **220,397,568 bytes**, with **234,520,576 bytes** sampled during four concurrent queries. The 250–350 MB estimate for light public traffic remains an estimate; Windows samples do not validate Render's Linux memory accounting or CPU behavior.

New evidence resides under ignored `results/deployment/`. The final exact source index is audited before a normal commit/push to `origin/main`; the resulting commit SHA, remote-head equality and working-tree status are verified in the final handoff. No history is rewritten.

## Remaining deployment blockers

1. The serving-only archive has **not** been approved for upload or published. Build-time bundle URL/hash must be supplied later.
2. No Render resources or actual frontend/backend HTTPS origins exist yet. Billing/usage controls must be checked before service creation; free compute does not guarantee absence of quota overage charges.
3. Linux installation, live startup/memory/TLS/CORS and idle-wake behavior are unverified until an approved deployment is observed.
4. Browser tools expose no enabled surfaces. Compiled DOM/CSS checks do not establish desktop/mobile pixels or chart rendering; the [manual visual checklist](demo_guide.md#manual-browser-sign-off) remains pending.

These are explicit deployment prerequisites, not claims that local preparation failed. See the [deployment guide](deployment_guide.md) for exact settings and the manual sequence. Publishing this preparation code does not deploy it.
