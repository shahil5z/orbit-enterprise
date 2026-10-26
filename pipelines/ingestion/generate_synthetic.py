"""Deterministic SIMULATED enterprise dataset generator.

Everything produced here is synthetic. No real company, customer or person is represented.
The generator deliberately injects data problems (duplicates, malformed rows, missing values,
outliers, broken foreign keys, impossible dates, inconsistent categories, schema drift) and
labelled operational anomalies so that downstream quality and ML components can be evaluated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS, SETTINGS
from orbit_core.io import write_json

START = pd.Timestamp("2023-01-01")
END = pd.Timestamp("2025-12-31")

REGIONS = [
    # id, name, currency, base demand multiplier, annual growth, seasonal phase (months)
    ("R01", "North America East", "USD", 1.30, 0.06, 0),
    ("R02", "North America West", "USD", 1.15, 0.08, 0),
    ("R03", "EMEA North", "EUR", 1.00, 0.04, 1),
    ("R04", "EMEA South", "EUR", 0.75, 0.03, 1),
    ("R05", "APAC", "SGD", 0.90, 0.10, 3),
    ("R06", "LATAM", "BRL", 0.55, 0.05, 6),
]
BUSINESS_UNITS = [
    ("BU01", "Cloud Services", 0.62),
    ("BU02", "Software Licenses", 0.78),
    ("BU03", "Hardware", 0.28),
    ("BU04", "Consulting", 0.35),
    ("BU05", "Support & Maintenance", 0.55),
]
SEGMENTS = [("Enterprise", 0.15, 9.0), ("Mid-Market", 0.35, 3.0), ("SMB", 0.50, 1.0)]
INDUSTRIES = ["Financial Services", "Healthcare", "Manufacturing", "Retail", "Public Sector",
              "Telecommunications", "Energy", "Technology"]


def _write_psv_extract(df: pd.DataFrame, path: Path, table: str) -> None:
    """Mimic a pipe-delimited database extract with a header comment and trailer row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"-- EXTRACT table={table} source=erp_core_db exported=2026-01-02T03:00:00Z\n")
        df.to_csv(fh, sep="|", index=False)
        fh.write(f"-- TRAILER rows={len(df)}\n")


