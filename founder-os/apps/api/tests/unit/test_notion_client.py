"""Notion transport client (arch §3.2): pacing, retries, pagination, pinned
version, typed token-free errors. All via httpx.MockTransport — no network.
"""
import json

import httpx
import pytest

from app.integrations.notion.client import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
)

TOKEN = "ntn_secret_test_token_value"


def make_client(handler, **kw):
    transport = httpx.MockTransport(handler)
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    clock = {"t": 0.0}

    def fake_monotonic() -> float:
        clock["t"] += 0.001  # time creeps forward a hair per call
        return clock["t"]

    client = NotionClient(
        TOKEN,
        transport=transport,
        sleep=fake_sleep,
        monotonic=fake_monotonic,
        **kw,
    )
    return client, sleeps, clock


async def test_pinned_version_and_auth_header_on_every_request():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [], "has_more": False, "next_cursor": None})

    client, _, _ = make_client(handler)
    await client.search_all()
    assert len(seen) >= 1
    for r in seen:
        assert r.headers["Notion-Version"] == "2022-06-28"
        assert r.headers["Authorization"] == f"Bearer {TOKEN}"


async def test_search_pagination_follows_next_cursor_at_100():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if body.get("start_cursor") is None:
            return httpx.Response(200, json={
                "results": [{"id": f"a{i}", "object": "page"} for i in range(100)],
                "has_more": True, "next_cursor": "cur2",
            })
        return httpx.Response(200, json={
            "results": [{"id": "b1", "object": "page"}],
            "has_more": False, "next_cursor": None,
        })

    client, _, _ = make_client(handler)
    results = await client.search_all()
    assert len(results) == 101
    assert calls[0]["page_size"] == 100
    assert calls[1]["start_cursor"] == "cur2"
    assert client.counters["search_pages"] == 2


async def test_429_honors_retry_after_then_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json={"id": "p1", "object": "page"})

    client, sleeps, _ = make_client(handler)
    page = await client.get_page("p1")
    assert page["id"] == "p1"
    assert 7.0 in sleeps
    assert client.counters["rate_limit_waits"] == 1


async def test_429_without_header_uses_exponential_backoff_then_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    client, sleeps, _ = make_client(handler, max_retries=3)
    with pytest.raises(NotionAPIError):
        await client.get_page("p1")
    backoffs = [s for s in sleeps if s >= 1.0]
    assert backoffs == [1.0, 2.0, 4.0]  # exponential fallback per retry


async def test_401_raises_auth_error_without_token_in_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    client, _, _ = make_client(handler)
    with pytest.raises(NotionAuthError) as exc:
        await client.get_page("p1")
    assert TOKEN not in str(exc.value)
    assert "401" in str(exc.value)


async def test_pacing_enforces_min_interval():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x", "object": "page"})

    client, sleeps, _ = make_client(handler, max_rps=2.0)  # min interval 0.5s
    await client.get_page("a")
    await client.get_page("b")
    # second request must have paced (clock barely moved between calls)
    assert any(0 < s <= 0.5 for s in sleeps)
    assert client.counters["api_requests"] == 2
