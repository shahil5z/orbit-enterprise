"""Python side of the Rust anomaly scorer: input export, invocation, and the Python baseline used for
benchmarking and for verifying that Rust produces the same numbers."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS

CRATE = Path(__file__).resolve().parent / "anomaly_scorer"
EXE = CRATE / "target" / "release" / ("orbit-anomaly-scorer.exe" if os.name == "nt" else "orbit-anomaly-scorer")
METRICS = ["opex", "fulfillment_hours", "neg_uptime_pct", "support_tickets"]


def export_input(ops: pd.DataFrame, path: Path) -> pd.DataFrame:
    df = ops.sort_values(["region_id", "bu_id", "op_date"]).copy()
    df["series_key"] = df.region_id + "|" + df.bu_id
    df["neg_uptime_pct"] = -df.uptime_pct  # outages are low uptime; invert so high = bad
    out = df[["series_key", "operation_id", *METRICS]]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, float_format="%.6f")
    return out


def cargo_env() -> dict:
    """On Windows (gnu host) link with the MinGW toolchain bundled inside the Rust sysroot.

    The w64devkit gcc that is also on PATH (used for C++) ships no libgcc_eh, which Rust's std needs,
    so the self-contained linker from the Rust toolchain is selected explicitly.
    """
    env = dict(os.environ)
    if os.name == "nt":
        sysroot = subprocess.run(["rustc", "--print", "sysroot"], capture_output=True, text=True,
                                 check=True).stdout.strip()
        gcc = Path(sysroot) / "lib" / "rustlib" / "x86_64-pc-windows-gnu" / "bin" / "self-contained" / \
            "x86_64-w64-mingw32-gcc.exe"
        if gcc.exists():
            env["CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER"] = str(gcc)
            env["RUSTFLAGS"] = "-C link-self-contained=yes"
    return env


def build(release: bool = True) -> Path:
    cmd = ["cargo", "build", "--quiet"] + (["--release"] if release else [])
    subprocess.run(cmd, cwd=CRATE, check=True, env=cargo_env())
    return EXE


def test() -> subprocess.CompletedProcess:
    return subprocess.run(["cargo", "test", "--release"], cwd=CRATE, capture_output=True, text=True, env=cargo_env())


def run_rust(input_csv: Path, output_csv: Path, window: int = 28, min_periods: int = 14) -> dict:
    if not EXE.exists():
        build()
    t0 = time.perf_counter()
    proc = subprocess.run([str(EXE), "--input", str(input_csv), "--output", str(output_csv), "--window", str(window),
                           "--min-periods", str(min_periods)], capture_output=True, text=True, check=True)
    wall = time.perf_counter() - t0
    import json
    stats = json.loads(proc.stderr.strip().splitlines()[-1])
    return {**stats, "wall_seconds_including_process_and_io": wall}


def robust_z_python(x: np.ndarray, window: int = 28, min_periods: int = 14) -> np.ndarray:
    """Reference implementation (numpy per window) with identical semantics to the Rust code."""
    out = np.full(len(x), np.nan)
    for t in range(len(x)):
        w = x[max(0, t - window):t]
        w = w[np.isfinite(w)]
        if len(w) < min_periods or not np.isfinite(x[t]):
            continue
        med = np.median(w)
        mad = np.median(np.abs(w - med))
        out[t] = (x[t] - med) / (1.4826 * mad) if mad > 0 else 0.0
    return out


def run_python(inp: pd.DataFrame, window: int = 28, min_periods: int = 14) -> pd.DataFrame:
    parts = []
    for _, g in inp.groupby("series_key", sort=False):
        res = {"operation_id": g.operation_id.to_numpy()}
        zs = []
        for m in METRICS:
            z = robust_z_python(g[m].to_numpy(float), window, min_periods)
            res[f"{m}_rz"] = z
            zs.append(np.abs(z))
        res["robust_score"] = np.nan_to_num(np.nanmax(np.vstack(zs), axis=0) if len(zs) else 0, nan=0.0)
        parts.append(pd.DataFrame(res))
    return pd.concat(parts, ignore_index=True)


def benchmark(ops: pd.DataFrame, workdir: Path = PATHS.outputs / "rust", repeats: int = 3) -> dict:
    inp_path, out_path = workdir / "ops_input.csv", workdir / "rust_scores.csv"
    inp = export_input(ops, inp_path)
    rust_runs = [run_rust(inp_path, out_path) for _ in range(repeats)]
    py_times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        py = run_python(inp)
        py_times.append(time.perf_counter() - t0)
    rust_df = pd.read_csv(out_path)
    merged = rust_df.merge(py, on="operation_id", suffixes=("_rust", "_py"))
    max_diff = float(np.nanmax(np.abs(merged.robust_score_rust - merged.robust_score_py)))
    rust_compute = [r["elapsed_ms"] / 1000 for r in rust_runs]
    rust_wall = [r["wall_seconds_including_process_and_io"] for r in rust_runs]
    return {"rows": int(len(inp)), "series": int(inp.series_key.nunique()), "metrics": METRICS, "window": 28,
            "repeats": repeats,
            "python_numpy_seconds": {"min": min(py_times), "median": float(np.median(py_times)), "all": py_times},
            "rust_internal_seconds_parse_compute_write": {"min": min(rust_compute), "median": float(np.median(rust_compute)),
                                       "all": rust_compute},
            "rust_wall_seconds_with_process_and_csv_io": {"min": min(rust_wall), "median": float(np.median(rust_wall)),
                                                         "all": rust_wall},
            "speedup_median_wall": float(np.median(py_times) / np.median(rust_wall)),
            "max_abs_score_difference_rust_vs_python": max_diff, "output_csv": str(out_path),
            "scores": rust_df}
