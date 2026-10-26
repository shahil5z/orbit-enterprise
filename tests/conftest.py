import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit_core.config import PATHS  # noqa: E402


def needs_tool(name: str):
    return pytest.mark.skipif(shutil.which(name) is None, reason=f"{name} not on PATH (run scripts/env.ps1)")


def needs_outputs(*rel: str):
    missing = [r for r in rel if not (PATHS.outputs / r).exists()]
    return pytest.mark.skipif(bool(missing), reason=f"pipeline outputs missing: {missing}")


def db_available() -> bool:
    try:
        from database.db import connect
        with connect() as c:
            c.execute("SELECT 1 FROM recommendations LIMIT 1")
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not db_available(), reason="PostgreSQL not reachable or not seeded")
