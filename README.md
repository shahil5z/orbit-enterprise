# ORBIT // ENTERPRISE

![ORBIT](logo.png)

ORBIT is a local, end-to-end enterprise data and decision intelligence platform. It covers simulated multi-source data, ingestion, quality gates, a Spark curation step, analytics, ML models, risk scoring, optimization, decision recommendations, a FastAPI backend, a Java integration service and a TypeScript web foundation. Phase 1 is backend and platform only. The full frontend is Phase 2.

## Quick start (Windows PowerShell, from the project root)

```powershell
. .\scripts\env.ps1                 # puts the portable tools from .tools on PATH
.\scripts\orbit.ps1 versions        # prints the toolchain versions
.\scripts\orbit.ps1 db-start        # starts portable PostgreSQL 17 on port 55432
.\scripts\orbit.ps1 migrate; .\scripts\orbit.ps1 seed
.\scripts\orbit.ps1 pipeline        # all 11 stages (add -Regenerate for fresh data)
.\scripts\orbit.ps1 test            # pytest suite
.\scripts\orbit.ps1 api             # FastAPI on http://127.0.0.1:8000/api/v1
.\scripts\orbit.ps1 java            # Java integration service on http://127.0.0.1:8081
.\scripts\orbit.ps1 web-check       # TypeScript type check and build
```

All tools live in `.tools\` (gitignored). Nothing is installed system-wide. Copy `.env.example` to `.env` and set the local database values.

See `docs/` for the architecture, data model, pipeline, ML, decision, optimization, API and technology notes, plus `PROJECT-CONTEXT.md` for the current verified state.

All data is synthetic, and the metrics describe models trained on simulated data.
