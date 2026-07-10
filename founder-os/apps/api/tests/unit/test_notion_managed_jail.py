"""Managed-tree ledger jail (arch §4) — the Notion write-jail P0 battery.

Fake Notion via httpx.MockTransport records EVERY request; the core assertion
mirrors the Obsidian vault-hash snapshot: zero mutating calls to any id
outside ledger ∪ root.
"""
import json

import httpx
import pytest

from app.integrations.notion.client import (
    ManagedTreeViolation,
    NotionClient,
)

ROOT = "cccccccc-0000-0000-0000-000000000001"
LEDGED = "dddddddd-0000-0000-0000-0000000000aa"
OUTSIDE = "eeeeeeee-0000-0000-0000-0000000000ff"


class FakeNotion:
    """Minimal stateful fake: pages with parents, children, archived flags."""

    def __init__(self):
        self.pages = {
            ROOT: {"parent": {"type": "workspace", "workspace": True}, "archived": False},
            LEDGED: {"parent": {"type": "page_id", "page_id": ROOT}, "archived": False},
            OUTSIDE: {"parent": {"type": "workspace", "workspace": True}, "archived": False},
        }
        self.children = {LEDGED: [{"object": "block", "id": "old1", "type": "paragraph",
                                   "paragraph": {"rich_text": []}}]}
        self.requests: list[tuple[str, str]] = []
        self.created_seq = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.requests.append((method, path))
        if method == "GET" and path.startswith("/v1/pages/"):
            pid = path.rsplit("/", 1)[-1]
            page = self.pages.get(pid)
            if page is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"object": "page", "id": pid, **page})
        if method == "POST" and path == "/v1/pages":
            body = json.loads(request.content)
            self.created_seq += 1
            new_id = f"ffffffff-0000-0000-0000-00000000{self.created_seq:04x}"
            self.pages[new_id] = {"parent": body["parent"], "archived": False}
            return httpx.Response(200, json={"object": "page", "id": new_id})
        if method == "PATCH" and path.startswith("/v1/pages/"):
            pid = path.rsplit("/", 1)[-1]
            body = json.loads(request.content)
            if "archived" in body:
                self.pages[pid]["archived"] = body["archived"]
            return httpx.Response(200, json={"object": "page", "id": pid})
        if method == "GET" and "/blocks/" in path and path.endswith("/children"):
            pid = path.split("/")[3]
            return httpx.Response(200, json={"results": self.children.get(pid, []),
                                             "has_more": False, "next_cursor": None})
        if method == "PATCH" and "/blocks/" in path and path.endswith("/children"):
            return httpx.Response(200, json={"results": []})
        if method == "DELETE" and "/v1/blocks/" in path:
            return httpx.Response(200, json={})
        return httpx.Response(400, json={"message": "unexpected"})

    def mutations(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p in self.requests if m in ("POST", "PATCH", "DELETE")]


def make(fake: FakeNotion) -> NotionClient:
    async def fast_sleep(_s):
        return None

    return NotionClient("ntn_test", transport=httpx.MockTransport(fake.handler),
                        sleep=fast_sleep, max_rps=10_000)


BLOCKS = [{"object": "block", "type": "paragraph",
           "paragraph": {"rich_text": [{"type": "text", "text": {"content": "hi"}}]}}]


async def test_create_under_root_records_ledger():
    fake = FakeNotion()
    client = make(fake)
    ledger: dict = {}
    await client.write_managed_page(ledger, ROOT, "Goals.md", "Goals", BLOCKS)
    assert "Goals.md" in ledger and ledger["Goals.md"]["id"] in fake.pages
    parent = fake.pages[ledger["Goals.md"]["id"]]["parent"]
    assert parent.get("page_id") == ROOT


