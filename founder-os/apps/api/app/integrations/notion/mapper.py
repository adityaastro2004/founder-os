"""PURE Notion-JSON → ObservedEvent mapping (arch §3.4–§3.7). No IO, no httpx.

Payloads carry CONTENT ONLY (no last_edited_time/urls) so content_hash is a
pure content signature; observed_at = the object's last_edited_time (real
event ordering for the cross-source merge rule).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.integrations.base import ObservedEvent

DONE_SELECT_VALUES = {"done", "complete", "completed", "shipped"}
GOAL_DB_TITLES = {"goals"}
PROJECT_DB_TITLES = {"projects", "roadmap"}
DECISION_DB_TITLES = {"decisions", "decision log"}
_UUID32 = re.compile(r"^[0-9a-fA-F]{32}$")


# ── ids ──────────────────────────────────────────────────────────────────

def normalize_uuid(raw: str) -> str:
    s = raw.strip().lower().replace("-", "")
    if _UUID32.match(s):
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"
    return raw.strip().lower()


def external_id_for(source_id: str, kind: str, notion_uuid: str) -> str:
    return f"notion:{source_id}:{kind}:{normalize_uuid(notion_uuid)}"


# ── rich text / property helpers ─────────────────────────────────────────

def _plain(rich: list | None) -> str:
    return "".join(r.get("plain_text", "") for r in (rich or []))


def _title_of(obj: dict) -> str:
    for prop in (obj.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _plain(prop.get("title")) or "Untitled"
    if obj.get("title"):  # database objects carry title at top level
        return _plain(obj["title"]) or "Untitled"
    return "Untitled"


def _parsed_when(obj: dict) -> datetime:
    ts = obj.get("last_edited_time") or obj.get("created_time")
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def simplify_properties(props: dict) -> dict:
    """Plain strings/bools/ISO dates keyed by name — hash-stable (arch §3.7)."""
    out: dict[str, Any] = {}
    for name, p in (props or {}).items():
        t = p.get("type")
        if t == "title":
            out[name] = _plain(p.get("title"))
        elif t == "rich_text":
            out[name] = _plain(p.get("rich_text"))
        elif t == "checkbox":
            out[name] = bool(p.get("checkbox"))
        elif t == "select":
            out[name] = (p.get("select") or {}).get("name")
        elif t == "status":
            out[name] = (p.get("status") or {}).get("name")
        elif t == "multi_select":
            out[name] = [v.get("name") for v in p.get("multi_select") or []]
        elif t == "date":
            out[name] = (p.get("date") or {}).get("start")
        elif t == "number":
            out[name] = p.get("number")
        # unsupported types (relation/people/files/…): preserved as type marker
        elif t:
            out[name] = f"<{t}>"
    return out


# ── task-status derivation (arch §3.5 precedence) ────────────────────────

def derive_status(props: dict, schema_props: dict) -> tuple[str | None, str | None]:
    """Returns (status, status_property_name) or (None, None) if no signal."""
    for name, sp in (schema_props or {}).items():
        if sp.get("type") == "checkbox":
            checked = bool((props.get(name) or {}).get("checkbox"))
            return ("done" if checked else "open"), name
    for name, sp in (schema_props or {}).items():
        if sp.get("type") == "status":
            group = ((props.get(name) or {}).get("status") or {}).get("group")
            name_val = ((props.get(name) or {}).get("status") or {}).get("name", "")
            done = group == "Complete" or name_val.casefold() in DONE_SELECT_VALUES
            return ("done" if done else "open"), name
    for name, sp in (schema_props or {}).items():
        if sp.get("type") == "select" and name.casefold() == "status":
            value = ((props.get(name) or {}).get("select") or {}).get("name", "") or ""
            return ("done" if value.casefold() in DONE_SELECT_VALUES else "open"), name
    return None, None


# ── entity-type routing (arch §3.4) ──────────────────────────────────────

def _route_db_row(db_schema: dict, database_map: dict, db_id: str) -> str | None:
    override = (database_map or {}).get(db_id) or (database_map or {}).get(normalize_uuid(db_id))
    if override:
        return override
    title = _plain(db_schema.get("title")).casefold().strip() if db_schema else ""
    if title in GOAL_DB_TITLES:
        return "goal"
    if title in PROJECT_DB_TITLES:
        return "project"
    if title in DECISION_DB_TITLES:
        return "decision"
    return None  # → sniff for task signal, else note


def blocks_to_body(blocks: list[dict]) -> tuple[str, bool]:
    """Text-bearing blocks → plain body text; returns (body, has_headings)."""
    lines: list[str] = []
    has_headings = False
    for b in blocks or []:
        t = b.get("type", "")
        payload = b.get(t) or {}
        text = _plain(payload.get("rich_text"))
        if not text:
            continue
        if t.startswith("heading_"):
            has_headings = True
            lines.append(text)
        elif t == "to_do":
            continue  # to_dos become their own task events, not note body
        else:
            lines.append(text)
    return "\n\n".join(lines), has_headings


def event_for_object(
    source_id: str,
    obj: dict,
    *,
    db_schemas: dict[str, dict],
    database_map: dict,
    blocks: list[dict] | None = None,
    parent_titles: dict[str, str] | None = None,
) -> ObservedEvent:
    """Map one page/row to its primary ObservedEvent."""
    parent = obj.get("parent") or {}
    props = obj.get("properties") or {}
    title = _title_of(obj)
    observed_at = _parsed_when(obj)
    eid = external_id_for(source_id, "page", obj["id"])

    entity_type = "note"
    status = None
    attributes: dict[str, Any] = {"notion_id": normalize_uuid(obj["id"])}
    hints: dict[str, Any] = {}

    if parent.get("type") == "database_id":
        db_id = parent["database_id"]
        schema = db_schemas.get(db_id) or db_schemas.get(normalize_uuid(db_id)) or {}
        routed = _route_db_row(schema, database_map, db_id)
        derived, status_prop = derive_status(props, schema.get("properties") or {})
        if routed:
            entity_type = routed
        elif derived is not None:
            entity_type = "task"
        if entity_type == "task":
            status = derived or "open"
            if status_prop:
                attributes["status_property"] = status_prop
        simplified = simplify_properties(props)
        attributes["properties"] = simplified
        for name, value in simplified.items():
            sp_type = ((schema.get("properties") or {}).get(name) or {}).get("type")
            if sp_type == "date" and value and "due" not in attributes:
                attributes["due"] = value
            if sp_type == "multi_select" and value:
                attributes.setdefault("tags", []).extend(value)
        db_title = _plain(schema.get("title")) if schema else ""
        if db_title:
            attributes["database"] = db_title
    else:
        parent_title = (parent_titles or {}).get(parent.get("page_id", ""), "")
        if parent_title.casefold() == "decisions":
            entity_type = "decision"

    body, has_headings = blocks_to_body(blocks or [])
    summary = (body.split("\n\n")[0] if body else "")[:500]

    payload: dict[str, Any] = {
        "entity_type": entity_type,
        "title": title,
        "summary": summary,
        "attributes": attributes,
        "relation_hints": hints,
        "parent_id": normalize_uuid(parent.get("page_id") or parent.get("database_id") or "") or None,
    }
    if body:
        payload["body"] = body
        payload["has_headings"] = has_headings
    if status is not None:
        payload["status"] = status

    return ObservedEvent(
        source="notion", kind=f"notion.{entity_type}", external_id=eid,
        payload=payload, observed_at=observed_at,
    )


def events_for_todo_blocks(source_id: str, page: dict, blocks: list[dict]) -> list[ObservedEvent]:
    """to_do blocks inside an observed page → task events (arch §3.4)."""
    page_eid = external_id_for(source_id, "page", page["id"])
    observed_at = _parsed_when(page)
    events: list[ObservedEvent] = []
    for b in blocks or []:
        if b.get("type") != "to_do":
            continue
        text = _plain((b.get("to_do") or {}).get("rich_text"))
        if not text:
            continue
        events.append(ObservedEvent(
            source="notion",
            kind="notion.task",
            external_id=external_id_for(source_id, "block", b["id"]),
            payload={
                "entity_type": "task",
                "title": text,
                "status": "done" if (b.get("to_do") or {}).get("checked") else "open",
                "attributes": {"notion_id": normalize_uuid(b["id"]),
                               "note_page": normalize_uuid(page["id"])},
                "relation_hints": {"derived_from_note": page_eid},
            },
            observed_at=observed_at,
        ))
    return events
