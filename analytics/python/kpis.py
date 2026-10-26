"""Enterprise KPI computation from the curated monthly KPI mart."""
from __future__ import annotations

import pandas as pd


def latest_period_kpis(kpis: pd.DataFrame) -> dict:
    """Company-wide KPIs for the latest month and trailing twelve months versus the prior twelve."""
    df = kpis.copy()
    df["month"] = pd.to_datetime(df["month"])
    last = df["month"].max()
    ttm = df[df.month > last - pd.DateOffset(months=12)]
    prev = df[(df.month <= last - pd.DateOffset(months=12)) & (df.month > last - pd.DateOffset(months=24))]

    def agg(x: pd.DataFrame) -> dict:
        rev, gm, opex = x.revenue.sum(), x.gross_margin.sum(), x.opex.sum()
        return {"revenue": round(rev, 2), "gross_margin": round(gm, 2), "opex": round(opex, 2),
                "operating_profit": round(gm - opex, 2), "gross_margin_pct": round(gm / rev, 4) if rev else None,
                "operating_margin_pct": round((gm - opex) / rev, 4) if rev else None,
                "transactions": int(x.txn_count.sum()), "incidents": int(x.incident_count.sum()),
                "incident_cost": round(x.incident_cost.sum(), 2)}

    cur, prv = agg(ttm), agg(prev)
    return {"as_of_month": str(last.date()), "ttm": cur, "prior_ttm": prv,
            "ttm_revenue_growth": round(cur["revenue"] / prv["revenue"] - 1, 4) if prv["revenue"] else None}


def kpis_by(kpis: pd.DataFrame, dim: str, months: int = 12) -> list[dict]:
    df = kpis.copy()
    df["month"] = pd.to_datetime(df["month"])
    last = df.month.max()
    cur = df[df.month > last - pd.DateOffset(months=months)]
    prev = df[(df.month <= last - pd.DateOffset(months=months)) & (df.month > last - pd.DateOffset(months=2 * months))]
    g = cur.groupby(dim).agg(revenue=("revenue", "sum"), gross_margin=("gross_margin", "sum"), opex=("opex", "sum"),
                             incidents=("incident_count", "sum"), uptime=("avg_uptime_pct", "mean"))
    g["prior_revenue"] = prev.groupby(dim).revenue.sum()
    g["revenue_growth"] = g.revenue / g.prior_revenue - 1
    g["gross_margin_pct"] = g.gross_margin / g.revenue
    g["operating_margin_pct"] = (g.gross_margin - g.opex) / g.revenue
    g["revenue_share"] = g.revenue / g.revenue.sum()
    return g.reset_index().round(4).to_dict(orient="records")
