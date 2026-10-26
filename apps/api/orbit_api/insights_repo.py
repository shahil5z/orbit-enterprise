"""Read-side queries for the Phase 2 UI. All aggregation happens in PostgreSQL; every value is a bound
parameter and the only interpolated SQL fragments are fixed strings defined in this module."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TXN_FILTER = (" WHERE (%(start)s::date IS NULL OR t.txn_date >= %(start)s)"
              " AND (%(end)s::date IS NULL OR t.txn_date <= %(end)s)"
              " AND (%(region_id)s::text IS NULL OR t.region_id = %(region_id)s)"
              " AND (%(bu_id)s::text IS NULL OR t.bu_id = %(bu_id)s)"
              " AND (%(segment)s::text IS NULL OR c.segment = %(segment)s)"
              " AND (%(product_id)s::text IS NULL OR t.product_id = %(product_id)s)")
TXN_FROM = (" FROM transactions t JOIN customers c ON c.customer_id = t.customer_id"
            " JOIN products p ON p.product_id = t.product_id")
TXN_AGG = (" sum(t.revenue)::float AS revenue, sum(t.revenue - t.cost)::float AS gross_margin,"
           " count(*) AS transactions, count(DISTINCT t.customer_id) AS customers")
GROUPS = {  # key: (select expression, group expression, join for label)
    "region": ("t.region_id AS key, r.name AS label", "t.region_id, r.name", " JOIN regions r ON r.region_id = t.region_id"),
    "business_unit": ("t.bu_id AS key, b.name AS label", "t.bu_id, b.name",
                      " JOIN business_units b ON b.bu_id = t.bu_id"),
    "segment": ("c.segment AS key, c.segment AS label", "c.segment", ""),
    "channel": ("t.channel AS key, t.channel AS label", "t.channel", ""),
    "product": ("t.product_id AS key, p.name AS label", "t.product_id, p.name", ""),
}
OPS_FILTER = (" WHERE (%(region_id)s::text IS NULL OR o.region_id = %(region_id)s)"
              " AND (%(bu_id)s::text IS NULL OR o.bu_id = %(bu_id)s)"
              " AND (%(start)s::date IS NULL OR o.op_date >= %(start)s)"
              " AND (%(end)s::date IS NULL OR o.op_date <= %(end)s)")
INC_FILTER = (" WHERE (%(region_id)s::text IS NULL OR i.region_id = %(region_id)s)"
              " AND (%(bu_id)s::text IS NULL OR i.bu_id = %(bu_id)s)"
              " AND (%(start)s::date IS NULL OR i.opened_at::date >= %(start)s)"
              " AND (%(end)s::date IS NULL OR i.opened_at::date <= %(end)s)"
              " AND (%(category)s::text IS NULL OR i.category = %(category)s)")


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class InsightQueries:
    """Mixin for Repository (needs _all/_one)."""

    _all: Any
    _one: Any

    def dimensions(self) -> dict:
        return {
            "regions": self._all("SELECT region_id AS id, name, currency FROM regions ORDER BY region_id"),
            "business_units": self._all("SELECT bu_id AS id, name FROM business_units ORDER BY bu_id"),
            "segments": [r["segment"] for r in self._all("SELECT DISTINCT segment FROM customers ORDER BY 1")],
            "products": self._all("SELECT product_id AS id, name, bu_id, category FROM products ORDER BY product_id"),
            "incident_categories": [r["category"] for r in self._all(
                "SELECT DISTINCT category FROM incidents WHERE category IS NOT NULL ORDER BY 1")],
            "date_range": self._one("SELECT min(txn_date) AS start, max(txn_date) AS end FROM transactions"),
        }

    def company_monthly(self, region_id: str | None = None) -> list[dict]:
        return self._all(
            "SELECT period_month, sum(value) FILTER (WHERE metric_name='revenue')::float AS revenue,"
            " sum(value) FILTER (WHERE metric_name='gross_margin')::float AS gross_margin,"
            " sum(value) FILTER (WHERE metric_name='opex')::float AS opex,"
            " sum(value) FILTER (WHERE metric_name='operating_profit')::float AS operating_profit,"
            " sum(value) FILTER (WHERE metric_name='incident_count')::float AS incidents,"
            " sum(value) FILTER (WHERE metric_name='txn_count')::float AS transactions,"
            " sum(value) FILTER (WHERE metric_name='marketing_spend')::float AS marketing_spend,"
            " avg(value) FILTER (WHERE metric_name='avg_uptime_pct')::float AS uptime_pct"
            " FROM metrics WHERE (%(r)s::text IS NULL OR region_id = %(r)s) GROUP BY period_month ORDER BY period_month",
            {"r": region_id})

    def txn_totals(self, f: dict) -> dict:
        return self._one("SELECT" + TXN_AGG + TXN_FROM + TXN_FILTER, f)

    def txn_monthly(self, f: dict) -> list[dict]:
        return self._all("SELECT date_trunc('month', t.txn_date)::date AS month," + TXN_AGG + TXN_FROM + TXN_FILTER
                         + " GROUP BY 1 ORDER BY 1", f)

    def txn_breakdown(self, f: dict, top_products: int = 15) -> dict:
        """Totals, monthly series and every group breakdown in ONE scan (GROUPING SETS), instead of 7 scans."""
        rows = self._all(
            "SELECT GROUPING(date_trunc('month', t.txn_date), t.region_id, t.bu_id, c.segment, t.channel, t.product_id) AS g,"
            " date_trunc('month', t.txn_date)::date AS month, t.region_id, t.bu_id, c.segment, t.channel, t.product_id,"
            + TXN_AGG + TXN_FROM + TXN_FILTER
            + " GROUP BY GROUPING SETS ((), (date_trunc('month', t.txn_date)), (t.region_id), (t.bu_id), (c.segment),"
              " (t.channel), (t.product_id))", f)
        names = {"region": {r["id"]: r["name"] for r in self._all("SELECT region_id AS id, name FROM regions")},
                 "business_unit": {r["id"]: r["name"] for r in self._all("SELECT bu_id AS id, name FROM business_units")},
                 "product": {r["id"]: r["name"] for r in self._all("SELECT product_id AS id, name FROM products")}}
        # GROUPING bitmask: bit order month(32) region(16) bu(8) segment(4) channel(2) product(1); 0 = column grouped
        col = {0b011111: "month", 0b101111: "region_id", 0b110111: "bu_id", 0b111011: "segment",
               0b111101: "channel", 0b111110: "product_id"}
        agg = ("revenue", "gross_margin", "transactions", "customers")
        out: dict = {"totals": None, "monthly": [], "region": [], "business_unit": [], "segment": [], "channel": [],
                     "product": []}
        for r in rows:
            vals = {k: r[k] for k in agg}
            if r["g"] == 0b111111:
                out["totals"] = vals
                continue
            c = col[r["g"]]
            if c == "month":
                out["monthly"].append({"month": r["month"], **vals})
                continue
            group = {"region_id": "region", "bu_id": "business_unit", "product_id": "product"}.get(c, c)
            key = r[c]
            out[group].append({"key": key, "label": names.get(group, {}).get(key, key), **vals})
        if out["totals"] is None:
            out["totals"] = {"revenue": None, "gross_margin": None, "transactions": 0, "customers": 0}
        out["monthly"].sort(key=lambda x: x["month"])
        for g in ("region", "business_unit", "segment", "channel", "product"):
            out[g].sort(key=lambda x: -(x["revenue"] or 0))
        out["product"] = out["product"][:top_products]
        return out

    def txn_group(self, f: dict, group: str, limit: int = 50) -> list[dict]:
        sel, grp, join = GROUPS[group]  # KeyError for unknown groups: callers pass fixed keys only
        return self._all(f"SELECT {sel}," + TXN_AGG + TXN_FROM + join + TXN_FILTER
                         + f" GROUP BY {grp} ORDER BY revenue DESC LIMIT %(limit)s", {**f, "limit": limit})

    def incident_breakdown(self, f: dict) -> dict:
        base = " FROM incidents i" + INC_FILTER
        return {
            "by_category": self._all("SELECT coalesce(i.category, 'Unknown') AS key, count(*) AS incidents,"
                                     " sum(i.cost_impact)::float AS cost" + base + " GROUP BY 1 ORDER BY 2 DESC", f),
            "by_severity": self._all("SELECT i.severity AS key, count(*) AS incidents, sum(i.cost_impact)::float AS cost,"
                                     " avg(extract(epoch FROM i.resolved_at - i.opened_at) / 3600)::float AS mttr_hours,"
                                     " count(*) FILTER (WHERE i.resolved_at IS NULL) AS open"
                                     + base + " GROUP BY 1 ORDER BY 1", f),
            "monthly": self._all("SELECT date_trunc('month', i.opened_at)::date AS month, count(*) AS incidents,"
                                 " count(*) FILTER (WHERE i.severity IN ('SEV1','SEV2')) AS major,"
                                 " avg(extract(epoch FROM i.resolved_at - i.opened_at) / 3600)::float AS mttr_hours"
                                 + base + " GROUP BY 1 ORDER BY 1", f),
            "recent": self._all("SELECT i.incident_id, i.region_id, i.bu_id, i.supplier_id, i.severity, i.category,"
                                " i.opened_at, i.resolved_at, i.cost_impact::float AS cost_impact" + base
                                + " ORDER BY i.opened_at DESC LIMIT 25", f),
        }

    def anomaly_page(self, run_id: str, f: dict, limit: int, offset: int) -> dict:
        where = (" FROM predictions p JOIN operations o ON o.operation_id = p.entity_id"
                 " WHERE p.run_id = %(run)s AND p.entity_type = 'operation' AND p.predicted_label = 1"
                 " AND (%(region_id)s::text IS NULL OR o.region_id = %(region_id)s)"
                 " AND (%(bu_id)s::text IS NULL OR o.bu_id = %(bu_id)s)"
                 " AND (%(start)s::date IS NULL OR o.op_date >= %(start)s)"
                 " AND (%(end)s::date IS NULL OR o.op_date <= %(end)s)")
        params = {**f, "run": run_id, "limit": limit, "offset": offset}
        rows = self._all("SELECT p.entity_id AS operation_id, o.op_date, o.region_id, o.bu_id, p.score AS anomaly_score,"
                         " p.actual_label AS labelled_anomaly, o.orders_processed, o.fulfillment_hours::float,"
                         " o.uptime_pct::float, o.support_tickets, o.opex::float, p.model_version" + where
                         + " ORDER BY p.score DESC LIMIT %(limit)s OFFSET %(offset)s", params)
        total = self._one("SELECT count(*) AS n" + where, params)["n"]
        return {"rows": rows, "total": total}

    def anomaly(self, run_id: str, operation_id: str) -> dict | None:
        return self._one("SELECT o.operation_id, o.op_date, o.region_id, o.bu_id, o.headcount::float,"
                         " o.orders_processed, o.fulfillment_hours::float, o.uptime_pct::float, o.uptime_imputed,"
                         " o.support_tickets, o.marketing_spend::float, o.opex::float, p.score AS anomaly_score,"
                         " p.predicted_label, p.actual_label AS labelled_anomaly, p.model_version"
                         " FROM operations o JOIN predictions p ON p.entity_id = o.operation_id AND p.run_id = %s"
                         " AND p.entity_type = 'operation' WHERE o.operation_id = %s", (run_id, operation_id))

    def ops_baseline(self, region_id: str, bu_id: str, day: date) -> dict:
        cols = ["orders_processed", "fulfillment_hours", "uptime_pct", "support_tickets", "opex", "marketing_spend",
                "headcount"]
        sel = ", ".join(f"avg({c})::float AS {c}_mean, stddev_samp({c})::float AS {c}_sd" for c in cols)
        row = self._one(f"SELECT count(*) AS days, {sel} FROM operations WHERE region_id = %s AND bu_id = %s"
                        " AND op_date BETWEEN %s AND %s AND op_date <> %s",
                        (region_id, bu_id, day - timedelta(days=90), day + timedelta(days=90), day))
        return row

    def incidents_near(self, region_id: str, day: date) -> list[dict]:
        return self._all("SELECT incident_id, bu_id, severity, category, opened_at, cost_impact::float AS cost_impact"
                         " FROM incidents WHERE region_id = %s AND opened_at::date BETWEEN %s AND %s ORDER BY opened_at",
                         (region_id, day - timedelta(days=2), day + timedelta(days=1)))

    def ops_monthly(self, f: dict) -> list[dict]:
        return self._all("SELECT date_trunc('month', o.op_date)::date AS month, sum(o.orders_processed) AS orders,"
                         " avg(o.fulfillment_hours)::float AS fulfillment_hours, avg(o.uptime_pct)::float AS uptime_pct,"
                         " sum(o.support_tickets) AS tickets, sum(o.headcount)::float / count(DISTINCT o.op_date) AS headcount,"
                         " sum(o.opex)::float AS opex FROM operations o" + OPS_FILTER + " GROUP BY 1 ORDER BY 1", f)

    def ops_bottlenecks(self, f: dict, days: int = 90) -> list[dict]:
        return self._all(
            "WITH last AS (SELECT max(op_date) AS d FROM operations), u AS (SELECT o.region_id, o.bu_id,"
            " avg(o.fulfillment_hours)::float AS fulfillment_hours, avg(o.uptime_pct)::float AS uptime_pct,"
            " 1000.0 * sum(o.support_tickets) / nullif(sum(o.orders_processed), 0) AS tickets_per_1k_orders,"
            " sum(o.orders_processed)::float / nullif(sum(o.headcount), 0) AS orders_per_head_day"
            " FROM operations o, last" + OPS_FILTER.replace(" WHERE", " WHERE o.op_date > last.d - %(days)s AND")
            + " GROUP BY 1, 2) SELECT u.*, r.name AS region_name, b.name AS bu_name,"
            " (u.fulfillment_hours - avg(u.fulfillment_hours) OVER ()) / nullif(stddev_samp(u.fulfillment_hours) OVER (), 0)"
            " AS fulfillment_z FROM u JOIN regions r USING (region_id) JOIN business_units b USING (bu_id)"
            " ORDER BY fulfillment_z DESC NULLS LAST", {**f, "days": days})

    def region_capacity_inputs(self) -> list[dict]:
        return self._all(
            "WITH last AS (SELECT max(op_date) AS d FROM operations), m AS (SELECT o.region_id,"
            " date_trunc('month', o.op_date) AS m, sum(o.orders_processed)::float AS orders,"
            " sum(o.headcount)::float AS hd, sum(o.opex)::float AS opex, sum(o.marketing_spend)::float AS mkt,"
            " count(DISTINCT o.op_date) AS days FROM operations o, last WHERE o.op_date > last.d - 730 GROUP BY 1, 2)"
            " SELECT region_id, percentile_cont(0.95) WITHIN GROUP (ORDER BY orders / nullif(hd, 0)) AS p95_oph,"
            " (SELECT sum(orders) / nullif(sum(hd), 0) FROM m m2 WHERE m2.region_id = m.region_id"
            "  AND m2.m > (SELECT max(m) FROM m) - interval '6 months') AS recent_oph,"
            " (SELECT sum(opex) FROM m m2 WHERE m2.region_id = m.region_id AND m2.m > (SELECT max(m) FROM m) - interval '6 months') AS opex_6m,"
            " (SELECT sum(mkt) FROM m m2 WHERE m2.region_id = m.region_id AND m2.m > (SELECT max(m) FROM m) - interval '6 months') AS mkt_6m,"
            " (SELECT sum(hd) / sum(days) FROM m m2 WHERE m2.region_id = m.region_id AND m2.m > (SELECT max(m) FROM m) - interval '6 months') AS headcount"
            " FROM m GROUP BY region_id ORDER BY region_id")

    def churn_customers(self, run_id: str, region_id: str | None, limit: int) -> list[dict]:
        return self._all("SELECT c.customer_id, c.name, c.region_id, c.segment, c.industry, p.score AS churn_probability,"
                         " c.satisfaction_score::float FROM predictions p JOIN customers c ON c.customer_id = p.entity_id"
                         " WHERE p.run_id = %s AND p.entity_type = 'customer' AND p.predicted_label = 1"
                         " AND (%s::text IS NULL OR c.region_id = %s) ORDER BY p.score DESC LIMIT %s",
                         (run_id, region_id, region_id, limit))

    def churn_by_segment(self, run_id: str, region_id: str | None) -> list[dict]:
        return self._all("SELECT c.segment, count(*) AS customers, sum(p.predicted_label) AS predicted_churn,"
                         " avg(p.score)::float AS avg_probability FROM predictions p"
                         " JOIN customers c ON c.customer_id = p.entity_id WHERE p.run_id = %s AND p.entity_type = 'customer'"
                         " AND (%s::text IS NULL OR c.region_id = %s) GROUP BY 1 ORDER BY 1", (run_id, region_id, region_id))

    def risk_driver_trend(self, run_id: str, region_id: str | None) -> list[dict]:
        return self._all(
            "WITH a AS (SELECT date_trunc('month', o.op_date)::date AS month, count(*) FILTER (WHERE p.predicted_label = 1)"
            " AS anomalies, count(*) AS unit_days FROM predictions p JOIN operations o ON o.operation_id = p.entity_id"
            " WHERE p.run_id = %(run)s AND p.entity_type = 'operation' AND (%(r)s::text IS NULL OR o.region_id = %(r)s)"
            " GROUP BY 1), i AS (SELECT date_trunc('month', opened_at)::date AS month,"
            " count(*) FILTER (WHERE severity IN ('SEV1', 'SEV2')) AS major_incidents FROM incidents"
            " WHERE (%(r)s::text IS NULL OR region_id = %(r)s) GROUP BY 1), m AS (SELECT period_month AS month,"
            " sum(value)::float AS revenue FROM metrics WHERE metric_name = 'revenue'"
            " AND (%(r)s::text IS NULL OR region_id = %(r)s) GROUP BY 1)"
            " SELECT m.month, m.revenue, coalesce(a.anomalies, 0) AS anomalies, coalesce(a.unit_days, 0) AS unit_days,"
            " coalesce(i.major_incidents, 0) AS major_incidents FROM m LEFT JOIN a USING (month) LEFT JOIN i USING (month)"
            " ORDER BY m.month", {"run": run_id, "r": region_id})

    def prediction_counts(self) -> dict[str, dict]:
        rows = self._all("SELECT model_version, count(*) AS predictions, sum(predicted_label) AS positives"
                         " FROM predictions GROUP BY 1")
        return {r["model_version"]: r for r in rows}

    def latest_model(self, name: str) -> dict | None:
        return self._one("SELECT model_version, model_name, task, algorithm, run_id, metrics, trained_at FROM model_runs"
                         " WHERE model_name = %s ORDER BY trained_at DESC LIMIT 1", (name,))

    def quality_dataset(self, run_id: str, dataset: str) -> dict | None:
        return self._one("SELECT dataset, rows_checked, quality_score, issue_count, issues, created_at"
                         " FROM data_quality_runs WHERE run_id = %s AND dataset = %s", (run_id, dataset))

    def quality_history(self, dataset: str) -> list[dict]:
        return self._all("SELECT run_id, quality_score, issue_count, rows_checked, created_at FROM data_quality_runs"
                         " WHERE dataset = %s ORDER BY created_at", (dataset,))

    def search(self, q: str, limit: int) -> dict:
        like = _like(q)
        p = {"q": like, "l": limit}
        return {
            "customer": self._all("SELECT customer_id AS id, name AS label, region_id || ' / ' || segment AS context"
                                  " FROM customers WHERE name ILIKE %(q)s OR customer_id ILIKE %(q)s"
                                  " ORDER BY name LIMIT %(l)s", p),
            "product": self._all("SELECT product_id AS id, name AS label, category AS context FROM products"
                                 " WHERE name ILIKE %(q)s OR product_id ILIKE %(q)s OR category ILIKE %(q)s"
                                 " ORDER BY name LIMIT %(l)s", p),
            "region": self._all("SELECT region_id AS id, name AS label, currency AS context FROM regions"
                                " WHERE name ILIKE %(q)s OR region_id ILIKE %(q)s ORDER BY region_id LIMIT %(l)s", p),
            "business_unit": self._all("SELECT bu_id AS id, name AS label, '' AS context FROM business_units"
                                       " WHERE name ILIKE %(q)s OR bu_id ILIKE %(q)s ORDER BY bu_id LIMIT %(l)s", p),
            "risk": self._all(
                "SELECT coalesce(k.bu_id, k.region_id) AS id, r.name || coalesce(' / ' || b.name, '') AS label,"
                " k.risk_level || ' ' || k.risk_score AS context, k.region_id, k.bu_id FROM risks k"
                " JOIN regions r ON r.region_id = k.region_id LEFT JOIN business_units b ON b.bu_id = k.bu_id"
                " WHERE k.run_id = (SELECT run_id FROM risks ORDER BY created_at DESC LIMIT 1)"
                " AND (r.name ILIKE %(q)s OR b.name ILIKE %(q)s OR k.risk_level ILIKE %(q)s OR k.explanation ILIKE %(q)s)"
                " ORDER BY k.risk_score DESC LIMIT %(l)s", p),
            "recommendation": self._all(
                "SELECT decision_id AS id, recommendation AS label, priority || ' / ' || entity_id AS context"
                " FROM recommendations WHERE run_id = (SELECT run_id FROM recommendations ORDER BY created_at DESC LIMIT 1)"
                " AND (recommendation ILIKE %(q)s OR observation ILIKE %(q)s OR cause ILIKE %(q)s OR entity_id ILIKE %(q)s)"
                " LIMIT %(l)s", p),
            "anomaly": self._all(
                "SELECT p.entity_id AS id, o.op_date::text AS label, o.region_id || ' / ' || o.bu_id AS context"
                " FROM predictions p JOIN operations o ON o.operation_id = p.entity_id"
                " WHERE p.run_id = (SELECT run_id FROM predictions ORDER BY created_at DESC LIMIT 1)"
                " AND p.entity_type = 'operation' AND p.predicted_label = 1"
                " AND (p.entity_id ILIKE %(q)s OR o.op_date::text ILIKE %(q)s) ORDER BY p.score DESC LIMIT %(l)s", p),
        }

    def recommendation(self, decision_id: str) -> dict | None:
        return self._one("SELECT run_id, decision_id, scope, entity_id, priority, observation, cause, forecast, risk,"
                         " recommendation, expected_impact, confidence, evidence, created_at FROM recommendations"
                         " WHERE decision_id = %s", (decision_id,))

    def region_names(self) -> dict[str, str]:
        return {r["region_id"]: r["name"] for r in self._all("SELECT region_id, name FROM regions")}

    def bu_names(self) -> dict[str, str]:
        return {r["bu_id"]: r["name"] for r in self._all("SELECT bu_id, name FROM business_units")}
