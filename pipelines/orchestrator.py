"""ORBIT pipeline orchestrator.

INGEST > VALIDATE > TRANSFORM > CURATE > ANALYZE > TRAIN > PREDICT > RISK > OPTIMIZE > DECISION > PUBLISH

Every stage reads its inputs from disk and writes its outputs to disk, so any stage can be re-run on
its own once its upstream outputs exist. Each stage is tracked (run_id, start/end, status,
records_processed, errors, component) in data/runs/<run_id>.json and, at PUBLISH, in PostgreSQL.

Usage:
  python -m pipelines.orchestrator all
  python -m pipelines.orchestrator ingest validate transform
  python -m pipelines.orchestrator optimize --run-id <id>
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from orbit_core.config import PATHS, SETTINGS, ensure_dirs
from orbit_core.io import read_json, write_json, write_parquet
from orbit_core.logging import get_logger, log
from orbit_core.runs import new_run_id, track_stage

STAGES = ["INGEST", "VALIDATE", "TRANSFORM", "CURATE", "ANALYZE", "TRAIN", "PREDICT", "RISK", "OPTIMIZE",
          "DECISION", "PUBLISH"]
OUT = PATHS.outputs
MARTS = PATHS.curated / "marts"
logger = get_logger("orchestrator")


def stage_ingest(run, regenerate: bool = False):
    from pipelines.ingestion.engine import ingest_all
    from pipelines.ingestion.generate_synthetic import generate
    if regenerate or not (PATHS.raw / "transactions.parquet").exists():
        run.details["generated"] = generate(PATHS.raw, SETTINGS.seed)["counts"]
    res = ingest_all(batch_id=run.run_id)
    run.records_processed = sum(r["record_count"] for r in res)
    run.details["datasets"] = {r["dataset_id"]: {k: r[k] for k in ("record_count", "duplicates_removed", "quarantined",
                                                                  "validation_status")} for r in res}
    for r in res:
        if r["validation_status"] == "FAILED":
            run.errors.append(f"{r['dataset_id']}: ingestion failed")


def stage_validate(run, **_):
    from pipelines.validation.quality import run_quality
    rep = run_quality()
    run.records_processed = sum(d["rows"] for d in rep["datasets"])
    run.details = {"overall_quality_score": rep["overall_quality_score"],
                   "scores": {d["dataset"]: d["quality_score"] for d in rep["datasets"]}}
    if rep["overall_quality_score"] < 80:
        raise RuntimeError(f"quality gate failed: overall score {rep['overall_quality_score']} < 80")


def stage_transform(run, **_):
    from pipelines.transformation.conform import conform
    log_ = conform()
    run.details = log_
    run.records_processed = log_["transactions"]["output"]
    conf = PATHS.curated / "conformed"
    # small samples for the Java ERP/CRM integration service and for documentation
    PATHS.samples.mkdir(parents=True, exist_ok=True)
    pd.read_parquet(conf / "customers.parquet").head(300).to_csv(PATHS.samples / "crm_accounts.csv", index=False)
    pd.read_parquet(conf / "suppliers.parquet").to_csv(PATHS.samples / "erp_suppliers.csv", index=False)


def stage_curate(run, **_):
    from pipelines.spark.run_spark import run_curate
    res = run_curate()
    run.details = res
    run.records_processed = sum(v for k, v in res.items() if isinstance(v, int))


def stage_analyze(run, **_):
    from analytics.python.run import run_analytics
    from analytics.r.runner import run as run_r
    res = run_analytics()
    r = run_r(OUT / "analytics" / "region_monthly.csv", OUT / "r" / "statistics.json")
    run.details = {"segments_k": res["segmentation"]["k"], "statistical_anomalies": res["statistical_anomalies"],
                   "r_engine": r["engine"], "anova_p": r["operating_margin_anova"]["p_value"]}
    run.records_processed = res["statistical_anomalies"]["rows"]


def stage_train(run, **_):
    from ml.anomaly_detection.operations import train as train_anom
    from ml.classification.churn import train as train_churn
    from ml.forecasting.revenue import train_and_forecast
    rm = pd.read_parquet(MARTS / "region_monthly")
    cf = pd.read_parquet(MARTS / "customer_features")
    ops = pd.read_parquet(MARTS / "ops_daily_features")
    labels = pd.read_csv(PATHS.raw / "_labels" / "operations_anomalies.csv")
    f = train_and_forecast(rm)
    c = train_churn(cf)
    a = train_anom(ops, labels)
    seg = read_json(OUT / "analytics" / "analytics_summary.json")["segmentation"]
    reports = {"revenue_forecast": f["report"], "churn_classifier": c["report"], "ops_anomaly_iforest": a["report"]}
    for name in reports:
        reports[name] = read_json(PATHS.models / read_json(PATHS.models / name / "latest.json")["path"]
                                  / "evaluation.json")
        reports[name]["artifact_path"] = f"ml/artifacts/{name}/{reports[name]['model_version']}"
    reports["customer_segmentation"] = {"task": "segmentation", "algorithm": "KMeans", "params": {"features": seg["features"]},
                                        "k": seg["k"], "silhouette_by_k": seg["silhouette_by_k"],
                                        "model_version": f"customer_segmentation-v1-k{seg['k']}",
                                        "trained_at": run.started_at.isoformat(), "artifact_path": "outputs/analytics"}
    write_json(OUT / "ml" / "model_reports.json", reports)
    write_parquet(c["predictions"][["customer_id", "split"]], OUT / "ml" / "churn_split.parquet")
    write_parquet(f["test_predictions"], OUT / "ml" / "forecast_test_predictions.parquet")
    run.details = {"forecast_test_mape": f["report"]["test"]["model"]["mape"],
                   "forecast_naive_test_mape": f["report"]["test"]["seasonal_naive"]["mape"],
                   "churn_test_roc_auc": c["report"]["test"]["roc_auc"], "churn_test_f1": c["report"]["test"]["f1"],
                   "anomaly_test_precision": a["report"]["test"]["precision"],
                   "anomaly_test_recall": a["report"]["test"]["recall"]}
    run.records_processed = len(rm) + len(cf) + len(ops)


def stage_predict(run, **_):
    from analytics.rust.scoring import benchmark
    from ml.anomaly_detection.operations import score as score_anom
    from ml.classification.churn import score as score_churn
    from ml.forecasting.revenue import forecast
    from ml.registry import load_latest
    rm = pd.read_parquet(MARTS / "region_monthly")
    cf = pd.read_parquet(MARTS / "customer_features")
    ops = pd.read_parquet(MARTS / "ops_daily_features")
    labels = pd.read_csv(PATHS.raw / "_labels" / "operations_anomalies.csv")
    fb, fv = load_latest("revenue_forecast")
    cb, cv = load_latest("churn_classifier")
    ab, av = load_latest("ops_anomaly_iforest")
    fc = forecast(fb, rm, 6)
    # keep the train/validation/test split marker from training for traceability
    ch = score_churn(cb, cf).merge(pd.read_parquet(OUT / "ml" / "churn_split.parquet"), on="customer_id", how="left")
    an = score_anom(ab, ops, labels)
    write_parquet(fc, OUT / "ml" / "forecast.parquet")
    write_parquet(ch, OUT / "ml" / "churn_predictions.parquet")
    write_parquet(an, OUT / "ml" / "anomaly_predictions.parquet")
    bench = benchmark(ops)
    scores = bench.pop("scores")
    write_parquet(scores, OUT / "rust" / "robust_scores.parquet")
    write_json(OUT / "rust" / "benchmark.json", bench)
    run.details = {"model_versions": {"forecast": fv, "churn": cv, "anomaly": av},
                   "forecast_rows": len(fc), "churn_scored": len(ch), "anomalies_flagged": int(an.is_anomaly.sum()),
                   "rust_benchmark": {k: bench[k] for k in ("rows", "speedup_median_wall",
                                                            "max_abs_score_difference_rust_vs_python")}}
    run.records_processed = len(fc) + len(ch) + len(an)


def stage_risk(run, **_):
    from analytics.cpp.simulation import run as run_mc
    from ml.risk.engine import build_region_inputs, build_unit_inputs, score_entity
    fc = pd.read_parquet(OUT / "ml" / "forecast.parquet")
    rar = run_mc(fc, OUT / "simulation")
    rm = pd.read_parquet(MARTS / "region_monthly")
    ch = pd.read_parquet(OUT / "ml" / "churn_predictions.parquet")
    an = pd.read_parquet(OUT / "ml" / "anomaly_predictions.parquet")
    inc = pd.read_parquet(PATHS.curated / "conformed" / "incidents.parquet")
    reports = read_json(OUT / "ml" / "model_reports.json")
    quality = read_json(OUT / "quality" / "quality_report.json")["overall_quality_score"] / 100
    model_quality = (reports["churn_classifier"]["test"]["roc_auc"] + reports["ops_anomaly_iforest"]["test"]["f1"]
                     + (1 - reports["revenue_forecast"]["test"]["model"]["mape"])) / 3
    reg_in = build_region_inputs(ch, rar, fc, rm, an, inc)
    regions = []
    for rid, raw in reg_in.items():
        coverage = quality * sum(v is not None and v == v for k, v in raw.items() if k != "_context") / 7
        regions.append({"entity_type": "region", "region_id": rid, **score_entity(raw, coverage, model_quality),
                        "_context": raw["_context"]})
    last = pd.to_datetime(rm.month).max()
    units = []
    for (rid, bu), raw in build_unit_inputs(reg_in, an, inc, last).items():
        coverage = quality * sum(v == v for v in raw.values()) / 7
        units.append({"entity_type": "business_unit", "region_id": rid, "bu_id": bu,
                      **score_entity(raw, coverage, model_quality)})
    write_json(OUT / "risk" / "risks.json", {"regions": regions, "business_units": units,
                                            "model_quality": model_quality, "monte_carlo": rar})
    run.details = {"region_levels": {r["region_id"]: f"{r['risk_level']} {r['risk_score']}" for r in regions},
                   "mc_total_var95": rar["total"]["var95"], "mc_elapsed_s": rar["elapsed_seconds"]}
    run.records_processed = len(regions) + len(units)


def run_optimization(params: dict | None, run_id: str, triggered_by: str) -> dict:
    from optimization.workflow import build_problem, solve, summarize_by_region, validate_params
    p = validate_params(params or {})
    risks = read_json(OUT / "risk" / "risks.json")
    unit_risk = {f"{u['region_id']}|{u['bu_id']}": u["risk_score"] for u in risks["business_units"]}
    problem = build_problem(pd.read_parquet(MARTS / "monthly_kpis"), pd.read_parquet(OUT / "ml" / "forecast.parquet"),
                            unit_risk, p)
    opt_id = f"OPT-{new_run_id()}"
    result = solve(problem, OUT / "optimization" / opt_id)
    doc = {"optimization_id": opt_id, "run_id": run_id, "triggered_by": triggered_by, "parameters": p,
           "status": result["status"], "objective": result.get("objective"),
           "baseline_objective": result["baseline"]["objective"], "improvement_abs": result.get("improvement_abs"),
           "improvement_pct": result.get("improvement_pct"), "by_region": summarize_by_region(result),
           "result": result, "assumptions": problem["assumptions"]}
    write_json(OUT / "optimization" / opt_id / "summary.json", doc)
    return doc


def stage_optimize(run, **_):
    doc = run_optimization({}, run.run_id, "pipeline")
    write_json(OUT / "optimization" / "latest.json", doc)
    if doc["status"] != "OPTIMAL":
        run.errors.append(f"optimizer status {doc['status']}")
    run.details = {k: doc[k] for k in ("optimization_id", "status", "objective", "baseline_objective",
                                        "improvement_abs", "improvement_pct")}
    run.records_processed = len(doc["result"].get("allocations", []))


def stage_decision(run, **_):
    from decision.engine import build_decisions
    risks = read_json(OUT / "risk" / "risks.json")
    region_risks = {r["region_id"]: r for r in risks["regions"]}
    decs = build_decisions(region_risks, read_json(OUT / "analytics" / "analytics_summary.json"),
                           read_json(OUT / "r" / "statistics.json"), pd.read_parquet(OUT / "ml" / "forecast.parquet"),
                           risks["monte_carlo"], pd.read_parquet(OUT / "ml" / "churn_predictions.parquet"),
                           read_json(OUT / "optimization" / "latest.json"),
                           read_json(OUT / "ml" / "model_reports.json")["churn_classifier"], run.run_id)
    write_json(OUT / "decisions" / "decisions.json", decs)
    run.records_processed = len(decs)
    run.details = {"decisions": len(decs), "priorities": pd.Series([d["priority"] for d in decs]).value_counts().to_dict()}


def stage_publish(run, **_):
    from database.db import migrate
    from database.seeds.load import persist_outputs, seed_core
    applied = migrate()
    core = seed_core()
    outs = persist_outputs(run.run_id)
    run.details = {"migrations_applied": applied, "core": core, "outputs": outs}
    run.records_processed = sum(core.values()) + sum(outs.values())


FUNCS = {"INGEST": stage_ingest, "VALIDATE": stage_validate, "TRANSFORM": stage_transform, "CURATE": stage_curate,
         "ANALYZE": stage_analyze, "TRAIN": stage_train, "PREDICT": stage_predict, "RISK": stage_risk,
         "OPTIMIZE": stage_optimize, "DECISION": stage_decision, "PUBLISH": stage_publish}
COMPONENT = {"INGEST": "python.ingestion", "VALIDATE": "python.quality", "TRANSFORM": "python.conform",
             "CURATE": "scala.spark", "ANALYZE": "python.analytics+r", "TRAIN": "python.sklearn",
             "PREDICT": "python.sklearn+rust", "RISK": "cpp.montecarlo+python.risk", "OPTIMIZE": "julia.jump_highs",
             "DECISION": "python.decision", "PUBLISH": "postgresql"}


def run_stages(stages: list[str], run_id: str | None = None, regenerate: bool = False) -> str:
    ensure_dirs()
    run_id = run_id or new_run_id()
    log(logger, "pipeline_start", run_id=run_id, stages=stages)
    for st in stages:
        with track_stage(run_id, st, COMPONENT[st]) as run:
            if st == "INGEST":
                FUNCS[st](run, regenerate=regenerate)
            else:
                FUNCS[st](run)
    if "PUBLISH" in stages or _db_available():
        try:
            from database.seeds.load import persist_stage_runs
            persist_stage_runs(PATHS.runs / f"{run_id}.json")
        except Exception as exc:  # run metadata stays on disk even if the database is down
            log(logger, "run_metadata_not_persisted", run_id=run_id, error=type(exc).__name__)
    log(logger, "pipeline_end", run_id=run_id)
    return run_id


def _db_available() -> bool:
    try:
        from database.db import connect
        with connect() as c:
            c.execute("SELECT 1 FROM pipeline_runs LIMIT 1")
        return True
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stages", nargs="+", help="'all' or one or more of: " + ", ".join(s.lower() for s in STAGES))
    ap.add_argument("--run-id", help="attach stages to an existing run id")
    ap.add_argument("--regenerate", action="store_true", help="regenerate the synthetic raw dataset")
    a = ap.parse_args(argv)
    stages = STAGES if a.stages == ["all"] else [s.upper() for s in a.stages]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error(f"unknown stage(s): {bad}")
    run_id = run_stages(stages, a.run_id, a.regenerate)
    doc = json.loads((PATHS.runs / f"{run_id}.json").read_text())
    print(json.dumps({"run_id": run_id, "stages": [{k: s[k] for k in ("stage", "status", "duration_s",
                                                                      "records_processed", "error_count")}
                                                   for s in doc["stages"]]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
