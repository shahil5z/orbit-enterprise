"""ORBIT // ENTERPRISE REST API (FastAPI). Run: uvicorn apps.api.orbit_api.main:app --port 8000"""
from __future__ import annotations

from datetime import date
from typing import Literal

import psycopg
from fastapi import APIRouter, Body, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from orbit_core.config import SETTINGS
from orbit_core.logging import get_logger, log

from .envelope import fail, ok
from .repository import Repository
from .services import Conflict, NotFound, OrbitService

logger = get_logger("api")
RegionId = Query(None, pattern=r"^R0[1-9]$")


class OptimizationParams(BaseModel):
    budget_multiplier: float = Field(1.0, ge=0.5, le=1.5, description="total budget relative to last 6 months")
    total_hires: int = Field(40, ge=0, le=200)
    risk_cap_factor: float = Field(0.95, ge=0.7, le=1.2, description="cap on risk-weighted spend vs baseline")
    min_region_share: float = Field(0.85, ge=0.5, le=1.0, description="minimum share of baseline spend per region")


def create_app(repo: Repository | None = None) -> FastAPI:
    app = FastAPI(title="ORBIT // ENTERPRISE API", version="1.0.0",
                  description="Decision intelligence API over simulated enterprise data. All responses use the "
                              "envelope {success, data, metadata, errors}.")
    app.state.service = OrbitService(repo or Repository())
    app.add_middleware(CORSMiddleware, allow_origins=list(SETTINGS.cors_origins), allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound):
        return fail(404, "NOT_FOUND", str(exc))

    @app.exception_handler(Conflict)
    async def _cf(_: Request, exc: Conflict):
        return fail(409, "CONFLICT", str(exc))

    @app.exception_handler(ValueError)
    async def _ve(_: Request, exc: ValueError):
        return fail(400, "INVALID_PARAMETERS", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _rv(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return fail(422, "VALIDATION_ERROR", "request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return fail(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(psycopg.OperationalError)
    async def _db(request: Request, exc: psycopg.OperationalError):
        log(logger, "database_unavailable", path=request.url.path, error_type=type(exc).__name__)
        return fail(503, "DATABASE_UNAVAILABLE", "database unavailable; start PostgreSQL (scripts/orbit.ps1 db-start)")

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):
        # details go to the structured log only; the client gets a sanitized message
        log(logger, "unhandled_error", path=request.url.path, error_type=type(exc).__name__, error=str(exc)[:500])
        return fail(500, "INTERNAL_ERROR", "internal error; see server logs")

    app.include_router(build_router(), prefix="/api/v1")
    return app


def svc(request: Request) -> OrbitService:
    return request.app.state.service


def build_router() -> APIRouter:
    r = APIRouter()

    @r.get("/health", tags=["system"])
    def health(s: OrbitService = Depends(svc)):
        return ok(s.health())

    @r.get("/data/quality", tags=["data"])
    def quality(s: OrbitService = Depends(svc)):
        return ok(s.quality())

    @r.get("/metrics", tags=["metrics"])
    def metrics(metric: str | None = Query(None, max_length=40), region_id: str | None = RegionId,
                bu_id: str | None = Query(None, pattern=r"^BU0[1-9]$"), start: date | None = None,
                end: date | None = None, limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0),
                s: OrbitService = Depends(svc)):
        if start and end and start > end:
            raise ValueError("start must be on or before end")
        data = s.metrics(metric=metric, region_id=region_id, bu_id=bu_id, start=start, end=end, limit=limit,
                         offset=offset)
        return ok(data, count=len(data["rows"]), limit=limit, offset=offset)

    @r.get("/analytics", tags=["analytics"])
    def analytics(s: OrbitService = Depends(svc)):
        return ok(s.analytics())

    @r.get("/forecasts", tags=["ml"])
    def forecasts(region_id: str | None = RegionId, s: OrbitService = Depends(svc)):
        d = s.forecasts(region_id)
        return ok(d, count=len(d["forecasts"]))

    @r.get("/anomalies", tags=["ml"])
    def anomalies(region_id: str | None = RegionId, limit: int = Query(100, ge=1, le=1000),
                  s: OrbitService = Depends(svc)):
        d = s.anomalies(region_id, limit)
        return ok(d, count=len(d["anomalies"]))

    @r.get("/risks", tags=["decision"])
    def risks(entity_type: Literal["region", "business_unit"] | None = None,
              level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None, s: OrbitService = Depends(svc)):
        d = s.risks(entity_type, level)
        return ok(d, count=len(d["risks"]))

    @r.get("/recommendations", tags=["decision"])
    def recommendations(priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None,
                        s: OrbitService = Depends(svc)):
        d = s.recommendations(priority)
        return ok(d, count=len(d["recommendations"]))

    @r.get("/optimization", tags=["optimization"])
    def optimization_runs(limit: int = Query(20, ge=1, le=200), s: OrbitService = Depends(svc)):
        return ok(s.optimization_runs(limit))

    @r.get("/optimization/{optimization_id}", tags=["optimization"])
    def optimization_run(optimization_id: str, s: OrbitService = Depends(svc)):
        if len(optimization_id) > 48:
            raise ValueError("invalid optimization id")
        return ok(s.optimization_run(optimization_id))

    @r.post("/optimization/run", tags=["optimization"], status_code=201)
    def run_optimization(params: OptimizationParams = Body(default_factory=OptimizationParams),
                         s: OrbitService = Depends(svc)):
        return ok(s.run_optimization(params.model_dump()), status_code=201)

    @r.get("/models", tags=["ml"])
    def models(s: OrbitService = Depends(svc)):
        return ok(s.models())

    @r.get("/models/{model_version}", tags=["ml"])
    def model(model_version: str, s: OrbitService = Depends(svc)):
        return ok(s.model(model_version))

    @r.get("/operations", tags=["operations"])
    def operations(limit: int = Query(20, ge=1, le=200), s: OrbitService = Depends(svc)):
        return ok(s.operations(limit))

    @r.get("/operations/runs/{run_id}", tags=["operations"])
    def pipeline_run(run_id: str, s: OrbitService = Depends(svc)):
        return ok(s.pipeline_run(run_id))

    return r


app = create_app()
