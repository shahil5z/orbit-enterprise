# BI datasets

`scripts\orbit.ps1 bi-export` (or `python -m bi.export`) writes flat CSV files plus `schema.json` to `data\bi\`.
They come from the seeded PostgreSQL. Run-scoped tables (forecasts, risks, recommendations, data quality) contain only the latest pipeline run.
All data is a **simulated enterprise dataset**.

| File | Grain | Rows (MEASURED, run 20261026T160340Z-f5255777) |
|---|---|---|
| dim_region.csv | region | 6 |
| dim_business_unit.csv | business unit | 5 |
| dim_kpi.csv | KPI (governance catalogue) | 22 |
| fact_metrics_monthly.csv | metric x month x region x business unit (long format) | 10,800 |
| fact_operations_monthly.csv | month x region x business unit | 1,080 |
| fact_forecasts.csv | region x target month | 36 |
| fact_risks.csv | region or business unit | 36 |
| fact_recommendations.csv | decision | 7 |
| fact_data_quality.csv | raw dataset | 11 |

The model is a star schema:
- Facts join `dim_region` on `region_id` and `dim_business_unit` on `bu_id`.
- `fact_metrics_monthly.metric_name` joins `dim_kpi.key`.
- The `cost` metric has no catalogue entry, so it does not match a KPI row.
- `schema.json` lists every column with its type, and the relationships.

Rules that apply in every tool:
- An empty `region_id` / `bu_id` in `fact_metrics_monthly` is a total row. Filter on it explicitly. If you don't, region totals are summed twice.
- Use `dim_kpi.unit` and `higher_is_better` for formatting and direction. Do not redefine KPIs in the BI tool (see `docs/kpi-governance.md`).
- Show risk with the `risk_level` text (LOW, MEDIUM, HIGH, CRITICAL), not colour alone.
- Percent metrics are stored as fractions (0.27 = 27%), except `avg_uptime_pct` and `quality_score`, which are on a 0 to 100 scale.

Tool guides: [Tableau](tableau.md), [Power BI](powerbi.md), [QlikView](qlikview.md).
Status: none of the three tools was installed or tested on this laptop. These guides are NOT TESTED. Only the CSV export itself is VERIFIED, by `tests/test_phase2.py::test_bi_export_writes_typed_datasets`.
