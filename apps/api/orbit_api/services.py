"""Service layer: combines repository reads with file-based pipeline artifacts; no HTTP concerns here."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from orbit_core.config import PATHS

from .repository import Repository


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _read(path: Path) -> dict:
    if not path.exists():
        raise NotFound(f"artifact not available: {path.relative_to(PATHS.root).as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


class OrbitService:
    _opt_lock = threading.Lock()

    def __init__(self, repo: Repository, outputs: Path = PATHS.outputs):
        self.repo, self.out = repo, outputs

    def _run(self, table: str) -> str:
        run_id = self.repo.latest_run_id(table)
        if not run_id:
            raise NotFound(f"no pipeline output in {table}; run the pipeline first")
        return run_id

    def health(self) -> dict:
        try:
            db = self.repo.ping()
            db_status = {"status": "up", "database": db["database"], "version": db["version"].split(",")[0]}
        except Exception:
            db_status = {"status": "down"}
        return {"status": "ok" if db_status["status"] == "up" else "degraded", "database": db_status}

    def quality(self) -> dict:
        run_id = self._run("data_quality_runs")
        report = _read(self.out / "quality" / "quality_report.json")
        return {"run_id": run_id, "overall_quality_score": report["overall_quality_score"],
                "scoring": report.get("scoring"), "datasets": self.repo.quality_runs(run_id)}

    def metrics(self, **kw) -> dict:
        return {"available_metrics": self.repo.metric_names(), "rows": self.repo.metrics(**kw)}

    def analytics(self) -> dict:
        a = _read(self.out / "analytics" / "analytics_summary.json")
        r = _read(self.out / "r" / "statistics.json")
        return {"company": a["company"], "by_region": a["by_region"], "by_business_unit": a["by_business_unit"],
                "trends": a["trends"], "segmentation": a["segmentation"], "correlations": a["correlations"],
                "statistical_anomalies": a["statistical_anomalies"], "r_statistics": r}

    def forecasts(self, region_id: str | None) -> dict:
        run_id = self._run("forecasts")
        return {"run_id": run_id, "forecasts": self.repo.forecasts(run_id, region_id)}

    def anomalies(self, region_id: str | None, limit: int) -> dict:
        run_id = self._run("predictions")
        return {"run_id": run_id, "anomalies": self.repo.anomalies(run_id, region_id, limit)}

    def risks(self, entity_type: str | None, level: str | None) -> dict:
        run_id = self._run("risks")
        mc = _read(self.out / "simulation" / "revenue_at_risk.json")
        return {"run_id": run_id, "monte_carlo": mc, "risks": self.repo.risks(run_id, entity_type, level)}

    def recommendations(self, priority: str | None) -> dict:
        run_id = self._run("recommendations")
        return {"run_id": run_id, "recommendations": self.repo.recommendations(run_id, priority)}

    def optimization_runs(self, limit: int) -> dict:
        return {"runs": self.repo.optimization_runs(limit)}

    def optimization_run(self, optimization_id: str) -> dict:
        row = self.repo.optimization_run(optimization_id)
        if not row:
            raise NotFound("optimization run not found")
        return row

    def run_optimization(self, params: dict) -> dict:
        from optimization.workflow import validate_params
        from pipelines.orchestrator import run_optimization
        validate_params(params)  # raises ValueError -> 400 before any work
        if not self._opt_lock.acquire(blocking=False):
            raise Conflict("an optimization run is already in progress")
        try:
            run_id = self._run("risks")
            doc = run_optimization(params, run_id, "api")
            self.repo.save_optimization(doc, run_id)
        finally:
            self._opt_lock.release()
        return {k: doc[k] for k in ("optimization_id", "run_id", "status", "parameters", "objective",
                                    "baseline_objective", "improvement_abs", "improvement_pct", "by_region",
                                    "assumptions")}

    def models(self) -> dict:
        return {"models": self.repo.models()}

    def model(self, version: str) -> dict:
        row = self.repo.model(version)
        if not row:
            raise NotFound("model version not found")
        return row

    def operations(self, limit: int) -> dict:
        bench = self.out / "rust" / "benchmark.json"
        return {"pipeline_runs": self.repo.pipeline_runs(limit), "table_counts": self.repo.table_counts(),
                "rust_benchmark": json.loads(bench.read_text()) if bench.exists() else None}

    def pipeline_run(self, run_id: str) -> dict:
        stages = self.repo.pipeline_run(run_id)
        if not stages:
            raise NotFound("pipeline run not found")
        return {"run_id": run_id, "stages": stages}
