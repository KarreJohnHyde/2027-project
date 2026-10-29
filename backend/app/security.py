"""Request-level protections: sliding-window rate limits and security headers."""

from __future__ import annotations

from collections import defaultdict, deque
import os
import threading
import time
from typing import Callable

from fastapi import HTTPException, Request, status
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import ENVIRONMENT, RATE_LIMIT_ENABLED
from app.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    reset_request_id,
    select_request_id,
)


class SlidingWindowLimiter:
    """In-process limiter. Suitable for a single worker; a shared store is
    required before scaling to several processes."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float = 60.0, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and current - hits[0] >= window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(current)
            return True


limiter = SlidingWindowLimiter()


def client_address(request: Request) -> str:
    """The caller's address for rate limiting.

    Vercel's edge overwrites X-Forwarded-For with the real client address, so it is
    trusted there (VERCEL=1); elsewhere a proxy header could be forged, and uvicorn's
    --proxy-headers already resolves trusted proxies into request.client."""
    if os.getenv("VERCEL") == "1":
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int) -> Callable[[Request], None]:
    enabled = RATE_LIMIT_ENABLED and ENVIRONMENT != "test"

    def dependency(request: Request) -> None:
        if not enabled:
            return
        if not limiter.allow(f"{bucket}:{client_address(request)}", limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {bucket}; try again in a minute.",
                headers={"Retry-After": "60"},
            )

    return dependency


class RequestIdMiddleware:
    """Bind one safe correlation ID and echo it on every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = select_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        token = bind_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response
