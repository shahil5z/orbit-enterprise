"""Phase 2: KPI governance, scenario model, and the page/drill-down/search/export endpoints."""
import pytest
from fastapi.testclient import TestClient

from apps.api.orbit_api.main import create_app
from decision import scenarios
from decision.scenarios import RegionBaseline
from orbit_core import kpis
from tests.conftest import needs_db
from tests.test_api import FakeRepo


# ---------- KPI governance ----------

def test_kpi_catalogue_is_unique_and_complete():
    keys = [k.key for k in kpis.CATALOGUE]
    assert len(keys) == len(set(keys))
    for k in kpis.CATALOGUE:
        assert k.unit in {"currency", "percent", "count", "hours", "score", "ratio"}
        assert k.definition and k.formula and k.source and k.dimensions
    assert {"revenue", "gross_margin_pct", "var95", "quality_score", "forecast_mape"} <= set(kpis.BY_KEY)


# ---------- scenario model ----------

BASE = [RegionBaseline("R01", 100.0, 0.4, 30.0, 5.0, 50.0, 0.7, 90.0, 12.0),
        RegionBaseline("R02", 50.0, 0.3, 12.0, 2.0, 20.0, 0.95, 44.0, 7.0)]


def test_zero_levers_equal_baseline():
    r = scenarios.run(BASE, {})
    assert r["label"] == "SCENARIO"
    assert all(abs(v) < 1e-9 for v in r["delta"].values())
    assert r["capacity_bound_regions"] == []


def test_demand_increase_raises_revenue_until_capacity_binds():
    r = scenarios.run(BASE, {"demand_change": 0.2})
    by = {x["region_id"]: x for x in r["regions"]}
    assert by["R01"]["scenario"]["revenue"] == pytest.approx(120.0)
    # R02 runs at 95% utilization: max served = 50 / 0.95 = 52.63
    assert by["R02"]["scenario"]["capacity_bound"] is True
    assert by["R02"]["scenario"]["revenue"] == pytest.approx(50 / 0.95)
    assert r["capacity_bound_regions"] == ["R02"]


def test_cost_increase_lowers_profit_and_churn_lowers_revenue():
    assert scenarios.run(BASE, {"cost_change": 0.1})["delta"]["operating_profit"] < 0
    assert scenarios.run(BASE, {"churn_change": 0.05})["delta"]["revenue"] == pytest.approx(-7.5)


@pytest.mark.parametrize("params", [{"demand_change": 0.5}, {"cost_change": -0.3}, {"bogus": 0.1}])
def test_scenario_validation(params):
    with pytest.raises(ValueError):
        scenarios.validate(params)


# ---------- endpoint validation without a database ----------

@pytest.fixture
def client():
    return TestClient(create_app(FakeRepo()), raise_server_exceptions=False)


def test_kpis_endpoint_serves_catalogue(client):
    r = client.get("/api/v1/kpis")
    assert r.status_code == 200
    assert {k["key"] for k in r.json()["data"]["kpis"]} == set(kpis.BY_KEY)


@pytest.mark.parametrize("method,url,body", [
    ("get", "/api/v1/search?q=a", None),
    ("get", "/api/v1/search?q=" + "x" * 61, None),
    ("get", "/api/v1/intelligence?segment=Galactic", None),
    ("get", "/api/v1/intelligence?region_id=R1;DROP", None),
    ("get", "/api/v1/anomalies/explore?limit=1000", None),
    ("get", "/api/v1/anomalies/bad%20id'", None),
    ("get", "/api/v1/exports/passwords.csv", None),
    ("post", "/api/v1/scenarios/run", {"demand_change": 0.9}),
])
def test_phase2_validation_returns_422(client, method, url, body):
    r = client.post(url, json=body) if method == "post" else client.get(url)
    assert r.status_code == 422, r.text[:300]
    assert r.json()["success"] is False


def test_intelligence_date_order_rejected(client):
    r = client.get("/api/v1/intelligence?start=2025-06-01&end=2025-01-01")
    assert r.status_code == 400


# ---------- live, against the seeded PostgreSQL ----------

@pytest.fixture
def live():
    return TestClient(create_app(), raise_server_exceptions=False)


