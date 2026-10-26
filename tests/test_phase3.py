"""Phase 3: production configuration, HTTP hardening, hosted degradation and DB publishing."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.orbit_api.main import create_app
from apps.api.orbit_api.services import NotFound, OrbitService
from orbit_core.config import Settings
from tests.conftest import needs_db
from tests.test_api import FakeRepo

RUN = {"optimization_id": "OPT-1", "run_id": "RUN1", "status": "OPTIMAL", "objective": 2.0, "baseline_objective": 1.0,
       "improvement_abs": 1.0, "improvement_pct": 1.0, "parameters": {"total_hires": 40}, "triggered_by": "pipeline",
       "created_at": "2026-10-26T00:00:00Z", "result": {"by_region": [{"region_id": "R01"}], "assumptions": {"a": 1}}}


class OptRepo(FakeRepo):
    def optimization_runs(self, limit):
        return [RUN]

    def optimization_run(self, oid):
        return RUN if oid == "OPT-1" else None

    def artifact(self, name):
        return {"overall_quality_score": 99.0, "scoring": None} if name == "quality/quality_report.json" else None

    def quality_runs(self, run_id):
        return []


def _settings(monkeypatch, **env):
    for k in ("ORBIT_DATABASE_URL", "DATABASE_URL", "ORBIT_CORS_ORIGINS", "ORBIT_LOCAL_ENGINES"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_prod_rejects_loopback_and_missing_db(monkeypatch):
    s = _settings(monkeypatch, ORBIT_ENV="prod")
    assert s.problems() == ["DATABASE_URL is not set in prod"] and s.cors_origins == () and not s.local_engines
    s = _settings(monkeypatch, ORBIT_ENV="prod", DATABASE_URL="postgresql://u:p@localhost/db",
                  ORBIT_CORS_ORIGINS="http://127.0.0.1:5173")
    assert len(s.problems()) == 2 and all("p@" not in p for p in s.problems())  # no secret in messages
    s = _settings(monkeypatch, ORBIT_ENV="prod", DATABASE_URL="postgresql://u:p@db.example.net/db?sslmode=require")
    assert s.problems() == [] and s.dsn.startswith("postgresql://")


def test_local_defaults_and_invalid_env(monkeypatch):
    s = _settings(monkeypatch, ORBIT_ENV="local")
    assert s.local_engines and s.cors_origins == ("http://localhost:5173",) and s.problems() == []
    monkeypatch.setenv("ORBIT_ENV", "staging")
    with pytest.raises(RuntimeError):
        Settings()


@pytest.fixture
def client():
    return TestClient(create_app(OptRepo()), raise_server_exceptions=False)


def test_security_headers_on_api_responses(client):
    r = client.get("/api/v1/health")
    for h in ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy"):
        assert h in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_body_limit_returns_413(client):
    r = client.post("/api/v1/scenarios/run", content=b"{" + b" " * 40_000 + b"}",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["errors"][0]["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_returns_429(monkeypatch):
    from apps.api.orbit_api import main
    monkeypatch.setattr(main, "SETTINGS", _settings(monkeypatch, ORBIT_ENV="local", ORBIT_RATE_LIMIT_PER_MIN="3"))
    c = TestClient(main.create_app(OptRepo()), raise_server_exceptions=False)
    codes = [c.get("/api/v1/capabilities").status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_hosted_optimization_serves_latest_persisted_run():
    c = TestClient(create_app(OptRepo(), local_engines=False), raise_server_exceptions=False)
    caps = c.get("/api/v1/capabilities").json()["data"]
    assert caps["optimization_solver"] is False and "workstation" in caps["note"]
    r = c.post("/api/v1/optimization/run", json={"total_hires": 10})
    d = r.json()["data"]
    assert r.status_code == 200 and d["mode"] == "persisted" and d["optimization_id"] == "OPT-1"
    assert "runs locally" in d["message"] and d["requested_parameters"]["total_hires"] == 10
    assert c.post("/api/v1/optimization/run", json={"total_hires": 5000}).status_code == 422


def test_hosted_optimization_without_runs_is_404():
    class NoRuns(OptRepo):
        def optimization_runs(self, limit):
            return []
    r = TestClient(create_app(NoRuns(), local_engines=False), raise_server_exceptions=False).post(
        "/api/v1/optimization/run", json={})
    assert r.status_code == 404 and "runs locally" in r.json()["errors"][0]["message"]


def test_artifact_falls_back_to_database(tmp_path):
    s = OrbitService(OptRepo(), outputs=tmp_path)
    assert s.artifact("quality/quality_report.json")["overall_quality_score"] == 99.0
    assert s.artifact("rust/benchmark.json", required=False) is None
    with pytest.raises(NotFound):
        s.artifact("r/statistics.json")
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "statistics.json").write_text(json.dumps({"local": True}))
    assert s.artifact("r/statistics.json") == {"local": True}  # local file wins


def test_unhandled_errors_never_leak_details(client):
    r = client.get("/api/v1/recommendations")
    assert r.status_code == 500 and "hunter2" not in r.text and "Traceback" not in r.text


@needs_db
def test_publish_round_trip_to_a_second_database():
    import psycopg
    from database.seeds.publish import publish
    from orbit_core.config import SETTINGS
    from apps.api.orbit_api.repository import Repository
    try:
        with psycopg.connect(SETTINGS.dsn, autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS orbit_publish_test")
            c.execute("CREATE DATABASE orbit_publish_test")
    except psycopg.Error:
        pytest.skip("role cannot create databases")
    from psycopg.conninfo import make_conninfo
    target = make_conninfo(SETTINGS.dsn, dbname="orbit_publish_test")
    with pytest.raises(ValueError):
        publish(SETTINGS.dsn)  # never onto itself
    try:
        counts = publish(target)
        src = Repository().table_counts()
        dst = Repository(target).table_counts()
        assert src == dst and counts["artifacts"] >= 5
        assert Repository(target).artifact("ml/model_reports.json") is not None
        hosted = TestClient(create_app(Repository(target), local_engines=False), raise_server_exceptions=False)
        hosted.app.state.service.out = Path("/nonexistent")  # no local files: DB artifacts only
        for path in ("/api/v1/data/quality", "/api/v1/analytics", "/api/v1/risks", "/api/v1/forecasts/series",
                     "/api/v1/operations", "/api/v1/models/catalog", "/api/v1/overview"):
            assert hosted.get(path).status_code == 200, path
        assert publish(target)["artifacts"] == counts["artifacts"]  # idempotent re-publish
    finally:
        with psycopg.connect(SETTINGS.dsn, autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS orbit_publish_test")
