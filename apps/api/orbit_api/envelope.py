"""Uniform response envelope: {success, data, metadata, errors}."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

API_VERSION = "v1"


def _meta(extra: dict | None = None) -> dict:
    return {"api_version": API_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": uuid.uuid4().hex[:12], **(extra or {})}


def ok(data: Any, status_code: int = 200, **metadata) -> JSONResponse:
    body = {"success": True, "data": data, "metadata": _meta(metadata), "errors": []}
    return JSONResponse(jsonable_encoder(body), status_code=status_code)


def fail(status_code: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    meta = _meta()
    errors = [{"code": code, "message": message, **({"details": details} if details else {})}]
    return JSONResponse(jsonable_encoder({"success": False, "data": None, "metadata": meta, "errors": errors}),
                        status_code=status_code)
