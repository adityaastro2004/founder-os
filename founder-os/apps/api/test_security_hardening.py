"""
Unit tests for the security-hardening pass (SSRF guard, security headers, rate
limiting). Pure-unit: no live server, DB, or Redis required.

Run standalone:
    python3 test_security_hardening.py
Or under pytest:
    pytest test_security_hardening.py
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crawler.ssrf import SSRFError, validate_public_url
from app.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware


# ── SSRF guard ───────────────────────────────────────────
BLOCKED_URLS = [
    "http://169.254.169.254/latest/meta-data/",  # EC2 metadata (link-local)
    "http://127.0.0.1/",                           # loopback
    "http://localhost/admin",                      # resolves to loopback
    "http://10.0.0.5/",                            # private
    "http://192.168.1.1/",                         # private
    "http://[::1]/",                               # IPv6 loopback
    "http://0.0.0.0/",                             # unspecified
    "ftp://example.com/",                          # disallowed scheme
    "file:///etc/passwd",                          # disallowed scheme
    "http:///nohost",                              # no host
]
ALLOWED_URLS = [
    "http://8.8.8.8/",       # public IP literal
    "https://1.1.1.1/",      # public IP literal
]


def test_ssrf_blocks_internal_and_bad_schemes():
    for url in BLOCKED_URLS:
        try:
            asyncio.run(validate_public_url(url))
        except SSRFError:
            continue
        raise AssertionError(f"validate_public_url should have blocked: {url}")


def test_ssrf_allows_public():
    for url in ALLOWED_URLS:
        asyncio.run(validate_public_url(url))  # must not raise


# ── Security headers ─────────────────────────────────────
def _headers_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_security_headers_present():
    resp = _headers_app().get("/ping")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "frame-ancestors 'none'" in resp.headers.get("Content-Security-Policy", "")
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")
    assert "server" not in {k.lower() for k in resp.headers}


# ── Rate limiting ────────────────────────────────────────
def _ratelimit_app(max_requests: int) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=max_requests,
        window_seconds=60,
        trust_proxy=True,
    )

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_rate_limit_trips_after_threshold():
    client = _ratelimit_app(max_requests=3)
    hdr = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(3):
        assert client.get("/ping", headers=hdr).status_code == 200
    blocked = client.get("/ping", headers=hdr)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") is not None


def test_rate_limit_is_per_client_ip():
    client = _ratelimit_app(max_requests=1)
    assert client.get("/ping", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 200
    # Different client IP → own bucket, not blocked.
    assert client.get("/ping", headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 200
    # Same first IP again → over its limit.
    assert client.get("/ping", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 429


if __name__ == "__main__":
    tests = [
        test_ssrf_blocks_internal_and_bad_schemes,
        test_ssrf_allows_public,
        test_security_headers_present,
        test_rate_limit_trips_after_threshold,
        test_rate_limit_is_per_client_ip,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
