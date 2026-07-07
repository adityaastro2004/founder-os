"""Phase 1 live E2E (arch §9): vault → state → managed folder, full loop.

Proves task 011's acceptance criteria against the running stack (:8000 +
Celery worker + Postgres + Redis + Ollama): observe, write-gate, dedup,
idempotent re-sync, checkbox toggle → same-entity status flip, managed-folder
render + non-managed hash invariance, state:// RAG mirror without dupes.

LLM-dependent behavior is asserted structurally only (testing.md rule 4);
timeouts are provider-aware (rule 5 — embedding + judge run on local Ollama).
"""
import hashlib
import pathlib
import shutil
import tempfile
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = "http://localhost:8000"
FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "obsidian_vault"
SYNC_WAIT_S = 600  # first sync embeds every entity on local Ollama — be generous


def vault_hashes(vault: pathlib.Path, exclude_top: str) -> dict:
    out = {}
    for p in sorted(vault.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(vault)
        if rel.parts[0] == exclude_top:
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def trigger_and_wait(c: httpx.Client, source_id: str, direction: str = "both") -> dict:
    """Trigger a sync and wait for a FRESH report.

    last_synced_at must ADVANCE past its pre-trigger value — polling for a
    truthy report returns the PREVIOUS sync's report instantly (that stale
    read masked the idempotency check entirely in an earlier run and let
    pytest tear down the temp vault under the still-queued task).
    """
    prev = c.get(f"/api/state/sources/{source_id}").json()["last_synced_at"]
    r = c.post(f"/api/state/sources/{source_id}/sync", json={"direction": direction})
    assert r.status_code == 202, r.text[:300]
    deadline = time.time() + SYNC_WAIT_S
    while time.time() < deadline:
        src = c.get(f"/api/state/sources/{source_id}").json()
        if src["status"] == "error":
            pytest.fail(f"sync errored: {src['last_error']}")
        if src["status"] == "active" and src["last_synced_at"] != prev \
                and src["last_sync_report"]:
            return src["last_sync_report"]
        time.sleep(3)
    pytest.fail(f"sync did not produce a fresh report within {SYNC_WAIT_S}s")


def test_obsidian_end_to_end():
    user = f"p1-e2e-{uuid.uuid4().hex[:8]}"
    c = httpx.Client(base_url=BASE, timeout=120, headers={"x-test-user": user})

    with tempfile.TemporaryDirectory(prefix="fos-vault-") as tmp:
        vault = pathlib.Path(tmp) / "vault"
        shutil.copytree(FIXTURE, vault)
        before_hashes = vault_hashes(vault, exclude_top="FounderOS")

        # ── register ────────────────────────────────────────────────────
        r = c.post("/api/state/sources", json={
            "type": "obsidian", "name": "e2e-vault",
            "config": {"vault_path": str(vault)},
        })
        assert r.status_code == 201, r.text[:300]
        source_id = r.json()["id"]

        # ── sync #1 ─────────────────────────────────────────────────────
        report1 = trigger_and_wait(c, source_id)
        assert report1["observed"] > 0 and report1["created"] > 0
        assert report1["errors"] == 0, report1

        # entities + provenance (US-1, US-4)
        ents = c.get("/api/state/entities", params={"limit": 100}).json()
        by_type = {}
        for e in ents["entities"]:
            by_type.setdefault(e["entity_type"], []).append(e)
            assert e["source"] == "observed"
            assert e["source_id"] == source_id
            assert 0 < e["confidence"] <= 0.99
            assert e["last_asserted_at"]
        assert "goal" in by_type and "project" in by_type
        assert "task" in by_type and "decision" in by_type
        titles = {e["title"] for e in ents["entities"]}
        assert "Reach $10k MRR" in titles and "Launch v2" in titles
        # write-gate: the empty 'todo' stub must NOT exist (US-3)
        assert "todo" not in {t.casefold() for t in titles}
        # dedup: Idea + Idea copy (near-duplicate bodies) → merged, not two notes
        idea_notes = [t for t in titles if "onboarding" in t.casefold()]
        assert len(idea_notes) == 1, f"dedup failed: {idea_notes}"
        gated_report_ok = report1["gated"] >= 1
        assert gated_report_ok, report1

        # relations (part_of task→project present)
        rels = c.get("/api/state/relations", params={"relation_type": "part_of"}).json()
        assert rels["total"] >= 1

        # managed folder rendered (US-2) + safety: nothing else touched
        managed = vault / "FounderOS"
        assert (managed / "Goals.md").exists() and (managed / "Tasks.md").exists()
        assert (managed / "Decisions.md").exists()
        assert "Reach $10k MRR" in (managed / "Goals.md").read_text()
        assert vault_hashes(vault, exclude_top="FounderOS") == before_hashes, \
            "P0: a non-managed vault file was modified"

        # RAG mirror (S4): state:// rows exist with the mirror category, and
        # they carry FULL bodies (B1) — assert on below-the-fold content.
        items = c.get("/api/knowledge/items", params={"category": "state_mirror"}).json()
        mirror_items = [i for i in items if (i.get("source_url") or "").startswith("state://")]
        assert mirror_items, "no state:// mirrored knowledge items"
        mirror_count_1 = len(mirror_items)
        search = c.post("/api/knowledge/search", json={
            "query": "community onboarding activation", "search_type": "semantic", "limit": 5,
        }).json()
        assert search["total_results"] >= 1

        # mentions edges exist (S1: note —mentions→ goal/project)
        mrels = c.get("/api/state/relations", params={"relation_type": "mentions"}).json()
        assert mrels["total"] >= 1, "note→goal/project mentions edges missing"

        entity_count_1 = ents["total"]

        # ── sync #2: idempotency (US-1 AC3) ─────────────────────────────
        report2 = trigger_and_wait(c, source_id)
        assert report2["created"] == 0, f"re-sync created entities: {report2}"
        assert report2["unchanged"] == report2["observed"], report2
        ents2 = c.get("/api/state/entities", params={"limit": 100}).json()
        assert ents2["total"] == entity_count_1
        # RAG mirror idempotency (S4): unchanged content → zero re-mirrored rows
        items2 = c.get("/api/knowledge/items", params={"category": "state_mirror"}).json()
        mirror_count_2 = len([i for i in items2 if (i.get("source_url") or "").startswith("state://")])
        assert mirror_count_2 == mirror_count_1, "re-sync duplicated mirrored knowledge"

        # ── checkbox toggle → same entity flips status ──────────────────
        launch = vault / "Projects" / "Launch v2.md"
        task_entity_before = next(
            e for e in ents2["entities"]
            if e["entity_type"] == "task" and e["title"] == "Write the changelog for v2"
        )
        assert task_entity_before["status"] == "open"
        launch.write_text(launch.read_text().replace(
            "- [ ] Write the changelog for v2", "- [x] Write the changelog for v2",
        ))
        report3 = trigger_and_wait(c, source_id)
        assert report3["created"] == 0, f"toggle must not create entities: {report3}"
        assert report3["updated"] >= 1, report3

        detail = c.get(f"/api/state/entities/{task_entity_before['id']}").json()
        assert detail["status"] == "done", "checkbox toggle did not flip the same entity"

        # rendered Tasks.md reflects the flip
        assert "- [x] Write the changelog for v2" in (vault / "FounderOS" / "Tasks.md").read_text()

        # overlap guard: rapid-fire second trigger while first holds the lock → 409
        prev = c.get(f"/api/state/sources/{source_id}").json()["last_synced_at"]
        first = c.post(f"/api/state/sources/{source_id}/sync", json={})
        second = c.post(f"/api/state/sources/{source_id}/sync", json={})
        assert first.status_code == 202
        assert second.status_code == 409, second.text[:200]
        # wait for the first to finish so teardown doesn't yank the vault from under it
        deadline = time.time() + SYNC_WAIT_S
        while time.time() < deadline:
            src = c.get(f"/api/state/sources/{source_id}").json()
            if src["status"] == "active" and src["last_synced_at"] != prev:
                break
            time.sleep(3)
