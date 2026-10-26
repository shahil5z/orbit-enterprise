"""PostgreSQL access helpers: connection, migrations. All statements are parameterized."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import psycopg

from orbit_core.config import SETTINGS

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
VIEWS = Path(__file__).resolve().parent / "schema" / "views.sql"


@contextmanager
def connect(dsn: str | None = None):
    conn = psycopg.connect(dsn or SETTINGS.dsn, connect_timeout=5)
    try:
        yield conn
    finally:
        conn.close()


def migrate(dsn: str | None = None) -> list[str]:
    applied = []
    with connect(dsn) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, "
                     "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.stem in done:
                continue
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.stem,))
            applied.append(f.stem)
        conn.execute(VIEWS.read_text(encoding="utf-8"))
        conn.commit()
    return applied
