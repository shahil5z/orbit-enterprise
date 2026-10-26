"""Metric helpers shared by all models."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, f1_score, precision_score, recall_score, roc_auc_score,
                             confusion_matrix)


def regression_metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    err = y_pred - y_true
    return {"mae": float(np.abs(err).mean()), "rmse": float(np.sqrt((err ** 2).mean())),
            "mape": float(np.mean(np.abs(err) / np.abs(y_true))), "bias": float(err.mean()), "n": int(len(y_true))}


def classification_metrics(y_true, scores, threshold: float) -> dict:
    y_true = np.asarray(y_true).astype(int)
    pred = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    out = {"threshold": float(threshold), "precision": float(precision_score(y_true, pred, zero_division=0)),
           "recall": float(recall_score(y_true, pred, zero_division=0)),
           "f1": float(f1_score(y_true, pred, zero_division=0)),
           "confusion": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
           "positive_rate": float(y_true.mean()), "predicted_positive_rate": float(pred.mean()), "n": int(len(y_true))}
    if len(set(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
        out["pr_auc"] = float(average_precision_score(y_true, scores))
    return out


def threshold_table(y_true, scores, thresholds) -> list[dict]:
    return [classification_metrics(y_true, scores, t) for t in thresholds]


def best_f1_threshold(y_true, scores, candidates=None) -> float:
    candidates = candidates if candidates is not None else np.unique(np.quantile(scores, np.linspace(0.5, 0.995, 80)))
    best = max(candidates, key=lambda t: f1_score(y_true, (scores >= t).astype(int), zero_division=0))
    return float(best)
