"""Data quality engine: rule-based checks over staged datasets, scored and reported."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS
from orbit_core.io import read_json, write_json
from pipelines.ingestion.engine import load_registry

# weight of each check family in the dataset score (sum = 1)
WEIGHTS = {"completeness": 0.25, "uniqueness": 0.15, "validity": 0.25, "consistency": 0.15,
           "referential_integrity": 0.15, "schema": 0.05}


def _pk(spec):
    pk = spec["primary_key"]
    return pk if isinstance(pk, list) else [pk]


def robust_outliers(s: pd.Series, z: float = 6.0) -> pd.Series:
    """Flag values whose robust z-score (median/MAD) exceeds z."""
    x = s.astype(float)
    med = x.median()
    mad = (x - med).abs().median()
    if not mad or np.isnan(mad):
        return pd.Series(False, index=s.index)
    return ((x - med).abs() / (1.4826 * mad)) > z


def check_dataset(name: str, df: pd.DataFrame, spec: dict, frames: dict[str, pd.DataFrame],
                  drift: dict | None = None) -> dict:
    n = max(len(df), 1)
    issues: list[dict] = []

    def add(check, family, column, count, severity, detail=""):
        if count:
            issues.append({"check": check, "family": family, "column": column, "count": int(count),
                           "rate": round(count / n, 5), "severity": severity, "detail": detail})

    cols = list(spec["schema"])
    missing_cells = int(df[cols].isna().sum().sum())
    nullable = set(spec.get("nullable", []))
    missing_cells = int(df[[c for c in cols if c not in nullable]].isna().sum().sum())
    for c in cols:
        if c in nullable:
            continue
        add("missing_values", "completeness", c, df[c].isna().sum(),
            "high" if c in spec.get("required", []) else "low")
    pk = _pk(spec)
    add("duplicate_primary_key", "uniqueness", ",".join(pk), df.duplicated(subset=pk).sum(), "high")
    for c, (lo, hi) in spec.get("ranges", {}).items():
        v = pd.to_numeric(df[c], errors="coerce")
        add("out_of_range", "validity", c, ((v < lo) | (v > hi)).sum(), "high", f"allowed [{lo}, {hi}]")
    for c, (lo, hi) in spec.get("date_bounds", {}).items():
        d = pd.to_datetime(df[c], errors="coerce")
        add("impossible_date", "validity", c, ((d < pd.Timestamp(lo)) | (d > pd.Timestamp(hi))).sum(), "high",
            f"allowed [{lo}, {hi}]")
    for a, b in spec.get("temporal_order", []):
        add("temporal_order_violation", "validity", f"{a}<{b}", (df[b] < df[a]).sum(), "high", f"{b} before {a}")
    for c in spec.get("outlier_columns", []):
        add("statistical_outlier", "validity", c, robust_outliers(df[c].dropna()).sum(), "medium", "robust z > 6")
    for rule in spec.get("derived_checks", []):
        expected = df.eval(rule["expression"])
        actual = df[rule["column"]].astype(float)
        mism = (expected.notna() & ((actual - expected).abs() > rule["rel_tolerance"] * expected.abs() + 0.01))
        add("derived_value_mismatch", "validity", rule["column"], mism.sum(), "high",
            f"expected {rule['column']} = {rule['expression']}")
    for c, allowed in spec.get("categories", {}).items():
        vals = df[c].dropna().astype(str)
        bad = ~vals.isin(allowed)
        fixable = vals[bad].str.lower().isin([a.lower() for a in allowed]).sum()
        add("inconsistent_category", "consistency", c, bad.sum(), "medium",
            f"{int(fixable)} differ only by case; allowed={allowed}")
    for c, ref in spec.get("foreign_keys", {}).items():
        ref_ds, ref_col = ref.split(".")
        if ref_ds in frames:
            vals = df[c].dropna()
            add("broken_foreign_key", "referential_integrity", c, (~vals.isin(frames[ref_ds][ref_col])).sum(),
                "high", f"references {ref}")
    if drift:
        k = len(drift.get("added_columns", [])) + len(drift.get("missing_columns", [])) + len(drift.get("type_changes", {}))
        if k:
            issues.append({"check": "schema_drift", "family": "schema", "column": None, "count": k, "rate": None,
                           "severity": "medium", "detail": drift})

    family_rate = {f: 0.0 for f in WEIGHTS}
    for it in issues:
        if it["family"] == "schema":
            family_rate["schema"] = 1.0
        elif it["family"] == "completeness":
            family_rate["completeness"] += it["count"] / (n * max(len(cols) - len(nullable), 1))
        else:
            family_rate[it["family"]] += it["rate"]
    score = 100 * sum(w * (1 - min(family_rate[f] * (1 if f == "schema" else 10), 1)) for f, w in WEIGHTS.items())
    return {"dataset": name, "rows": int(len(df)), "missing_cells": missing_cells,
            "quality_score": round(score, 2), "issue_count": int(sum(i["count"] for i in issues)),
            "issues": issues}


def run_quality(staging_dir: Path = PATHS.staging, out_dir: Path = PATHS.outputs / "quality",
                registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    meta_file = staging_dir / "_ingestion_metadata.json"
    meta = {d["dataset_id"]: d for d in read_json(meta_file)["datasets"]} if meta_file.exists() else {}
    frames = {n: pd.read_parquet(staging_dir / f"{n}.parquet") for n in registry["datasets"]
              if (staging_dir / f"{n}.parquet").exists()}
    results = [check_dataset(n, frames[n], registry["datasets"][n], frames, meta.get(n, {}).get("schema_drift"))
               for n in frames]
    total_rows = sum(r["rows"] for r in results) or 1
    overall = round(sum(r["quality_score"] * r["rows"] for r in results) / total_rows, 2)
    report = {"overall_quality_score": overall, "datasets": results,
              "quarantined_records": {n: m.get("quarantined", 0) for n, m in meta.items()},
              "duplicates_removed_at_ingestion": {n: m.get("duplicates_removed", 0) for n, m in meta.items()},
              "scoring": {"weights": WEIGHTS, "method": "100 * sum(weight * (1 - min(10 * issue_rate, 1))) per "
                          "family; overall is row-weighted mean"}}
    write_json(out_dir / "quality_report.json", report)
    (out_dir / "quality_report.md").write_text(to_markdown(report), encoding="utf-8")
    return report


def to_markdown(report: dict) -> str:
    lines = ["# Data Quality Report", "", f"Overall quality score: **{report['overall_quality_score']} / 100**", "",
             "| Dataset | Rows | Score | Issues |", "|---|---:|---:|---:|"]
    for r in report["datasets"]:
        lines.append(f"| {r['dataset']} | {r['rows']} | {r['quality_score']} | {r['issue_count']} |")
    lines += ["", "## Issues", ""]
    for r in report["datasets"]:
        for i in r["issues"]:
            lines.append(f"- **{r['dataset']}** `{i['check']}` on `{i['column']}`: {i['count']} "
                         f"({i['severity']}) {i['detail'] if isinstance(i['detail'], str) else ''}")
    return "\n".join(lines) + "\n"
