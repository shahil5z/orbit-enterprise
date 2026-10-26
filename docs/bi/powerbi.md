# Power BI

NOT TESTED: Power BI Desktop was not available on this laptop.

1. Run `scripts\orbit.ps1 bi-export`.
2. Get Data > Text/CSV, then load every CSV in `data\bi\`. In Power Query, set the column types from `schema.json`. `period_month` and `target_month` are Date, and the decimals are Decimal Number.
3. In Model view, create single-direction one-to-many relationships:
   - `dim_region[region_id]` to each fact's `region_id`
   - `dim_business_unit[bu_id]` to each fact's `bu_id`
   - `dim_kpi[key]` to `fact_metrics_monthly[metric_name]`
4. Base measure (regional rows only, so totals are not double counted):
   ```DAX
   Metric Value = CALCULATE ( SUM ( fact_metrics_monthly[value] ), NOT ISBLANK ( fact_metrics_monthly[region_id] ) )
   Revenue = CALCULATE ( [Metric Value], fact_metrics_monthly[metric_name] = "revenue" )
   Gross Margin % = DIVIDE ( CALCULATE ( [Metric Value], fact_metrics_monthly[metric_name] = "gross_margin" ), [Revenue] )
   ```
   The `Gross Margin %` formula matches `dim_kpi` row `gross_margin_pct`: a ratio of sums, not an average of ratios.
5. Risk visual: a table with `risk_level` as a text column. Conditional formatting is optional and only supplements the text.
6. Put the text "Simulated enterprise dataset" on every report page.
