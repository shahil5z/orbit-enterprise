"""Risk engine: transparent weighted scoring of normalised risk factors per region and business unit.

Every factor is a computed metric from an upstream stage. Normalisation references and weights are
explicit constants so a score can be reproduced by hand from the stored factor values.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# factor -> (weight, reference value at which the factor saturates to 1.0, description)
FACTORS = {
    "churn_exposure": (0.22, 0.25, "revenue-weighted mean churn probability of active customers"),
    "revenue_at_risk": (0.18, 0.15, "CVaR95 / expected revenue over the forecast horizon (C++ Monte Carlo)"),
    "forecast_decline": (0.15, 0.15, "forecast revenue decline vs last 6 months (0 if growing)"),
    "operational_anomalies": (0.15, 0.05, "share of last 90 days flagged anomalous (Isolation Forest)"),
    "incident_severity": (0.12, 6.0, "SEV1/SEV2 incidents in last 6 months"),
    "compliance_gap": (0.10, 0.25, "(100 - compliance score) / 100, latest month"),
    "fx_volatility": (0.08, 0.12, "latest monthly FX volatility"),
}
LEVELS = [(25, "LOW"), (50, "MEDIUM"), (70, "HIGH"), (101, "CRITICAL")]
ACTIONS = {
    "churn_exposure": "Launch a retention programme for at-risk accounts (top churn-probability customers first).",
    "revenue_at_risk": "Tighten forecast governance and build a downside plan covering the CVaR95 shortfall.",
    "forecast_decline": "Review pipeline and pricing in this unit; reallocate growth budget toward higher-return units.",
    "operational_anomalies": "Open an operations review of flagged days (opex spikes, fulfillment delays, outages).",
    "incident_severity": "Run a post-incident review and supplier performance audit for major incidents.",
    "compliance_gap": "Escalate compliance remediation; schedule an internal audit.",
    "fx_volatility": "Evaluate FX hedging for exposed contracts.",
}


def level_for(score: float) -> str:
    return next(name for limit, name in LEVELS if score < limit)


def score_entity(raw: dict[str, float], coverage: float, model_quality: float) -> dict:
    factors = []
    total = 0.0
    for name, (w, ref, desc) in FACTORS.items():
        v = raw.get(name)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            norm = 0.0
        else:
            norm = float(np.clip(v / ref, 0, 1))
        contrib = 100 * w * norm
        total += contrib
        factors.append({"factor": name, "raw_value": None if v is None else round(float(v), 6),
                        "normalized": round(norm, 4), "weight": w, "contribution": round(contrib, 2),
                        "description": desc})
    factors.sort(key=lambda f: -f["contribution"])
    top = [f for f in factors if f["contribution"] > 0][:3]
    score = round(total, 2)
    level = level_for(score)
    confidence = round(float(np.clip(coverage * model_quality, 0, 1)), 3)
    action = ACTIONS[top[0]["factor"]] if top and level != "LOW" else "Monitor; no action required at current risk level."
    explanation = (f"Risk score {score} ({level}). Largest contributors: "
                   + ", ".join(f"{f['factor']} ({f['contribution']} pts, raw {f['raw_value']})" for f in top)
                   + f". Confidence {confidence} = data coverage {round(coverage, 3)} x model quality {round(model_quality, 3)}.")
    return {"risk_score": score, "risk_level": level, "risk_factors": factors, "top_factors": [f["factor"] for f in top],
            "confidence": confidence, "recommended_action": action, "explanation": explanation}


def build_region_inputs(churn_preds: pd.DataFrame, rar: dict, forecast: pd.DataFrame, rm: pd.DataFrame,
                        anomaly_preds: pd.DataFrame, incidents: pd.DataFrame) -> dict[str, dict]:
    rm = rm.copy()
    rm["month"] = pd.to_datetime(rm.month)
    last = rm.month.max()
    out = {}
    anomaly_preds = anomaly_preds.copy()
    anomaly_preds["op_date"] = pd.to_datetime(anomaly_preds.op_date)
    recent_anom = anomaly_preds[anomaly_preds.op_date > anomaly_preds.op_date.max() - pd.Timedelta(days=90)]
    inc = incidents.copy()
    inc["opened_at"] = pd.to_datetime(inc.opened_at, utc=True).dt.tz_localize(None)
    recent_inc = inc[(inc.opened_at > last - pd.DateOffset(months=5)) & inc.severity.isin(["SEV1", "SEV2"])]
    for rid, g in rm.groupby("region_id"):
        cp = churn_preds[churn_preds.region_id == rid]
        w = cp.monetary.clip(lower=0)
        churn_exp = float((cp.churn_probability * w).sum() / w.sum()) if w.sum() > 0 else np.nan
        reg_rar = rar["regions"].get(rid, {})
        rar_ratio = reg_rar.get("cvar95", np.nan) / reg_rar["expected"] if reg_rar.get("expected") else np.nan
        fc = forecast[forecast.region_id == rid].forecast.sum()
        last6 = g[g.month > last - pd.DateOffset(months=6)].revenue.sum()
        decline = max(0.0, 1 - fc / last6) if last6 else np.nan
        latest = g[g.month == last].iloc[0]
        out[rid] = {
            "churn_exposure": churn_exp, "revenue_at_risk": rar_ratio, "forecast_decline": decline,
            "operational_anomalies": float(recent_anom[recent_anom.region_id == rid].is_anomaly.mean()),
            "incident_severity": float((recent_inc.region_id == rid).sum()),
            "compliance_gap": (100 - float(latest.compliance_score)) / 100 if pd.notna(latest.compliance_score) else np.nan,
            "fx_volatility": float(latest.fx_volatility) if pd.notna(latest.fx_volatility) else np.nan,
            "_context": {"forecast_6m": float(fc), "last_6m_revenue": float(last6), "customers_scored": int(len(cp))},
        }
    return out


def build_unit_inputs(region_inputs: dict, anomaly_preds: pd.DataFrame, incidents: pd.DataFrame,
                      last_month: pd.Timestamp) -> dict[tuple[str, str], dict]:
    """Business-unit level: unit-specific operational and incident factors, region-level for the rest."""
    a = anomaly_preds.copy()
    a["op_date"] = pd.to_datetime(a.op_date)
    a = a[a.op_date > a.op_date.max() - pd.Timedelta(days=90)]
    inc = incidents.copy()
    inc["opened_at"] = pd.to_datetime(inc.opened_at, utc=True).dt.tz_localize(None)
    inc = inc[(inc.opened_at > last_month - pd.DateOffset(months=5)) & inc.severity.isin(["SEV1", "SEV2"])]
    out = {}
    for (rid, bu), g in a.groupby(["region_id", "bu_id"]):
        base = {k: v for k, v in region_inputs[rid].items() if k != "_context"}
        base["operational_anomalies"] = float(g.is_anomaly.mean())
        # unit incident count scaled x5 so it is comparable with the region-level reference (5 BUs per region)
        base["incident_severity"] = float(((inc.region_id == rid) & (inc.bu_id == bu)).sum()) * 5
        out[(rid, bu)] = base
    return out
