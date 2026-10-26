"""BI extract: writes flat, typed CSV datasets plus schema.json to data/bi for Tableau, Power BI and QlikView.

Every dataset comes from the seeded PostgreSQL (latest pipeline run for run-scoped tables). KPI names,
units and formulas come from orbit_core.kpis so BI tools use the same definitions as the API and UI.
Usage: python -m bi.export [--out data/bi]"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from database.db import connect
from orbit_core import kpis

ROOT = Path(__file__).resolve().parent.parent

LATEST = "(SELECT run_id FROM {t} ORDER BY created_at DESC LIMIT 1)"

DATASETS: dict[str, tuple[str, str]] = {
    "dim_region": ("SELECT region_id, name AS region_name, currency FROM regions ORDER BY region_id",
                   "One row per sales region."),
    "dim_business_unit": ("SELECT bu_id, name AS business_unit_name FROM business_units ORDER BY bu_id",
                          "One row per business unit."),
    "fact_metrics_monthly": (
        "SELECT m.period_month, m.region_id, m.bu_id, m.metric_name, m.value, m.run_id FROM metrics m "
        "ORDER BY m.metric_name, m.period_month, m.region_id NULLS FIRST, m.bu_id NULLS FIRST",
        "Long-format monthly KPI values. NULL region_id / bu_id means the company or region total."),
    "fact_forecasts": (
        "SELECT f.region_id, f.target_month, f.horizon, f.forecast, f.lower_80, f.upper_80, f.model_version, "
        "mr.algorithm, f.run_id FROM forecasts f JOIN model_runs mr USING (model_version) "
        f"WHERE f.run_id = {LATEST.format(t='forecasts')} ORDER BY f.region_id, f.target_month",
        "Revenue forecast per region with 80% interval, latest run only."),
    "fact_risks": (
        "SELECT entity_type, region_id, bu_id, risk_score, risk_level, confidence, recommended_action, explanation, "
        f"run_id FROM risks WHERE run_id = {LATEST.format(t='risks')} ORDER BY risk_score DESC",
        "Risk score and level per region and business unit, latest run only. Level is text, not colour."),
    "fact_recommendations": (
        "SELECT decision_id, scope, entity_id, priority, observation, cause, forecast, risk, recommendation, "
        f"expected_impact, confidence, run_id FROM recommendations WHERE run_id = {LATEST.format(t='recommendations')} "
        "ORDER BY CASE priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, decision_id",
        "Decision Center recommendations with their reasoning fields, latest run only."),
    "fact_data_quality": (
        "SELECT dataset, rows_checked, quality_score, issue_count, run_id FROM data_quality_runs "
        f"WHERE run_id = {LATEST.format(t='data_quality_runs')} ORDER BY dataset",
        "Quality score per raw dataset, latest run only."),
    "fact_operations_monthly": (
        "SELECT date_trunc('month', o.op_date)::date AS period_month, o.region_id, o.bu_id, count(*) AS days, "
        "sum(o.orders_processed) AS orders_processed, avg(o.headcount) AS avg_headcount, "
        "avg(o.fulfillment_hours) AS avg_fulfillment_hours, avg(o.uptime_pct) AS avg_uptime_pct, "
        "sum(o.support_tickets) AS support_tickets, sum(o.marketing_spend) AS marketing_spend, sum(o.opex) AS opex "
        "FROM operations o GROUP BY 1, 2, 3 ORDER BY 1, 2, 3",
        "Orders, headcount, fulfillment hours, uptime, tickets and spend per month, region and business unit."),
}


def _pgtype(code: int) -> str:
    return {16: "boolean", 20: "integer", 21: "integer", 23: "integer", 700: "decimal", 701: "decimal",
            1700: "decimal", 1082: "date", 1114: "datetime", 1184: "datetime"}.get(code, "string")


def export(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    schema = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "label": "Simulated enterprise dataset", "encoding": "utf-8", "delimiter": ",", "datasets": {}}
    with connect() as c:
        for name, (sql, desc) in DATASETS.items():
            cur = c.execute(sql)
            cols = [(d.name, _pgtype(d.type_code)) for d in cur.description]
            n = 0
            with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow([c_ for c_, _ in cols])
                for row in cur:
                    w.writerow(["" if v is None else v for v in row])
                    n += 1
            schema["datasets"][name] = {"file": f"{name}.csv", "description": desc, "rows": n,
                                        "columns": [{"name": a, "type": b} for a, b in cols]}
    rows = [{"key": k.key, "name": k.name, "definition": k.definition, "formula": k.formula, "source": k.source,
             "refresh": k.refresh, "dimensions": "|".join(k.dimensions), "unit": k.unit,
             "higher_is_better": k.higher_is_better} for k in kpis.CATALOGUE]
    with (out / "dim_kpi.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    schema["datasets"]["dim_kpi"] = {"file": "dim_kpi.csv", "rows": len(rows),
                                     "description": "KPI governance catalogue (orbit_core.kpis).",
                                     "columns": [{"name": k, "type": "boolean" if k == "higher_is_better" else "string"} for k in rows[0]]}
    schema["relationships"] = [
        {"from": f"{f}.region_id", "to": "dim_region.region_id"} for f in
        ("fact_metrics_monthly", "fact_forecasts", "fact_risks", "fact_operations_monthly")
    ] + [{"from": f"{f}.bu_id", "to": "dim_business_unit.bu_id"} for f in
         ("fact_metrics_monthly", "fact_risks", "fact_operations_monthly")] + [
        {"from": "fact_metrics_monthly.metric_name", "to": "dim_kpi.key", "note": "only metrics with a catalogue entry match"}]
    (out / "schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return schema


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "bi"))
    s = export(Path(ap.parse_args().out))
    for k, v in s["datasets"].items():
        print(f"{k:26s} {v['rows']:>8d} rows")


if __name__ == "__main__":
    main()
