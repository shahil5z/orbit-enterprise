import json

import pytest

from orbit_core import runs
from orbit_core.config import PATHS
from tests.conftest import needs_outputs


def test_track_stage_records_success_and_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "PATHS", type("P", (), {"runs": tmp_path})())
    rid = runs.new_run_id()
    with runs.track_stage(rid, "INGEST", "test") as r:
        r.records_processed = 5
    with pytest.raises(RuntimeError):
        with runs.track_stage(rid, "VALIDATE", "test"):
            raise RuntimeError("boom")
    doc = json.loads((tmp_path / f"{rid}.json").read_text())
    assert [s["status"] for s in doc["stages"]] == ["SUCCESS", "FAILED"]
    assert doc["stages"][0]["records_processed"] == 5
    assert "RuntimeError: boom" in doc["stages"][1]["errors"][0]


@pytest.mark.skipif(not (PATHS.curated / "conformed" / "_transform_log.json").exists(), reason="transform not run")
def test_transform_rejects_invalid_transactions_and_keeps_counts_consistent():
    log = json.loads((PATHS.curated / "conformed" / "_transform_log.json").read_text())
    t = log["transactions"]
    assert t["input"] - t["rejected"] == t["output"]
    assert t["rejected"] > 0


@pytest.mark.skipif(not (PATHS.curated / "conformed" / "transactions.parquet").exists(), reason="transform not run")
def test_conformed_transactions_satisfy_contract():
    import pandas as pd
    t = pd.read_parquet(PATHS.curated / "conformed" / "transactions.parquet")
    c = pd.read_parquet(PATHS.curated / "conformed" / "customers.parquet")
    assert (t.quantity > 0).all()
    assert t.transaction_id.is_unique
    assert t.customer_id.isin(c.customer_id).all()
    assert ((t.revenue - t.quantity * t.unit_price * (1 - t.discount_pct)).abs() < 0.05).all()


@needs_outputs("quality/quality_report.json")
def test_quality_report_written_in_both_formats():
    rep = json.loads((PATHS.outputs / "quality" / "quality_report.json").read_text())
    assert 0 <= rep["overall_quality_score"] <= 100
    assert (PATHS.outputs / "quality" / "quality_report.md").exists()
