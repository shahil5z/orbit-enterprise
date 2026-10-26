"""Build and invoke the C++ Monte Carlo revenue-at-risk engine."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent / "monte_carlo" / "revenue_at_risk.cpp"
EXE = SRC.parent / "build" / ("revenue_at_risk.exe" if os.name == "nt" else "revenue_at_risk")


def build() -> Path:
    EXE.parent.mkdir(parents=True, exist_ok=True)
    if EXE.exists() and EXE.stat().st_mtime > SRC.stat().st_mtime:
        return EXE
    cmd = ["g++", "-O2", "-std=c++17", "-Wall", "-Wextra", "-o", str(EXE), str(SRC)]
    if os.name == "nt":
        cmd.insert(1, "-static")  # avoid needing MinGW runtime DLLs on PATH at run time
    subprocess.run(cmd, check=True)
    return EXE


def run(forecast: pd.DataFrame, workdir: Path, sims: int = 200000, rho: float = 0.35, seed: int = 7) -> dict:
    exe = build()
    workdir.mkdir(parents=True, exist_ok=True)
    inp, out = workdir / "mc_input.csv", workdir / "revenue_at_risk.json"
    forecast[["region_id", "horizon", "forecast", "log_sd"]].to_csv(inp, index=False, float_format="%.6f")
    subprocess.run([str(exe), "--input", str(inp), "--output", str(out), "--sims", str(sims), "--rho", str(rho),
                    "--seed", str(seed)], check=True, capture_output=True, text=True)
    return json.loads(out.read_text(encoding="utf-8"))