async def test_update_replaces_blocks_only_for_ledger_ids():
    fake = FakeNotion()
    client = make(fake)
    ledger = {"Tasks.md": {"id": LEDGED, "hash": "stale"}}
    await client.write_managed_page(ledger, ROOT, "Tasks.md", "Tasks", BLOCKS)
    # old child deleted, new appended — and ONLY on the ledgered id (or its
    # own child blocks, which the fake listed under it)
    assert ("DELETE", "/v1/blocks/old1") in fake.requests
    for m, p in fake.mutations():
        legal = LEDGED in p or ROOT in p or p == "/v1/blocks/old1"
        assert legal, (m, p)


async def test_parent_key_must_be_ledgered():
    fake = FakeNotion()
    client = make(fake)
    with pytest.raises(ManagedTreeViolation):
        await client.write_managed_page({}, ROOT, "Projects/X.md", "X", BLOCKS,
                                        parent_key="Projects")  # Projects not in ledger


async def test_founder_moved_page_recreated_never_followed():
    fake = FakeNotion()
    fake.pages[LEDGED]["parent"] = {"type": "page_id", "page_id": OUTSIDE}  # moved!
    client = make(fake)
    ledger = {"Tasks.md": {"id": LEDGED, "hash": "x"}}
    await client.write_managed_page(ledger, ROOT, "Tasks.md", "Tasks", BLOCKS)
    # ledger now points at a fresh page under root; the moved page was never mutated
    assert ledger["Tasks.md"]["id"] != LEDGED
    mutated_ids = [p for m, p in fake.mutations()]
    assert not any(LEDGED in p for p in mutated_ids)
    assert not any(OUTSIDE in p for p in mutated_ids)


async def test_prune_archives_only_ledger_orphans():
    fake = FakeNotion()
    # a legitimate managed page under root that fell out of the render set
    fake.pages["99999999-0000-0000-0000-000000000001"] = {
        "parent": {"type": "page_id", "page_id": ROOT}, "archived": False}
    client = make(fake)
    ledger = {"Tasks.md": {"id": LEDGED, "hash": "x"},
              "Old.md": {"id": "99999999-0000-0000-0000-000000000001", "hash": "y"}}
    archived = await client.prune_managed_pages(ledger, keep={"Tasks.md"},
                                                managed_root_id=ROOT)
    assert archived == ["Old.md"]
    assert fake.pages["99999999-0000-0000-0000-000000000001"]["archived"] is True
    assert "Old.md" not in ledger and "Tasks.md" in ledger
    assert not any(m == "DELETE" for m, _ in fake.mutations())


async def test_prune_drops_founder_moved_page_without_archiving():
    """N2 verify-or-drop: a ledgered page moved OUTSIDE the tree is dropped
    from the ledger and never mutated."""
    fake = FakeNotion()
    client = make(fake)
    ledger = {"Moved.md": {"id": OUTSIDE, "hash": "y"}}  # parent = workspace
    archived = await client.prune_managed_pages(ledger, keep=set(),
                                                managed_root_id=ROOT)
    assert archived == []
    assert fake.pages[OUTSIDE]["archived"] is False
    assert "Moved.md" not in ledger
    assert not any(OUTSIDE in p for m, p in fake.mutations())


async def test_zero_mutations_outside_ledger_and_root_across_session():
    """The fake-transport equivalent of the Obsidian whole-vault hash check."""
    fake = FakeNotion()
    client = make(fake)
    ledger = {"Tasks.md": {"id": LEDGED, "hash": "stale"}}
    await client.write_managed_page(ledger, ROOT, "Tasks.md", "Tasks", BLOCKS)
    await client.write_managed_page(ledger, ROOT, "Goals.md", "Goals", BLOCKS)
    await client.prune_managed_pages(ledger, keep={"Tasks.md", "Goals.md"}, managed_root_id=ROOT)
    allowed = {LEDGED, ROOT} | {v["id"] for v in ledger.values()}
    for method, path in fake.mutations():
        if path == "/v1/pages":      # create — parent checked in its own test
            continue
        pid = path.split("/")[3] if "/blocks/" in path and path.endswith("/children") \
            else path.rsplit("/", 1)[-1]
        if pid == "old1":            # child block of a ledgered page
            continue
        assert pid in allowed, (method, path)
