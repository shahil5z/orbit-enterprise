# Data model

PostgreSQL schema is in `database/migrations`. There are 10 core tables (regions, departments, customers, products, suppliers, employees, sales transactions, operations events, finance ledger, purchase orders) and run tables: pipeline_runs, stage_runs, data_quality_results, metrics, model_runs, forecasts, predictions, risks, optimization_runs and recommendations. All writes go through parameterized SQL in `database/seeds/load.py`. Measured on the last run: PUBLISH loaded 467,465 rows.
