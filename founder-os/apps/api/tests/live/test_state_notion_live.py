"""Phase 2 live E2E (arch §10.2): real Notion workspace → state → managed tree.

GATING: skips without NOTION_TEST_TOKEN / NOTION_TEST_ROOT_PAGE_ID — but task
015's QA gate record REQUIRES a recorded real run; a skip does NOT satisfy it.

Founder setup (once): notion.so/my-integrations → internal integration with
content capabilities (read/update/insert) → create a "Founder OS Test" page →
share it (and any seed pages) with the integration → put in apps/api/.env:
    NOTION_TEST_TOKEN=ntn_...
    NOTION_TEST_ROOT_PAGE_ID=<32-hex page id from the page URL>
The suite SEEDS its own workspace content under a `E2E Seed` page beside the
managed tree on first run (idempotent), including a tasks database and enough
filler pages to force search pagination (arch AC).
"""
import os
import pathlib
import time
import uuid as uuidlib

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = "http://localhost:8000"
SYNC_WAIT_S = 1500  # first Notion walk is paced at ~3 req/s (arch §9)


def _env(key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip() or None
    return None


TOKEN = _env("NOTION_TEST_TOKEN")
ROOT = _env("NOTION_TEST_ROOT_PAGE_ID")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not TOKEN or not ROOT,
        reason=(
            "NOTION_TEST_TOKEN / NOTION_TEST_ROOT_PAGE_ID not set — SKIPPED, but "
            "task 015's gate record REQUIRES a recorded real run; a skip does NOT "
            "satisfy the gate."
        ),
    ),
]

NOTION_VERSION = "2022-06-28"
FILLER_COUNT = 105  # forces search_pages >= 2 (pagination AC)


class Notion:
    """Independent test-side client (NOT the app's) for seeding + verification."""

    def __init__(self, token: str):
        self.c = httpx.Client(
            base_url="https://api.notion.com", timeout=30,
            headers={"Authorization": f"Bearer {token}",
                     "Notion-Version": NOTION_VERSION,
                     "Content-Type": "application/json"},
        )

    def search_all(self) -> list[dict]:
        out, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self.c.post("/v1/search", json=body).json()
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                return out
            cursor = data["next_cursor"]
            time.sleep(0.35)

    def create_page(self, parent_id: str, title: str, children: list | None = None) -> dict:
        payload = {"parent": {"type": "page_id", "page_id": parent_id},
                   "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}}}
        if children:
            payload["children"] = children
        r = self.c.post("/v1/pages", json=payload)
        r.raise_for_status()
        time.sleep(0.35)
        return r.json()

    def create_database(self, parent_id: str, title: str, props: dict) -> dict:
        r = self.c.post("/v1/databases", json={
            "parent": {"type": "page_id", "page_id": parent_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": {"Name": {"title": {}}, **props},
        })
        r.raise_for_status()
        time.sleep(0.35)
        return r.json()

    def create_row(self, db_id: str, name: str, props: dict | None = None) -> dict:
        r = self.c.post("/v1/pages", json={
            "parent": {"type": "database_id", "database_id": db_id},
            "properties": {"Name": {"title": [{"type": "text", "text": {"content": name}}]},
                           **(props or {})},
        })
        r.raise_for_status()
        time.sleep(0.35)
        return r.json()

    def patch_page(self, page_id: str, payload: dict) -> dict:
        r = self.c.patch(f"/v1/pages/{page_id}", json=payload)
        r.raise_for_status()
        time.sleep(0.35)
        return r.json()

    def get_page(self, page_id: str) -> dict:
        return self.c.get(f"/v1/pages/{page_id}").json()

    def children(self, page_id: str) -> list[dict]:
        return self.c.get(f"/v1/blocks/{page_id}/children?page_size=100").json().get("results", [])


def seed_workspace(n: Notion, root: str) -> dict:
    """Idempotent: everything under one `E2E Seed` child page of the root."""
    for page in n.search_all():
        if page.get("object") == "page":
            title_prop = next((p for p in page.get("properties", {}).values()
                               if p.get("type") == "title"), {})
            title = "".join(t.get("plain_text", "") for t in title_prop.get("title", []))
            if title == "E2E Seed" and (page.get("parent") or {}).get("page_id", "").replace("-", "") == root.replace("-", ""):
                # already seeded — locate the tasks db + note page
                seed_id = page["id"]
                dbs = [c for c in n.children(seed_id) if c["type"] == "child_database"]
                notes = [c for c in n.children(seed_id) if c["type"] == "child_page"]
                return {"seed_id": seed_id, "reused": True, "dbs": dbs, "notes": notes}

    seed = n.create_page(root, "E2E Seed")
    seed_id = seed["id"]
    goals_db = n.create_database(seed_id, "Goals", {})
    n.create_row(goals_db["id"], "Reach $10k MRR")
    projects_db = n.create_database(seed_id, "Projects", {})
    n.create_row(projects_db["id"], "Launch v2")
    tasks_db = n.create_database(seed_id, "Sprint Tasks", {
        "Done": {"checkbox": {}}, "Due": {"date": {}},
    })
    n.create_row(tasks_db["id"], "Write the changelog", {"Done": {"checkbox": False}})
    n.create_row(tasks_db["id"], "Record the demo", {"Done": {"checkbox": False}})
    n.create_row(tasks_db["id"], "Cut release branch", {"Done": {"checkbox": True}})
    decisions_db = n.create_database(seed_id, "Decisions", {})
    n.create_row(decisions_db["id"], "Price pro tier at $49")
    n.create_page(seed_id, "Community onboarding idea", children=[
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
            {"type": "text", "text": {"content":
                "Users who join via the community Slack activate at a much higher "
                "rate. Build a guided onboarding flow pairing each new signup with "
                "an existing community member during their first week."}}]}},
    ])
    n.create_page(seed_id, "Community-led onboarding concept", children=[
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
            {"type": "text", "text": {"content":
                "New users joining through the community Slack activate at a far "
                "higher rate. Build a guided onboarding flow that pairs signups "
                "with community members in week one."}}]}},
    ])
    n.create_page(seed_id, "Untitled")  # gate-reject candidate (empty)
    bulk = n.create_page(seed_id, "Bulk")
    for i in range(FILLER_COUNT):
        n.create_page(bulk["id"], f"Filler {i:03d}")
    return {"seed_id": seed_id, "reused": False}


