"""Tombstone diff + reactivation predicates (arch §3.6.2, §13)."""
from datetime import datetime, timezone

from app.integrations.notion.mapper import (
    classify_tombstone,
    should_reactivate,
    tombstone_event,
)

SRC = "11111111-2222-3333-4444-555555555555"
T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 8, tzinfo=timezone.utc)


def test_classify_trashed_vs_unshared():
    assert classify_tombstone({"in_trash": True}) == "trashed"
    assert classify_tombstone({"archived": True}) == "trashed"
    assert classify_tombstone(None) == "unshared"          # 404/restricted GET
    assert classify_tombstone({"archived": False, "in_trash": False}) is None  # still alive


def test_tombstone_event_shape():
    ev = tombstone_event(SRC, "page", "bbbbbbbb-0000-0000-0000-000000000003",
                         reason="trashed", observed_at=T1)
    assert ev.kind == "notion.tombstone"
    assert ev.payload == {"tombstone": True, "reason": "trashed"}
    assert ev.provenance == "observed"
    assert ev.external_id.endswith(":page:bbbbbbbb-0000-0000-0000-000000000003")


def test_reactivation_predicate():
    # normal event newer than archival → reactivate (restore-from-trash)
    assert should_reactivate(entity_archived_at=T0, event_observed_at=T1) is True
    # stale event older than archival → never resurrect
    assert should_reactivate(entity_archived_at=T1, event_observed_at=T0) is False
