# API

FastAPI, base `/api/v1`. Responses use the envelope `{success, data, metadata, errors}`.

Endpoints (all VERIFIED 200 on 2026-10-26):
- health, data/quality, metrics, analytics, forecasts, anomalies, risks, recommendations
- optimization, optimization/{id}, models, models/{version}, operations, operations/runs/{id}
- POST optimization/run returns 201

Errors:
- 400 bad value, 404 not found, 409 optimization already running, 422 validation, 503 database down, 500 sanitized

Java integration service (port 8081, VERIFIED 200 on /health and /api/crm/accounts):
- /health
- /api/crm/accounts, /api/crm/accounts/{id}
- /api/erp/suppliers
- GET/POST /api/erp/purchase-orders
