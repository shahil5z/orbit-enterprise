# Data pipeline

Run with `python -m pipelines.orchestrator all [--regenerate] [--run-id ID]` or with individual stage names.

MEASURED, run 20261026T160340Z-f5255777:
- INGEST 421,862 records
- TRANSFORM 383,967
- CURATE (Spark) 17.3 s
- PUBLISH 467,465 rows
- total about 54 s

The quality gate blocks the run below a score of 80. The measured score was 99.61, covering completeness, validity, uniqueness, referential integrity and freshness. Bad rows go to quarantine instead of being dropped silently.
