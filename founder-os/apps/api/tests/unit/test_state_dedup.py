"""Dedup + merge semantics (arch §2.4–2.5): threshold behavior + the full merge table."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.state.dedup import embed_text_for, merge

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 6, tzinfo=timezone.utc)


def existing_entity(**over):
    base = dict(
        title="Ship landing page",
        summary="Build and deploy the new landing page",
        status="open",
        attributes={"note_path": "a.md", "aliases": []},
        confidence=0.700,
        last_asserted_at=T0,
        source="observed",
        source_id="src-old",
    )
    base.update(over)
    return SimpleNamespace(**base)


def candidate(**over):
    base = dict(
        title="Ship the landing page",
        summary="Build and deploy the new landing page for launch",
        status="done",
        attributes={"note_path": "b.md"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def observation(observed_at=T1, source_id="src-new"):
    return SimpleNamespace(observed_at=observed_at, source_id=source_id)


def test_embed_text_format():
    e = SimpleNamespace(entity_type="task", title="Ship it", summary="x" * 600)
    text = embed_text_for(e)
    assert text.startswith("task: Ship it\n")
    assert len(text) <= len("task: Ship it\n") + 500


def test_merge_title_kept_incoming_becomes_alias():
    ex = existing_entity()
    changes = merge(ex, candidate(), observation())
    assert "title" not in changes  # existing title survives
    assert changes["attributes"]["aliases"] == ["Ship the landing page"]


def test_merge_alias_cap_5_and_dedup():
    ex = existing_entity(attributes={"aliases": ["a", "b", "c", "d", "e"]})
    changes = merge(ex, candidate(title="f"), observation())
    assert len(changes["attributes"]["aliases"]) == 5
    ex2 = existing_entity(attributes={"aliases": ["Ship the landing page"]})
    changes2 = merge(ex2, candidate(), observation())
    assert changes2["attributes"]["aliases"] == ["Ship the landing page"]  # no dupe


def test_merge_summary_only_if_20pct_longer():
    ex = existing_entity(summary="short summary here")
    longer = "x" * int(len("short summary here") * 1.3)
    changes = merge(ex, candidate(summary=longer), observation())
    assert changes["summary"] == longer
    barely = "short summary here!!"
    changes2 = merge(existing_entity(summary="short summary here"),
                     candidate(summary=barely), observation())
    assert "summary" not in changes2


def test_merge_status_newer_observation_wins():
    changes = merge(existing_entity(), candidate(status="done"), observation(observed_at=T1))
    assert changes["status"] == "done"
    changes2 = merge(existing_entity(last_asserted_at=T1), candidate(status="done"),
                     observation(observed_at=T0))
    assert "status" not in changes2  # stale observation loses


def test_merge_confidence_asymptotic_formula():
    changes = merge(existing_entity(confidence=0.700), candidate(), observation())
    assert changes["confidence"] == pytest.approx(0.700 + 0.300 * 0.15)
    near = merge(existing_entity(confidence=0.995), candidate(), observation())
    assert near["confidence"] <= 0.99


def test_merge_last_asserted_max_and_source_takeover():
    changes = merge(existing_entity(), candidate(), observation(observed_at=T1, source_id="src-new"))
    assert changes["last_asserted_at"] == T1
    assert changes["source_id"] == "src-new"
    stale = merge(existing_entity(last_asserted_at=T1), candidate(), observation(observed_at=T0))
    assert stale["last_asserted_at"] == T1  # max(existing, incoming)


def test_merge_attributes_shallow_incoming_wins_except_aliases():
    ex = existing_entity(attributes={"note_path": "a.md", "keep": 1, "aliases": ["x"]})
    changes = merge(ex, candidate(attributes={"note_path": "b.md", "new": 2}), observation())
    attrs = changes["attributes"]
    assert attrs["note_path"] == "b.md" and attrs["keep"] == 1 and attrs["new"] == 2
    assert "x" in attrs["aliases"]


def test_merge_reembed_flag_only_when_summary_changed():
    longer = "y" * 100
    changes = merge(existing_entity(summary="short"), candidate(summary=longer), observation())
    assert changes["_reembed"] is True
    changes2 = merge(existing_entity(), candidate(summary=None), observation())
    assert changes2.get("_reembed", False) is False
