# Technology rationale

- Python: pipeline, ML and API (a mature ecosystem).
- Spark/Scala: curation, so the design scales past one machine (locally it is overhead).
- PostgreSQL: relational serving store.
- R: statistical tests.
- Rust: a fast, safe batch scorer (24x to 30x measured).
- C++: Monte Carlo throughput.
- Julia/JuMP/HiGHS: concise LP/MIP modeling with an open solver.
- Java: an enterprise integration service with no dependencies (JDK HttpServer).
- TypeScript: a typed API client for the Phase 2 frontend.
