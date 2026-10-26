import pandas as pd

from pipelines.validation.quality import check_dataset, robust_outliers

SPEC = {"schema": {"id": "string", "v": "float", "d": "date", "fk": "string"}, "primary_key": "id",
        "required": ["id"], "ranges": {"v": [0, 100]}, "date_bounds": {"d": ["2020-01-01", "2026-12-31"]},
        "foreign_keys": {"fk": "parent.pid"}}


def test_clean_dataset_scores_100():
    df = pd.DataFrame({"id": ["a", "b"], "v": [1.0, 2.0], "d": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                       "fk": ["p1", "p1"]})
    rep = check_dataset("t", df, SPEC, {"parent": pd.DataFrame({"pid": ["p1"]})})
    assert rep["quality_score"] == 100 and rep["issue_count"] == 0


def test_defects_are_detected_and_lower_the_score():
    df = pd.DataFrame({"id": ["a", "a", "c", "d"], "v": [1.0, 500.0, None, 3.0],
                       "d": pd.to_datetime(["2024-01-01", "1990-01-01", "2024-01-01", "2024-01-01"]),
                       "fk": ["p1", "p1", "zz", "p1"]})
    rep = check_dataset("t", df, SPEC, {"parent": pd.DataFrame({"pid": ["p1"]})})
    checks = {i["check"] for i in rep["issues"]}
    assert {"duplicate_primary_key", "out_of_range", "impossible_date", "missing_values"} <= checks
    assert any("foreign" in c for c in checks)
    assert rep["quality_score"] < 100


def test_robust_outliers_flags_extreme_value():
    s = pd.Series([10.0] * 50 + [11.0] * 50 + [1000.0])
    assert robust_outliers(s).iloc[-1] and robust_outliers(s).sum() == 1
