# PROJECT-CONTEXT

Last updated: 2026-10-26 (Asia/Calcutta). Phase 1 complete. Phase 2 (frontend) and Phase 3 (audit, GitHub, deploy) are NOT STARTED.

## State
- VERIFIED: the full pipeline run `20261026T160340Z-f5255777` (with --regenerate) finished all 11 stages with SUCCESS in about 54 s.
- VERIFIED: pytest 77 passed, 0 skipped. Java SelfTest 21/21. cargo test 2/2. tsc --noEmit exit 0.
- VERIFIED: every API endpoint returned 200. A bad query returned 422 and POST /optimization/run returned 201. Java /health and /api/crm/accounts returned 200.
- NOT VERIFIED: production deployment, auth, load and performance under concurrency, behavior on real data.

## Toolchain (VERIFIED versions)
Python 3.13.15, Java 21.0.12, Node 24.20.0, Git 2.55.0, g++ 16.2.0 (w64devkit), rustc 1.99.1, R 4.6.1, Julia 1.11.7 (JuMP 1.32.1, HiGHS 1.26.1), Spark 4.0.4 / Scala 2.13.16, PostgreSQL 17.7 portable, TypeScript 5.9.3.

## Known deviations
- Rust and C++ live under `analytics/rust` and `analytics/cpp`.
- An extra PUBLISH stage loads outputs into PostgreSQL.
- Correlations in the simulated data are high by construction.
- Optimization coefficients are planning assumptions, not fitted values.

## Gotchas
- The `&` in the folder path breaks `.cmd` shims. Call `node node_modules\typescript\bin\tsc` directly.
- Rust links with the self-contained MinGW linker of its sysroot (see `analytics/rust/scoring.py` cargo_env).