def generate(out_dir: Path = PATHS.raw, seed: int = SETTINGS.seed, n_customers: int = 2500) -> dict:
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels_dir = out_dir / "_labels"
    labels_dir.mkdir(exist_ok=True)
    days = pd.date_range(START, END, freq="D")

    # organizations (JSON)
    orgs = [
        {"org_id": "ORG01", "name": "Orbit Holdings (simulated)", "parent_org_id": None, "country": "US"},
        {"org_id": "ORG02", "name": "Orbit Technology Group (simulated)", "parent_org_id": "ORG01", "country": "US"},
        {"org_id": "ORG03", "name": "Orbit Services International (simulated)", "parent_org_id": "ORG01", "country": "IE"},
    ]
    write_json(out_dir / "organizations.json", orgs)

    regions = pd.DataFrame(REGIONS, columns=["region_id", "name", "currency", "demand_multiplier",
                                             "annual_growth", "seasonal_phase"])
    regions[["region_id", "name", "currency"]].to_csv(out_dir / "regions.csv", index=False)

    bus = pd.DataFrame(BUSINESS_UNITS, columns=["bu_id", "name", "gross_margin"])
    bus["org_id"] = np.where(bus.bu_id.isin(["BU04", "BU05"]), "ORG03", "ORG02")
    bus[["bu_id", "org_id", "name"]].to_csv(out_dir / "business_units.csv", index=False)

    # products (JSON) with an inconsistent-category defect
    products = []
    pid = 1
    for bu_id, bu_name, margin in BUSINESS_UNITS:
        for k in range(8):
            price = float(np.round(rng.lognormal(mean=np.log(900 if bu_id != "BU03" else 2500), sigma=0.5), 2))
            category = bu_name.split(" ")[0]
            if rng.random() < 0.08:
                category = category.upper()  # injected inconsistency
            products.append({
                "product_id": f"P{pid:03d}", "bu_id": bu_id, "name": f"{bu_name} Offering {k + 1}",
                "category": category, "unit_price": price,
                "unit_cost": round(price * (1 - margin) * float(rng.uniform(0.9, 1.1)), 2),
            })
            pid += 1
    with (out_dir / "products.json").open("w", encoding="utf-8") as fh:
        json.dump({"source": "product_catalog_service", "schema_version": "1.0", "items": products}, fh, indent=1)
    prod = pd.DataFrame(products)

    # customers (CSV)
    seg_names = [s[0] for s in SEGMENTS]
    seg = rng.choice(seg_names, size=n_customers, p=[s[1] for s in SEGMENTS])
    reg = rng.choice(regions.region_id, size=n_customers, p=[0.22, 0.2, 0.18, 0.12, 0.17, 0.11])
    signup = START - pd.to_timedelta(rng.integers(0, 1500, n_customers), unit="D")
    late = rng.random(n_customers) < 0.25
    signup = signup.where(~late, START + pd.to_timedelta(rng.integers(0, 700, n_customers), unit="D"))
    satisfaction = np.clip(rng.normal(7.2, 1.5, n_customers), 1, 10)
    # latent churn hazard: low satisfaction, SMB, LATAM / EMEA South higher
    hazard = (0.10 + 0.08 * (seg == "SMB") + 0.05 * np.isin(reg, ["R04", "R06"])
              + 0.06 * (satisfaction < 6) - 0.05 * (seg == "Enterprise"))
    churned = rng.random(n_customers) < hazard * 1.6
    churn_date = pd.Series(pd.NaT, index=range(n_customers))
    cd = pd.Timestamp("2024-06-01") + pd.to_timedelta(rng.integers(0, 520, n_customers), unit="D")
    churn_date[churned] = cd[churned]
    customers = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(1, n_customers + 1)],
        "name": [f"Simulated Customer {i:05d}" for i in range(1, n_customers + 1)],
        "region_id": reg, "segment": seg,
        "industry": rng.choice(INDUSTRIES, size=n_customers),
        "signup_date": signup.strftime("%Y-%m-%d"),
        "satisfaction_score": np.round(satisfaction, 1),
        "credit_limit": np.round(np.where(seg == "Enterprise", 500000, np.where(seg == "Mid-Market", 120000, 25000))
                                 * rng.uniform(0.6, 1.4, n_customers), -2),
    })
    miss = rng.random(n_customers) < 0.04
    customers.loc[miss, "industry"] = np.nan  # missing values
    customers.loc[rng.choice(n_customers, 6, replace=False), "signup_date"] = "2031-02-30"  # impossible dates
    seg_bad = rng.choice(n_customers, 25, replace=False)
    customers.loc[seg_bad, "segment"] = customers.loc[seg_bad, "segment"].str.lower()  # inconsistent categories
    customers.to_csv(out_dir / "customers.csv", index=False)

    # transactions (Parquet)
    reg_lookup = regions.set_index("region_id")
    seg_rate = {s[0]: s[2] for s in SEGMENTS}
    base_rate = np.array([seg_rate[s] for s in seg]) * 0.045
    signup_ts = pd.to_datetime(customers.signup_date, errors="coerce").fillna(START)
    rows = []
    month_idx = (days.year - 2023) * 12 + days.month - 1
    for i, cust in enumerate(customers.itertuples(index=False)):
        r = reg_lookup.loc[cust.region_id]
        t = np.asarray((days - START).days) / 365.0
        growth = (1 + r.annual_growth) ** t
        if cust.region_id == "R05":  # trend change: APAC acceleration from July 2024
            growth = growth * np.where(np.asarray(days) >= pd.Timestamp("2024-07-01"), 1 + 0.35 * (t - 1.5).clip(0), 1)
        if cust.region_id == "R04":  # trend change: EMEA South contraction during 2025
            growth = growth * np.where(np.asarray(days) >= pd.Timestamp("2025-01-01"), 0.8, 1)
        season = 1 + 0.25 * np.sin(2 * np.pi * (np.asarray(days.month) - 1 + r.seasonal_phase) / 12 - np.pi / 2)
        q_end = np.isin(np.asarray(days.month), [3, 6, 9, 12]) & (np.asarray(days.day) >= 20)
        lam = base_rate[i] * r.demand_multiplier * growth * season * (1 + 0.6 * q_end)
        active = np.asarray(days >= signup_ts.iloc[i])
        if not pd.isna(churn_date[i]):
            active &= np.asarray(days < churn_date[i])
        counts = rng.poisson(lam * active)
        idx = np.nonzero(counts)[0]
        for d in idx:
            for _ in range(counts[d]):
                rows.append((cust.customer_id, cust.region_id, d))
    tx = pd.DataFrame(rows, columns=["customer_id", "region_id", "day_idx"])
    n = len(tx)
    seg_of = pd.Series(seg, index=customers.customer_id)
    bu_pref = rng.choice(prod.product_id, size=n)
    tx["product_id"] = bu_pref
    p = prod.set_index("product_id").loc[tx.product_id]
    tx["bu_id"] = p.bu_id.values
    tx["txn_date"] = days[tx.day_idx.values]
    seg_q = seg_of.loc[tx.customer_id].map({"Enterprise": 12, "Mid-Market": 5, "SMB": 2}).values
    tx["quantity"] = rng.poisson(seg_q) + 1
    tx["unit_price"] = np.round(p.unit_price.values * rng.uniform(0.95, 1.05, n), 2)
    tx["discount_pct"] = np.round(np.clip(rng.normal(0.08, 0.05, n), 0, 0.4), 3)
    tx["revenue"] = np.round(tx.quantity * tx.unit_price * (1 - tx.discount_pct), 2)
    tx["cost"] = np.round(tx.quantity * p.unit_cost.values * rng.uniform(0.95, 1.08, n), 2)
    tx["channel"] = rng.choice(["direct", "partner", "online"], size=n, p=[0.5, 0.3, 0.2])
    tx = tx.sort_values("txn_date").reset_index(drop=True)
    tx.insert(0, "transaction_id", [f"T{i:07d}" for i in range(1, n + 1)])
    tx = tx.drop(columns="day_idx")
    # injected defects
    out_idx = rng.choice(n, 40, replace=False)
    tx.loc[out_idx, "revenue"] = tx.loc[out_idx, "revenue"] * 25  # outliers
    tx.loc[rng.choice(n, 30, replace=False), "quantity"] = -1  # invalid range
    tx.loc[rng.choice(n, int(n * 0.01), replace=False), "discount_pct"] = np.nan  # missing
    tx.loc[rng.choice(n, 15, replace=False), "customer_id"] = "C99999"  # broken FK
    dups = tx.sample(n=int(n * 0.004), random_state=seed)
    tx = pd.concat([tx, dups], ignore_index=True)  # duplicates
    tx["txn_date"] = pd.to_datetime(tx.txn_date)
    tx.to_parquet(out_dir / "transactions.parquet", index=False)

    # operations (CSV, daily per region x BU) with labelled anomalies
    grid = pd.MultiIndex.from_product([days, regions.region_id, bus.bu_id],
                                      names=["op_date", "region_id", "bu_id"]).to_frame(index=False)
    daily = (tx.assign(d=tx.txn_date.dt.normalize())
             .groupby(["d", "region_id", "bu_id"]).agg(orders=("transaction_id", "size"),
                                                         rev=("revenue", "sum")).reset_index()
             .rename(columns={"d": "op_date"}))
    ops = grid.merge(daily, on=["op_date", "region_id", "bu_id"], how="left").fillna({"orders": 0, "rev": 0})
    m = len(ops)
    hc_base = ops.region_id.map(reg_lookup.demand_multiplier).values * 18
    ops["headcount"] = np.round(hc_base * rng.uniform(0.9, 1.1, m) + (ops.op_date - START).dt.days.values / 365 * 2)
    ops["orders_processed"] = ops.orders.astype(int)
    ops["fulfillment_hours"] = np.round(np.clip(rng.normal(30, 4, m) + 0.02 * ops.orders, 4, None), 2)
    ops["uptime_pct"] = np.round(np.clip(rng.normal(99.6, 0.15, m), 97, 100), 3)
    ops["support_tickets"] = rng.poisson(3 + 0.4 * ops.orders)
    ops["marketing_spend"] = np.round(ops.rev * rng.uniform(0.04, 0.07, m) + rng.uniform(200, 600, m), 2)
    ops["opex"] = np.round(ops.headcount * 520 + ops.rev * 0.12 + rng.normal(0, 400, m), 2)
    is_anom = np.zeros(m, dtype=bool)
    anom_type = np.array([""] * m, dtype=object)
    k = int(m * 0.006)
    a_idx = rng.choice(m, k, replace=False)
    kinds = rng.choice(["opex_spike", "fulfillment_delay", "outage", "ticket_surge"], size=k)
    for j, kind in zip(a_idx, kinds):
        if kind == "opex_spike":
            ops.loc[j, "opex"] *= rng.uniform(2.2, 3.5)
        elif kind == "fulfillment_delay":
            ops.loc[j, "fulfillment_hours"] *= rng.uniform(2.5, 4.0)
        elif kind == "outage":
            ops.loc[j, "uptime_pct"] = round(float(rng.uniform(85, 95)), 3)
        else:
            ops.loc[j, "support_tickets"] = int(ops.loc[j, "support_tickets"] * rng.uniform(4, 7) + 20)
        is_anom[j] = True
        anom_type[j] = kind
    ops["op_date"] = ops.op_date.dt.strftime("%Y-%m-%d")
    ops.loc[rng.choice(m, 60, replace=False), "uptime_pct"] = np.nan  # missing sensor values
    ops = ops.drop(columns=["orders", "rev"])
    ops.insert(0, "operation_id", [f"OP{i:07d}" for i in range(1, m + 1)])
    ops.to_csv(out_dir / "operations.csv", index=False)
    pd.DataFrame({"operation_id": ops.operation_id[is_anom], "anomaly_type": anom_type[is_anom]}).to_csv(
        labels_dir / "operations_anomalies.csv", index=False)

    # employees and suppliers (pipe-delimited DB extracts)
    ne = 1200
    emp = pd.DataFrame({
        "employee_id": [f"E{i:05d}" for i in range(1, ne + 1)],
        "bu_id": rng.choice(bus.bu_id, ne), "region_id": rng.choice(regions.region_id, ne),
        "role": rng.choice(["Engineer", "Sales", "Support", "Consultant", "Operations", "Manager"], ne),
        "hire_date": (pd.Timestamp("2015-01-01") + pd.to_timedelta(rng.integers(0, 3800, ne), unit="D")).strftime("%Y-%m-%d"),
        "annual_salary": np.round(rng.lognormal(np.log(85000), 0.3, ne), -2),
        "performance_rating": rng.choice([1, 2, 3, 4, 5], ne, p=[0.05, 0.15, 0.45, 0.25, 0.10]),
        "is_active": rng.random(ne) > 0.09,
    })
    emp.loc[rng.choice(ne, 8, replace=False), "annual_salary"] = -1  # invalid range
    _write_psv_extract(emp, out_dir / "db_extract" / "employees.psv", "hr.employees")
    ns = 60
    sup = pd.DataFrame({
        "supplier_id": [f"S{i:03d}" for i in range(1, ns + 1)],
        "name": [f"Simulated Supplier {i:03d}" for i in range(1, ns + 1)],
        "region_id": rng.choice(regions.region_id, ns),
        "category": rng.choice(["Components", "Logistics", "Cloud Infrastructure", "Facilities", "Contractors"], ns),
        "annual_spend": np.round(rng.lognormal(np.log(400000), 0.9, ns), -2),
        "on_time_delivery_pct": np.round(np.clip(rng.normal(93, 4, ns), 70, 100), 1),
        "quality_score": np.round(np.clip(rng.normal(8, 1, ns), 3, 10), 1),
    })
    _write_psv_extract(sup, out_dir / "db_extract" / "suppliers.psv", "procurement.suppliers")

    # incidents (paged API-style JSON)
    ni = 900
    opened = START + pd.to_timedelta(rng.integers(0, len(days) * 24, ni), unit="h")
    sev = rng.choice(["SEV1", "SEV2", "SEV3", "SEV4"], ni, p=[0.04, 0.16, 0.4, 0.4])
    hours = np.where(sev == "SEV1", rng.gamma(2, 6, ni), rng.gamma(2, 20, ni))
    resolved = opened + pd.to_timedelta(hours, unit="h")
    inc = pd.DataFrame({
        "incident_id": [f"INC{i:05d}" for i in range(1, ni + 1)],
        "region_id": rng.choice(regions.region_id, ni, p=[0.15, 0.15, 0.15, 0.2, 0.15, 0.2]),
        "bu_id": rng.choice(bus.bu_id, ni), "supplier_id": rng.choice(sup.supplier_id, ni),
        "severity": sev, "category": rng.choice(["Outage", "Security", "Quality", "Supply", "Compliance"], ni),
        "opened_at": opened.strftime("%Y-%m-%dT%H:%M:%SZ"), "resolved_at": resolved.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cost_impact": np.round(np.where(sev == "SEV1", 80000, np.where(sev == "SEV2", 20000, 3000))
                                * rng.lognormal(0, 0.6, ni), 2),
    })
    bad = rng.choice(ni, 10, replace=False)
    inc.loc[bad, "resolved_at"] = (opened[bad] - pd.Timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")  # impossible
    inc.loc[rng.choice(ni, 20, replace=False), "severity"] = "sev2"  # inconsistent
    inc_dir = out_dir / "incidents_api"
    inc_dir.mkdir(exist_ok=True)
    recs = inc.to_dict(orient="records")
    recs.insert(100, {"incident_id": None, "region_id": "R01", "severity": "SEV3"})  # malformed record
    recs.insert(400, {"incident_id": "INC_BROKEN", "opened_at": "not-a-date", "cost_impact": "n/a"})
    page_size = 250
    pages = [recs[i:i + page_size] for i in range(0, len(recs), page_size)]
    for pi, chunk in enumerate(pages, 1):
        write_json(inc_dir / f"page_{pi:03d}.json", {
            "page": pi, "page_size": page_size, "total_pages": len(pages),
            "next": f"page_{pi + 1:03d}.json" if pi < len(pages) else None, "data": chunk})

    # risk indicators (JSON lines, monthly per region) with schema drift from 2025-07
    months = pd.date_range(START, END, freq="MS")
    with (out_dir / "risk_indicators.jsonl").open("w", encoding="utf-8") as fh:
        for mth in months:
            for r in regions.itertuples():
                rec = {"region_id": r.region_id, "month": mth.strftime("%Y-%m-%d"),
                       "fx_volatility": round(float(abs(rng.normal(0.04 if r.currency in ("USD", "EUR") else 0.09, 0.02))), 4),
                       "compliance_score": round(float(np.clip(rng.normal(88 if r.region_id != "R06" else 78, 5), 40, 100)), 1),
                       "supplier_concentration": round(float(rng.uniform(0.15, 0.55)), 3),
                       "credit_exposure": round(float(rng.lognormal(np.log(2e6), 0.4)), 2)}
                if mth >= pd.Timestamp("2025-07-01"):
                    rec["geo_risk_index"] = round(float(rng.uniform(0, 1)), 3)  # schema drift
                fh.write(json.dumps(rec) + "\n")

    summary = {
        "seed": seed, "simulated": True, "date_range": [str(START.date()), str(END.date())],
        "counts": {"organizations": len(orgs), "regions": len(regions), "business_units": len(bus),
                   "products": len(prod), "customers": len(customers), "transactions": len(tx),
                   "operations": len(ops), "employees": ne, "suppliers": ns, "incidents": ni + 2,
                   "risk_indicators": len(months) * len(regions)},
        "injected": {"transaction_duplicates": len(dups), "transaction_outliers": 40, "negative_quantity": 30,
                     "broken_customer_fk": 15, "operations_anomalies": int(is_anom.sum()),
                     "impossible_signup_dates": 6, "impossible_incident_dates": 10, "malformed_incident_records": 2,
                     "customers_churned": int(churned.sum())},
    }
    write_json(labels_dir / "generation_summary.json", summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the simulated ORBIT enterprise dataset")
    ap.add_argument("--seed", type=int, default=SETTINGS.seed)
    ap.add_argument("--customers", type=int, default=2500)
    ap.add_argument("--out", type=Path, default=PATHS.raw)
    a = ap.parse_args()
    print(json.dumps(generate(a.out, a.seed, a.customers), indent=2))


if __name__ == "__main__":
    main()
