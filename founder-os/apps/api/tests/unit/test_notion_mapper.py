"""Notion mapper (arch §3.4–§3.7): fixture objects → ObservedEvents."""
import json
import pathlib

from app.integrations.notion import mapper

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "notion_workspace"
SRC = "11111111-2222-3333-4444-555555555555"


def load(name):
    return json.loads((FIX / name).read_text())


def schemas():
    return {
        d["id"]: d for d in (
            load("db_tasks.json"), load("db_goals.json"), load("db_projects.json"),
            load("db_decisions.json"), load("db_status_variant.json"),
            load("db_select_variant.json"),
        )
    }


def test_task_db_rows_map_with_checkbox_status_and_attrs():
    rows = load("db_tasks_rows.json")["rows"]
    events = [mapper.event_for_object(SRC, r, db_schemas=schemas(), database_map={}) for r in rows]
    assert [e.payload["entity_type"] for e in events] == ["task", "task", "task"]
    ship = events[0]
    assert ship.payload["status"] == "open"
    assert ship.payload["attributes"]["due"] == "2026-07-15"
    assert "launch" in ship.payload["attributes"]["tags"]
    assert ship.payload["attributes"]["status_property"] == "Done"
    done = events[1]
    assert done.payload["status"] == "done"


def test_status_group_and_select_variants():
    ev_status = mapper.event_for_object(SRC, load("row_status_variant.json"),
                                        db_schemas=schemas(), database_map={})
    assert ev_status.payload["entity_type"] == "task"
    assert ev_status.payload["status"] == "done"          # group == Complete
    ev_select = mapper.event_for_object(SRC, load("row_select_variant.json"),
                                        db_schemas=schemas(), database_map={})
    assert ev_select.payload["status"] == "done"          # "Shipped" in done-set


def test_goal_project_decision_db_title_heuristics():
    for fixture, expected in (
        ("db_goals_rows.json", "goal"),
        ("db_projects_rows.json", "project"),
        ("db_decisions_rows.json", "decision"),
    ):
        row = load(fixture)["rows"][0]
        ev = mapper.event_for_object(SRC, row, db_schemas=schemas(), database_map={})
        assert ev.payload["entity_type"] == expected, fixture


def test_database_map_override_beats_heuristics():
    row = load("db_goals_rows.json")["rows"][0]
    dbid = row["parent"]["database_id"]
    ev = mapper.event_for_object(SRC, row, db_schemas=schemas(),
                                 database_map={dbid: "note"})
    assert ev.payload["entity_type"] == "note"


def test_plain_page_maps_to_note_with_body():
    page = load("page_note.json")
    blocks = load("page_note_blocks.json")["results"]
    ev = mapper.event_for_object(SRC, page, db_schemas={}, database_map={}, blocks=blocks)
    assert ev.payload["entity_type"] == "note"
    assert "activate at a much higher rate" in ev.payload["body"]
    assert ev.payload["has_headings"] is True


def test_todo_blocks_emit_tasks_with_hints():
    page = load("page_with_todos.json")
    blocks = load("page_with_todos_blocks.json")["results"]
    page_ev = mapper.event_for_object(SRC, page, db_schemas={}, database_map={}, blocks=blocks)
    todo_evs = mapper.events_for_todo_blocks(SRC, page, blocks)
    assert len(todo_evs) == 2
    assert todo_evs[0].payload["status"] == "open"
    assert todo_evs[1].payload["status"] == "done"
    assert todo_evs[0].payload["relation_hints"]["derived_from_note"] == page_ev.external_id


def test_payload_excludes_volatile_fields_hash_stable():
    from app.state.reconciler import canonical_content_hash

    page = load("page_note.json")
    blocks = load("page_note_blocks.json")["results"]
    ev1 = mapper.event_for_object(SRC, page, db_schemas={}, database_map={}, blocks=blocks)
    page2 = dict(page)
    page2["last_edited_time"] = "2026-07-09T23:59:00.000Z"  # refetch later, same content
    page2["url"] = "https://notion.so/different"
    ev2 = mapper.event_for_object(SRC, page2, db_schemas={}, database_map={}, blocks=blocks)
    assert canonical_content_hash(ev1.payload) == canonical_content_hash(ev2.payload)
    # but observed_at tracks last_edited_time
    assert ev1.observed_at != ev2.observed_at


def test_untitled_empty_page_still_emits_gateable_candidate():
    ev = mapper.event_for_object(SRC, load("page_untitled_empty.json"),
                                 db_schemas={}, database_map={}, blocks=[])
    assert ev.payload["entity_type"] == "note"
    assert ev.payload["title"] == "Untitled"  # gate filler-set will reject it
