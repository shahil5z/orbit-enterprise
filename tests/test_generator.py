import json

from pipelines.ingestion.generate_synthetic import generate


def test_generator_is_deterministic(tmp_path):
    a = generate(tmp_path / "a", 123, n_customers=150)
    b = generate(tmp_path / "b", 123, n_customers=150)
    assert a["counts"] == b["counts"]
    assert (tmp_path / "a" / "customers.csv").read_bytes() == (tmp_path / "b" / "customers.csv").read_bytes()
    summary = json.loads((tmp_path / "a" / "_labels" / "generation_summary.json").read_text())
    assert "simulated" in json.dumps(summary).lower()


def test_different_seed_changes_data(tmp_path):
    generate(tmp_path / "a", 1, n_customers=150)
    generate(tmp_path / "b", 2, n_customers=150)
    assert (tmp_path / "a" / "customers.csv").read_bytes() != (tmp_path / "b" / "customers.csv").read_bytes()
