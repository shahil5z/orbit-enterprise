import pytest
from fastapi.testclient import TestClient

from apps.api.orbit_api.main import create_app
from tests.conftest import needs_db


class FakeRepo:
    """In-memory repository so envelope, validation and error paths are tested without a database."""

    def ping(self):
        return {"version": "PostgreSQL 17.7, fake", "database": "orbit"}

    def latest_run_id(self, table):
        return "RUN1"

    def risks(self, run_id, entity_type, level):
        return [{"entity_type": "region", "region_id": "R01", "bu_id": None, "risk_score": 51.0, "risk_level": "HIGH"}]

    def recommendations(self, run_id, priority):
        raise RuntimeError("secret internal detail: password=hunter2")

    def optimization_run(self, oid):
        return None

    def metrics(self, **kw):
        return []

    def metric_names(self):
        return ["revenue"]


class EmptyRepo(FakeRepo):
    def latest_run_id(self, table):
        return None


@pytest.fixture
def client():
    return TestClient(create_app(FakeRepo()), raise_server_exceptions=False)


def test_health_envelope(client):
    r = client.get("/api/v1/health")
    b = r.json()
    assert r.status_code == 200 and b["success"] is True and b["errors"] == []
    assert set(b) == {"success", "data", "metadata", "errors"}
    assert b["metadata"]["api_version"] == "v1" and b["data"]["database"]["status"] == "up"


def test_internal_errors_are_sanitized(client):
    r = client.get("/api/v1/recommendations")
    assert r.status_code == 500
    body = r.text
    assert "hunter2" not in body and "secret" not in body
    assert r.json()["errors"][0]["code"] == "INTERNAL_ERROR"


@pytest.mark.parametrize("url", ["/api/v1/metrics?region_id=R99x", "/api/v1/metrics?limit=0",
                                 "/api/v1/risks?level=EXTREME", "/api/v1/anomalies?limit=100000"])
def test_query_validation_returns_422(client, url):
    r = client.get(url)
    assert r.status_code == 422 and r.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_metrics_date_order_rejected(client):
    r = client.get("/api/v1/metrics?start=2025-05-01&end=2025-01-01")
    assert r.status_code == 400 and r.json()["errors"][0]["code"] == "INVALID_PARAMETERS"


def test_sql_injection_like_input_is_rejected_or_inert(client):
    r = client.get("/api/v1/metrics", params={"metric": "revenue'; DROP TABLE metrics;--"})
    assert r.status_code == 200 and r.json()["data"]["rows"] == []


def test_not_found_paths(client):
    assert client.get("/api/v1/does-not-exist").status_code == 404
    r = client.get("/api/v1/optimization/OPT-unknown")
    assert r.status_code == 404 and r.json()["success"] is False


def test_optimization_run_rejects_out_of_range_params(client):
    r = client.post("/api/v1/optimization/run", json={"total_hires": 5000})
    assert r.status_code == 422
    r = client.post("/api/v1/optimization/run", json={"budget_multiplier": "lots"})
    assert r.status_code == 422


def test_no_pipeline_output_gives_404():
    c = TestClient(create_app(EmptyRepo()), raise_server_exceptions=False)
    r = c.get("/api/v1/risks")
    assert r.status_code == 404 and "run the pipeline" in r.json()["errors"][0]["message"]


def test_cors_allows_configured_origin_only(client):
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    bad = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_openapi_lists_all_resources(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/v1/health", "/api/v1/data/quality", "/api/v1/metrics", "/api/v1/analytics", "/api/v1/forecasts",
              "/api/v1/anomalies", "/api/v1/risks", "/api/v1/recommendations", "/api/v1/optimization",
              "/api/v1/optimization/run", "/api/v1/models", "/api/v1/operations"]:
        assert p in paths


# ---------- integration against the real seeded PostgreSQL ----------

@pytest.fixture
def live():
    return TestClient(create_app(), raise_server_exceptions=False)


@needs_db
@pytest.mark.parametrize("url", ["/api/v1/health", "/api/v1/data/quality", "/api/v1/metrics?metric=revenue&limit=10",
                                 "/api/v1/analytics", "/api/v1/forecasts", "/api/v1/anomalies", "/api/v1/risks",
                                 "/api/v1/recommendations", "/api/v1/optimization", "/api/v1/models",
                                 "/api/v1/operations"])
def test_live_endpoints(live, url):
    r = live.get(url)
    assert r.status_code == 200, r.text[:500]
    assert r.json()["success"] is True


@needs_db
def test_live_forecast_region_filter(live):
    rows = live.get("/api/v1/forecasts?region_id=R01").json()["data"]["forecasts"]
    assert rows and {r["region_id"] for r in rows} == {"R01"}


@needs_db
def test_live_model_lookup(live):
    models = live.get("/api/v1/models").json()["data"]["models"]
    v = models[0]["model_version"]
    assert live.get(f"/api/v1/models/{v}").json()["data"]["model_version"] == v
    assert live.get("/api/v1/models/nope-v1").status_code == 404
