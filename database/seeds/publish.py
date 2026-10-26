"""Publish the local pipeline state to a hosted PostgreSQL (e.g. Neon) for the hosted API.

The heavy engines (Spark, Julia, R, Rust, C++, Java, ML training) run on the workstation. This script copies
their persisted results, never recomputes them:
  1. apply migrations to the target,
  2. replace every application table on the target with the local rows (COPY streaming, FK order),
  3. upsert the JSON artifacts the API reads from data/outputs into the `artifacts` table.

Usage (PowerShell):  $env:ORBIT_TARGET_DATABASE_URL = "<url>";  scripts/orbit.ps1 publish
The target URL is read from the environment only and is never printed or logged.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.conninfo import conninfo_to_dict

from database.db import connect, migrate
from orbit_core.config import PATHS, SETTINGS

JSON_ARTIFACTS = ["quality/quality_report.json", "analytics/analytics_summary.json", "r/statistics.json",
                  "simulation/revenue_at_risk.json", "rust/benchmark.json", "ml/model_reports.json"]
SKIP = {"schema_migrations", "artifacts"}


def _tables_in_fk_order(conn) -> list[str]:
    tables = [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")]
    deps = {t: set() for t in tables}
    for child, parent in conn.execute(
            "SELECT c.conrelid::regclass::text, c.confrelid::regclass::text FROM pg_constraint c"
            " WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace"):
        if child in deps and parent != child:
            deps[child].add(parent)
    order, seen = [], set()

    def visit(t):
        if t in seen:
            return
        seen.add(t)
        for p in sorted(deps.get(t, ())):
            visit(p)
        order.append(t)

    for t in sorted(tables):
        visit(t)
    return [t for t in order if t not in SKIP]


def _scrub_paths(value: object, root: Path = PATHS.root) -> object:
    """Rewrite absolute workstation paths as project-relative ones so the hosted API never exposes them."""
    if isinstance(value, dict):
        return {k: _scrub_paths(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_paths(v, root) for v in value]
    if isinstance(value, str) and len(value) < 1024:
        p = Path(value)
        if p.is_absolute():
            try:
                return p.relative_to(root).as_posix()
            except ValueError:
                return p.name
    return value


def _artifacts(out: Path) -> dict[str, object]:
    docs = {rel: _scrub_paths(json.loads((out / rel).read_text(encoding="utf-8")))
            for rel in JSON_ARTIFACTS if (out / rel).exists()}
    test = out / "ml" / "forecast_test_predictions.parquet"
    if test.exists():
        t = pd.read_parquet(test)
        t["month"] = pd.to_datetime(t["month"]).dt.strftime("%Y-%m-%d")
        docs["ml/forecast_test_predictions.json"] = json.loads(t.to_json(orient="records"))
    return docs


def _same_database(a: str, b: str) -> bool:
    ia, ib = conninfo_to_dict(a), conninfo_to_dict(b)
    return all(ia.get(k) == ib.get(k) for k in ("host", "port", "dbname"))


def publish(target: str, source: str | None = None, out: Path = PATHS.outputs) -> dict:
    source = source or SETTINGS.dsn
    if _same_database(target, source):
        raise ValueError("target equals the source database; refusing to publish onto itself")
    migrate(target)
    counts: dict[str, int] = {}
    with connect(source) as src, connect(target) as dst:
        tables = _tables_in_fk_order(src)
        with dst.transaction():
            dst.execute("TRUNCATE " + ", ".join(tables) + " CASCADE")  # names come from the catalog
            for t in tables:
                cols = [r[0] for r in src.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'"
                    " AND table_name = %s ORDER BY ordinal_position", (t,))]
                col_sql = ", ".join(f'"{c}"' for c in cols)
                with src.cursor().copy(f"COPY {t} ({col_sql}) TO STDOUT") as rd, \
                        dst.cursor().copy(f"COPY {t} ({col_sql}) FROM STDIN") as wr:
                    for chunk in rd:
                        wr.write(chunk)
                counts[t] = dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for name, body in _artifacts(out).items():
                dst.execute("INSERT INTO artifacts (name, body) VALUES (%s, %s::jsonb) ON CONFLICT (name) DO UPDATE"
                            " SET body = EXCLUDED.body, created_at = now()", (name, json.dumps(body)))
            counts["artifacts"] = dst.execute("SELECT count(*) FROM artifacts").fetchone()[0]
        # sequences follow the copied ids
        for (seq_sql,) in dst.execute(
                "SELECT format('SELECT setval(%L, COALESCE((SELECT max(%I) FROM %I), 1))', s.relname, a.attname, t.relname)"
                " FROM pg_class s JOIN pg_depend d ON d.objid = s.oid JOIN pg_class t ON t.oid = d.refobjid"
                " JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid WHERE s.relkind = 'S'"
                ).fetchall():
            dst.execute(seq_sql)
        dst.commit()
    return counts


def main() -> int:
    target = os.getenv("ORBIT_TARGET_DATABASE_URL", "")
    if not target:
        print("ORBIT_TARGET_DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        counts = publish(target)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except psycopg.Error as e:  # message from the server; the URL itself is not part of it
        print(f"publish failed: {type(e).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
