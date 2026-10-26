"""Statistical anomaly detection on operational metrics using the Spark-computed trailing z-scores."""
from __future__ import annotations

import pandas as pd

METRICS = {"opex_z": "high", "fulfillment_hours_z": "high", "support_tickets_z": "high", "uptime_pct_z": "low"}


def zscore_anomalies(ops: pd.DataFrame, threshold: float = 4.0) -> pd.DataFrame:
    df = ops.copy()
    flags = []
    for col, direction in METRICS.items():
        z = df[col] if direction == "high" else -df[col]
        flags.append((z > threshold).rename(col))
    f = pd.concat(flags, axis=1).fillna(False)
    df["z_flag"] = f.any(axis=1)
    df["z_flag_metrics"] = f.apply(lambda r: ",".join(c.replace("_z", "") for c in f.columns if r[c]), axis=1)
    df["z_max"] = pd.concat([df[c] if d == "high" else -df[c] for c, d in METRICS.items()], axis=1).max(axis=1)
    return df
