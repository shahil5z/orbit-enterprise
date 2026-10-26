import json

import pandas as pd
import pytest

from pipelines.ingestion.engine import coerce, detect_type, ingest_dataset, read_source, schema_drift

SPEC = {"path": "t.csv", "format": "csv", "primary_key": "id",
        "schema": {"id": "string", "amount": "float", "day": "date"}, "required": ["id", "amount"]}


def _write(tmp_path, text, name="t.csv"):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_detect_type_basic():
    assert detect_type(pd.Series(["1", "2", "3"])) == "int"
    assert detect_type(pd.Series(["1.5", "2"])) == "float"
    assert detect_type(pd.Series(["2024-01-01", "2024-02-03"])) in ("date", "datetime")
    assert detect_type(pd.Series(["a", "b"])) == "category"  # low cardinality
    assert detect_type(pd.Series([f"id{i}" for i in range(5000)])) == "string"


def test_coerce_flags_unparseable_values():
    df = pd.DataFrame({"id": ["a", "b"], "amount": ["1.5", "oops"], "day": ["2024-01-01", "2024-01-02"]})
    typed, bad = coerce(df, SPEC["schema"])
    assert bad.tolist() == [False, True]
    assert typed.amount.isna().tolist() == [False, True]


def test_schema_drift_detects_added_and_missing_columns():
    d = schema_drift({"a": "int", "b": "string"}, {"a": "int", "c": "float"})
    assert d["added_columns"] == ["c"] and d["missing_columns"] == ["b"]


def test_ingest_removes_exact_duplicates_and_quarantines_bad_required(tmp_path):
    _write(tmp_path, "id,amount,day\na,1,2024-01-01\na,1,2024-01-01\nb,xx,2024-01-02\nc,3,2024-01-03\n")
    meta = ingest_dataset("t", SPEC, raw_dir=tmp_path, staging_dir=tmp_path / "stg", batch_id="test")
    assert meta["record_count_raw"] == 4
    assert meta["duplicates_removed"] == 1
    assert meta["quarantined"] == 1
    assert meta["record_count"] == 2
    q = pd.read_csv(tmp_path / "stg" / "_quarantine" / "t.csv")
    assert q._quarantine_reason.tolist() == ["type_parse_failure"]
    staged = pd.read_parquet(tmp_path / "stg" / "t.parquet")
    assert set(staged.columns) >= {"_batch_id", "_ingested_at", "_pk_conflict"}
    assert meta["validation_status"] == "PASSED_WITH_WARNINGS"


def test_ingest_flags_pk_conflicts_without_dropping(tmp_path):
    _write(tmp_path, "id,amount,day\na,1,2024-01-01\na,2,2024-01-01\n")
    meta = ingest_dataset("t", SPEC, raw_dir=tmp_path, staging_dir=tmp_path / "stg")
    assert meta["pk_conflicts"] == 1 and meta["record_count"] == 2


def test_ingest_missing_required_is_quarantined(tmp_path):
    _write(tmp_path, "id,amount,day\n,1,2024-01-01\nb,2,2024-01-02\n")
    meta = ingest_dataset("t", SPEC, raw_dir=tmp_path, staging_dir=tmp_path / "stg")
    assert meta["quarantined"] == 1 and meta["record_count"] == 1


def test_ingest_all_rows_bad_fails(tmp_path):
    _write(tmp_path, "id,amount,day\na,x,2024-01-01\n")
    assert ingest_dataset("t", SPEC, raw_dir=tmp_path, staging_dir=tmp_path / "stg")["validation_status"] == "FAILED"


def test_unsupported_format_raises(tmp_path):
    with pytest.raises(ValueError, match="unsupported format"):
        read_source({"path": "x", "format": "xml"}, tmp_path)


def test_missing_source_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_source(SPEC, tmp_path)


def test_api_pages_follow_cursor_and_stop_on_cycle(tmp_path):
    d = tmp_path / "api"
    d.mkdir()
    (d / "page_001.json").write_text(json.dumps({"data": [{"id": 1}], "next": "page_002.json"}))
    (d / "page_002.json").write_text(json.dumps({"data": [{"id": 2}], "next": "page_001.json"}))
    df = read_source({"path": "api", "format": "api_pages", "records_key": "data"}, tmp_path)
    assert df.id.tolist() == [1, 2]