def trigger_and_wait(c: httpx.Client, source_id: str, *, full_walk: bool = False,
                     direction: str = "both") -> dict:
    prev = c.get(f"/api/state/sources/{source_id}").json()["last_synced_at"]
    r = c.post(f"/api/state/sources/{source_id}/sync",
               json={"direction": direction, "full_walk": full_walk})
    assert r.status_code == 202, r.text[:300]
    deadline = time.time() + SYNC_WAIT_S
    while time.time() < deadline:
        src = c.get(f"/api/state/sources/{source_id}").json()
        if src["status"] == "error":
            pytest.fail(f"sync errored: {src['last_error']}")
        if src["status"] == "active" and src["last_synced_at"] != prev and src["last_sync_report"]:
            return src["last_sync_report"]
        time.sleep(10)
    pytest.fail(f"no fresh report within {SYNC_WAIT_S}s")


def test_notion_end_to_end():
    user = f"p2-e2e-{uuidlib.uuid4().hex[:8]}"
    api = httpx.Client(base_url=BASE, timeout=120, headers={"x-test-user": user})
    n = Notion(TOKEN)

    seed_workspace(n, ROOT)

    # ── register (token in body only) ───────────────────────────────────
    r = api.post("/api/state/sources", json={
        "type": "notion", "name": "e2e-workspace",
        "config": {"managed_root_page_id": ROOT, "token": TOKEN},
    })
    assert r.status_code == 201, r.text[:400]
    body = r.json()
    source_id = body["id"]
    assert TOKEN not in r.text, "token leaked into the registration response"
    assert "token" not in body["config"]

    # ── sync #1 (first = full walk) ──────────────────────────────────────
    report1 = trigger_and_wait(api, source_id)
    assert report1["errors"] == 0, report1
    assert report1["created"] > 0
    assert report1.get("search_pages", 0) >= 2, f"pagination AC: {report1}"

    ents = api.get("/api/state/entities", params={"limit": 100}).json()
    by_type: dict = {}
    titles = set()
    for e in ents["entities"]:
        by_type.setdefault(e["entity_type"], []).append(e)
        titles.add(e["title"])
        assert e["source"] == "observed"
        assert e["source_id"] == source_id
    for etype, expected in (("goal", "Reach $10k MRR"), ("project", "Launch v2"),
                            ("task", "Write the changelog"),
                            ("decision", "Price pro tier at $49")):
        assert expected in {x["title"] for x in by_type.get(etype, [])}, (etype, titles)
    # structured property signal (US-4): status came from the checkbox property
    changelog = next(x for x in by_type["task"] if x["title"] == "Write the changelog")
    assert changelog["status"] == "open"
    # gate: the untitled empty page must not exist
    assert "Untitled" not in titles
    # dedup: near-duplicate onboarding notes merged
    onboarding = [t for t in titles if "onboarding" in t.casefold()]
    assert len(onboarding) == 1, onboarding

    # managed tree rendered under the root
    root_children = {c.get("child_page", {}).get("title") for c in n.children(ROOT)
                     if c["type"] == "child_page"}
    assert {"Goals", "Tasks", "Decisions"} <= {t.removesuffix(".md") for t in root_children if t}

    # ── safety snapshot (P0): non-managed pages untouched by sync #2 ─────
    managed_ids = set()
    src_row = api.get(f"/api/state/sources/{source_id}").json()
    snapshot = {}
    for page in n.search_all():
        pid = page["id"]
        snapshot[pid] = page.get("last_edited_time")
    report2 = trigger_and_wait(api, source_id)
    assert report2["created"] == 0, f"re-sync created entities: {report2}"
    assert report2["unchanged"] == report2["observed"], report2
    assert report2.get("pages_skipped_unchanged", 0) > 0, report2  # churn-free
    after = {p["id"]: p.get("last_edited_time") for p in n.search_all()}
    for pid, ts in snapshot.items():
        assert after.get(pid) == ts, f"P0: non-managed page {pid} was modified"

    # ── toggle the checkbox → same entity flips ──────────────────────────
    row = next(p for p in n.search_all()
               if p.get("object") == "page"
               and any(t.get("plain_text") == "Write the changelog"
                       for pr in p.get("properties", {}).values() if pr.get("type") == "title"
                       for t in pr.get("title", [])))
    n.patch_page(row["id"], {"properties": {"Done": {"checkbox": True}}})
    report3 = trigger_and_wait(api, source_id)
    assert report3["created"] == 0, report3
    detail = api.get(f"/api/state/entities/{changelog['id']}").json()
    assert detail["status"] == "done", "checkbox toggle did not flip the same entity"

    # ── trash a note → full walk → archived, never resurrected ───────────
    note_page = next(p for p in n.search_all()
                     if p.get("object") == "page"
                     and any(t.get("plain_text") == "Community onboarding idea"
                             for pr in p.get("properties", {}).values() if pr.get("type") == "title"
                             for t in pr.get("title", [])))
    n.patch_page(note_page["id"], {"archived": True})
    report4 = trigger_and_wait(api, source_id, full_walk=True)
    assert report4.get("archived", 0) >= 1, report4
    listed = api.get("/api/state/entities", params={"limit": 100}).json()
    assert "Community onboarding idea" not in {e["title"] for e in listed["entities"]}
    archived_listed = api.get("/api/state/entities",
                              params={"limit": 100, "include_archived": True}).json()
    assert any("onboarding" in e["title"].casefold() and e["status"] in ("archived", "open", "active")
               for e in archived_listed["entities"])

    # ── token hygiene ────────────────────────────────────────────────────
    for path in (f"/api/state/sources/{source_id}", "/api/state/sources"):
        assert TOKEN not in api.get(path).text, f"token leaked in {path}"
    logs_dir = pathlib.Path(__file__).resolve().parents[4] / "logs"
    for logname in ("api.log", "celery.log"):
        f = logs_dir / logname
        if f.exists():
            assert TOKEN not in f.read_text(errors="replace"), f"token leaked in {logname}"
