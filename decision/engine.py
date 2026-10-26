"""Decision intelligence: deterministic, evidence-referenced recommendations (no LLM).

Each decision is assembled from computed metrics only. Every sentence is produced from a template
filled with values that also appear in `evidence`, each pointing at the artifact and key it came from.
"""
from __future__ import annotations

import pandas as pd

REGION_NAMES = {"R01": "North America East", "R02": "North America West", "R03": "EMEA North",
                "R04": "EMEA South", "R05": "APAC", "R06": "LATAM"}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _money(x: float) -> str:
    return f"{x / 1e6:,.2f}M"


def build_decisions(region_risks: dict, analytics: dict, r_stats: dict, forecast: pd.DataFrame, rar: dict,
                    churn_preds: pd.DataFrame, optimization: dict, churn_report: dict, run_id: str) -> list[dict]:
    by_region = {r["region_id"]: r for r in analytics["by_region"]}
    trends = {t["region_id"]: t for t in analytics["trends"]}
    yoy = {t["region_id"]: t for t in r_stats.get("yoy_paired_tests", [])}
    opt_reg = {r["region_id"]: r for r in optimization.get("by_region", [])}
    decisions = []
    for rid, risk in sorted(region_risks.items(), key=lambda kv: -kv[1]["risk_score"]):
        name = REGION_NAMES.get(rid, rid)
        k = by_region[rid]
        ctx = risk["_context"]
        y = yoy.get(rid, {})
        ev = [
            {"source": "analytics", "ref": f"data/outputs/analytics/analytics_summary.json#by_region[{rid}].revenue_growth",
             "value": k["revenue_growth"]},
            {"source": "analytics", "ref": f"data/outputs/analytics/analytics_summary.json#by_region[{rid}].operating_margin_pct", "value": k["operating_margin_pct"]},
            {"source": "r_statistics", "ref": f"data/outputs/r/statistics.json#yoy_paired_tests[{rid}].p_value",
             "value": y.get("p_value")},
            {"source": "forecast", "ref": f"forecasts[{rid}].sum(horizon 1..6)", "value": ctx["forecast_6m"]},
            {"source": "monte_carlo_cpp", "ref": f"data/outputs/simulation/revenue_at_risk.json#regions.{rid}.cvar95",
             "value": rar["regions"][rid]["cvar95"]},
            {"source": "risk_engine", "ref": f"risks[region={rid}].risk_score", "value": risk["risk_score"]},
        ]
        observation = (f"{name}: trailing-12-month revenue {_money(k['revenue'])} ({_pct(k['revenue_growth'])} vs prior "
                       f"12 months), operating margin {_pct(k['operating_margin_pct'])}.")
        if y:
            observation += (f" Paired t-test of 2025 vs 2024 monthly revenue: mean YoY {_pct(y['mean_yoy_growth'])}, "
                            f"p={y['p_value']:.3g} ({y['direction']}).")
        causes = []
        for f in risk["risk_factors"][:3]:
            if f["contribution"] > 0:
                causes.append(f"{f['factor']} contributes {f['contribution']} of {risk['risk_score']} risk points "
                              f"(raw value {f['raw_value']}).")
        cp = trends.get(rid, {}).get("changepoint")
        if cp:
            causes.append(f"Trend change detected around {cp['month']}: 12-month average revenue slope moved from "
                          f"{_money(cp['slope_before'])}/month to {_money(cp['slope_after'])}/month.")
            ev.append({"source": "analytics", "ref": f"data/outputs/analytics/analytics_summary.json#trends[{rid}].changepoint.month", "value": cp["month"]})
        growth6 = ctx["forecast_6m"] / ctx["last_6m_revenue"] - 1 if ctx["last_6m_revenue"] else 0.0
        forecast_txt = (f"Next 6 months forecast {_money(ctx['forecast_6m'])} vs {_money(ctx['last_6m_revenue'])} in the "
                        f"last 6 months ({_pct(growth6)}). Monte Carlo P5 {_money(rar['regions'][rid]['p5'])}, "
                        f"CVaR95 shortfall {_money(rar['regions'][rid]['cvar95'])}.")
        cp_reg = churn_preds[(churn_preds.region_id == rid) & (churn_preds.predicted_churn == 1)]
        at_stake = float((cp_reg.monetary / cp_reg.tenure_days.clip(lower=90) * 90).sum()) if len(cp_reg) else 0.0
        impact_parts = []
        if len(cp_reg):
            impact_parts.append(f"{len(cp_reg)} customers predicted to churn (model precision "
                                f"{_pct(churn_report['test']['precision'])}); their average quarterly revenue at stake is "
                                f"about {_money(at_stake)}.")
            ev.append({"source": "churn_model", "ref": f"predictions[region={rid}, predicted_churn=1].count",
                       "value": int(len(cp_reg))})
        o = opt_reg.get(rid)
        if o:
            impact_parts.append(f"Optimized allocation changes this region's marketing budget by "
                                f"{_pct(o['spend_change_pct'])} and hires from {int(o['baseline_hires'])} to "
                                f"{int(o['optimized_hires'])}.")
            ev.append({"source": "optimization_julia", "ref": f"optimization.by_region[{rid}].spend_change_pct",
                       "value": o["spend_change_pct"]})
        decisions.append({
            "decision_id": f"{run_id}-{rid}", "scope": "region", "entity_id": rid, "entity_name": name,
            "priority": risk["risk_level"], "observation": observation,
            "cause": " ".join(causes) if causes else "No dominant risk driver identified.",
            "forecast": forecast_txt,
            "risk": f"{risk['risk_level']} ({risk['risk_score']}/100). {risk['explanation']}",
            "recommendation": risk["recommended_action"],
            "expected_impact": " ".join(impact_parts) if impact_parts else "No quantified impact available.",
            "confidence": risk["confidence"], "evidence": ev,
            "method": "deterministic templates over computed metrics; no language model used",
        })
    company = analytics["company"]
    opt_txt = (f"Optimization ({optimization.get('status')}) improves expected incremental gross margin by "
               f"{_money(optimization.get('improvement_abs', 0))} ({_pct(optimization.get('improvement_pct', 0))}) "
               f"versus the pro-rata baseline under the same budget." if optimization.get("improvement_abs") is not None
               else "Optimization result unavailable.")
    decisions.insert(0, {
        "decision_id": f"{run_id}-COMPANY", "scope": "company", "entity_id": "ORG01", "entity_name": "Company",
        "priority": max((r["risk_level"] for r in region_risks.values()),
                        key=["LOW", "MEDIUM", "HIGH", "CRITICAL"].index),
        "observation": f"TTM revenue {_money(company['ttm']['revenue'])} ({_pct(company['ttm_revenue_growth'])} YoY), "
                       f"operating margin {_pct(company['ttm']['operating_margin_pct'])}.",
        "cause": "Highest-risk regions: " + ", ".join(
            f"{REGION_NAMES[r]} ({v['risk_score']})" for r, v in sorted(region_risks.items(),
                                                                        key=lambda kv: -kv[1]["risk_score"])[:2]) + ".",
        "forecast": f"Total 6-month forecast {_money(forecast.forecast.sum())}; Monte Carlo P5 "
                    f"{_money(rar['total']['p5'])}, VaR95 {_money(rar['total']['var95'])}.",
        "risk": f"Portfolio CVaR95 shortfall {_money(rar['total']['cvar95'])} over 6 months.",
        "recommendation": "Apply the optimized budget and hiring allocation, and prioritise retention in the highest "
                          "risk regions listed above.",
        "expected_impact": opt_txt, "confidence": round(min(r["confidence"] for r in region_risks.values()), 3),
        "evidence": [{"source": "analytics", "ref": "data/outputs/analytics/analytics_summary.json#company.ttm.revenue", "value": company["ttm"]["revenue"]},
                     {"source": "monte_carlo_cpp", "ref": "data/outputs/simulation/revenue_at_risk.json#total.var95", "value": rar["total"]["var95"]},
                     {"source": "optimization_julia", "ref": "optimization.improvement_abs",
                      "value": optimization.get("improvement_abs")}],
        "method": "deterministic templates over computed metrics; no language model used",
    })
    return decisions
