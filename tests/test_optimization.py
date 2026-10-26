import json

import pandas as pd
import pytest

from optimization.workflow import build_problem, solve, validate_params
from orbit_core.config import PATHS
from tests.conftest import needs_outputs, needs_tool


@pytest.mark.parametrize("bad", [{"budget_multiplier": 3}, {"total_hires": -1}, {"risk_cap_factor": 0.1},
                                 {"min_region_share": 1.5}])
def test_invalid_parameters_rejected(bad):
    with pytest.raises(ValueError):
        validate_params(bad)


def _problem(**p):
    kpis = pd.read_parquet(PATHS.curated / "marts" / "monthly_kpis")
    fc = pd.read_parquet(PATHS.outputs / "ml" / "forecast.parquet")
    return build_problem(kpis, fc, {}, validate_params(p))


@needs_outputs("ml/forecast.parquet")
def test_problem_budget_matches_baseline_spend():
    prob = _problem()
    assert prob["budget"] == pytest.approx(sum(u["base_spend"] for u in prob["units"]), rel=1e-6)
    assert all(u["return_tier2"] < u["return_tier1"] for u in prob["units"])


@needs_tool("julia")
@needs_outputs("ml/forecast.parquet")
def test_optimizer_respects_constraints_and_beats_baseline(tmp_path):
    prob = _problem()
    res = solve(prob, tmp_path)
    assert res["status"] == "OPTIMAL"
    assert res["objective"] >= res["baseline"]["objective"] - 1e-6
    a = pd.DataFrame(res["allocations"])
    assert a.optimized_spend.sum() == pytest.approx(prob["budget"], rel=1e-6)
    assert a.optimized_hires.sum() == prob["total_hires"]
    assert (a.optimized_spend >= 0.6 * a.baseline_spend - 1e-6).all()


@needs_tool("julia")
@needs_outputs("ml/forecast.parquet")
def test_infeasible_hiring_rejected_before_solve(tmp_path):
    prob = _problem()
    prob["total_hires"] = 10_000
    with pytest.raises(ValueError, match="infeasible"):
        solve(prob, tmp_path)


@needs_outputs("optimization/latest.json")
def test_pipeline_stored_baseline_and_optimized():
    doc = json.loads((PATHS.outputs / "optimization" / "latest.json").read_text())
    assert doc["baseline_objective"] > 0 and doc["by_region"]
