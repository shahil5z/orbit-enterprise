"""Operational anomaly detection with Isolation Forest, evaluated against the injected labels.

Labels are never used for training; they are only used to measure precision/recall.
Fit on 2023-2024, evaluated on 2025.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml.evaluation.metrics import classification_metrics, threshold_table
from ml.registry import fingerprint_frame, model_version, save_model

FEATURES = ["opex_z", "fulfillment_hours_z", "uptime_pct_z", "support_tickets_z"]


def _X(ops: pd.DataFrame) -> np.ndarray:
    X = ops[FEATURES].astype(float).clip(-50, 50).fillna(0.0).to_numpy()
    return np.abs(X)


def train(ops: pd.DataFrame, labels: pd.DataFrame, seed: int = 42) -> dict:
    ops = ops.copy()
    ops["op_date"] = pd.to_datetime(ops.op_date)
    ops["label"] = ops.operation_id.isin(labels.operation_id).astype(int)
    train_df = ops[ops.op_date < "2025-01-01"].dropna(subset=["opex_mean28"])
    test_df = ops[ops.op_date >= "2025-01-01"]
    params = {"n_estimators": 300, "contamination": 0.01, "max_samples": 4096}
    model = IsolationForest(random_state=seed, **params).fit(_X(train_df))
    score = lambda d: -model.score_samples(_X(d))  # higher = more anomalous
    s_train, s_test = score(train_df), score(test_df)
    thr = float(np.quantile(s_train, 1 - params["contamination"]))
    z_rule = (test_df[FEATURES].abs().max(axis=1) > 4).astype(float).to_numpy()
    report = {"task": "anomaly_detection", "algorithm": "IsolationForest", "params": params, "features": FEATURES,
              "split": {"train_period": "2023-01-01..2024-12-31", "test_period": "2025-01-01..2025-12-31",
                        "train_rows": len(train_df), "test_rows": len(test_df)},
              "threshold": {"value": thr, "method": "99th percentile of training scores"},
              "test": classification_metrics(test_df.label, s_test, thr),
              "train_anomaly_rate": float((s_train >= thr).mean()),
              "test_anomaly_rate": float((s_test >= thr).mean()),
              "baseline_zscore_rule_test": classification_metrics(test_df.label, z_rule, 0.5),
              "threshold_analysis": threshold_table(test_df.label, s_test,
                                                    [float(np.quantile(s_train, q)) for q in (0.95, 0.98, 0.99, 0.995, 0.999)])}
    version = model_version("ops_anomaly_iforest", params, fingerprint_frame(train_df[FEATURES]))
    save_model("ops_anomaly_iforest", version, {"model": model, "threshold": thr}, report)
    all_scores = score(ops)
    preds = ops[["operation_id", "op_date", "region_id", "bu_id", "label"]].assign(
        anomaly_score=all_scores, is_anomaly=(all_scores >= thr).astype(int))
    return {"version": version, "report": report, "predictions": preds}


def score(bundle: dict, ops: pd.DataFrame, labels: pd.DataFrame | None = None) -> pd.DataFrame:
    s = -bundle["model"].score_samples(_X(ops))
    out = ops[["operation_id", "op_date", "region_id", "bu_id"]].copy()
    out["anomaly_score"] = s
    out["is_anomaly"] = (s >= bundle["threshold"]).astype(int)
    out["label"] = ops.operation_id.isin(labels.operation_id).astype(int) if labels is not None else None
    return out
