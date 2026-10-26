"""Seed PostgreSQL from the conformed layer and persist pipeline outputs.

Reference/core tables are fully reloaded (idempotent); analytical tables are appended per run_id.
COPY is used for large tables; all other statements are parameterized.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from database.db import connect
from orbit_core.config import PATHS

CORE = [  # load order respects foreign keys
    ("organizations", ["org_id", "name", "parent_org_id", "country"]),
    ("regions", ["region_id", "name", "currency"]),
    ("business_units", ["bu_id", "org_id", "name"]),
    ("products", ["product_id", "bu_id", "name", "category", "unit_price", "unit_cost"]),
    ("customers", ["customer_id", "name", "region_id", "segment", "industry", "signup_date", "satisfaction_score",
                   "credit_limit"]),
    ("suppliers", ["supplier_id", "name", "region_id", "category", "annual_spend", "on_time_delivery_pct",
                   "quality_score"]),
    ("employees", ["employee_id", "bu_id", "region_id", "role", "hire_date", "annual_salary", "performance_rating",
                   "is_active"]),
    ("transactions", ["transaction_id", "customer_id", "product_id", "region_id", "bu_id", "txn_date", "quantity",
                      "unit_price", "discount_pct", "revenue", "cost", "channel"]),
    ("operations", ["operation_id", "op_date", "region_id", "bu_id", "headcount", "orders_processed",
                    "fulfillment_hours", "uptime_pct", "uptime_imputed", "support_tickets", "marketing_spend", "opex"]),
    ("incidents", ["incident_id", "region_id", "bu_id", "supplier_id", "severity", "category", "opened_at",
                   "resolved_at", "cost_impact"]),
]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if v is pd.NaT or (isinstance(v, pd.Timestamp) and pd.isna(v)):
        return None
    if isinstance(v, np.generic):
        return v.item()
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _copy(conn, table: str, cols: list[str], df: pd.DataFrame) -> int:
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
            for row in df[cols].itertuples(index=False, name=None):
                cp.write_row([_clean(v) for v in row])
    return len(df)


def seed_core(conformed: Path = PATHS.curated / "conformed", dsn: str | None = None) -> dict:
    counts = {}
    with connect(dsn) as conn:
        with conn.transaction():
            conn.execute("TRUNCATE " + ", ".join(t for t, _ in reversed(CORE)) + " CASCADE")
            for table, cols in CORE:
                df = pd.read_parquet(conformed / f"{table}.parquet")
                if table == "operations":
                    df = df.rename(columns={"uptime_missing": "uptime_imputed"})
                if table == "organizations":
                    df = df.sort_values("parent_org_id", na_position="first")
                counts[table] = _copy(conn, table, cols, df)
    return counts


def _j(obj) -> str:
    return json.dumps(obj, default=lambda o: o.item() if isinstance(o, np.generic) else str(o))


def persist_outputs(run_id: str, out: Path = PATHS.outputs, dsn: str | None = None) -> dict:
    """Persist everything a run produced. Re-running for the same run_id replaces that run's rows."""
    counts = {}
    q = json.loads((out / "quality" / "quality_report.json").read_text())
    with connect(dsn) as conn, conn.transaction():
        for t in ("data_quality_runs", "metrics", "forecasts", "predictions", "risks", "recommendations",
                  "optimization_runs"):
            conn.execute(f"DELETE FROM {t} WHERE run_id = %s", (run_id,))
        for d in q["datasets"]:
            conn.execute("INSERT INTO data_quality_runs (run_id, dataset, rows_checked, quality_score, issue_count, issues)"
                         " VALUES (%s, %s, %s, %s, %s, %s)", (run_id, d["dataset"], d["rows"], d["quality_score"],
                                                              d["issue_count"], _j(d["issues"])))
        counts["data_quality_runs"] = len(q["datasets"])

        km = pd.read_parquet(PATHS.curated / "marts" / "monthly_kpis")
        m = km.melt(id_vars=["region_id", "bu_id", "month"],
                    value_vars=["revenue", "cost", "gross_margin", "opex", "operating_profit", "txn_count",
                                "active_customers", "incident_count", "avg_uptime_pct", "marketing_spend"],
                    var_name="metric_name", value_name="value")
        m["run_id"] = run_id
        conn.execute("DELETE FROM metrics")  # metrics hold the latest curated values only
        with conn.cursor() as cur:
            with cur.copy("COPY metrics (metric_name, period_month, region_id, bu_id, value, run_id) FROM STDIN") as cp:
                for r in m.itertuples(index=False):
                    cp.write_row([r.metric_name, r.month, r.region_id, r.bu_id, _clean(r.value), run_id])
        counts["metrics"] = len(m)

        reports = json.loads((out / "ml" / "model_reports.json").read_text())
        for name, rep in reports.items():
            conn.execute(
                "INSERT INTO model_runs (model_version, model_name, task, algorithm, run_id, metrics, params, artifact_path,"
                " trained_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (model_version) DO UPDATE SET"
                " run_id = EXCLUDED.run_id, metrics = EXCLUDED.metrics, trained_at = EXCLUDED.trained_at",
                (rep["model_version"], name, rep["task"], rep["algorithm"], run_id,
                 _j({k: rep.get(k) for k in ("validation", "test", "baseline_logistic_regression_test",
                                              "baseline_zscore_rule_test", "selected", "silhouette_by_k", "k")}),
                 _j(rep.get("params", {})), rep.get("artifact_path", ""), rep["trained_at"]))
        counts["model_runs"] = len(reports)

        fc = pd.read_parquet(out / "ml" / "forecast.parquet")
        fv = reports["revenue_forecast"]["model_version"]
        for r in fc.itertuples(index=False):
            conn.execute("INSERT INTO forecasts (model_version, region_id, target_month, horizon, forecast, lower_80,"
                         " upper_80, run_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (fv, r.region_id, r.month.date(), int(r.horizon), round(r.forecast, 2), round(r.lower_80, 2),
                          round(r.upper_80, 2), run_id))
        counts["forecasts"] = len(fc)

        n_pred = 0
        with conn.cursor() as cur:
            with cur.copy("COPY predictions (model_version, entity_type, entity_id, score, predicted_label, actual_label,"
                          " split, run_id) FROM STDIN") as cp:
                ch = pd.read_parquet(out / "ml" / "churn_predictions.parquet")
                cv = reports["churn_classifier"]["model_version"]
                for r in ch.itertuples(index=False):
                    cp.write_row([cv, "customer", r.customer_id, float(r.churn_probability), int(r.predicted_churn),
                                  int(r.actual_churn), getattr(r, "split", None), run_id])
                an = pd.read_parquet(out / "ml" / "anomaly_predictions.parquet")
                av = reports["ops_anomaly_iforest"]["model_version"]
                for r in an.itertuples(index=False):
                    cp.write_row([av, "operation", r.operation_id, float(r.anomaly_score), int(r.is_anomaly),
                                  int(r.label), None, run_id])
                n_pred = len(ch) + len(an)
        counts["predictions"] = n_pred

        risks = json.loads((out / "risk" / "risks.json").read_text())
        for r in risks["regions"] + risks["business_units"]:
            conn.execute("INSERT INTO risks (run_id, entity_type, region_id, bu_id, risk_score, risk_level, risk_factors,"
                         " confidence, recommended_action, explanation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                         (run_id, r["entity_type"], r["region_id"], r.get("bu_id"), r["risk_score"], r["risk_level"],
                          _j(r["risk_factors"]), r["confidence"], r["recommended_action"], r["explanation"]))
        counts["risks"] = len(risks["regions"]) + len(risks["business_units"])

        opt = json.loads((out / "optimization" / "latest.json").read_text())
        persist_optimization(conn, opt, run_id, "pipeline")
        counts["optimization_runs"] = 1

        decs = json.loads((out / "decisions" / "decisions.json").read_text())
        for d in decs:
            conn.execute("INSERT INTO recommendations (decision_id, run_id, scope, entity_id, priority, observation, cause,"
                         " forecast, risk, recommendation, expected_impact, confidence, evidence) VALUES"
                         " (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (decision_id) DO NOTHING",
                         (d["decision_id"], run_id, d["scope"], d["entity_id"], d["priority"], d["observation"],
                          d["cause"], d["forecast"], d["risk"], d["recommendation"], d["expected_impact"],
                          d["confidence"], _j(d["evidence"])))
        counts["recommendations"] = len(decs)
    return counts


