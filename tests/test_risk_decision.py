import json

import pytest

from ml.risk.engine import FACTORS, level_for, score_entity
from orbit_core.config import PATHS
from tests.conftest import needs_outputs

FULL = {"churn_exposure": 0.2, "revenue_at_risk": 0.1, "forecast_decline": 0.05, "operational_anomalies": 0.01,
        "incident_severity": 2.0, "compliance_gap": 0.1, "fx_volatility": 0.05}


def test_factor_weights_sum_to_one():
    assert sum(w for w, _, _ in FACTORS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("score,level", [(0, "LOW"), (24.99, "LOW"), (25, "MEDIUM"), (50, "HIGH"), (70, "CRITICAL"),
                                         (100, "CRITICAL")])
def test_level_boundaries(score, level):
    assert level_for(score) == level


def test_score_is_bounded_and_explained():
    r = score_entity(FULL, 1.0, 0.9)
    assert 0 <= r["risk_score"] <= 100
    assert r["explanation"] and r["recommended_action"]
    assert len(r["risk_factors"]) == len(FACTORS)


def test_worse_inputs_increase_risk():
    worse = {**FULL, "churn_exposure": 0.6, "forecast_decline": 0.3}
    assert score_entity(worse, 1, 0.9)["risk_score"] > score_entity(FULL, 1, 0.9)["risk_score"]


def test_missing_factor_lowers_confidence_not_crash():
    partial = {**FULL, "fx_volatility": float("nan")}
    assert score_entity(partial, 6 / 7, 0.9)["confidence"] < score_entity(FULL, 1, 0.9)["confidence"]


@needs_outputs("decisions/decisions.json")
def test_decisions_are_evidence_backed_and_llm_free():
    decs = json.loads((PATHS.outputs / "decisions" / "decisions.json").read_text())
    assert decs and decs[0]["scope"] == "company"
    for d in decs:
        for k in ("observation", "cause", "forecast", "risk", "recommendation", "expected_impact", "confidence"):
            assert d[k] not in (None, "")
        assert d["evidence"] and "no language model" in d["method"]
