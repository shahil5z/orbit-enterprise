"""ANALYZE stage: compute KPIs, statistics, correlations, trends, segmentation and statistical anomalies."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.python import anomalies, kpis, segmentation, statistics, trends
from orbit_core.config import PATHS
from orbit_core.io import write_json, write_parquet


def run_analytics(marts: Path = PATHS.curated / "marts", out: Path = PATHS.outputs / "analytics") -> dict:
    km = pd.read_parquet(marts / "monthly_kpis")
    rm = pd.read_parquet(marts / "region_monthly")
    cf = pd.read_parquet(marts / "customer_features")
    ops = pd.read_parquet(marts / "ops_daily_features")
    result = {
        "company": kpis.latest_period_kpis(km),
        "by_region": kpis.kpis_by(km, "region_id"),
        "by_business_unit": kpis.kpis_by(km, "bu_id"),
        "summary_statistics": statistics.summarize(rm, ["revenue", "cost", "opex", "marketing_spend", "headcount",
                                                        "incident_count", "fx_volatility", "compliance_score"]),
        "correlations": statistics.correlations(rm, ["revenue", "opex", "marketing_spend", "headcount", "txn_count",
                                                     "incident_count", "incident_cost", "avg_uptime_pct",
                                                     "fx_volatility", "compliance_score"]),
        "trends": trends.region_trends(rm),
    }
    seg, seg_meta = segmentation.segment_customers(cf)
    result["segmentation"] = seg_meta
    flagged = anomalies.zscore_anomalies(ops)
    result["statistical_anomalies"] = {"threshold_z": 4.0, "flagged": int(flagged.z_flag.sum()),
                                       "rows": int(len(flagged))}
    write_parquet(seg, out / "customer_segments.parquet")
    write_parquet(flagged[flagged.z_flag][["operation_id", "op_date", "region_id", "bu_id", "z_max", "z_flag_metrics"]],
                  out / "statistical_anomalies.parquet")
    # CSV export consumed by the R statistical workflow (keeps R dependency-light: base R + jsonlite)
    rm.assign(month=pd.to_datetime(rm.month).dt.strftime("%Y-%m-%d")).to_csv(out / "region_monthly.csv", index=False)
    write_json(out / "analytics_summary.json", result)
    return result
