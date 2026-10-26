"""Monthly revenue forecasting per region.

Model: ridge regression on year-over-year log growth, with lagged growth, seasonality and region
indicators. Baseline: seasonal naive (same month last year). Chronological split:
train <= 2025-03, validation 2025-04..2025-06, test 2025-07..2025-12. The selected model is refit
on all history and rolled forward recursively for the forecast horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from ml.evaluation.metrics import regression_metrics
from ml.registry import fingerprint_frame, model_version, save_model

TRAIN_END, VAL_END = pd.Timestamp("2025-03-01"), pd.Timestamp("2025-06-01")


def build_features(rm: pd.DataFrame) -> pd.DataFrame:
    df = rm[["region_id", "month", "revenue"]].copy()
    df["month"] = pd.to_datetime(df.month)
    df = df.sort_values(["region_id", "month"])
    g = df.groupby("region_id").revenue
    df["lag12"] = g.shift(12)
    df["yoy_log"] = np.log(df.revenue / df.lag12)
    gy = df.groupby("region_id").yoy_log
    df["yoy_lag1"] = gy.shift(1)
    df["yoy_lag2"] = gy.shift(2)
    df["yoy_lag3"] = gy.shift(3)
    df["moy_sin"] = np.sin(2 * np.pi * df.month.dt.month / 12)
    df["moy_cos"] = np.cos(2 * np.pi * df.month.dt.month / 12)
    return df


def _X(df: pd.DataFrame, regions: list[str]) -> np.ndarray:
    base = df[["yoy_lag1", "yoy_lag2", "yoy_lag3", "moy_sin", "moy_cos"]].to_numpy()
    onehot = np.stack([(df.region_id == r).to_numpy(float) for r in regions], axis=1)
    return np.hstack([base, onehot])


def train_and_forecast(rm: pd.DataFrame, horizon: int = 6, alpha: float = 1.0) -> dict:
    df = build_features(rm).dropna(subset=["yoy_lag3", "yoy_log"])
    regions = sorted(df.region_id.unique())
    train, val, test = df[df.month <= TRAIN_END], df[(df.month > TRAIN_END) & (df.month <= VAL_END)], df[df.month > VAL_END]

    def fit(d):
        return Ridge(alpha=alpha).fit(_X(d, regions), d.yoy_log)

    m = fit(train)
    # one-step-ahead evaluation: lags are actual history (what is known at forecast time for t+1)
    pred = lambda mod, d: d.lag12.to_numpy() * np.exp(mod.predict(_X(d, regions)))
    val_m, val_b = regression_metrics(val.revenue, pred(m, val)), regression_metrics(val.revenue, val.lag12)
    m2 = fit(pd.concat([train, val]))
    test_pred = pred(m2, test)
    test_m, test_b = regression_metrics(test.revenue, test_pred), regression_metrics(test.revenue, test.lag12)
    selected = "ridge_yoy" if val_m["mape"] < val_b["mape"] else "seasonal_naive"
    residual_sd = float(np.std(np.log(test.revenue / (test_pred if selected == "ridge_yoy" else test.lag12))))

    final = fit(df)
    bundle = {"model": final, "regions": regions, "selected": selected, "residual_log_sd": residual_sd}
    fc = forecast(bundle, rm, horizon)
    params = {"alpha": alpha, "features": ["yoy_lag1", "yoy_lag2", "yoy_lag3", "moy_sin", "moy_cos", "region"],
              "target": "log(revenue_t / revenue_t-12)"}
    version = model_version("revenue_forecast", params, fingerprint_frame(rm[["region_id", "month", "revenue"]]))
    test_detail = test.assign(prediction=test_pred)[["region_id", "month", "revenue", "prediction", "lag12"]]
    report = {"task": "forecasting", "algorithm": "Ridge on YoY log growth", "params": params,
              "split": {"train_end": str(TRAIN_END.date()), "validation_end": str(VAL_END.date()),
                        "train_rows": len(train), "validation_rows": len(val), "test_rows": len(test)},
              "validation": {"model": val_m, "seasonal_naive": val_b},
              "test": {"model": test_m, "seasonal_naive": test_b}, "selected": selected,
              "residual_log_sd": residual_sd, "horizon_months": horizon}
    save_model("revenue_forecast", version, bundle, report)
    return {"version": version, "report": report, "forecast": fc, "test_predictions": test_detail}


def forecast(bundle: dict, rm: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
    """Roll the fitted model forward recursively; uncertainty grows with sqrt(horizon)."""
    regions, model, selected = bundle["regions"], bundle["model"], bundle["selected"]
    hist = rm[["region_id", "month", "revenue"]].copy()
    hist["month"] = pd.to_datetime(hist.month)
    rows = []
    for step in range(1, horizon + 1):
        nxt_month = hist.month.max() + pd.DateOffset(months=1)
        new = []
        for r in regions:
            h = hist[hist.region_id == r].sort_values("month")
            rev = h.revenue.to_numpy()
            lag12 = float(rev[-12])
            yoy = np.log(rev[-3:] / rev[-15:-12])
            feat = pd.DataFrame([{"region_id": r, "yoy_lag1": yoy[-1], "yoy_lag2": yoy[-2], "yoy_lag3": yoy[-3],
                                  "moy_sin": np.sin(2 * np.pi * nxt_month.month / 12),
                                  "moy_cos": np.cos(2 * np.pi * nxt_month.month / 12)}])
            point = lag12 * float(np.exp(model.predict(_X(feat, regions))[0])) if selected == "ridge_yoy" else lag12
            sd = bundle["residual_log_sd"] * np.sqrt(step)
            rows.append({"region_id": r, "month": nxt_month, "horizon": step, "forecast": point,
                         "lower_80": point * np.exp(-1.2816 * sd), "upper_80": point * np.exp(1.2816 * sd),
                         "log_sd": sd})
            new.append({"region_id": r, "month": nxt_month, "revenue": point})
        hist = pd.concat([hist, pd.DataFrame(new)], ignore_index=True)
    return pd.DataFrame(rows)
