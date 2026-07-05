"""external_id scheme (arch §3.3): toggle-stable task ids, rename semantics,
founderos_id override, ordinals for identical texts, event emission mapping (§3.4).
"""
from datetime import datetime, timezone

from app.integrations.obsidian.client import (
    events_for_note,
    external_id_for_note,
    external_id_for_task,
    normalize_checkbox_text,
    parse_note,
)

SRC = "11111111-2222-3333-4444-555555555555"
NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def test_note_id_is_path_keyed_and_nfc():
    a = external_id_for_note(SRC, "Notes/Café.md", {})
    b = external_id_for_note(SRC, "Notes/Café.md", {})  # decomposed é
    assert a == b == f"obsidian:{SRC}:note:Notes/Café.md"


def test_founderos_id_frontmatter_overrides_path():
    eid = external_id_for_note(SRC, "anywhere/x.md", {"founderos_id": "goal-q3"})
    assert eid == f"obsidian:{SRC}:note:id:goal-q3"


def test_task_id_survives_checkbox_toggle():
    open_line = "- [ ] Ship the landing page"
    done_line = "- [x] Ship the landing page"
    n_open = normalize_checkbox_text(open_line)
    n_done = normalize_checkbox_text(done_line)
    assert n_open == n_done == "Ship the landing page"
    assert external_id_for_task(SRC, "p.md", n_open, 1) == external_id_for_task(SRC, "p.md", n_done, 1)


def test_task_text_edit_changes_id():
    a = external_id_for_task(SRC, "p.md", "Ship the landing page", 1)
    b = external_id_for_task(SRC, "p.md", "Ship the marketing page", 1)
    assert a != b


def test_identical_text_ordinals_stable_when_distinct_tasks_reorder():
    note_v1 = "- [ ] call investor\n- [ ] write update\n- [ ] call investor\n"
    note_v2 = "- [ ] write update\n- [ ] call investor\n- [ ] call investor\n"
    ids_v1 = [e.external_id for e in events_for_note(SRC, "t.md", parse_note("t.md", note_v1), NOW) if e.kind == "obsidian.task"]
    ids_v2 = [e.external_id for e in events_for_note(SRC, "t.md", parse_note("t.md", note_v2), NOW) if e.kind == "obsidian.task"]
    # same multiset of ids: distinct-task reorder shifts nothing
    assert sorted(ids_v1) == sorted(ids_v2)
    # the two identical "call investor" lines get :2 suffix on the second only
    assert sum(1 for i in ids_v1 if i.endswith(":2")) == 1


def test_events_mapping_frontmatter_goal_project_decision_note_task():
    text = (
        "---\ngoal: Reach $10k MRR\nproject: Launch v2\n---\n"
        "# Launch plan\n\nBody.\n\n- [ ] ship it\n"
    )
    events = events_for_note(SRC, "Projects/Launch v2.md", parse_note("Projects/Launch v2.md", text), NOW)
    kinds = sorted(e.kind for e in events)
    assert kinds == ["obsidian.goal", "obsidian.note", "obsidian.project", "obsidian.task"]
    task = next(e for e in events if e.kind == "obsidian.task")
    assert task.payload["status"] == "open"
    assert task.payload["relation_hints"]["part_of_project"] == "Launch v2"
    assert task.payload["relation_hints"]["derived_from_note"].endswith("Launch v2.md")
    for e in events:
        assert e.provenance == "observed"
        assert e.source == "obsidian"


def test_decision_by_tag_and_by_path():
    by_tag = events_for_note(SRC, "n.md", parse_note("n.md", "decided stuff #decision\n"), NOW)
    by_path = events_for_note(SRC, "Decisions/pick-db.md", parse_note("Decisions/pick-db.md", "# Pick DB\nwe chose postgres\n"), NOW)
    assert any(e.kind == "obsidian.decision" for e in by_tag)
    assert any(e.kind == "obsidian.decision" for e in by_path)


def test_nested_task_relation_hint():
    text = "- [ ] parent\n    - [ ] child\n"
    events = [e for e in events_for_note(SRC, "n.md", parse_note("n.md", text), NOW) if e.kind == "obsidian.task"]
    child = next(e for e in events if e.payload["title"] == "child")
    parent = next(e for e in events if e.payload["title"] == "parent")
    assert child.payload["relation_hints"]["parent_task_external_id"] == parent.external_id
