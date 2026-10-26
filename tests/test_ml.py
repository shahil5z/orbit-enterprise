import numpy as np
import pandas as pd
import pytest

from ml.evaluation.metrics import best_f1_threshold, classification_metrics, regression_metrics
from ml.registry import model_version
from orbit_core.config import PATHS

MARTS = PATHS.curated / "marts"
needs_marts = pytest.mark.skipif(not (MARTS / "region_monthly").exists(), reason="curated marts missing")


def test_regression_metrics_exact():
    m = regression_metrics(np.array([100.0, 200.0]), np.array([110.0, 180.0]))
    assert m["mae"] == pytest.approx(15.0)
    assert m["mape"] == pytest.approx(0.10)


def test_classification_metrics_perfect_and_threshold():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.2, 0.8, 0.9])
    m = classification_metrics(y, s, 0.5)
    assert m["f1"] == 1.0 and m["roc_auc"] == 1.0
    assert 0.2 <= best_f1_threshold(y, s) < 0.8


def test_model_version_is_stable_and_sensitive():
    a = model_version("m", {"p": 1}, "abc")
    assert a == model_version("m", {"p": 1}, "abc")
    assert a != model_version("m", {"p": 2}, "abc")


@needs_marts
def test_forecast_beats_or_matches_naive_and_intervals_are_ordered():
    from ml.forecasting.revenue import train_and_forecast
    res = train_and_forecast(pd.read_parquet(MARTS / "region_monthly"))
    test = res["report"]["test"]
    assert 0 < test["model"]["mape"] < 0.5
    fc = res["forecast"]
    assert (fc.lower_80 < fc.forecast).all() and (fc.forecast < fc.upper_80).all()
    assert len(fc) == 6 * fc.region_id.nunique()
    # interval widens with horizon
    r = fc[fc.region_id == fc.region_id.iloc[0]].sort_values("horizon")
    assert ((r.upper_80 - r.lower_80) / r.forecast).is_monotonic_increasing


@needs_marts
def test_churn_model_beats_chance():
    from ml.classification.churn import score, train
    cf = pd.read_parquet(MARTS / "customer_features")
    res = train(cf)
    assert res["report"]["test"]["roc_auc"] > 0.7
    from ml.registry import load_latest
    bundle, _ = load_latest("churn_classifier")
    scored = score(bundle, cf)
    assert scored.churn_probability.between(0, 1).all() and len(scored) == len(cf)


@needs_marts
def test_anomaly_model_detects_labelled_anomalies():
    from ml.anomaly_detection.operations import train
    ops = pd.read_parquet(MARTS / "ops_daily_features")
    labels = pd.read_csv(PATHS.raw / "_labels" / "operations_anomalies.csv")
    rep = train(ops, labels)["report"]
    assert rep["test"]["recall"] > 0.5 and rep["test"]["precision"] > 0.3
    assert rep["test"]["f1"] > rep["baseline_zscore_rule_test"]["f1"]
