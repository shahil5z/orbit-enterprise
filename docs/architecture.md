# Architecture

Layers:
1. Sources: a synthetic generator (`pipelines/`, seeded) produces CRM, ERP, finance, HR and operations datasets in CSV, JSON and Parquet under data/raw.
2. Pipeline: `pipelines/orchestrator.py` runs INGEST, VALIDATE, TRANSFORM, CURATE (Spark), ANALYZE, TRAIN, PREDICT, RISK, OPTIMIZE, DECISION and PUBLISH. Every stage is recorded in data/runs and in pipeline_runs.
3. Storage: Parquet zones (raw, staging, curated, outputs) plus PostgreSQL 17 (core tables and run outputs).
4. Compute: Python (pandas, scikit-learn), Spark/Scala for curation, R for statistics, Rust for batch scoring, C++ for Monte Carlo and Julia/JuMP/HiGHS for optimization.
5. Decision: `decision/engine.py` combines rules with the evidence. It does not use an LLM.
6. Serving: FastAPI (`apps/api`) reads PostgreSQL. The Java JDK HttpServer (`services/java`) exposes the CRM/ERP integration APIs.
7. Web: the TypeScript client and types in `apps/web` (foundation only).
