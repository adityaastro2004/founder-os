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


class ManagedTreeViolation(Exception):
    """A mutation attempted outside the managed-page ledger ∪ root (P0)."""


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
            try:
                response = await self._client.request(
                    method, path, json=payload, headers=self._headers,
                )
            except httpx.HTTPError as exc:
                # S4: transport failures become typed errors (never raw httpx
                # messages in last_error) and retry like 5xx — mid-outbound
                # timeouts are routine against a remote API.
                if transient_retries >= 2:
                    raise NotionAPIError(
                        f"Notion transport error ({type(exc).__name__}) on {method} {path}",
                    ) from None
                transient_retries += 1
                await self._sleep(float(2 ** transient_retries))
                continue
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
                try:
                    # clamp: the header is remote-controlled (N1); HTTP-date or
                    # garbage falls back to exponential
                    wait = min(float(retry_after), 60.0) if retry_after else float(2 ** retries)
                except ValueError:
                    wait = float(2 ** retries)
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
                        *, counter: str | None = None,
                        max_items: int | None = None) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        while True:
            if max_items is not None and len(results) >= max_items:
                logger.warning("notion pagination stopped at cap %d on %s", max_items, path)
                return results[:max_items]
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

    async def search_all(self, query: str = "", *, max_objects: int | None = None) -> list[dict]:
        """Full enumeration, newest-first (S1): with the sort, the object cap
        keeps the NEWEST objects — recent edits can never be silently dropped."""
        payload: dict = {"sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        if query:
            payload["query"] = query
        return await self._paginate("POST", "/v1/search", payload,
                                    counter="search_pages", max_items=max_objects)

    async def search_since(self, cutoff_iso: str, *, max_objects: int | None = None) -> list[dict]:
        """Incremental primitive (arch §6/S1): newest-first pagination that
        STOPS once a page older than the cutoff appears — O(edits), not
        O(workspace)."""
        payload: dict = {"sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        results: list[dict] = []
        cursor: str | None = None
        while True:
            body = dict(payload)
            body["page_size"] = 100
            if cursor:
                body["start_cursor"] = cursor
            data = await self._request("POST", "/v1/search", body)
            self.counters["search_pages"] += 1
            batch = data.get("results", [])
            for obj in batch:
                if (obj.get("last_edited_time") or "9999") < cutoff_iso:
                    return results
                results.append(obj)
                if max_objects is not None and len(results) >= max_objects:
                    return results
            if not data.get("has_more") or not data.get("next_cursor"):
                return results
            cursor = data["next_cursor"]

    async def get_page(self, page_id: str) -> dict:
        return await self._request("GET", f"/v1/pages/{page_id}")

    async def get_database(self, database_id: str) -> dict:
        return await self._request("GET", f"/v1/databases/{database_id}")

    async def get_block_children(self, block_id: str) -> list[dict]:
        return await self._paginate("GET", f"/v1/blocks/{block_id}/children")

    async def get_blocks_recursive(self, block_id: str, *, depth: int = 3) -> list[dict]:
        """Flattened text-bearing blocks, recursing into children (arch §3.3,
        depth cap 3 — S8: nested to_dos/bullets under toggles must not vanish)."""
        blocks = await self.get_block_children(block_id)
        if depth <= 1:
            return blocks
        out: list[dict] = []
        for b in blocks:
            out.append(b)
            if b.get("has_children") and b.get("type") not in ("child_page", "child_database"):
                out.extend(await self.get_blocks_recursive(b["id"], depth=depth - 1))
        return out

    # ── managed-tree jailed write sinks (arch §4) ────────────────────────
    # Structural rule: these three methods are the ONLY Notion mutations in
    # the codebase. Ledger-primary jail: update/archive only ids the ledger
    # owns; create only under root ∪ ledger; parent GET-verified before every
    # update; founder-moved pages are dropped + recreated, NEVER followed.

    async def _raw_create_page(self, parent_id: str, title: str) -> str:
        data = await self._request("POST", "/v1/pages", {
            "parent": {"type": "page_id", "page_id": parent_id},
            "properties": {"title": {"title": [
                {"type": "text", "text": {"content": title}}]}},
        })
        return data["id"]

    async def _raw_replace_children(self, page_id: str, blocks: list[dict]) -> None:
        existing = await self._paginate("GET", f"/v1/blocks/{page_id}/children")
        for block in existing:
            await self._request("DELETE", f"/v1/blocks/{block['id']}")
        for i in range(0, len(blocks), 100):
            await self._request("PATCH", f"/v1/blocks/{page_id}/children",
                                {"children": blocks[i:i + 100]})

    async def write_managed_page(
        self,
        ledger: dict,
        managed_root_id: str,
        key: str,
        title: str,
        blocks: list[dict],
        *,
        parent_key: str | None = None,
        content_hash: str = "",
    ) -> str:
        """Create-or-update the managed page for `key`. Mutates `ledger`."""
        if parent_key is not None:
            parent_entry = (ledger or {}).get(parent_key)
            if not parent_entry:
                raise ManagedTreeViolation(
                    f"parent key {parent_key!r} is not in the managed ledger"
                )
            parent_id = parent_entry["id"]
        else:
            parent_id = managed_root_id

        entry = (ledger or {}).get(key)
        if entry:
            page_id = entry["id"]
            page = None
            try:
                page = await self.get_page(page_id)
            except NotionAPIError as exc:
                if exc.status != 404:
                    raise
            parent = (page or {}).get("parent") or {}
            legal_parents = {managed_root_id} | {v["id"] for v in ledger.values()}
            if (
                page is None
                or page.get("archived") or page.get("in_trash")
                or parent.get("page_id") not in legal_parents
            ):
                # Founder moved/trashed it: drop from ledger, log, recreate
                # under the root. NEVER follow a page outside the tree (§4.3).
                logger.warning(
                    "managed page for %r moved/gone — recreating under root", key,
                )
                del ledger[key]
                entry = None
            else:
                await self._raw_replace_children(page_id, blocks)
                ledger[key]["hash"] = content_hash
                return page_id

        page_id = await self._raw_create_page(parent_id, title)
        # Ledger append BEFORE any further ops (§4.1)
        ledger[key] = {"id": page_id, "hash": content_hash}
        if blocks:
            await self._raw_replace_children(page_id, blocks)
        return page_id

    async def prune_managed_pages(self, ledger: dict, *, keep: set[str],
                                  managed_root_id: str | None = None) -> list[str]:
        """Archive (never delete) ledger pages absent from the keep-set."""
        archived: list[str] = []
        legal_parents = {v["id"] for v in ledger.values()}
        if managed_root_id:
            legal_parents.add(managed_root_id)  # N2 fix: root children are ours
        for key in sorted(set(ledger) - set(keep)):
            page_id = ledger[key]["id"]
            # verify-or-drop (N2): never archive a page the founder moved out
            try:
                page = await self.get_page(page_id)
            except NotionAPIError as exc:
                if exc.status == 404:
                    del ledger[key]
                    continue
                raise
            if page.get("archived") or page.get("in_trash")                     or (page.get("parent") or {}).get("page_id") not in legal_parents:
                del ledger[key]  # moved/gone — not ours to touch anymore
                continue
            await self._request("PATCH", f"/v1/pages/{page_id}", {"archived": True})
            del ledger[key]
            archived.append(key)
        return archived
