"""The 8 path-parameter endpoints against the real seeded database: valid IDs and controlled errors."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import needs_db

pytestmark = needs_db
LEAK = re.compile(r"Traceback|File \"|psycopg|postgres(ql)?://|SELECT ", re.I)


@pytest.fixture(scope="module")
def client():
    from apps.api.orbit_api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def ids(client):
    g = lambda p: client.get("/api/v1" + p).json()["data"]
    return {
        "region": next(r["region_id"] for r in g("/risks")["risks"] if r.get("region_id")),
        "operation": g("/anomalies?limit=1")["anomalies"][0]["operation_id"],
        "decision": g("/recommendations")["recommendations"][0]["decision_id"],
        "dataset": g("/data/quality")["datasets"][0]["dataset"],
        "optimization": g("/optimization?limit=1")["runs"][0]["optimization_id"],
        "model": g("/models")["models"][0]["model_version"],
        "run": g("/operations?limit=1")["pipeline_runs"][0]["run_id"],
    }


def ok(client, path):
    r = client.get("/api/v1" + path)
    assert r.status_code == 200, (path, r.status_code)
    body = r.json()
    assert body["success"] is True and body["errors"] == [] and body["data"]
    return body["data"]


def controlled(client, path, statuses):
    r = client.get("/api/v1" + path)
    assert r.status_code in statuses, (path, r.status_code)
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert re.fullmatch(r"[A-Z_]+", body["errors"][0]["code"])
    assert not LEAK.search(json.dumps(body))


def test_risk_region(client, ids):
    d = ok(client, f"/risks/region/{ids['region']}")
    assert d["region_id"] == ids["region"] and isinstance(d["region"]["risk_score"], float)
    controlled(client, "/risks/region/R99", {400, 404})
    controlled(client, "/risks/region/XYZ", {400})


def test_anomaly(client, ids):
    assert ok(client, f"/anomalies/{ids['operation']}")["operation"]["operation_id"] == ids["operation"]
    controlled(client, "/anomalies/OP9999999", {404})
    controlled(client, "/anomalies/bad%20id", {422})


def test_decision_trace(client, ids):
    assert ok(client, f"/decisions/{ids['decision']}/trace")["decision"]["decision_id"] == ids["decision"]
    controlled(client, "/decisions/no-such-decision/trace", {404})


def test_quality_dataset(client, ids):
    assert ok(client, f"/data/quality/{ids['dataset']}")["dataset"]["dataset"] == ids["dataset"]
    controlled(client, "/data/quality/no_such_dataset", {404})


@pytest.mark.parametrize("kind", ["risks.csv", "recommendations.csv", "anomalies.csv", "risk-report.md"])
def test_exports(client, kind):
    r = client.get(f"/api/v1/exports/{kind}")
    assert r.status_code == 200 and f"orbit-{kind}" in r.headers["content-disposition"]
    assert len(r.text) > 50 and "ORBIT //" not in r.text


def test_exports_invalid(client):
    controlled(client, "/exports/secrets.txt", {422})


def test_optimization_run(client, ids):
    d = ok(client, f"/optimization/{ids['optimization']}")
    assert d["optimization_id"] == ids["optimization"] and d["status"] == "OPTIMAL"
    controlled(client, "/optimization/OPT-does-not-exist", {404})


def test_model_version(client, ids):
    d = ok(client, f"/models/{ids['model']}")
    assert d["model_version"] == ids["model"] and d["metrics"]
    controlled(client, "/models/no-such-model", {404})


def test_pipeline_run(client, ids):
    d = ok(client, f"/operations/runs/{ids['run']}")
    assert d["run_id"] == ids["run"] and len(d["stages"]) == 11
    controlled(client, "/operations/runs/no-such-run", {404})
