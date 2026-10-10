# RollbackIQ incident console

A read-only React + TypeScript + Tailwind view over the control-plane API
(`backend/app/api/incident_api.py`), which serves the incident document assembled
from the committed evidence artifacts in `evidence/`.

Every number the console shows arrived from an artifact the pipeline or the Duo
flow actually wrote. The console cannot approve, execute or verify anything, and
it says so.

## Views

| View | Shows |
| --- | --- |
| Overview | current release and digest, baseline, detection breaches, verification verdict, p95 across the incident |
| Timeline | deploy → baseline → windows → detection → approval → rollback → verification → Duo audit, all UTC |
| Investigation | the Duo flow's session record, the audit note it posted, the detector's reasons, the nature of the regression |
| Approval centre | the approval record (actor, decision, scope, expiry) and all 18 safety-gate checks |
| Verification | independent post-rollback window, before/after comparison, independence timestamps |
| Incident report | evidence links, pipeline jobs, and what the report explicitly does not claim |

## Run it

```bash
# 1. API (serves /api/... and, once built, the dashboard itself)
.venv/bin/uvicorn app.api.incident_api:app --app-dir backend --port 8000

# 2. Dashboard, either built and served by the API:
cd dashboard && npm install && npm run build   # -> dashboard/dist, mounted at / by the API
#    or as a dev server with the API running:
npm run dev                                    # http://localhost:5173, proxies /api to :8000
```

## Checks

`npm run build` runs `tsc --noEmit` (strict) before Vite builds, so a type error
fails the build. The API's own faithfulness tests live in
`backend/tests/test_incident_api.py` and run with the rest of the suite:

```bash
.venv/bin/python -m pytest -q
```
