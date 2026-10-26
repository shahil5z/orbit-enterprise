"""Vercel Python Function entrypoint. vercel.json rewrites /api/* here; FastAPI sees the original path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps.api.orbit_api.main import app  # noqa: E402,F401
