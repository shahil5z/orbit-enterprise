"""OPTIMIZE stage: build the allocation problem from forecasts and risk scores, solve it in Julia,
and store baseline vs optimized scenarios.

Planning assumptions (explicit because the simulated data has no causal marketing effect):
  * INCREMENTAL_REVENUE_PER_DOLLAR: assumed incremental revenue per marketing dollar up to current spend.
  * Spend above the current level earns half that return (diminishing returns).
  * Returns scale with the unit's gross margin %, its region's forecast growth and (1 - risk/200).
  * A new hire adds HIRE_UPLIFT of current revenue per head over the horizon, at the unit's margin.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS
from orbit_core.io import write_json

JULIA_MODEL = PATHS.root / "analytics" / "julia" / "allocation.jl"
INCREMENTAL_REVENUE_PER_DOLLAR = 1.8
HIRE_UPLIFT = 0.15
DEFAULTS = {"total_hires": 40, "risk_cap_factor": 0.95, "min_region_share": 0.85, "budget_multiplier": 1.0}


def build_problem(kpis: pd.DataFrame, forecast: pd.DataFrame, unit_risk: dict, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    k = kpis.copy()
    k["month"] = pd.to_datetime(k.month)
    last = k.month.max()
    recent = k[k.month > last - pd.DateOffset(months=6)]
    g = recent.groupby(["region_id", "bu_id"]).agg(spend=("marketing_spend", "sum"), revenue=("revenue", "sum"),
                                                    gm=("gross_margin", "sum"), heads=("avg_headcount", "mean"))
    reg_last6 = recent.groupby("region_id").revenue.sum()
    reg_fc = forecast.groupby("region_id").forecast.sum()
    growth = (reg_fc / reg_last6 - 1).to_dict()
    units = []
    for (rid, bu), row in g.iterrows():
        risk = float(unit_risk.get(f"{rid}|{bu}", 0.0))
        gm_pct = row.gm / row.revenue if row.revenue else 0.0
        adj = gm_pct * (1 + growth.get(rid, 0.0)) * (1 - risk / 200)
        r1 = INCREMENTAL_REVENUE_PER_DOLLAR * adj
        units.append({"unit_id": f"{rid}|{bu}", "region_id": rid, "bu_id": bu, "base_spend": round(float(row.spend), 2),
                      "return_tier1": round(r1, 6), "return_tier2": round(r1 / 2, 6), "risk_score": risk,
                      "hire_value": round(float(row.revenue / row.heads * HIRE_UPLIFT * gm_pct * (1 - risk / 200)), 2),
                      "max_hires": int(max(1, round(row.heads * 0.1)))})
    budget = round(sum(u["base_spend"] for u in units) * p["budget_multiplier"], 2)
    return {"budget": budget, "total_hires": int(p["total_hires"]), "risk_cap_factor": float(p["risk_cap_factor"]),
            "min_region_share": float(p["min_region_share"]), "horizon_months": 6,
            "assumptions": {"incremental_revenue_per_dollar": INCREMENTAL_REVENUE_PER_DOLLAR, "hire_uplift": HIRE_UPLIFT,
                            "forecast_growth_by_region": {r: round(v, 4) for r, v in growth.items()}},
            "units": units}


def validate_params(params: dict) -> dict:
    p = {**DEFAULTS, **params}
    if not (0.5 <= float(p["budget_multiplier"]) <= 1.5):
        raise ValueError("budget_multiplier must be within [0.5, 1.5]")
    if not (0 <= int(p["total_hires"]) <= 200):
        raise ValueError("total_hires must be within [0, 200]")
    if not (0.7 <= float(p["risk_cap_factor"]) <= 1.2):
        raise ValueError("risk_cap_factor must be within [0.7, 1.2]")
    if not (0.5 <= float(p["min_region_share"]) <= 1.0):
        raise ValueError("min_region_share must be within [0.5, 1.0]")
    return p


def solve(problem: dict, workdir: Path, timeout_s: int = 600) -> dict:
    julia = shutil.which("julia")
    if not julia:
        raise RuntimeError("julia not found on PATH (run scripts/env.ps1)")
    if sum(u["max_hires"] for u in problem["units"]) < problem["total_hires"]:
        raise ValueError("total_hires exceeds the sum of per-unit hire caps; problem is infeasible")
    workdir.mkdir(parents=True, exist_ok=True)
    inp, out = workdir / "input.json", workdir / "result.json"
    write_json(inp, problem)
    proj = str(JULIA_MODEL.parent)
    subprocess.run([julia, f"--project={proj}", str(JULIA_MODEL), str(inp), str(out)], check=True,
                   capture_output=True, text=True, timeout=timeout_s)
    result = json.loads(out.read_text(encoding="utf-8"))
    return result


def summarize_by_region(result: dict) -> list[dict]:
    if "allocations" not in result:
        return []
    a = pd.DataFrame(result["allocations"])
    g = a.groupby("region_id").agg(baseline_spend=("baseline_spend", "sum"), optimized_spend=("optimized_spend", "sum"),
                                   baseline_hires=("baseline_hires", "sum"), optimized_hires=("optimized_hires", "sum"))
    g["spend_change_pct"] = g.optimized_spend / g.baseline_spend - 1
    return g.reset_index().round(4).to_dict(orient="records")
