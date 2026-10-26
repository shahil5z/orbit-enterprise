"""Customer churn risk classification (no purchase in the 90 days after the feature cutoff)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.evaluation.metrics import best_f1_threshold, classification_metrics, threshold_table
from ml.registry import fingerprint_frame, model_version, save_model

NUMERIC = ["recency_days", "frequency", "monetary", "avg_txn_value", "avg_discount", "distinct_products",
           "distinct_bus", "revenue_last_90d", "revenue_prev_90d", "txns_last_90d", "online_share", "tenure_days",
           "revenue_trend", "satisfaction_score", "credit_limit"]
CATEGORICAL = ["segment", "region_id"]


def features(cf: pd.DataFrame) -> pd.DataFrame:
    X = cf[NUMERIC].astype(float).copy()
    for c in ("monetary", "avg_txn_value", "revenue_last_90d", "revenue_prev_90d", "credit_limit"):
        X[c] = np.log1p(X[c])
    for c in CATEGORICAL:
        for v in sorted(cf[c].dropna().unique()):
            X[f"{c}={v}"] = (cf[c] == v).astype(float)
    return X


def train(cf: pd.DataFrame, seed: int = 42) -> dict:
    X, y = features(cf), cf.churned_next_90d.astype(int).to_numpy()
    idx = np.arange(len(cf))
    tr, tmp = train_test_split(idx, test_size=0.4, stratify=y, random_state=seed)
    va, te = train_test_split(tmp, test_size=0.5, stratify=y[tmp], random_state=seed)
    params = {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 15, "l2_regularization": 1.0}
    gb = HistGradientBoostingClassifier(random_state=seed, **params).fit(X.iloc[tr], y[tr])
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X.iloc[tr].fillna(0), y[tr])
    s_va, s_te = gb.predict_proba(X.iloc[va])[:, 1], gb.predict_proba(X.iloc[te])[:, 1]
    thr = best_f1_threshold(y[va], s_va, np.round(np.arange(0.05, 0.95, 0.01), 2))
    lr_te = lr.predict_proba(X.iloc[te].fillna(0))[:, 1]
    lr_thr = best_f1_threshold(y[va], lr.predict_proba(X.iloc[va].fillna(0))[:, 1], np.round(np.arange(0.05, 0.95, 0.01), 2))
    report = {"task": "classification", "target": "churned_next_90d", "algorithm": "HistGradientBoostingClassifier",
              "params": params, "features": list(X.columns),
              "split": {"train": len(tr), "validation": len(va), "test": len(te), "method": "stratified random 60/20/20",
                        "positive_rate": float(y.mean())},
              "threshold_selection": "max F1 on validation",
              "validation": classification_metrics(y[va], s_va, thr), "test": classification_metrics(y[te], s_te, thr),
              "baseline_logistic_regression_test": classification_metrics(y[te], lr_te, lr_thr),
              "test_threshold_analysis": threshold_table(y[te], s_te, [0.2, 0.3, 0.4, 0.5, 0.6])}
    version = model_version("churn_classifier", params, fingerprint_frame(cf[NUMERIC + ["churned_next_90d"]]))
    save_model("churn_classifier", version, {"model": gb, "threshold": thr, "columns": list(X.columns)}, report)
    all_scores = gb.predict_proba(X)[:, 1]
    split = np.array(["train"] * len(cf), dtype=object)
    split[va], split[te] = "validation", "test"
    preds = pd.DataFrame({"customer_id": cf.customer_id, "region_id": cf.region_id, "segment": cf.segment,
                          "churn_probability": all_scores, "predicted_churn": (all_scores >= thr).astype(int),
                          "actual_churn": y, "split": split, "monetary": cf.monetary,
                          "tenure_days": cf.tenure_days})
    return {"version": version, "report": report, "predictions": preds}


def score(bundle: dict, cf: pd.DataFrame) -> pd.DataFrame:
    X = features(cf).reindex(columns=bundle["columns"], fill_value=0.0)
    p = bundle["model"].predict_proba(X)[:, 1]
    return pd.DataFrame({"customer_id": cf.customer_id, "region_id": cf.region_id, "segment": cf.segment,
                         "churn_probability": p, "predicted_churn": (p >= bundle["threshold"]).astype(int),
                         "actual_churn": cf.churned_next_90d.astype(int), "monetary": cf.monetary,
                         "tenure_days": cf.tenure_days})
