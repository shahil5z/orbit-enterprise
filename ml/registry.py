"""Minimal file-based model registry: versioned artifacts + evaluation reports."""
from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

from orbit_core.config import PATHS
from orbit_core.io import write_json


def model_version(name: str, params: dict, data_fingerprint: str) -> str:
    h = hashlib.sha256(json.dumps({"n": name, "p": params, "d": data_fingerprint}, sort_keys=True, default=str)
                       .encode()).hexdigest()[:10]
    return f"{name}-v1-{h}"


def save_model(name: str, version: str, model, report: dict, root: Path = PATHS.models) -> Path:
    d = root / name / version
    d.mkdir(parents=True, exist_ok=True)
    with (d / "model.pkl").open("wb") as fh:
        pickle.dump(model, fh)
    report = {**report, "model_name": name, "model_version": version,
              "trained_at": datetime.now(timezone.utc).isoformat()}
    write_json(d / "evaluation.json", report)
    write_json(root / name / "latest.json", {"version": version, "path": str(d.relative_to(root))})
    return d


def load_latest(name: str, root: Path = PATHS.models):
    latest = json.loads((root / name / "latest.json").read_text())
    with (root / latest["path"] / "model.pkl").open("rb") as fh:
        return pickle.load(fh), latest["version"]


def fingerprint_frame(df) -> str:
    import pandas as pd
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16]
