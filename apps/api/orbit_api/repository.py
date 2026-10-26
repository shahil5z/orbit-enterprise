"""Data access layer. Every query is parameterized; identifiers come only from fixed whitelists."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from orbit_core.config import SETTINGS

from .insights_repo import InsightQueries

RUN_TABLES = {"data_quality_runs", "forecasts", "predictions", "risks", "recommendations", "optimization_runs",
              "pipeline_runs"}


class Repository(InsightQueries):
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or SETTINGS.dsn

    @contextmanager
    def _conn(self):
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as conn:
            yield conn

    def _all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute(sql, params).fetchone()

    def artifact(self, name: str) -> dict | list | None:
        """A JSON artifact published by database/seeds/publish.py (hosted deployments have no data/outputs)."""
        try:
            row = self._one("SELECT body FROM artifacts WHERE name = %s", (name,))
        except psycopg.errors.UndefinedTable:
            return None
        return row["body"] if row else None

    def ping(self) -> dict:
        return self._one("SELECT version() AS version, current_database() AS database")

    def latest_run_id(self, table: str) -> str | None:
        if table not in RUN_TABLES:
            raise ValueError("unknown table")
        row = self._one(f"SELECT run_id FROM {table} ORDER BY created_at DESC LIMIT 1")
        return row["run_id"] if row else None

    def quality_runs(self, run_id: str) -> list[dict]:
        return self._all("SELECT dataset, rows_checked, quality_score, issue_count, issues, created_at"
                         " FROM data_quality_runs WHERE run_id = %s ORDER BY dataset", (run_id,))

    def metrics(self, metric: str | None, region_id: str | None, bu_id: str | None, start, end,
                limit: int, offset: int) -> list[dict]:
        return self._all(
            "SELECT metric_name, period_month, region_id, bu_id, value FROM metrics"
            " WHERE (%(m)s::text IS NULL OR metric_name = %(m)s) AND (%(r)s::text IS NULL OR region_id = %(r)s)"
            " AND (%(b)s::text IS NULL OR bu_id = %(b)s) AND (%(s)s::date IS NULL OR period_month >= %(s)s)"
            " AND (%(e)s::date IS NULL OR period_month <= %(e)s)"
            " ORDER BY period_month, region_id, bu_id, metric_name LIMIT %(l)s OFFSET %(o)s",
            {"m": metric, "r": region_id, "b": bu_id, "s": start, "e": end, "l": limit, "o": offset})

    def metric_names(self) -> list[str]:
        return [r["metric_name"] for r in self._all("SELECT DISTINCT metric_name FROM metrics ORDER BY 1")]

    def forecasts(self, run_id: str, region_id: str | None) -> list[dict]:
        return self._all("SELECT model_version, region_id, target_month, horizon, forecast, lower_80, upper_80"
                         " FROM forecasts WHERE run_id = %s AND (%s::text IS NULL OR region_id = %s)"
                         " ORDER BY region_id, horizon", (run_id, region_id, region_id))

    def anomalies(self, run_id: str, region_id: str | None, limit: int) -> list[dict]:
        return self._all(
            "SELECT p.entity_id AS operation_id, o.op_date, o.region_id, o.bu_id, p.score AS anomaly_score,"
            " p.actual_label AS labelled_anomaly, p.model_version FROM predictions p"
            " JOIN operations o ON o.operation_id = p.entity_id"
            " WHERE p.run_id = %s AND p.entity_type = 'operation' AND p.predicted_label = 1"
            " AND (%s::text IS NULL OR o.region_id = %s) ORDER BY p.score DESC LIMIT %s",
            (run_id, region_id, region_id, limit))

    def risks(self, run_id: str, entity_type: str | None, level: str | None) -> list[dict]:
        return self._all("SELECT entity_type, region_id, bu_id, risk_score, risk_level, risk_factors, confidence,"
                         " recommended_action, explanation FROM risks WHERE run_id = %s"
                         " AND (%s::text IS NULL OR entity_type = %s) AND (%s::text IS NULL OR risk_level = %s)"
                         " ORDER BY risk_score DESC", (run_id, entity_type, entity_type, level, level))

    def recommendations(self, run_id: str, priority: str | None) -> list[dict]:
        return self._all("SELECT decision_id, scope, entity_id, priority, observation, cause, forecast, risk,"
                         " recommendation, expected_impact, confidence, evidence FROM recommendations"
                         " WHERE run_id = %s AND (%s::text IS NULL OR priority = %s)"
                         " ORDER BY CASE priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2"
                         " ELSE 3 END, decision_id", (run_id, priority, priority))

    def optimization_runs(self, limit: int) -> list[dict]:
        return self._all("SELECT optimization_id, run_id, status, objective, baseline_objective, improvement_abs,"
                         " improvement_pct, parameters, triggered_by, created_at FROM optimization_runs"
                         " ORDER BY created_at DESC LIMIT %s", (limit,))

    def optimization_run(self, optimization_id: str) -> dict | None:
        return self._one("SELECT optimization_id, run_id, status, objective, baseline_objective, improvement_abs,"
                         " improvement_pct, parameters, result, triggered_by, created_at FROM optimization_runs"
                         " WHERE optimization_id = %s", (optimization_id,))

    def save_optimization(self, doc: dict, run_id: str) -> None:
        from database.seeds.load import persist_optimization
        with psycopg.connect(self.dsn) as conn:
            persist_optimization(conn, doc, run_id, "api")

    def models(self) -> list[dict]:
        return self._all("SELECT model_version, model_name, task, algorithm, run_id, metrics, params, artifact_path,"
                         " trained_at FROM model_runs ORDER BY trained_at DESC")

    def model(self, version: str) -> dict | None:
        return self._one("SELECT model_version, model_name, task, algorithm, run_id, metrics, params, artifact_path,"
                         " trained_at FROM model_runs WHERE model_version = %s", (version,))

    def pipeline_runs(self, limit: int) -> list[dict]:
        return self._all("SELECT run_id, min(started_at) AS started_at, max(ended_at) AS ended_at, count(*) AS stages,"
                         " sum(records_processed) AS records_processed, sum(error_count) AS errors,"
                         " bool_and(status = 'SUCCESS') AS all_succeeded FROM pipeline_runs GROUP BY run_id"
                         " ORDER BY min(started_at) DESC LIMIT %s", (limit,))

    def pipeline_run(self, run_id: str) -> list[dict]:
        return self._all("SELECT stage, component, status, started_at, ended_at, duration_s, records_processed,"
                         " error_count, details FROM pipeline_runs WHERE run_id = %s ORDER BY started_at", (run_id,))

    def table_counts(self) -> dict:
        tables = ["customers", "transactions", "operations", "incidents", "employees", "suppliers", "metrics",
                  "forecasts", "predictions", "risks", "recommendations", "optimization_runs", "model_runs"]
        with self._conn() as c:
            return {t: c.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in tables}
