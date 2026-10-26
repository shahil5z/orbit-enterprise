"""Structured JSON-lines logging shared by every pipeline component."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from .config import PATHS, SETTINGS


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        root = logging.getLogger("orbit")
        root.setLevel(SETTINGS.log_level)
        try:
            PATHS.logs.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(PATHS.logs / "orbit.jsonl", encoding="utf-8")
            fh.setFormatter(JsonFormatter())
            root.addHandler(fh)
        except OSError:
            # Read-only filesystems (serverless) log to stderr only.
            pass
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(JsonFormatter())
        root.addHandler(sh)
        root.propagate = False
        _configured = True
    return logging.getLogger(f"orbit.{name}")


def log(logger: logging.Logger, msg: str, **ctx) -> None:
    logger.info(msg, extra={"ctx": ctx})
