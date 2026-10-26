"""Descriptive statistics and correlation analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(df: pd.DataFrame, columns: list[str]) -> dict:
    out = {}
    for c in columns:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if s.empty:
            continue
        out[c] = {"count": int(s.size), "mean": float(s.mean()), "std": float(s.std()), "min": float(s.min()),
                  "p05": float(s.quantile(0.05)), "p50": float(s.median()), "p95": float(s.quantile(0.95)),
                  "max": float(s.max()), "skew": float(s.skew()), "missing": int(df[c].isna().sum())}
    return out


def correlations(df: pd.DataFrame, columns: list[str], method: str = "spearman", min_abs: float = 0.3) -> dict:
    corr = df[columns].corr(method=method)
    pairs = []
    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            v = corr.loc[a, b]
            if not np.isnan(v) and abs(v) >= min_abs:
                pairs.append({"a": a, "b": b, "rho": round(float(v), 4)})
    pairs.sort(key=lambda p: -abs(p["rho"]))
    return {"method": method, "matrix": corr.round(4).to_dict(), "strong_pairs": pairs}
