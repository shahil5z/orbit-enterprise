"""Trend estimation and structural change detection on monthly series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def linear_trend(y: np.ndarray) -> dict:
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else 0.0
    return {"slope_per_month": float(slope), "intercept": float(intercept), "r2": float(r2),
            "slope_pct_of_mean": float(slope / y.mean()) if y.mean() else None}


def changepoint(y: np.ndarray, min_seg: int = 6) -> dict | None:
    """Single change point in the growth rate: choose the split that minimises total SSE of two linear fits."""
    n = len(y)
    if n < 2 * min_seg:
        return None
    x = np.arange(n, dtype=float)
    best = None
    full_sse = float(((y - np.polyval(np.polyfit(x, y, 1), x)) ** 2).sum())
    for k in range(min_seg, n - min_seg):
        p1, p2 = np.polyfit(x[:k], y[:k], 1), np.polyfit(x[k:], y[k:], 1)
        sse = float(((y[:k] - np.polyval(p1, x[:k])) ** 2).sum() + ((y[k:] - np.polyval(p2, x[k:])) ** 2).sum())
        if best is None or sse < best["sse"]:
            best = {"index": k, "sse": sse, "slope_before": float(p1[0]), "slope_after": float(p2[0])}
    best["sse_reduction"] = round(1 - best["sse"] / full_sse, 4) if full_sse else 0.0
    return best


def region_trends(region_monthly: pd.DataFrame) -> list[dict]:
    out = []
    df = region_monthly.copy()
    df["month"] = pd.to_datetime(df.month)
    for rid, g in df.sort_values("month").groupby("region_id"):
        # deseasonalise with a 12-month rolling mean before estimating the trend
        y = g.revenue.rolling(12).mean().dropna().to_numpy()
        months = g.month.iloc[11:].dt.strftime("%Y-%m").tolist()
        cp = changepoint(y)
        rec = {"region_id": rid, "trend": linear_trend(y), "series": "revenue_rolling12_mean"}
        if cp and cp["sse_reduction"] > 0.5:
            rec["changepoint"] = {**cp, "month": months[cp["index"]]}
        out.append(rec)
    return out
