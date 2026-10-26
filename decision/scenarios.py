"""Scenario Lab: deterministic what-if model over the latest pipeline baseline.

The baseline per region is the 6-month revenue forecast plus the last 6 months of actual cost,
marketing, headcount and order structure. Levers are applied with explicit, documented assumptions
(returned with every result). Output is a scenario, not a forecast: it is always labelled SCENARIO."""
from __future__ import annotations

from dataclasses import dataclass

from optimization.workflow import INCREMENTAL_REVENUE_PER_DOLLAR

ASSUMPTIONS = {
    "horizon_months": 6,
    "incremental_revenue_per_marketing_dollar": INCREMENTAL_REVENUE_PER_DOLLAR,
    "marketing_return_above_current_spend": 0.5,
    "labour_share_of_non_marketing_opex": 0.4,
    "capacity_from_workforce_elasticity": 0.5,
    "capacity_proxy": "95th percentile of monthly orders per head x headcount, last 24 months",
    "churn_change_meaning": "change in the share of revenue lost to churn over the horizon (percentage points)",
    "revenue_at_risk_scaling": "regional Monte Carlo P5 and CVaR95 scaled by scenario revenue / baseline revenue; totals are sums of regional values, not portfolio percentiles",
    "source": "planning assumptions; the simulated data has no causal model for these levers",
}

LEVERS = {  # name: (min, max, description)
    "demand_change": (-0.3, 0.3, "change in customer demand"),
    "cost_change": (-0.2, 0.3, "change in non-marketing operating cost and unit cost"),
    "capacity_change": (-0.3, 0.3, "change in operational capacity"),
    "workforce_change": (-0.2, 0.2, "change in headcount"),
    "marketing_budget_change": (-0.5, 0.5, "change in marketing budget"),
    "churn_change": (-0.1, 0.1, "change in churned revenue share (customer behaviour)"),
}


def validate(params: dict) -> dict:
    out = {}
    for k, (lo, hi, _) in LEVERS.items():
        v = float(params.get(k, 0.0))
        if not lo <= v <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
        out[k] = v
    unknown = set(params) - set(LEVERS)
    if unknown:
        raise ValueError(f"unknown levers: {sorted(unknown)}")
    return out


@dataclass
class RegionBaseline:
    region_id: str
    revenue: float          # 6-month forecast revenue
    gross_margin_pct: float
    opex: float             # last 6 months, includes marketing
    marketing: float        # last 6 months
    headcount: float        # average
    utilization: float      # orders / capacity proxy, last 6 months
    p5: float
    cvar95: float


def _region(b: RegionBaseline, p: dict) -> dict:
    a = ASSUMPTIONS
    mkt_delta = b.marketing * p["marketing_budget_change"]
    rate = a["incremental_revenue_per_marketing_dollar"] * (a["marketing_return_above_current_spend"] if mkt_delta > 0 else 1)
    demanded = b.revenue * (1 + p["demand_change"] - p["churn_change"]) + mkt_delta * rate
    cap_factor = (1 + p["capacity_change"]) * (1 + a["capacity_from_workforce_elasticity"] * p["workforce_change"])
    max_served = b.revenue * cap_factor / max(b.utilization, 1e-6)
    served = max(0.0, min(demanded, max_served))
    gm = served * b.gross_margin_pct * (1 - p["cost_change"] * (1 - b.gross_margin_pct) / max(b.gross_margin_pct, 1e-6))
    non_mkt = b.opex - b.marketing
    opex = (non_mkt * (1 + p["cost_change"]) * (1 + a["labour_share_of_non_marketing_opex"] * p["workforce_change"])
            + b.marketing + mkt_delta)
    base_profit = b.revenue * b.gross_margin_pct - b.opex
    scale = served / b.revenue if b.revenue else 0
    return {
        "region_id": b.region_id,
        "baseline": {"revenue": b.revenue, "gross_margin": b.revenue * b.gross_margin_pct, "opex": b.opex,
                     "operating_profit": base_profit, "utilization": b.utilization, "p5": b.p5, "cvar95": b.cvar95},
        "scenario": {"revenue": served, "demanded_revenue": demanded, "gross_margin": gm, "opex": opex,
                     "operating_profit": gm - opex, "utilization": min(1.0, b.utilization * (demanded / b.revenue) / cap_factor)
                     if b.revenue else 0, "capacity_bound": demanded > max_served, "p5": b.p5 * scale,
                     "cvar95": b.cvar95 * scale},
    }


def run(baselines: list[RegionBaseline], params: dict) -> dict:
    p = validate(params)
    regions = [_region(b, p) for b in baselines]
    keys = ("revenue", "gross_margin", "opex", "operating_profit", "p5", "cvar95")
    tot = {side: {k: sum(r[side][k] for r in regions) for k in keys} for side in ("baseline", "scenario")}
    delta = {k: tot["scenario"][k] - tot["baseline"][k] for k in keys}
    pct = {k: (delta[k] / tot["baseline"][k] if tot["baseline"][k] else None) for k in keys}
    return {"label": "SCENARIO", "parameters": p, "assumptions": ASSUMPTIONS, "regions": regions, "totals": tot,
            "delta": delta, "delta_pct": pct,
            "capacity_bound_regions": [r["region_id"] for r in regions if r["scenario"]["capacity_bound"]]}
