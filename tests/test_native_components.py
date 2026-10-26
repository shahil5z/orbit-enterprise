"""Rust, C++, R, Julia and Java components exercised through their real toolchains."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from orbit_core.config import PATHS
from tests.conftest import needs_outputs, needs_tool


@needs_tool("cargo")
def test_rust_unit_tests_pass():
    from analytics.rust.scoring import test
    r = test()
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "test result: ok" in r.stdout


@needs_tool("cargo")
def test_rust_matches_python_baseline(tmp_path):
    from analytics.rust.scoring import build, robust_z_python, run_rust
    build()
    rng = np.random.default_rng(0)
    n = 200
    x = rng.normal(100, 5, n)
    x[150] = 400
    df = pd.DataFrame({"series_key": "A", "operation_id": [f"O{i}" for i in range(n)], "opex": x,
                       "fulfillment_hours": x, "neg_uptime_pct": -x, "support_tickets": x})
    df.to_csv(tmp_path / "in.csv", index=False)
    run_rust(tmp_path / "in.csv", tmp_path / "out.csv")
    out = pd.read_csv(tmp_path / "out.csv")
    py = robust_z_python(x)
    rust = out[[c for c in out.columns if c.startswith("opex")][0]].to_numpy()
    m = ~np.isnan(py)
    assert m.sum() > 100
    assert np.allclose(rust[m], py[m], atol=1e-4)
    assert out.robust_score.idxmax() == 150


@needs_tool("cargo")
def test_rust_rejects_bad_input(tmp_path):
    from analytics.rust.scoring import EXE, build
    build()
    (tmp_path / "bad.csv").write_text("wrong,header\n1,2\n")
    r = subprocess.run([str(EXE), "--input", str(tmp_path / "bad.csv"), "--output", str(tmp_path / "o.csv")],
                       capture_output=True, text=True)
    assert r.returncode != 0


@needs_tool("g++")
def test_cpp_monte_carlo_quantiles_ordered(tmp_path):
    from analytics.cpp.simulation import run
    fc = pd.DataFrame({"region_id": ["R01"] * 3 + ["R02"] * 3, "horizon": [1, 2, 3] * 2,
                       "forecast": [100.0, 100, 100, 50, 50, 50], "log_sd": [0.05, 0.07, 0.09] * 2})
    res = run(fc, tmp_path, sims=20000)
    t = res["total"]
    assert t["p5"] < t["p50"] < t["p95"]
    assert t["cvar95"] >= t["var95"] > 0
    assert t["expected"] == pytest.approx(450, rel=0.02)


@needs_tool("g++")
def test_cpp_rejects_invalid_input(tmp_path):
    from analytics.cpp.simulation import build
    exe = build()
    (tmp_path / "bad.csv").write_text("region_id,horizon,forecast,log_sd\nR01,1,-5,0.1\n")
    r = subprocess.run([str(exe), "--input", str(tmp_path / "bad.csv"), "--output", str(tmp_path / "o.json")],
                       capture_output=True, text=True)
    assert r.returncode != 0


@needs_tool("Rscript")
@needs_outputs("analytics/region_monthly.csv")
def test_r_statistical_workflow(tmp_path):
    from analytics.r.runner import run
    res = run(PATHS.outputs / "analytics" / "region_monthly.csv", tmp_path / "stats.json")
    assert res["engine"].startswith("R.")
    assert 0 <= res["operating_margin_anova"]["p_value"] <= 1
    assert len(res["yoy_paired_tests"]) == 6


def _java_home_bins():
    return shutil.which("javac") and shutil.which("java")


@pytest.mark.skipif(not _java_home_bins(), reason="java/javac not on PATH")
def test_java_service_self_test(tmp_path):
    root = PATHS.root / "services" / "java"
    srcs = [str(p) for p in (root / "src").rglob("*.java")]
    out = tmp_path / "classes"
    subprocess.run(["javac", "-d", str(out), *srcs], check=True, capture_output=True, text=True)
    r = subprocess.run(["java", "-cp", str(out), "com.orbit.integration.SelfTest"], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout[-3000:]
    assert "failed=0" in r.stdout
