"""TRANSFORM stage: apply deterministic, documented cleaning rules to staged data.

Output is the conformed layer (data/curated/conformed) consumed by the Spark CURATE job and loaded
into PostgreSQL. Every rule records how many rows it touched so the effect is auditable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS
from orbit_core.io import write_json, write_parquet

CANON = {
    "segment": {"enterprise": "Enterprise", "mid-market": "Mid-Market", "smb": "SMB"},
    "category": {"cloud": "Cloud", "software": "Software", "hardware": "Hardware", "consulting": "Consulting",
                 "support": "Support"},
    "severity": {"sev1": "SEV1", "sev2": "SEV2", "sev3": "SEV3", "sev4": "SEV4"},
}


def _canon(s: pd.Series, mapping: dict) -> tuple[pd.Series, int]:
    out = s.astype("string").str.lower().map(mapping).fillna(s)
    return out, int((out != s).fillna(False).sum())


def conform(staging_dir: Path = PATHS.staging, out_dir: Path = PATHS.curated / "conformed") -> dict:
    load = lambda n: pd.read_parquet(staging_dir / f"{n}.parquet").drop(
        columns=["_pk_conflict", "_batch_id", "_ingested_at"], errors="ignore")
    log: dict[str, dict] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir = out_dir / "_rejected"
    rejected_dir.mkdir(exist_ok=True)

    for n in ("organizations", "regions", "business_units", "suppliers"):
        write_parquet(load(n), out_dir / f"{n}.parquet")

    products = load("products")
    products["category"], k = _canon(products["category"], CANON["category"])
    log["products"] = {"category_normalized": k}
    write_parquet(products, out_dir / "products.parquet")

    customers = load("customers")
    customers["segment"], k = _canon(customers["segment"], CANON["segment"])
    customers["industry"] = customers["industry"].fillna("Unknown")
    log["customers"] = {"segment_normalized": k, "industry_filled_unknown": int((customers.industry == "Unknown").sum()),
                        "signup_date_null": int(customers.signup_date.isna().sum())}
    write_parquet(customers, out_dir / "customers.parquet")

    tx = load("transactions")
    n0 = len(tx)
    tx = tx.drop_duplicates(subset=["transaction_id"], keep="first")
    bad_fk = ~tx.customer_id.isin(customers.customer_id)
    bad_qty = tx.quantity.isna() | (tx.quantity <= 0)
    gross = tx.quantity.astype(float) * tx.unit_price
    # fill missing discount from the recorded revenue identity before checking consistency
    miss_disc = tx.discount_pct.isna()
    tx.loc[miss_disc, "discount_pct"] = (1 - tx.revenue / gross)[miss_disc].round(3)
    expected = gross * (1 - tx.discount_pct)
    mismatch = (tx.revenue - expected).abs() > 0.01 * expected.abs() + 0.01
    implausible_disc = (tx.discount_pct < 0) | (tx.discount_pct > 0.6)
    reject = bad_fk | bad_qty | mismatch | implausible_disc
    rej = tx[reject].copy()
    rej["reject_reason"] = np.select([bad_fk[reject], bad_qty[reject], implausible_disc[reject]],
                                     ["broken_customer_fk", "invalid_quantity", "implausible_discount"],
                                     "revenue_identity_mismatch")
    rej.astype(str).to_csv(rejected_dir / "transactions.csv", index=False)
    tx = tx[~reject].copy()
    tx["gross_margin"] = (tx.revenue - tx.cost).round(2)
    tx["txn_month"] = tx.txn_date.dt.to_period("M").dt.to_timestamp()
    log["transactions"] = {"input": n0, "pk_duplicates_dropped": int(n0 - len(tx) - len(rej)),
                           "discount_imputed": int(miss_disc.sum()), "rejected": int(len(rej)),
                           "rejected_by_reason": rej.reject_reason.value_counts().to_dict(), "output": int(len(tx))}
    write_parquet(tx, out_dir / "transactions.parquet")

    ops = load("operations")
    ops["uptime_missing"] = ops.uptime_pct.isna()
    # impute uptime with the median for the same region/BU (documented, flagged)
    ops["uptime_pct"] = ops.groupby(["region_id", "bu_id"]).uptime_pct.transform(lambda s: s.fillna(s.median()))
    log["operations"] = {"uptime_imputed": int(ops.uptime_missing.sum())}
    write_parquet(ops, out_dir / "operations.parquet")

    emp = load("employees")
    bad_sal = emp.annual_salary <= 0
    emp.loc[bad_sal, "annual_salary"] = np.nan
    log["employees"] = {"invalid_salary_nulled": int(bad_sal.sum())}
    write_parquet(emp, out_dir / "employees.parquet")

    inc = load("incidents")
    inc["severity"], k = _canon(inc["severity"], CANON["severity"])
    bad_order = inc.resolved_at < inc.opened_at
    inc.loc[bad_order, "resolved_at"] = pd.NaT
    inc["resolution_hours"] = ((inc.resolved_at - inc.opened_at).dt.total_seconds() / 3600).round(2)
    log["incidents"] = {"severity_normalized": k, "impossible_resolution_nulled": int(bad_order.sum())}
    write_parquet(inc, out_dir / "incidents.parquet")

    risk = load("risk_indicators")
    write_parquet(risk, out_dir / "risk_indicators.parquet")
    write_json(out_dir / "_transform_log.json", log)
    return log