def persist_optimization(conn, opt: dict, run_id: str, triggered_by: str) -> None:
    res = opt["result"]
    conn.execute("INSERT INTO optimization_runs (optimization_id, run_id, status, objective, baseline_objective,"
                 " improvement_abs, improvement_pct, parameters, result, triggered_by) VALUES"
                 " (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (optimization_id) DO NOTHING",
                 (opt["optimization_id"], run_id, res["status"], res.get("objective"), res["baseline"]["objective"],
                  res.get("improvement_abs"), res.get("improvement_pct"), _j(opt["parameters"]), _j(opt), triggered_by))


def persist_stage_runs(run_file: Path, dsn: str | None = None) -> int:
    doc = json.loads(run_file.read_text())
    with connect(dsn) as conn, conn.transaction():
        for s in doc["stages"]:
            conn.execute("INSERT INTO pipeline_runs (run_id, stage, component, status, started_at, ended_at, duration_s,"
                         " records_processed, error_count, details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                         " ON CONFLICT (run_id, stage) DO UPDATE SET status = EXCLUDED.status, ended_at = EXCLUDED.ended_at,"
                         " duration_s = EXCLUDED.duration_s, records_processed = EXCLUDED.records_processed,"
                         " error_count = EXCLUDED.error_count, details = EXCLUDED.details",
                         (s["run_id"], s["stage"], s["component"], s["status"], s["started_at"], s["ended_at"],
                          s["duration_s"], s["records_processed"], s["error_count"],
                          _j({"errors": s["errors"], **s["details"]})))
    return len(doc["stages"])
