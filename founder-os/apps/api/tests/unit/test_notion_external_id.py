"""Notion external_id scheme (arch §3.6): UUID-stable identity."""
import json
import pathlib

from app.integrations.notion import mapper

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "notion_workspace"
SRC = "11111111-2222-3333-4444-555555555555"


def load(name):
    return json.loads((FIX / name).read_text())


def test_scheme_format_and_dash_normalization():
    assert mapper.external_id_for(SRC, "page", "BBBBBBBB0000000000000000000000A1") == \
        f"notion:{SRC}:page:bbbbbbbb-0000-0000-0000-0000000000a1"
    assert mapper.external_id_for(SRC, "block", "f1-f2") .startswith(f"notion:{SRC}:block:")


def test_rename_and_move_keep_the_same_id():
    """UUIDs are stable across renames AND moves — hard identity, unlike
    Obsidian's dedup-based rename survival (arch §3.6)."""
    page = load("page_note.json")
    ev1 = mapper.event_for_object(SRC, page, db_schemas={}, database_map={}, blocks=[])
    moved = dict(page)
    moved["parent"] = {"type": "page_id", "page_id": "cccccccc-0000-0000-0000-000000000009"}
    moved["properties"] = {"title": {"type": "title", "title": [
        {"type": "text", "text": {"content": "Renamed idea"}, "plain_text": "Renamed idea"}]}}
    ev2 = mapper.event_for_object(SRC, moved, db_schemas={}, database_map={}, blocks=[])
    assert ev1.external_id == ev2.external_id
    assert ev2.payload["title"] == "Renamed idea"  # retitle flows; D2 hard_match applies it


def test_db_row_and_plain_page_share_page_kind():
    row = load("db_tasks_rows.json")["rows"][0]
    ev = mapper.event_for_object(SRC, row, db_schemas={
        row["parent"]["database_id"]: load("db_tasks.json")}, database_map={})
    assert f":page:{row['id']}" in ev.external_id


def test_todo_toggle_keeps_id_payload_hash_changes():
    from app.state.reconciler import canonical_content_hash

    page = load("page_with_todos.json")
    blocks = load("page_with_todos_blocks.json")["results"]
    evs_before = mapper.events_for_todo_blocks(SRC, page, blocks)
    toggled = json.loads(json.dumps(blocks))
    toggled[0]["to_do"]["checked"] = True
    evs_after = mapper.events_for_todo_blocks(SRC, page, toggled)
    assert evs_before[0].external_id == evs_after[0].external_id
    assert canonical_content_hash(evs_before[0].payload) != canonical_content_hash(evs_after[0].payload)
