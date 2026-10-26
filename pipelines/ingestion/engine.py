"""Multi-format ingestion engine.

For each registered source: read raw records, detect the observed schema, compare against the
expected contract (schema drift), coerce types, quarantine malformed records, flag duplicates,
and write a staging Parquet file plus an ingestion metadata record.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from orbit_core.config import PATHS
from orbit_core.io import write_json, write_parquet

SOURCES_FILE = PATHS.root / "configs" / "sources.json"


def load_registry(path: Path = SOURCES_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- readers ----------

def _read_db_extract(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if not ln.startswith("--")]
    trailer = [ln for ln in lines if ln.startswith("-- TRAILER")]
    from io import StringIO
    df = pd.read_csv(StringIO("\n".join(body)), sep="|", dtype=str, keep_default_na=False, na_values=[""])
    if trailer:
        expected = int(trailer[0].split("rows=")[1])
        if expected != len(df):
            raise ValueError(f"extract trailer mismatch: trailer={expected} parsed={len(df)}")
    return df


def read_source(spec: dict, raw_dir: Path) -> pd.DataFrame:
    path = raw_dir / spec["path"]
    fmt = spec["format"]
    if fmt == "csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    if fmt == "parquet":
        return pd.read_parquet(path)
    if fmt == "json":
        return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    if fmt == "json_envelope":
        return pd.DataFrame(json.loads(path.read_text(encoding="utf-8"))[spec["records_key"]])
    if fmt == "jsonl":
        return pd.DataFrame([json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()])
    if fmt == "db_extract":
        return _read_db_extract(path)
    if fmt == "api_pages":
        records, page = [], "page_001.json"
        seen = set()
        while page and page not in seen:  # follow the "next" cursor like a paged REST API
            seen.add(page)
            doc = json.loads((path / page).read_text(encoding="utf-8"))
            records.extend(doc[spec["records_key"]])
            page = doc.get("next")
        return pd.DataFrame(records)
    raise ValueError(f"unsupported format: {fmt}")


# ---------- schema detection ----------

def detect_type(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "unknown"
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_integer_dtype(s):
        return "int"
    if pd.api.types.is_float_dtype(s):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    sample = s.astype(str).head(500)
    if sample.str.lower().isin(["true", "false"]).all():
        return "bool"
    num = pd.to_numeric(sample, errors="coerce")
    if num.notna().mean() > 0.98:
        return "int" if (num.dropna() % 1 == 0).all() and not sample.str.contains(r"\.").any() else "float"
    if sample.str.match(r"^\d{4}-\d{2}-\d{2}$").mean() > 0.95:
        return "date"
    if sample.str.match(r"^\d{4}-\d{2}-\d{2}T").mean() > 0.95:
        return "datetime"
    if s.nunique() <= max(20, len(s) * 0.01):
        return "category"
    return "string"


def detect_schema(df: pd.DataFrame) -> dict[str, str]:
    return {c: detect_type(df[c]) for c in df.columns}


COMPATIBLE = {
    "string": {"string", "category", "unknown"}, "category": {"category", "string", "unknown"},
    "int": {"int", "unknown"}, "float": {"float", "int", "unknown"}, "date": {"date", "datetime", "unknown"},
    "datetime": {"datetime", "date", "unknown"}, "bool": {"bool", "unknown"},
}


def schema_drift(expected: dict[str, str], observed: dict[str, str]) -> dict:
    return {
        "added_columns": sorted(set(observed) - set(expected)),
        "missing_columns": sorted(set(expected) - set(observed)),
        "type_changes": {c: {"expected": expected[c], "observed": observed[c]} for c in expected
                         if c in observed and observed[c] not in COMPATIBLE[expected[c]]},
    }


# ---------- coercion + quarantine ----------

def coerce(df: pd.DataFrame, schema: dict[str, str]) -> tuple[pd.DataFrame, pd.Series]:
    """Cast columns to contract types. Returns (typed frame, per-row parse-failure mask)."""
    out = df.copy()
    bad = pd.Series(False, index=df.index)
    for col, typ in schema.items():
        if col not in out.columns:
            out[col] = pd.NA
            continue
        raw = out[col]
        present = raw.notna() & (raw.astype(str).str.strip() != "")
        if typ in ("int", "float"):
            val = pd.to_numeric(raw, errors="coerce")
            bad |= present & val.isna()
            out[col] = val.astype("Int64") if typ == "int" and (val.dropna() % 1 == 0).all() else val.astype(float)
        elif typ == "date":
            val = pd.to_datetime(raw, errors="coerce", format="mixed")
            bad |= present & val.isna()
            out[col] = val.dt.normalize()
        elif typ == "datetime":
            val = pd.to_datetime(raw, errors="coerce", utc=True, format="mixed")
            bad |= present & val.isna()
            out[col] = val
        elif typ == "bool":
            out[col] = raw.astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
        else:
            out[col] = raw.where(present, None).astype("string")
    return out, bad


def _parse_fail_col(raw: pd.DataFrame, typed: pd.DataFrame, col: str) -> pd.Series:
    if col not in raw.columns:
        return pd.Series(False, index=raw.index)
    present = raw[col].notna() & (raw[col].astype(str).str.strip() != "")
    return present & typed[col].isna()


def _pk_cols(spec: dict) -> list[str]:
    pk = spec["primary_key"]
    return pk if isinstance(pk, list) else [pk]


def ingest_dataset(name: str, spec: dict, raw_dir: Path = PATHS.raw, staging_dir: Path = PATHS.staging,
                   batch_id: str = "manual", schema_version: str = "1.0") -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    raw = read_source(spec, raw_dir)
    observed = detect_schema(raw)
    drift = schema_drift(spec["schema"], observed)
    typed, parse_fail = coerce(raw, spec["schema"])
    pk = _pk_cols(spec)
    required = spec.get("required", [])
    missing_required = typed[required].isna().any(axis=1)
    # unparseable values in required columns quarantine the row; elsewhere they are nulled and counted
    req_parse_fail = pd.Series(False, index=raw.index)
    for c in required:
        col_fail = _parse_fail_col(raw, typed, c)
        req_parse_fail |= col_fail
    nullified = int((parse_fail & ~req_parse_fail).sum())
    parse_fail = req_parse_fail
    quarantine_mask = parse_fail | missing_required
    quarantined = raw[quarantine_mask].copy()
    reasons = np.where(parse_fail[quarantine_mask], "type_parse_failure", "missing_required_field")
    quarantined["_quarantine_reason"] = reasons
    good = typed[~quarantine_mask].copy()
    # duplicate detection: exact-row duplicates are removed, PK-only conflicts are flagged and kept for review
    exact_dup = good.duplicated(keep="first")
    pk_dup = good.duplicated(subset=pk, keep="first") & ~exact_dup
    good = good[~exact_dup].copy()
    good["_pk_conflict"] = pk_dup[~exact_dup].values
    good["_batch_id"] = batch_id
    good["_ingested_at"] = ts
    extra = drift["added_columns"]
    keep_cols = list(spec["schema"]) + extra + ["_pk_conflict", "_batch_id", "_ingested_at"]
    for c in extra:  # drifted columns are carried but typed by detection, not by contract
        good[c] = pd.to_numeric(good[c], errors="coerce") if observed.get(c) in ("int", "float") else good[c]
    good = good[keep_cols]
    write_parquet(good, staging_dir / f"{name}.parquet")
    if len(quarantined):
        qdir = staging_dir / "_quarantine"
        qdir.mkdir(parents=True, exist_ok=True)
        quarantined.astype(str).to_csv(qdir / f"{name}.csv", index=False)
    fingerprint = hashlib.sha256(json.dumps(observed, sort_keys=True).encode()).hexdigest()[:16]
    error_count = int(quarantine_mask.sum())
    status = "PASSED" if error_count == 0 and nullified == 0 and not any(drift.values()) else "PASSED_WITH_WARNINGS"
    if len(good) == 0:
        status = "FAILED"
    return {
        "dataset_id": name, "source": str(spec["path"]), "format": spec["format"], "batch_id": batch_id,
        "ingestion_timestamp": ts, "schema_version": schema_version, "schema_fingerprint": fingerprint,
        "record_count_raw": int(len(raw)), "record_count": int(len(good)), "duplicates_removed": int(exact_dup.sum()),
        "pk_conflicts": int(pk_dup.sum()), "invalid_values_nullified": nullified, "quarantined": error_count, "error_count": error_count,
        "validation_status": status, "observed_schema": observed, "schema_drift": drift,
    }


def ingest_all(batch_id: str, raw_dir: Path = PATHS.raw, staging_dir: Path = PATHS.staging,
               registry: dict | None = None) -> list[dict]:
    registry = registry or load_registry()
    results = []
    for name, spec in registry["datasets"].items():
        results.append(ingest_dataset(name, spec, raw_dir, staging_dir, batch_id, registry["schema_version"]))
    write_json(staging_dir / "_ingestion_metadata.json", {"batch_id": batch_id, "datasets": results})
    return results
