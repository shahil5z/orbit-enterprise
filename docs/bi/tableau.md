# Tableau

NOT TESTED: Tableau was not available on this laptop. These steps use only standard Text File connector features.

1. Run `scripts\orbit.ps1 bi-export`.
2. Connect > To a File > Text file, then pick `data\bi\fact_metrics_monthly.csv`.
3. Add the other files to the data source as **relationships**, not joins:
   - `dim_region` on `region_id`
   - `dim_business_unit` on `bu_id`
   - `dim_kpi` on `metric_name = key`
4. Set the types from `schema.json`:
   - `period_month` and `target_month` are Date.
   - `value`, `forecast`, `lower_80` and `upper_80` are Number (decimal).
5. Add a data source filter so company totals are not double counted: `ISNULL([region_id]) = FALSE` for regional views, or `ISNULL([region_id])` for company views.
6. Suggested sheets:
   - **Revenue trend**: `period_month` on Columns, `SUM(value)` on Rows, filtered to `metric_name = "revenue"`, with `region_name` on Color and a text label.
   - **Forecast band**: from `fact_forecasts`, draw `forecast` as a line, with `lower_80` and `upper_80` as a reference band.
   - **Risk table**: from `fact_risks`, show `region_name`, `bu_id`, `risk_score` and `risk_level` as text, sorted by `risk_score` descending.
7. Add a caption to every dashboard: "Simulated enterprise dataset".
