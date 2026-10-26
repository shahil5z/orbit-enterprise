# KPI governance

There is one definition per KPI. It lives in `orbit_core/kpis.py` (`CATALOGUE`). Each entry records:
- key and display name
- business definition and formula
- source table
- refresh cadence and allowed dimensions
- unit and direction (`higher_is_better`)
- a plain-language meaning

Consumers (VERIFIED by tests):
- API: `GET /api/v1/kpis` serves the catalogue (`tests/test_phase2.py::test_kpis_endpoint_serves_catalogue`).
- UI: `useReference` loads the catalogue once. The Overview, Intelligence, Forecasts, Risk, Operations and Quality pages take KPI names, units and definitions from it.
- BI: `dim_kpi.csv` is written from the same catalogue (`bi/export.py`).

Rules:
1. Ratios are computed as ratios of sums at the grain shown, never as averages of ratios.
2. Totals for a filtered view are recomputed from the filtered rows. They are never summed from stored total rows.
3. A KPI change means editing `kpis.py` and the producing pipeline stage in the same commit, and updating the test that pins the catalogue keys.
4. Estimates are labelled as such: forecasts carry an 80% interval, scenario outputs are labelled SCENARIO, and risk scores carry a confidence.
5. Every screen and extract is labelled "Simulated enterprise dataset".

The current catalogue has 22 KPIs (MEASURED from `kpis.CATALOGUE`):
revenue, gross_margin, gross_margin_pct, opex, operating_profit, operating_margin_pct, revenue_growth, txn_count, active_customers, marketing_spend, avg_uptime_pct, incident_count, incident_cost, mttr_hours, orders_per_head, fulfillment_hours, churn_rate, forecast_mape, quality_score, risk_score, var95, cvar95.

Known gap: the `cost` metric in the `metrics` table has no catalogue entry (Phase 3).
