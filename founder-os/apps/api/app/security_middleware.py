"""
Application-layer security middleware for the Founder OS API.

Two concerns handled here so they hold regardless of the reverse-proxy topology
(systemd uvicorn, docker+Caddy, or direct):

  * ``SecurityHeadersMiddleware`` — sets baseline hardening headers on every
    response: clickjacking defense (X-Frame-Options + CSP frame-ancestors),
    MIME-sniffing defense (X-Content-Type-Options), referrer scoping, HSTS, and
    a restrictive Permissions-Policy. The API serves JSON only, so a strict
    ``default-src 'none'`` CSP is safe here.

  * ``RateLimitMiddleware`` — a lightweight, in-process fixed-window limiter to
    blunt request-flood abuse of expensive endpoints (LLM/research/generate).
    This is app-layer abuse mitigation, NOT a substitute for edge/WAF DDoS
    protection. Fails OPEN: any internal error lets the request through rather
    than causing an outage.

See standards/security.md.
"""

from __future__ import annotations

import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# API responses are JSON/data, never framed HTML — lock the browser down hard.
_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # Browsers ignore HSTS over plain http, so it is safe to always send.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # Strip the framework's Server banner (version disclosure).
        if "server" in response.headers:
            del response.headers["server"]
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process fixed-window rate limiter keyed on the client IP.

    The deployment sits behind a trusted front proxy (Vercel rewrite / Caddy),
    which collapses many clients onto a few egress IPs; when ``trust_proxy`` is
    set the original client is taken from the left-most ``X-Forwarded-For`` hop
    so users are limited individually rather than as one shared bucket.
    """

    def __init__(
        self,
        app,
        *,
        max_requests: int,
        window_seconds: int,
        trust_proxy: bool = True,
        exempt_paths: frozenset[str] = frozenset({"/"}),
    ):
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._trust_proxy = trust_proxy
        self._exempt = exempt_paths
        self._hits: dict[str, deque[float]] = {}
        self._last_prune = 0.0

    def _client_key(self, request: Request) -> str:
        if self._trust_proxy:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                # Left-most entry is the original client per the trusted proxy.
                first = xff.split(",")[0].strip()
                if first:
                    return first
        client = request.client
        return client.host if client else "unknown"

    def _prune(self, now: float) -> None:
        # Drop empty/stale buckets occasionally so memory stays bounded.
        cutoff = now - self._window
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] < cutoff]
        for k in stale:
            self._hits.pop(k, None)
        self._last_prune = now

    async def dispatch(self, request: Request, call_next):
        try:
            if request.method == "OPTIONS" or request.url.path in self._exempt:
                return await call_next(request)

            now = time.monotonic()
            key = self._client_key(request)
            dq = self._hits.setdefault(key, deque())

            cutoff = now - self._window
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= self._max:
                retry_after = max(1, int(self._window - (now - dq[0])))
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Slow down and try again."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

            dq.append(now)
            if now - self._last_prune > self._window:
                self._prune(now)
        except Exception:
            # Fail open — a limiter bug must never take the API down.
            return await call_next(request)

        return await call_next(request)
