"""Service layer: combines repository reads with file-based pipeline artifacts; no HTTP concerns here."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from orbit_core.config import PATHS, SETTINGS

from .repository import Repository


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class OrbitService:
    _opt_lock = threading.Lock()

    def __init__(self, repo: Repository, outputs: Path = PATHS.outputs, local_engines: bool | None = None):
        self.repo, self.out = repo, outputs
        self.local_engines = SETTINGS.local_engines if local_engines is None else local_engines

    def artifact(self, rel: str, required: bool = True) -> dict | list | None:
        """A pipeline artifact: the local data/outputs file when present, else the copy published to the DB."""
        path = self.out / rel
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        lookup = getattr(self.repo, "artifact", None)
        doc = lookup(rel) if lookup else None
        if doc is None and required:
            raise NotFound(f"artifact not available: data/outputs/{rel}")
        return doc

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
        return {"status": "ok" if db_status["status"] == "up" else "degraded", "database": db_status,
                "environment": SETTINGS.env, "capabilities": self.capabilities()}

    def capabilities(self) -> dict:
        return {"optimization_solver": self.local_engines,
                "note": None if self.local_engines else
                "Julia, Spark, R, Rust, C++, Java and ML training run on the workstation; this deployment serves "
                "their latest persisted results."}

    def quality(self) -> dict:
        run_id = self._run("data_quality_runs")
        report = self.artifact("quality/quality_report.json")
        return {"run_id": run_id, "overall_quality_score": report["overall_quality_score"],
                "scoring": report.get("scoring"), "datasets": self.repo.quality_runs(run_id)}

    def metrics(self, **kw) -> dict:
        return {"available_metrics": self.repo.metric_names(), "rows": self.repo.metrics(**kw)}

    def analytics(self) -> dict:
        a = self.artifact("analytics/analytics_summary.json")
        r = self.artifact("r/statistics.json")
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
        mc = self.artifact("simulation/revenue_at_risk.json")
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
        validate_params(params)  # raises ValueError -> 400 before any work
        if not self.local_engines:
            return self._persisted_optimization(params)
        from pipelines.orchestrator import run_optimization  # workstation only (not bundled when hosted)
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

    def _persisted_optimization(self, params: dict) -> dict:
        """Hosted mode: the Julia solver is not installed, so return the latest persisted run, clearly labelled."""
        runs = self.repo.optimization_runs(1)
        if not runs:
            raise NotFound("no persisted optimization run; the Julia solver runs locally (scripts/orbit.ps1)")
        row = self.repo.optimization_run(runs[0]["optimization_id"])
        res = row.get("result") or {}
        return {"optimization_id": row["optimization_id"], "run_id": row["run_id"], "status": row["status"],
                "parameters": row["parameters"], "objective": row["objective"],
                "baseline_objective": row["baseline_objective"], "improvement_abs": row["improvement_abs"],
                "improvement_pct": row["improvement_pct"], "by_region": res.get("by_region", []),
                "assumptions": res.get("assumptions", {}), "mode": "persisted", "requested_parameters": params,
                "message": "The Julia JuMP + HiGHS solver runs locally, not on this hosted deployment. Showing the "
                           "latest persisted run instead; its parameters may differ from the ones requested."}

    def models(self) -> dict:
        return {"models": self.repo.models()}

    def model(self, version: str) -> dict:
        row = self.repo.model(version)
        if not row:
            raise NotFound("model version not found")
        return row

    def operations(self, limit: int) -> dict:
        return {"pipeline_runs": self.repo.pipeline_runs(limit), "table_counts": self.repo.table_counts(),
                "rust_benchmark": self.artifact("rust/benchmark.json", required=False)}

    def pipeline_run(self, run_id: str) -> dict:
        stages = self.repo.pipeline_run(run_id)
        if not stages:
            raise NotFound("pipeline run not found")
        return {"run_id": run_id, "stages": stages}
