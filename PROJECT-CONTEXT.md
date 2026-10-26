# PROJECT-CONTEXT

Last updated: 2026-10-26 (Asia/Calcutta).
- Phase 1 (platform) is complete, commit 2ad2333.
- Phase 2 (frontend, BI, KPI governance) is complete: see the Phase 2 commit.
- Phase 3 (audit, GitHub, deploy) is NOT STARTED and is not authorized yet.

## State
- VERIFIED (laptop): pipeline run `20261026T160340Z-f5255777`, all 11 stages SUCCESS.
- VERIFIED (laptop): the test suites pass.
  - pytest: 115 passed, 0 skipped. This includes `tests/test_phase2.py`: the KPI catalogue, the scenario model, endpoint validation, live endpoints and the BI export.
  - Web: vitest 24 passed. `eslint src e2e` reported 0 problems. `tsc --noEmit` exit 0. `vite build` exit 0.
- VERIFIED (laptop): Playwright passed 7 of 7 against the production build and the live API:
  - 4 journeys:
    - overview > anomaly > forecast > risk > recommendation
    - optimization (real Julia/HiGHS) > compare
    - risk > evidence > recommendation
    - data quality > pipeline status
  - Every page loads with no console errors and no horizontal overflow at 1440x900, 1280x720 and 820x1180.
- VERIFIED: 14 real screenshots are in `docs/screenshots`. They were captured on the laptop against the live API.
- NOT VERIFIED: auth, deployment, concurrency and load, behavior on real data, and the Tableau / Power BI / QlikView guides (none of the tools are installed).

## MEASURED (laptop, single client, warm process; median of 5 after 1 discarded call)
| Endpoint | First call | Median |
|---|---|---|
| intelligence (unfiltered) | 4.9 s (uncached) | 41 ms (cached) |
| intelligence?region_id=R04 | 1.1 s | 39 ms |
| overview | | 517 ms |
| risks/region/R04 | | 491 ms |
| search | | 339 ms |
| operations/summary | | 231 ms |
| other GETs | | 9 to 180 ms |
| POST optimization/run (Julia process start + solve) | | 5.9 s |

- The intelligence cache is keyed by the latest pipeline run id. One GROUPING SETS scan replaced 7 scans over 384k transactions; it was checked equal to the old queries.
- Bundle (vite build, gzip):
  - react 54.4 kB
  - charts (Recharts) 112.5 kB
  - app shell 8.6 kB
  - CSS 4.5 kB
  - each page 1.3 to 3.4 kB (lazy loaded)

## Frontend rules
- Only `apps/web/src/services/http.ts` may call `fetch`. ESLint `no-restricted-globals` enforces this, and a probe confirmed the rule fires.
- No hard-coded business data in the UI. Every number comes from `/api/v1`.
- Risk levels and statuses are always text. Colour is only a supplement.
- Forecast model: ridge_yoy, test MAPE 9.0% vs seasonal naive 15.3%. The naive baseline wins in R01, R02, R03 and R06, and the Forecasts page shows this per region.

## Toolchain (VERIFIED versions)
- Python 3.13.15, Java 21.0.12, Node 24.20.0, Git 2.55.0, g++ 16.2.0, rustc 1.99.1, R 4.6.1, Julia 1.11.7 (JuMP 1.32.1, HiGHS 1.26.1), Spark 4.0.4, PostgreSQL 17.7 portable, TypeScript 5.9.3.
- Web: React 18, Vite 6.0.7, Vitest 3.0.5, Playwright (chromium build 1148 in `.tools\ms-playwright`).

## Gotchas
- The `&` in the folder path breaks `.cmd` shims, so `orbit.ps1` calls the node scripts directly (npm-cli.js, vite.js, cli.js).
- Do not pipe `orbit.ps1` through `2>&1` in Windows PowerShell 5.1. Native stderr warnings become terminating errors.
- Background servers started from a remote shell session die when that session ends. Start the API and preview in the same session as e2e.
- npm reports that the esbuild postinstall is not approved under allowScripts. The build works anyway, because the platform binary package ships prebuilt.

## Phase 3 remaining
- Security audit:
  - Authentication and authorization (none today)
  - Rate limiting
  - Dependency audit
  - CSP headers
- GitHub push and CI (pytest, vitest, eslint, build, Playwright). Phase 3 needs approval for this.
- Vercel or other deployment of the web build, plus a hosted API and a hosted database. Phase 3 needs approval for this too.
- Performance:
  - Warm the intelligence cache at startup, or pre-aggregate transactions in the pipeline.
  - Split the Recharts chunk.
  - Profile overview and risks/region (about 0.5 s).
- Add a KPI catalogue entry for the `cost` metric.
- Manually test the BI tool guides in Tableau, Power BI and QlikView.
- Real-data connectors. All data is a simulated enterprise dataset.
