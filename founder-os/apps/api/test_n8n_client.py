"""
Unit tests for the n8n REST client (app/workflows/n8n_client.py) — ADR-008 Track C1.

Standalone, runnable, no live n8n (httpx MockTransport — per standards/testing.md):
    cd founder-os/apps/api && source .venv/bin/activate && python3 test_n8n_client.py

Covers:
  - request construction: correct method/path, X-N8N-API-KEY header sent
  - create_workflow returns the n8n workflow id (top-level and nested shapes)
  - activate/deactivate hit the right endpoints
  - error mapping: 401/403 → N8nAuthError, 404 → N8nNotFoundError,
    5xx → N8nUnavailableError, transport failure → N8nUnavailableError
  - the API key never appears in a raised error message (C-5)
"""

import asyncio
import sys

import httpx

from app.workflows.n8n_client import (
    N8nAuthError,
    N8nClient,
    N8nError,
    N8nNotFoundError,
    N8nUnavailableError,
)

_passed = 0
_failed = 0

API_KEY = "n8n-secret-api-key-abcdef-0123456789"
BASE = "http://localhost:5678"


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


def _client_with_handler(handler) -> N8nClient:
    """
    Build an N8nClient whose underlying httpx.AsyncClient uses a MockTransport.
    We construct the real N8nClient (so header/auth wiring is exercised), then
    swap the transport on the lazily-created httpx client.
    """
    client = N8nClient(base_url=BASE, api_key=API_KEY)
    # Force-create the underlying httpx client, then replace its transport.
    inner = client._http  # APIClient
    # Disable retry sleeps in tests — we assert error MAPPING, not backoff timing
    # (backoff/circuit-breaker behavior is covered by api_client's own tests).
    inner.retry_config.max_retries = 0

    transport = httpx.MockTransport(handler)
    inner._client = httpx.AsyncClient(
        base_url=BASE,
        headers=inner.default_headers,
        transport=transport,
    )
    return client


async def run() -> None:
    # ---- request construction + header ----
    print("== request construction: method, path, API-key header ==")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["api_key_header"] = request.headers.get("X-N8N-API-KEY")
        return httpx.Response(200, json={"id": "n8n-wf-77", "name": "x"})

    client = _client_with_handler(handler)
    wf_id = await client.create_workflow({"name": "x", "nodes": [], "connections": {}})
    await client.aclose()

    check("create_workflow POSTs", captured.get("method") == "POST")
    check("create_workflow hits /api/v1/workflows",
          captured.get("path") == "/api/v1/workflows", detail=captured.get("path"))
    check("X-N8N-API-KEY header is sent with the configured key",
          captured.get("api_key_header") == API_KEY)
    check("create_workflow returns the n8n id (top-level shape)",
          wf_id == "n8n-wf-77", detail=str(wf_id))

    # ---- nested {data:{id}} response shape ----
    print("== create_workflow handles nested {data:{id}} shape ==")
    client = _client_with_handler(
        lambda r: httpx.Response(200, json={"data": {"id": "nested-99"}})
    )
    wf_id = await client.create_workflow({"name": "x"})
    await client.aclose()
    check("nested id extracted", wf_id == "nested-99", detail=str(wf_id))

    # ---- activate / deactivate endpoints ----
    print("== activate / deactivate hit the right endpoints ==")
    paths = []

    def act_handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"id": "n8n-wf-77", "active": True})

    client = _client_with_handler(act_handler)
    await client.activate_workflow("n8n-wf-77")
    await client.deactivate_workflow("n8n-wf-77")
    await client.aclose()
    check("activate hits /workflows/{id}/activate",
          "/api/v1/workflows/n8n-wf-77/activate" in paths, detail=str(paths))
    check("deactivate hits /workflows/{id}/deactivate",
          "/api/v1/workflows/n8n-wf-77/deactivate" in paths, detail=str(paths))

    # ---- error mapping ----
    print("== error mapping by status code ==")

    async def expect_error(status, exc_type, name):
        c = _client_with_handler(
            lambda r, _s=status: httpx.Response(_s, json={"message": "nope"})
        )
        raised = None
        try:
            await c.health()
        except Exception as e:  # noqa: BLE001
            raised = e
        await c.aclose()
        check(name, isinstance(raised, exc_type),
              detail=f"got {type(raised).__name__ if raised else None}")
        return raised

    await expect_error(401, N8nAuthError, "401 → N8nAuthError")
    await expect_error(403, N8nAuthError, "403 → N8nAuthError")
    await expect_error(404, N8nNotFoundError, "404 → N8nNotFoundError")
    await expect_error(500, N8nUnavailableError, "500 → N8nUnavailableError")
    await expect_error(503, N8nUnavailableError, "503 → N8nUnavailableError")
    err_422 = await expect_error(422, N8nError, "422 → generic N8nError")

    # ---- transport failure → unavailable ----
    print("== transport failure → N8nUnavailableError ==")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    c = _client_with_handler(boom)
    raised = None
    try:
        await c.health()
    except Exception as e:  # noqa: BLE001
        raised = e
    await c.aclose()
    check("connection error → N8nUnavailableError",
          isinstance(raised, N8nUnavailableError),
          detail=f"got {type(raised).__name__ if raised else None}")

    # ---- secret never in error message (C-5) ----
    print("== API key never leaks into a raised error message (C-5) ==")
    leaked = []
    for e in [err_422, raised]:
        if e and API_KEY in str(e):
            leaked.append(str(e))
    check("API key absent from all raised error messages", not leaked,
          detail=str(leaked))

    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    asyncio.run(run())
