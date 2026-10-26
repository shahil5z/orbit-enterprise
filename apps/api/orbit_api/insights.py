"""Phase 2 service layer: page-level aggregates, drill-downs, traceability, scenarios, search and exports.
Reuses Phase 1 artifacts and tables; nothing here invents data."""
from __future__ import annotations

import csv
import io
import math
from datetime import date

import pandas as pd

from decision import scenarios
from orbit_core.kpis import catalogue

from .services import NotFound, OrbitService, _read

MODEL_PURPOSE = {
    "revenue_forecast": "Six-month regional revenue forecast with 80% intervals; feeds risk, optimization and decisions.",
    "churn_classifier": "Customer churn probability; drives churn exposure risk and retention recommendations.",
    "ops_anomaly_iforest": "Flags unusual operating days per region and business unit for operations review.",
    "customer_segmentation": "Groups customers by behaviour (RFM and trend) for targeting and analysis.",
}
OPS_ASSUMPTIONS = {
    "uptime_target_pct": 99.5,
    "orders_target": "same month prior year x 1.03 (planning assumption)",
    "fulfillment_target": "median monthly fulfillment hours of the prior 12 months",
    "orders_forecast": "seasonal naive: same month prior year x trailing 12-month growth",
    "capacity_proxy": "95th percentile of monthly orders per head (last 24 months) x that month's headcount",
}


