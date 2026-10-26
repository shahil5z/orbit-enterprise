"""Customer segmentation with K-means on standardised RFM-style features."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = ["recency_days", "frequency", "monetary", "avg_txn_value", "distinct_products", "revenue_trend"]


def segment_customers(cf: pd.DataFrame, k_range=range(3, 7), seed: int = 42) -> tuple[pd.DataFrame, dict]:
    X = cf[FEATURES].copy()
    X["monetary"] = np.log1p(X.monetary)
    X["avg_txn_value"] = np.log1p(X.avg_txn_value)
    X["frequency"] = np.log1p(X.frequency)
    X["revenue_trend"] = np.log(X.revenue_trend.clip(lower=1e-3))
    Z = StandardScaler().fit_transform(X)
    scores = {}
    models = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Z)
        scores[k] = float(silhouette_score(Z, km.labels_, sample_size=min(2000, len(Z)), random_state=seed))
        models[k] = km
    best_k = max(scores, key=scores.get)
    labels = models[best_k].labels_
    out = cf[["customer_id", "region_id", "segment"]].copy()
    out["cluster"] = labels
    prof = cf.assign(cluster=labels).groupby("cluster").agg(
        customers=("customer_id", "size"), avg_monetary=("monetary", "mean"), avg_frequency=("frequency", "mean"),
        avg_recency_days=("recency_days", "mean"), churn_rate=("churned_next_90d", "mean"),
        enterprise_share=("segment", lambda s: (s == "Enterprise").mean()))
    # name clusters by value and recency so they read as business segments
    order = prof.avg_monetary.rank(ascending=False).astype(int)
    names = {}
    for c, row in prof.iterrows():
        if row.avg_recency_days > 45:
            names[c] = "Lapsing"
        elif order[c] == 1:
            names[c] = "Strategic High Value"
        elif row.avg_monetary >= prof.avg_monetary.median():
            names[c] = "Core Growth"
        else:
            names[c] = "Long Tail"
    prof["label"] = prof.index.map(names)
    out["cluster_label"] = out.cluster.map(names)
    return out, {"k": best_k, "silhouette_by_k": scores, "features": FEATURES,
                 "profiles": prof.reset_index().round(4).to_dict(orient="records")}
