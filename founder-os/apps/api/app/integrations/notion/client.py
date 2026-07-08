"""Notion HTTP transport (arch §3.2). The ONLY module that talks to the API.

Sequential requests with a min-interval pacer (provably ≤ max_rps average),
429 retry honoring Retry-After (exponential fallback), cursor pagination at
page_size=100, pinned Notion-Version. Errors are typed and NEVER contain the
token (standards/security.md).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.notion.com"
DEFAULT_API_VERSION = "2022-06-28"


class NotionAPIError(Exception):
    """Non-auth API failure. Message carries method/path/status only."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NotionAuthError(NotionAPIError):
    """401/403 — token invalid, revoked, or page not shared."""


class NotionClient:
    def __init__(
        self,
        token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        max_rps: float = 3.0,
        max_retries: int = 5,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": api_version,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, timeout=timeout_s, transport=transport,
        )
        self._min_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._max_retries = max_retries
        self._sleep = sleep or asyncio.sleep
        self._monotonic = monotonic or time.monotonic
        self._last_request_at: float | None = None
        self.counters: dict[str, int] = {
            "api_requests": 0, "rate_limit_waits": 0, "search_pages": 0,
        }

    async def close(self) -> None:
        await self._client.aclose()

    # ── core request path ────────────────────────────────────────────────

    async def _pace(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._monotonic() - self._last_request_at
            wait = self._min_interval - elapsed
            if wait > 0:
                await self._sleep(wait)
        self._last_request_at = self._monotonic()

    async def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        retries = 0
        transient_retries = 0
        while True:
            await self._pace()
            self.counters["api_requests"] += 1
            response = await self._client.request(
                method, path, json=payload, headers=self._headers,
            )
            if response.status_code in (401, 403):
                raise NotionAuthError(
                    f"Notion auth failed ({response.status_code}) on {method} {path} "
                    "— token invalid/revoked or resource not shared with the integration",
                    status=response.status_code,
                )
            if response.status_code == 429:
                if retries >= self._max_retries:
                    raise NotionAPIError(
                        f"Notion rate limit persisted after {retries} retries on {method} {path}",
                        status=429,
                    )
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else float(2 ** retries)
                self.counters["rate_limit_waits"] += 1
                retries += 1
                await self._sleep(wait)
                continue
            if response.status_code in (502, 503, 504):
                if transient_retries >= 2:
                    raise NotionAPIError(
                        f"Notion {response.status_code} persisted on {method} {path}",
                        status=response.status_code,
                    )
                transient_retries += 1
                await self._sleep(float(2 ** transient_retries))
                continue
            if response.status_code >= 400:
                raise NotionAPIError(
                    f"Notion API error {response.status_code} on {method} {path}",
                    status=response.status_code,
                )
            return response.json()

    async def _paginate(self, method: str, path: str, payload: dict | None = None,
                        *, counter: str | None = None) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        while True:
            body = dict(payload or {})
            body["page_size"] = 100
            if cursor:
                body["start_cursor"] = cursor
            if method == "GET":
                # blocks/children paginates via query params
                q = f"?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
                data = await self._request("GET", path + q)
            else:
                data = await self._request(method, path, body)
            if counter:
                self.counters[counter] = self.counters.get(counter, 0) + 1
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            cursor = data.get("next_cursor")
            if not cursor:
                return results

    # ── read endpoints (arch §3.2 complete list) ─────────────────────────

    async def search_all(self, query: str = "") -> list[dict]:
        payload: dict = {"query": query} if query else {}
        return await self._paginate("POST", "/v1/search", payload, counter="search_pages")

    async def get_page(self, page_id: str) -> dict:
        return await self._request("GET", f"/v1/pages/{page_id}")

    async def get_database(self, database_id: str) -> dict:
        return await self._request("GET", f"/v1/databases/{database_id}")

    async def get_block_children(self, block_id: str) -> list[dict]:
        return await self._paginate("GET", f"/v1/blocks/{block_id}/children")
