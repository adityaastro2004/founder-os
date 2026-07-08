"""Reconciler pure parts (arch §2.2): content-hash canonicalization + candidate shaping.
DB-bound pipeline behavior is proven by the live E2E (tests/live/test_state_obsidian_live.py).
"""
from datetime import datetime, timezone

from app.integrations.base import ObservedEvent
from app.state.reconciler import SyncCounters, canonical_content_hash, _as_candidate

NOW = datetime(2026, 7, 6, tzinfo=timezone.utc)


def test_content_hash_stable_across_key_order():
    a = canonical_content_hash({"b": 1, "a": {"y": 2, "x": 3}})
    b = canonical_content_hash({"a": {"x": 3, "y": 2}, "b": 1})
    assert a == b and len(a) == 64


def test_content_hash_changes_on_value_change():
    a = canonical_content_hash({"title": "x", "status": "open"})
    b = canonical_content_hash({"title": "x", "status": "done"})
    assert a != b


def test_content_hash_serializes_nonjson_types():
    assert canonical_content_hash({"at": NOW})  # datetime via default=str, no raise


def test_as_candidate_shapes_payload():
    ev = ObservedEvent(
        source="obsidian", kind="obsidian.task", external_id="e1",
        payload={"entity_type": "task", "title": "  Ship   it  ", "status": "open"},
        observed_at=NOW,
    )
    c = _as_candidate(ev)
    assert c.entity_type == "task" and c.status == "open"
    assert c.attributes == {} and c.summary is None


def test_sync_counters_roundtrip():
    c = SyncCounters(observed=3, created=2, gated=1)
    d = c.as_dict()
    assert d["observed"] == 3 and d["created"] == 2 and d["gated"] == 1
    assert set(d) >= {"unchanged", "merged", "updated", "mirrored", "errors", "judge_calls"}


def test_sync_counters_include_archived():
    c = SyncCounters(archived=2)
    assert c.as_dict()["archived"] == 2


def test_tombstone_payload_detection():
    from app.state.reconciler import is_tombstone

    assert is_tombstone({"tombstone": True, "reason": "trashed"}) is True
    assert is_tombstone({"entity_type": "note", "title": "x"}) is False


def test_mirror_kinds_suffix_rule():
    """D3: any adapter's .note/.decision kinds mirror — no per-source coupling."""
    from app.state.mirror import kind_mirrors

    assert kind_mirrors("obsidian.note") and kind_mirrors("obsidian.decision")
    assert kind_mirrors("notion.note") and kind_mirrors("notion.decision")
    assert not kind_mirrors("notion.task")
    assert not kind_mirrors("notion.tombstone")