LIVE = ["/api/v1/kpis", "/api/v1/dimensions", "/api/v1/overview", "/api/v1/intelligence",
        "/api/v1/intelligence?region_id=R04&segment=SMB&start=2025-01-01&end=2025-06-30",
        "/api/v1/forecasts/series", "/api/v1/forecasts/series?region_id=R04", "/api/v1/risks/region/R04",
        "/api/v1/anomalies/explore?region_id=R04", "/api/v1/operations/summary?bu_id=BU02", "/api/v1/scenarios/levers",
        "/api/v1/data/quality/incidents", "/api/v1/models/catalog", "/api/v1/system", "/api/v1/search?q=EMEA"]


@needs_db
@pytest.mark.parametrize("url", LIVE)
def test_live_phase2_endpoints(live, url):
    r = live.get(url)
    assert r.status_code == 200, r.text[:500]
    assert r.json()["success"] is True


@needs_db
def test_live_overview_matches_ttm_components(live):
    d = live.get("/api/v1/overview").json()["data"]
    t = d["ttm"]
    assert t["operating_profit"] == pytest.approx(t["gross_margin"] - t["opex"], rel=1e-6)
    assert sum(r["revenue"] for r in d["by_region"]) == pytest.approx(t["revenue"], rel=1e-6)
    assert d["label"] == "Simulated enterprise dataset"


@needs_db
def test_live_filters_narrow_results(live):
    all_rev = live.get("/api/v1/intelligence").json()["data"]["comparison"]["revenue"]["current"]
    r04 = live.get("/api/v1/intelligence?region_id=R04").json()["data"]
    assert 0 < r04["comparison"]["revenue"]["current"] < all_rev
    assert {g["key"] for g in r04["by_region"]} == {"R04"}


@needs_db
def test_live_anomaly_drilldown_and_trace(live):
    rows = live.get("/api/v1/anomalies/explore?limit=1").json()["data"]["rows"]
    d = live.get(f"/api/v1/anomalies/{rows[0]['operation_id']}").json()["data"]
    assert d["deviations"] and d["explanation"]
    assert live.get("/api/v1/anomalies/NOPE-1").status_code == 404
    recs = live.get("/api/v1/recommendations").json()["data"]["recommendations"]
    chain = live.get(f"/api/v1/decisions/{recs[0]['decision_id']}/trace").json()["data"]["chain"]
    assert [c["level"] for c in chain] == ["recommendation", "forecast", "model_output", "metric", "dataset"]


@needs_db
def test_live_scenario_zero_is_baseline_and_demand_moves_revenue(live):
    zero = live.post("/api/v1/scenarios/run", json={}).json()["data"]
    assert all(abs(v) < 1e-6 for v in zero["delta"].values())
    up = live.post("/api/v1/scenarios/run", json={"demand_change": 0.1}).json()["data"]
    assert up["delta"]["revenue"] > 0 and up["label"] == "SCENARIO"


@needs_db
def test_live_search_and_exports(live):
    res = live.get("/api/v1/search?q=EMEA").json()["data"]["results"]
    assert any(r["type"] == "region" and r["id"] == "R03" for r in res)
    assert live.get("/api/v1/search?q=%25%25").json()["data"]["results"] == []  # LIKE wildcards are escaped
    csv = live.get("/api/v1/exports/risks.csv")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("entity_type") and len(csv.text.splitlines()) > 10
    md = live.get("/api/v1/exports/risk-report.md")
    assert md.status_code == 200 and "Simulated enterprise dataset" in md.text


@needs_db
def test_bi_export_writes_typed_datasets(tmp_path):
    import csv as _csv
    from bi.export import export
    s = export(tmp_path)
    assert s["label"] == "Simulated enterprise dataset"
    for name, meta in s["datasets"].items():
        with (tmp_path / meta["file"]).open(encoding="utf-8") as fh:
            rows = list(_csv.reader(fh))
        assert rows[0] == [c["name"] for c in meta["columns"]]
        assert len(rows) - 1 == meta["rows"] > 0, name
    risk_levels = {r["risk_level"] for r in _csv.DictReader((tmp_path / "fact_risks.csv").open(encoding="utf-8"))}
    assert risk_levels <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
