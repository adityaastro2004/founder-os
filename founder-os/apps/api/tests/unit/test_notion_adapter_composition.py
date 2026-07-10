"""S7: NotionAdapter.observe_source composition over a fake workspace —
cursor/exclusion/tombstone/watermark behavior (MockTransport, no network)."""
import json

import httpx
import pytest

from app.integrations.notion.adapter import NotionAdapter

SRC = "11111111-2222-3333-4444-555555555555"
ROOT = "cccccccc-0000-0000-0000-000000000001"
MANAGED_CHILD = "cccccccc-0000-0000-0000-000000000002"   # engine page under root
NOTE = "bbbbbbbb-0000-0000-0000-000000000001"
TRASHED = "bbbbbbbb-0000-0000-0000-000000000003"


def page(pid, title, parent, edited, **flags):
    return {
        "object": "page", "id": pid, "last_edited_time": edited,
        "created_time": "2026-07-01T00:00:00.000Z",
        "archived": flags.get("archived", False), "in_trash": flags.get("in_trash", False),
        "parent": parent,
        "properties": {"title": {"type": "title", "title": [
            {"type": "text", "text": {"content": title}, "plain_text": title}]}},
    }


WORKSPACE = [
    page(ROOT, "Founder OS", {"type": "workspace", "workspace": True}, "2026-07-08T09:00:00.000Z"),
    page(MANAGED_CHILD, "Goals", {"type": "page_id", "page_id": ROOT}, "2026-07-08T09:30:00.000Z"),
    page(NOTE, "Substantive planning note", {"type": "workspace", "workspace": True},
         "2026-07-08T10:00:00.000Z"),
    page(TRASHED, "Old roadmap", {"type": "workspace", "workspace": True},
         "2026-07-08T08:00:00.000Z", in_trash=True, archived=True),
]


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/search":
        body = json.loads(request.content)
        assert body.get("sort", {}).get("timestamp") == "last_edited_time"  # S1 pin
        results = sorted(WORKSPACE, key=lambda o: o["last_edited_time"], reverse=True)
        return httpx.Response(200, json={"results": results, "has_more": False,
                                         "next_cursor": None})
    if "/blocks/" in path and path.endswith("/children"):
        return httpx.Response(200, json={"results": [
            {"object": "block", "id": "bl1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": "body text"},
                                          "plain_text": "body text of the planning note"}]}},
        ], "has_more": False, "next_cursor": None})
    if path.startswith("/v1/pages/"):
        pid = path.rsplit("/", 1)[-1]
        match = next((p for p in WORKSPACE if p["id"] == pid), None)
        return httpx.Response(200, json=match) if match else httpx.Response(404, json={})
    return httpx.Response(400, json={"message": f"unexpected {path}"})


@pytest.fixture()
def patched_client(monkeypatch):
    from app.integrations.notion import adapter as adapter_mod
    from app.integrations.notion.client import NotionClient

    def _factory(credentials, settings):
        async def fast_sleep(_s):
            return None
        return NotionClient(credentials["token"], transport=httpx.MockTransport(handler),
                            sleep=fast_sleep, max_rps=10_000)

    monkeypatch.setattr(adapter_mod, "_client_for", _factory)


CONFIG = {"managed_root_page_id": ROOT, "managed_pages": {}}


async def test_full_walk_composition(patched_client):
    a = NotionAdapter()
    events, cursor = await a.observe_source(
        CONFIG, SRC,
        credentials={"token": "ntn_fake"},
        sync_cursor={"managed_pages": {"Goals.md": {"id": MANAGED_CHILD, "hash": "x"}}},
        full_walk=True,
    )
    kinds = [e.kind for e in events]
    # managed subtree (root + its child) never observed
    assert not any(ROOT in e.external_id or MANAGED_CHILD in e.external_id for e in events)
    # the live note observed; the trashed page tombstoned
    assert "notion.note" in kinds and "notion.tombstone" in kinds
    tomb = next(e for e in events if e.kind == "notion.tombstone")
    assert TRASHED in tomb.external_id and tomb.payload["reason"] == "trashed"
    # watermark = max last_edited_time seen; full-walk timestamp set
    assert cursor["last_edited_watermark"] == "2026-07-08T10:00:00+00:00Z".replace("+00:00Z", "Z") \
        or cursor["last_edited_watermark"].startswith("2026-07-08T10:00:00")
    assert "last_full_walk_at" in cursor
    assert cursor["_counters"]["search_pages"] >= 1


async def test_incremental_uses_watermark_and_skips_old(patched_client):
    a = NotionAdapter()
    events, cursor = await a.observe_source(
        CONFIG, SRC,
        credentials={"token": "ntn_fake"},
        sync_cursor={
            "last_edited_watermark": "2026-07-08T09:45:00Z",
            "last_full_walk_at": "2026-07-08T09:45:00Z",
            "managed_pages": {},
        },
    )
    # only the NOTE (10:00) is newer than watermark−120s; no tombstones on
    # incremental (trash is invisible to incremental scans by design)
    assert [e.kind for e in events if e.kind != "notion.tombstone"] == ["notion.note"]
