"""Phase 2 endpoints (page aggregates, drill-downs, traceability, scenarios, search, exports)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .envelope import ok
from .insights import InsightService

Region = Query(None, pattern=r"^R0[1-9]$")
BU = Query(None, pattern=r"^BU0[1-9]$")
SAFE_ID = r"^[A-Za-z0-9_\-]{1,64}$"


class ScenarioParams(BaseModel):
    demand_change: float = Field(0.0, ge=-0.3, le=0.3)
    cost_change: float = Field(0.0, ge=-0.2, le=0.3)
    capacity_change: float = Field(0.0, ge=-0.3, le=0.3)
    workforce_change: float = Field(0.0, ge=-0.2, le=0.2)
    marketing_budget_change: float = Field(0.0, ge=-0.5, le=0.5)
    churn_change: float = Field(0.0, ge=-0.1, le=0.1)


def ins(request: Request) -> InsightService:
    return request.app.state.insights


def _dates(start, end):
    if start and end and start > end:
        raise ValueError("start must be on or before end")


def build_insights_router() -> APIRouter:
    r = APIRouter()

    @r.get("/kpis", tags=["governance"])
    def kpis(s: InsightService = Depends(ins)):
        return ok(s.kpis())

    @r.get("/dimensions", tags=["reference"])
    def dimensions(s: InsightService = Depends(ins)):
        return ok(s.dimensions())

    @r.get("/overview", tags=["pages"])
    def overview(s: InsightService = Depends(ins)):
        return ok(s.overview())

    @r.get("/intelligence", tags=["pages"])
    def intelligence(start: date | None = None, end: date | None = None, region_id: str | None = Region,
                     bu_id: str | None = BU, segment: Literal["Enterprise", "Mid-Market", "SMB"] | None = None,
                     product_id: str | None = Query(None, pattern=r"^P\d{2,4}$"),
                     category: str | None = Query(None, max_length=40), s: InsightService = Depends(ins)):
        _dates(start, end)
        return ok(s.intelligence({"start": start, "end": end, "region_id": region_id, "bu_id": bu_id,
                                  "segment": segment, "product_id": product_id, "category": category}))

    @r.get("/forecasts/series", tags=["ml"])
    def forecast_series(region_id: str | None = Region, s: InsightService = Depends(ins)):
        return ok(s.forecast_series(region_id))

    @r.get("/risks/region/{region_id}", tags=["decision"])
    def risk_region(region_id: str, s: InsightService = Depends(ins)):
        if not region_id or len(region_id) != 3 or not region_id.startswith("R0"):
            raise ValueError("invalid region id")
        return ok(s.risk_detail(region_id))

    @r.get("/anomalies/explore", tags=["ml"])
    def anomaly_explore(region_id: str | None = Region, bu_id: str | None = BU, start: date | None = None,
                        end: date | None = None, limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
                        s: InsightService = Depends(ins)):
        _dates(start, end)
        d = s.anomalies({"region_id": region_id, "bu_id": bu_id, "start": start, "end": end}, limit, offset)
        return ok(d, count=len(d["rows"]), total=d["total"], limit=limit, offset=offset)

    @r.get("/anomalies/{operation_id}", tags=["ml"])
    def anomaly(operation_id: str = Path(..., pattern=SAFE_ID), s: InsightService = Depends(ins)):
        return ok(s.anomaly(operation_id))

    @r.get("/operations/summary", tags=["operations"])
    def ops_summary(region_id: str | None = Region, bu_id: str | None = BU, start: date | None = None,
                    end: date | None = None, category: str | None = Query(None, max_length=40),
                    s: InsightService = Depends(ins)):
        _dates(start, end)
        return ok(s.operations_summary({"region_id": region_id, "bu_id": bu_id, "start": start, "end": end,
                                        "category": category}))

    @r.get("/decisions/{decision_id}/trace", tags=["decision"])
    def trace(decision_id: str, s: InsightService = Depends(ins)):
        if len(decision_id) > 64:
            raise ValueError("invalid decision id")
        return ok(s.decision_trace(decision_id))

    @r.get("/scenarios/levers", tags=["scenarios"])
    def levers(s: InsightService = Depends(ins)):
        return ok(s.scenario({}))

    @r.post("/scenarios/run", tags=["scenarios"])
    def scenario(params: ScenarioParams = Body(default_factory=ScenarioParams), s: InsightService = Depends(ins)):
        return ok(s.scenario(params.model_dump()))

    @r.get("/data/quality/{dataset}", tags=["data"])
    def quality_dataset(dataset: str, s: InsightService = Depends(ins)):
        if len(dataset) > 40:
            raise ValueError("invalid dataset")
        return ok(s.quality_dataset(dataset))

    @r.get("/models/catalog", tags=["ml"])
    def model_catalog(s: InsightService = Depends(ins)):
        return ok(s.models())

    @r.get("/system", tags=["system"])
    def system(s: InsightService = Depends(ins)):
        return ok(s.system())

    @r.get("/search", tags=["search"])
    def search(q: str = Query(..., min_length=2, max_length=60), limit: int = Query(5, ge=1, le=20),
               s: InsightService = Depends(ins)):
        d = s.search(q.strip(), limit)
        return ok(d, count=len(d["results"]))

    @r.get("/exports/{kind}", tags=["exports"])
    def export(kind: Literal["risks.csv", "recommendations.csv", "anomalies.csv", "risk-report.md"],
               s: InsightService = Depends(ins)):
        body, media, name = s.export(kind)
        return Response(body, media_type=f"{media}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="orbit-{name}"'})

    return r
