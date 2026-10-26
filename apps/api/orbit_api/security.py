"""HTTP hardening: security headers, request body limit, per-client rate limit.

The rate limiter is in-process. On serverless platforms each warm instance keeps its own window, so it
bounds abuse per instance rather than globally; a shared store (e.g. Redis) would be needed for a hard
global limit.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from starlette.types import ASGIApp, Receive, Scope, Send

from .envelope import fail

API_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cache-control": "no-store",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
DOCS_PATHS = ("/docs", "/redoc")


def client_key(scope: Scope) -> str:
    headers = dict(scope.get("headers") or [])
    fwd = headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",")[0].strip()
    if fwd:
        return fwd
    client = scope.get("client")
    return client[0] if client else "unknown"


class HardeningMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int, rate_per_min: int, hsts: bool):
        self.app, self.max_body, self.rate, self.hsts = app, max_body_bytes, rate_per_min, hsts
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _limited(self, key: str) -> bool:
        if self.rate <= 0:
            return False
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.rate:
                return True
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory under address churn
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] <= 60}
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        extra = dict(API_HEADERS)
        if not path.startswith(DOCS_PATHS):
            extra["content-security-policy"] = API_CSP
        if self.hsts:
            extra["strict-transport-security"] = "max-age=63072000; includeSubDomains"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (k.encode(), v.encode()) for k, v in extra.items() if k.encode() not in existing]
            await send(message)

        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_body):
            await fail(413, "PAYLOAD_TOO_LARGE", f"request body exceeds {self.max_body} bytes")(scope, receive,
                                                                                               send_with_headers)
            return
        if path.startswith("/api/") and self._limited(client_key(scope)):
            resp = fail(429, "RATE_LIMITED", "too many requests; retry in a minute")
            resp.headers["retry-after"] = "60"
            await resp(scope, receive, send_with_headers)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise ValueError("request body too large")
            return message

        await self.app(scope, limited_receive, send_with_headers)
