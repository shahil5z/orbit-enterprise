"""Run metadata tracking: every stage records run_id, timings, status, records and errors."""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import PATHS
from .logging import get_logger, log

_logger = get_logger("runs")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


class StageRun:
    def __init__(self, run_id: str, stage: str, component: str):
        self.run_id = run_id
        self.stage = stage
        self.component = component
        self.records_processed = 0
        self.errors: list[str] = []
        self.details: dict = {}
        self.started_at = datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.status = "RUNNING"
        self.duration_s = 0.0

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "component": self.component,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_s": round(self.duration_s, 3),
            "records_processed": self.records_processed,
            "error_count": len(self.errors),
            "errors": self.errors[:50],
            "details": self.details,
        }


@contextmanager
def track_stage(run_id: str, stage: str, component: str):
    run = StageRun(run_id, stage, component)
    t0 = time.perf_counter()
    log(_logger, "stage_start", run_id=run_id, stage=stage, component=component)
    try:
        yield run
        run.status = "SUCCESS" if not run.errors else "SUCCESS_WITH_ERRORS"
    except Exception as exc:  # recorded then re-raised so the orchestrator stops
        run.status = "FAILED"
        run.errors.append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        run.duration_s = time.perf_counter() - t0
        run.ended_at = datetime.now(timezone.utc)
        PATHS.runs.mkdir(parents=True, exist_ok=True)
        path = PATHS.runs / f"{run_id}.json"
        existing = json.loads(path.read_text()) if path.exists() else {"run_id": run_id, "stages": []}
        existing["stages"].append(run.as_dict())
        path.write_text(json.dumps(existing, indent=2, default=str))
        log(_logger, "stage_end", **{k: v for k, v in run.as_dict().items() if k != "details"})
