# Data model

PostgreSQL schema is in `database/migrations`. There are 10 core tables (organizations, regions, business_units, products, customers, suppliers, employees, transactions, operations, incidents), 9 run tables (pipeline_runs, data_quality_runs, metrics, model_runs, forecasts, predictions, risks, optimization_runs, recommendations) and an `artifacts` table for JSON outputs. All writes go through parameterized SQL in `database/seeds/load.py`.

## Row counts

Two different counts appear in this project. They measure different scopes.

- **PUBLISH stage rows (467,465 for run 20261026T190344Z-3ee718d0).** The `records_processed` of the PUBLISH stage is the sum of the rows `seed_core()` reloads into the 10 core tables (421,561) and the rows `persist_outputs()` writes for that one run (45,904: predictions 35,009, metrics 10,800, forecasts 36, risks 36, data_quality_runs 11, recommendations 7, model_runs 4, optimization_runs 1). It does not include `pipeline_runs`, which is written after the stages finish, or rows kept from earlier runs.
- **Total persisted rows (537,561 across the 19 tables after the 2026-10-27 publish).** `database/seeds/publish.py` copies every table as it is in the local warehouse. Per-run tables keep history from earlier runs: predictions 105,027 (3 runs x 35,009), recommendations 21 (3 x 7), data_quality_runs 33 (3 x 11), pipeline_runs 33 (3 runs x 11 stages) and optimization_runs 10 (pipeline and API solves). That adds 70,096 rows: 467,465 + 70,096 = 537,561. The `artifacts` table (7 JSON documents) is counted separately.

The API serves the latest run; history rows remain for lineage and the run history views.