def _clean(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _chg(cur, prev):
    return (cur / prev - 1) if cur is not None and prev not in (None, 0) else None


def run_status(run: dict) -> str:
    if run.get("ended_at") is None:
        return "RUNNING"
    if run.get("all_succeeded"):
        return "WARNING" if (run.get("errors") or 0) > 0 else "SUCCESS"
    return "FAILED"


def stage_status(st: dict) -> str:
    if st["status"] == "SUCCESS" and (st.get("error_count") or 0) > 0:
        return "WARNING"
    return st["status"]


class InsightService:
    def __init__(self, core: OrbitService):
        self.core, self.repo, self.out = core, core.repo, core.out
        self._cache: dict = {}  # (latest pipeline run_id, filters) -> intelligence payload

    def _cached(self, name: str, f: dict, build):
        """Transaction aggregates only change when the pipeline republishes, so results are keyed by the latest
        pipeline run id (risks table). A new run makes every old key unreachable; the dict is bounded at 64 entries."""
        key = (name, self.repo.latest_run_id("risks"), tuple(sorted((k, str(v)) for k, v in f.items())))
        if key not in self._cache:
            if len(self._cache) >= 64:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = build()
        return self._cache[key]

    # ---- reference --------------------------------------------------------------------------
    def kpis(self) -> dict:
        return {"kpis": catalogue()}

    def dimensions(self) -> dict:
        return self.repo.dimensions()

    # ---- overview ---------------------------------------------------------------------------
    def overview(self) -> dict:
        a = self.core.analytics()
        monthly = self.repo.company_monthly(None)
        df = pd.DataFrame(monthly)
        comparisons = {}
        if len(df) >= 15:
            last_q, prev_q, ly_q = df.iloc[-3:], df.iloc[-6:-3], df.iloc[-15:-12]
            for k in ("revenue", "gross_margin", "opex", "operating_profit", "incidents", "transactions"):
                cur, pq, lq = float(last_q[k].sum()), float(prev_q[k].sum()), float(ly_q[k].sum())
                comparisons[k] = {"current": cur, "prior_quarter": pq, "same_quarter_last_year": lq,
                                  "qoq": _chg(cur, pq), "yoy": _chg(cur, lq)}
            comparisons["period"] = {"current": [str(last_q.iloc[0]["period_month"]), str(last_q.iloc[-1]["period_month"])],
                                     "prior_quarter_start": str(prev_q.iloc[0]["period_month"]),
                                     "same_quarter_last_year_start": str(ly_q.iloc[0]["period_month"])}
        names, bus = self.repo.region_names(), self.repo.bu_names()
        risks = self.core.risks(None, None)
        recs = self.core.recommendations(None)
        anomalies = self.repo.anomaly_page(self.core._run("predictions"), _nofilter(), 5, 0)
        return _clean({
            "label": "Simulated enterprise dataset",
            "as_of_month": a["company"]["as_of_month"], "ttm": a["company"]["ttm"], "prior_ttm": a["company"]["prior_ttm"],
            "ttm_revenue_growth": a["company"]["ttm_revenue_growth"], "quarter_comparison": comparisons,
            "monthly": monthly,
            "by_region": [{**r, "name": names.get(r["region_id"])} for r in a["by_region"]],
            "by_business_unit": [{**b, "name": bus.get(b["bu_id"])} for b in a["by_business_unit"]],
            "top_risks": risks["risks"][:6], "monte_carlo_total": risks["monte_carlo"]["total"],
            "top_anomalies": anomalies["rows"], "anomaly_total": anomalies["total"],
            "recommendations": recs["recommendations"][:5], "run_id": recs["run_id"],
        })

    # ---- intelligence -----------------------------------------------------------------------
    def intelligence(self, f: dict) -> dict:
        return self._cached("intelligence", f, lambda: self._intelligence(f))

    def _intelligence(self, f: dict) -> dict:
        dr = self.repo.dimensions()["date_range"]
        start, end = f["start"] or dr["start"], f["end"] or dr["end"]
        f = {**f, "start": start, "end": end}
        span = (end - start).days + 1
        prior = {**f, "start": date.fromordinal(start.toordinal() - span), "end": date.fromordinal(start.toordinal() - 1)}
        b = self.repo.txn_breakdown(f)
        tot, ptot = b["totals"], self.repo.txn_totals(prior)
        comparison = {k: {"current": tot[k], "prior": ptot[k], "change": _chg(tot[k], ptot[k])}
                      for k in ("revenue", "gross_margin", "transactions", "customers")}
        inc = self.repo.incident_breakdown(f)
        seg = self.core.analytics()["segmentation"]
        return _clean({"filters": {k: (str(v) if isinstance(v, date) else v) for k, v in f.items()},
                       "comparison_period": {"start": str(prior["start"]), "end": str(prior["end"])},
                       "comparison": comparison, "monthly": b["monthly"],
                       "by_region": b["region"], "by_business_unit": b["business_unit"],
                       "by_segment": b["segment"], "by_channel": b["channel"], "top_products": b["product"], "incidents": inc,
                       "behaviour_segments": seg})

    # ---- forecasts --------------------------------------------------------------------------
    def forecast_series(self, region_id: str | None) -> dict:
        fc = self.core.forecasts(region_id)
        rows = fc["forecasts"]
        if not rows:
            raise NotFound("no forecasts for this selection")
        hist = [{"month": str(m["period_month"]), "actual": m["revenue"]} for m in self.repo.company_monthly(region_id)]
        if region_id:
            fut = [{"month": str(r["target_month"]), "horizon": r["horizon"], "forecast": r["forecast"],
                    "lower_80": r["lower_80"], "upper_80": r["upper_80"]} for r in rows]
            band_note = "80% interval from model residual spread"
        else:
            g = pd.DataFrame(rows).groupby(["target_month", "horizon"], as_index=False)[["forecast", "lower_80", "upper_80"]].sum()
            fut = [{"month": str(r.target_month), "horizon": int(r.horizon), "forecast": float(r.forecast),
                    "lower_80": float(r.lower_80), "upper_80": float(r.upper_80)} for r in g.itertuples()]
            band_note = "sum of regional 80% bounds (conservative: assumes regions move together)"
        report = _read(self.out / "ml" / "model_reports.json")["revenue_forecast"]
        test_path = self.out / "ml" / "forecast_test_predictions.parquet"
        backtest, region_acc = [], {}
        if test_path.exists():
            t = pd.read_parquet(test_path)
            for rid, g in t.groupby("region_id"):
                region_acc[rid] = {"mape": float((abs(g.revenue - g.prediction) / g.revenue).mean()),
                                   "naive_mape": float((abs(g.revenue - g.lag12) / g.revenue).mean()), "n": len(g)}
            if region_id:
                t = t[t.region_id == region_id]
            bt = t.groupby("month", as_index=False)[["revenue", "prediction", "lag12"]].sum()
            backtest = [{"month": str(r.month.date()), "actual": float(r.revenue), "prediction": float(r.prediction),
                         "seasonal_naive": float(r.lag12)} for r in bt.itertuples()]
        return _clean({"run_id": fc["run_id"], "target": "revenue", "region_id": region_id,
                       "model_version": rows[0]["model_version"], "algorithm": report.get("selected"),
                       "horizon_months": report.get("horizon_months"), "band": band_note, "history": hist,
                       "forecast": fut, "backtest": backtest, "accuracy": report["test"],
                       "accuracy_by_region": region_acc, "split": report.get("split"),
                       "features": report.get("params", {}).get("features")})

    # ---- risk -------------------------------------------------------------------------------
    def risk_detail(self, region_id: str) -> dict:
        r = self.core.risks(None, None)
        rows = [x for x in r["risks"] if x["region_id"] == region_id]
        if not rows:
            raise NotFound("no risk rows for region")
        run_id = r["run_id"]
        recs = [x for x in self.core.recommendations(None)["recommendations"] if x["entity_id"] == region_id]
        return _clean({"run_id": run_id, "region_id": region_id, "name": self.repo.region_names().get(region_id),
                       "region": next((x for x in rows if x["entity_type"] == "region"), None),
                       "business_units": [x for x in rows if x["entity_type"] == "business_unit"],
                       "monte_carlo": r["monte_carlo"]["regions"].get(region_id),
                       "driver_trend": self.repo.risk_driver_trend(self.core._run("predictions"), region_id),
                       "churn_by_segment": self.repo.churn_by_segment(self.core._run("predictions"), region_id),
                       "top_churn_customers": self.repo.churn_customers(self.core._run("predictions"), region_id, 15),
                       "recommendation": recs[0] if recs else None})

    # ---- anomalies --------------------------------------------------------------------------
    def anomalies(self, f: dict, limit: int, offset: int) -> dict:
        run_id = self.core._run("predictions")
        page = self.repo.anomaly_page(run_id, f, limit, offset)
        return _clean({"run_id": run_id, **page, "limit": limit, "offset": offset})

    def anomaly(self, operation_id: str) -> dict:
        run_id = self.core._run("predictions")
        row = self.repo.anomaly(run_id, operation_id)
        if not row:
            raise NotFound("operation not found")
        base = self.repo.ops_baseline(row["region_id"], row["bu_id"], row["op_date"])
        deviations = []
        for m in ("orders_processed", "fulfillment_hours", "uptime_pct", "support_tickets", "opex", "marketing_spend",
                  "headcount"):
            mean, sd, v = base.get(f"{m}_mean"), base.get(f"{m}_sd"), row.get(m)
            if mean is None or v is None:
                continue
            z = (float(v) - mean) / sd if sd else None
            deviations.append({"metric": m, "value": float(v), "baseline_mean": mean, "baseline_sd": sd, "z": z,
                               "pct_vs_mean": _chg(float(v), mean)})
        deviations.sort(key=lambda d: -abs(d["z"] or 0))
        near = self.repo.incidents_near(row["region_id"], row["op_date"])
        top = [d for d in deviations if d["z"] is not None and abs(d["z"]) >= 2.5][:3]
        parts = [f"{d['metric'].replace('_', ' ')} {d['value']:,.1f} vs local mean {d['baseline_mean']:,.1f} "
                 f"({d['z']:+.1f} sd)" for d in top]
        if near:
            parts.append(f"{len(near)} incident(s) in the region within the window ({', '.join(sorted({i['severity'] for i in near}))})")
        if row.get("uptime_imputed"):
            parts.append("uptime value was imputed during transformation")
        if not top:
            parts.insert(0, "no single metric deviates more than 2.5 sd, so the model is reacting to the combination "
                            "of values or to rolling-window features")
        if row.get("labelled_anomaly") == 0:
            parts.append("the simulated ground truth does not label this day anomalous (possible false positive)")
        explanation = "Possible explanation: " + "; ".join(parts) + "."
        return _clean({"run_id": run_id, "operation": row, "baseline_days": base["days"], "baseline_window": "same region and business unit, 90 days either side, excluding the day",
                       "deviations": deviations, "incidents_nearby": near, "explanation": explanation,
                       "explanation_method": "rule-based: metrics beyond 2.5 sd of the surrounding 180 days plus nearby incidents"})

    # ---- operations -------------------------------------------------------------------------
    def operations_summary(self, f: dict) -> dict:
        monthly = pd.DataFrame(self.repo.ops_monthly(f))
        if monthly.empty:
            raise NotFound("no operations for this selection")
        monthly["orders_per_head"] = monthly.orders / monthly.headcount
        p95 = float(monthly.orders_per_head.tail(24).quantile(0.95))
        monthly["capacity"] = p95 * monthly.headcount
        monthly["utilization"] = monthly.orders / monthly.capacity
        monthly["orders_target"] = monthly.orders.shift(12) * 1.03
        prior_med = monthly.fulfillment_hours.shift(1).rolling(12).median()
        monthly["fulfillment_target"] = prior_med
        monthly["uptime_target"] = OPS_ASSUMPTIONS["uptime_target_pct"]
        tail = monthly.tail(24)
        growth = tail.orders.iloc[-12:].sum() / tail.orders.iloc[:12].sum() if len(tail) == 24 else 1.0
        last = pd.Timestamp(monthly.month.iloc[-1])
        fc = []
        for h in range(1, 4):
            m = last + pd.DateOffset(months=h)
            ly = monthly[pd.to_datetime(monthly.month) == m - pd.DateOffset(years=1)]
            if not ly.empty:
                fc.append({"month": str(m.date()), "orders_forecast": float(ly.orders.iloc[0] * growth)})
        latest = monthly.iloc[-1]
        prev = monthly.iloc[-13] if len(monthly) >= 13 else None
        kpi = {k: {"current": float(latest[k]), "same_month_last_year": float(prev[k]) if prev is not None else None,
                   "yoy": _chg(float(latest[k]), float(prev[k])) if prev is not None else None}
               for k in ("orders", "fulfillment_hours", "uptime_pct", "tickets", "headcount", "orders_per_head", "opex")}
        monthly["month"] = monthly.month.astype(str)
        return _clean({"filters": {k: (str(v) if isinstance(v, date) else v) for k, v in f.items()},
                       "latest_month": monthly.month.iloc[-1], "kpis": kpi,
                       "monthly": monthly.to_dict(orient="records"), "orders_forecast": fc,
                       "incidents": self.repo.incident_breakdown({**f, "category": f.get("category")}),
                       "bottlenecks": self.repo.ops_bottlenecks(f), "assumptions": OPS_ASSUMPTIONS})

    # ---- decisions --------------------------------------------------------------------------
    def decision_trace(self, decision_id: str) -> dict:
        rec = self.repo.recommendation(decision_id)
        if not rec:
            raise NotFound("decision not found")
        region = rec["entity_id"] if rec["scope"] == "region" else None
        fc_model = self.repo.latest_model("revenue_forecast")
        churn = self.repo.latest_model("churn_classifier")
        counts = self.repo.prediction_counts()
        forecasts = self.core.forecasts(region)["forecasts"]
        monthly = self.repo.company_monthly(region)[-12:]
        quality = {d["dataset"]: d for d in self.repo.quality_runs(self.core._run("data_quality_runs"))}
        stages = {s["stage"]: s for s in self.repo.pipeline_run(rec["run_id"])}
        kpis = {k["key"]: k for k in catalogue()}

        def stage(name):
            s = stages.get(name)
            return None if not s else {"stage": name, "status": stage_status(s), "records_processed": s["records_processed"],
                                       "ended_at": s["ended_at"], "component": s["component"]}

        chain = [
            {"level": "recommendation", "title": rec["recommendation"], "detail": rec["expected_impact"],
             "confidence": rec["confidence"], "ref": f"recommendations[{decision_id}]"},
            {"level": "forecast", "title": f"6-month revenue forecast {'for ' + region if region else 'all regions'}",
             "detail": rec["forecast"], "rows": forecasts, "ref": f"forecasts[run={rec['run_id']}]"},
            {"level": "model_output", "title": "Models behind the forecast and risk",
             "models": [{**m, "predictions": counts.get(m["model_version"], {}).get("predictions")}
                        for m in (fc_model, churn) if m], "ref": "model_runs"},
            {"level": "metric", "title": "Monthly revenue (last 12 months)", "kpi": kpis["revenue"], "rows": monthly,
             "ref": "metrics[metric_name=revenue]"},
            {"level": "dataset", "title": "Source datasets and pipeline lineage",
             "datasets": [quality.get(d) for d in ("transactions", "customers", "operations") if quality.get(d)],
             "lineage": [s for s in (stage(n) for n in ("INGEST", "VALIDATE", "TRANSFORM", "CURATE", "TRAIN",
                                                         "PREDICT", "RISK", "DECISION")) if s],
             "ref": "data_quality_runs, pipeline_runs"},
        ]
        return _clean({"decision": rec, "chain": chain})

    # ---- scenarios --------------------------------------------------------------------------
    def scenario_baseline(self) -> list[scenarios.RegionBaseline]:
        fc = pd.DataFrame(self.core.forecasts(None)["forecasts"]).groupby("region_id").forecast.sum()
        a = {r["region_id"]: r for r in self.core.analytics()["by_region"]}
        mc = self.core.risks(None, None)["monte_carlo"]["regions"]
        out = []
        for c in self.repo.region_capacity_inputs():
            rid = c["region_id"]
            if rid not in fc.index:
                continue
            util = min(1.0, (c["recent_oph"] or 0) / c["p95_oph"]) if c["p95_oph"] else 1.0
            out.append(scenarios.RegionBaseline(rid, float(fc[rid]), float(a[rid]["gross_margin_pct"]), float(c["opex_6m"]),
                                                float(c["mkt_6m"]), float(c["headcount"]), util,
                                                float(mc[rid]["p5"]), float(mc[rid]["cvar95"])))
        return out

    def scenario(self, params: dict) -> dict:
        res = scenarios.run(self.scenario_baseline(), params)
        names = self.repo.region_names()
        for r in res["regions"]:
            r["name"] = names.get(r["region_id"])
        res["levers"] = {k: {"min": lo, "max": hi, "description": d} for k, (lo, hi, d) in scenarios.LEVERS.items()}
        res["baseline_label"] = "BASELINE: latest pipeline forecast and last 6 months of actuals"
        return _clean(res)

    # ---- quality / models / system ------------------------------------------------------------
    def quality_dataset(self, dataset: str) -> dict:
        run_id = self.core._run("data_quality_runs")
        row = self.repo.quality_dataset(run_id, dataset)
        if not row:
            raise NotFound("dataset not found in latest quality run")
        stages = {s["stage"]: s for s in self.repo.pipeline_run(run_id)}
        ingest = (stages.get("INGEST") or {}).get("details") or {}
        return _clean({"run_id": run_id, "dataset": row, "history": self.repo.quality_history(dataset),
                       "ingestion": {"stage": stages.get("INGEST", {}).get("status"),
                                     "ended_at": stages.get("INGEST", {}).get("ended_at"),
                                     **(ingest.get("datasets", {}).get(dataset) or {}),
                                     "generated": (ingest.get("generated") or {}).get(dataset)},
                       "pipeline": [{"stage": s["stage"], "status": stage_status(s), "ended_at": s["ended_at"]}
                                    for s in stages.values()]})

    def models(self) -> dict:
        counts = self.repo.prediction_counts()
        reports = _read(self.out / "ml" / "model_reports.json")
        out = []
        for m in self.core.models()["models"]:
            rep = reports.get(m["model_name"], {})
            feats = rep.get("features") or (m.get("params") or {}).get("features") or []
            c = counts.get(m["model_version"], {})
            out.append({**m, "purpose": MODEL_PURPOSE.get(m["model_name"]), "features": feats,
                        "prediction_count": c.get("predictions", 0), "positive_predictions": c.get("positives"),
                        "status": "ACTIVE" if m["model_version"] == rep.get("model_version") else "SUPERSEDED"})
        return _clean({"models": out})

    def system(self) -> dict:
        ops = self.core.operations(20)
        runs = [{**r, "status": run_status(r)} for r in ops["pipeline_runs"]]
        latest = self.core.pipeline_run(runs[0]["run_id"]) if runs else None
        if latest:
            latest["stages"] = [{**s, "status": stage_status(s)} for s in latest["stages"]]
        return _clean({"runs": runs, "latest": latest, "table_counts": ops["table_counts"],
                       "rust_benchmark": ops["rust_benchmark"], "health": self.core.health()})

    def search(self, q: str, limit: int) -> dict:
        res = self.repo.search(q, limit)
        return {"query": q, "results": [{"type": t, **r} for t, rows in res.items() for r in rows],
                "counts": {t: len(r) for t, r in res.items()}}

    # ---- exports ----------------------------------------------------------------------------
    @staticmethod
    def to_csv(rows: list[dict], cols: list[str]) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})
        return buf.getvalue()

    def export(self, kind: str) -> tuple[str, str, str]:
        if kind == "risks.csv":
            r = self.core.risks(None, None)
            rows = [{**x, "top_factors": "; ".join(f"{f['factor']}={f['contribution']}" for f in
                                                    sorted(x["risk_factors"], key=lambda f: -f["contribution"])[:3])}
                    for x in r["risks"]]
            return self.to_csv(rows, ["entity_type", "region_id", "bu_id", "risk_score", "risk_level", "confidence",
                                      "top_factors", "recommended_action", "explanation"]), "text/csv", kind
        if kind == "recommendations.csv":
            r = self.core.recommendations(None)["recommendations"]
            return self.to_csv(r, ["decision_id", "scope", "entity_id", "priority", "observation", "cause", "forecast",
                                   "risk", "recommendation", "expected_impact", "confidence"]), "text/csv", kind
        if kind == "anomalies.csv":
            p = self.anomalies(_nofilter(), 1000, 0)["rows"]
            return self.to_csv(p, ["operation_id", "op_date", "region_id", "bu_id", "anomaly_score", "labelled_anomaly",
                                   "orders_processed", "fulfillment_hours", "uptime_pct", "support_tickets", "opex",
                                   "model_version"]), "text/csv", kind
        if kind == "risk-report.md":
            r = self.core.risks(None, None)
            recs = self.core.recommendations(None)["recommendations"]
            names = self.repo.region_names()
            t = r["monte_carlo"]["total"]
            lines = ["# ORBIT // ENTERPRISE risk report", "", "Simulated enterprise dataset. Run " + r["run_id"] + ".", "",
                     "## Portfolio revenue at risk (6 months, C++ Monte Carlo, "
                     f"{r['monte_carlo']['simulations']:,} simulations)", "",
                     f"- Expected {t['expected']:,.0f}; P5 {t['p5']:,.0f}; P95 {t['p95']:,.0f}",
                     f"- VaR95 {t['var95']:,.0f}; CVaR95 {t['cvar95']:,.0f}", "", "## Regions", "",
                     "| Region | Score | Level | Confidence | Recommended action |", "|---|---|---|---|---|"]
            for x in [x for x in r["risks"] if x["entity_type"] == "region"]:
                lines.append(f"| {names.get(x['region_id'], x['region_id'])} | {x['risk_score']} | {x['risk_level']} | "
                             f"{x['confidence']} | {x['recommended_action']} |")
            lines += ["", "## Recommendations", ""]
            for x in recs:
                lines.append(f"- [{x['priority']}] {x['entity_id']}: {x['recommendation']} Impact: {x['expected_impact']}")
            return "\n".join(lines) + "\n", "text/markdown", kind
        raise NotFound("unknown export")


def _nofilter() -> dict:
    return {"region_id": None, "bu_id": None, "start": None, "end": None}
