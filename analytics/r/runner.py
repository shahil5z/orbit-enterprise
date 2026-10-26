"""Invoke the R statistical workflow."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "statistical_analysis.R"


def run(input_csv: Path, output_json: Path) -> dict:
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript not found on PATH (run scripts/env.ps1)")
    subprocess.run([rscript, str(SCRIPT), str(input_csv), str(output_json)], check=True, capture_output=True, text=True)
    return json.loads(output_json.read_text(encoding="utf-8"))
