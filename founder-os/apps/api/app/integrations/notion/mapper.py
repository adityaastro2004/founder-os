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


def _oneline(text: str) -> str:
    """Collapse whitespace incl. newlines (N3): hostile titles must not inject
    extra markdown lines into rendered managed pages."""
    return " ".join(text.split())


def title_of(obj: dict) -> str:
    """Public alias — adapters must not reach for private helpers."""
    return _title_of(obj)


def plain_text(rich: list | None) -> str:
    """Public alias for rich-text extraction."""
    return _plain(rich)


def _title_of(obj: dict) -> str:
    for prop in (obj.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _oneline(_plain(prop.get("title"))) or "Untitled"
    if obj.get("title"):  # database objects carry title at top level
        return _oneline(_plain(obj["title"])) or "Untitled"
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
            # §3.5 strict: done iff the status GROUP is Complete (name-based
            # leniency was an undocumented deviation — reviewer nit)
            return ("done" if group == "Complete" else "open"), name
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
        # B2: a row whose DATABASE sits under an observed page inherits that
        # page as project context (arch §3.4: part_of_project = its title).
        db_parent_pid = normalize_uuid(
            ((schema.get("parent") or {}).get("page_id")) or "")
        db_parent_title = (parent_titles or {}).get(db_parent_pid)
        if db_parent_title:
            hints["part_of_project"] = db_parent_title
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
        parent_pid = normalize_uuid(parent.get("page_id") or "")
        parent_title = (parent_titles or {}).get(parent_pid, "")
        if parent_title.casefold() == "decisions":
            entity_type = "decision"
        # B2: page-under-page containment → derived_from the observed parent
        if parent_pid and parent_pid in (parent_titles or {}):
            hints["derived_from_note"] = external_id_for(source_id, "page", parent_pid)

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


# ── tombstones (arch §3.6.2) ─────────────────────────────────────────────

def classify_tombstone(obj: dict | None) -> str | None:
    """None obj = confirming GET 404/restricted → 'unshared'. Flags → 'trashed'.
    Alive object → None (no tombstone)."""
    if obj is None:
        return "unshared"
    if obj.get("in_trash") or obj.get("archived"):
        return "trashed"
    return None


def tombstone_event(source_id: str, kind: str, notion_uuid: str, *,
                    reason: str, observed_at) -> ObservedEvent:
    return ObservedEvent(
        source="notion",
        kind="notion.tombstone",
        external_id=external_id_for(source_id, kind, notion_uuid),
        payload={"tombstone": True, "reason": reason},
        observed_at=observed_at,
    )


# ── outbound: churn-free managed rendering (arch §5) ─────────────────────

STATIC_FOOTER = "> Managed by Founder OS — edits here are overwritten."
_FOOTER_RE = re.compile(r"^> Managed by Founder OS.*$", re.M)
_MAX_RICH_TEXT = 2000
_MAX_BLOCKS_PER_APPEND = 100


def prepare_managed_markdown(md: str) -> str:
    """Swap the renderer's timestamped footer for the static one — any per-sync
    timestamp would defeat churn-freedom by definition (arch §5)."""
    return _FOOTER_RE.sub(STATIC_FOOTER, md)


def _hash_of(md: str) -> str:
    import hashlib

    return hashlib.sha256(md.encode("utf-8")).hexdigest()


def should_write(ledger: dict, key: str, prepared_md: str) -> bool:
    """Skip entirely (zero requests) when the ledger hash matches."""
    entry = (ledger or {}).get(key) or {}
    return entry.get("hash") != _hash_of(prepared_md)


should_write.hash_of = _hash_of  # exposed for ledger updates + tests


def _rich_runs(text: str) -> list[dict]:
    """Inline **bold**/*italic* → annotated runs; split at the 2000-char cap."""
    runs: list[dict] = []
    token_re = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
    for part in token_re.split(text):
        if not part:
            continue
        annotations = {}
        content = part
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            content, annotations = part[2:-2], {"bold": True}
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            content, annotations = part[1:-1], {"italic": True}
        for i in range(0, len(content), _MAX_RICH_TEXT):
            chunk = content[i:i + _MAX_RICH_TEXT]
            run: dict = {"type": "text", "text": {"content": chunk}}
            if annotations:
                run["annotations"] = annotations
            runs.append(run)
    return runs or [{"type": "text", "text": {"content": ""}}]


def md_to_blocks(md: str) -> list[dict]:
    """Convert exactly the closed dialect OUR renderer emits (arch §5):
    #/## headings, - bullets, - [ ]/- [x] to_dos, **bold**/*italic*, > quote.
    Unknown constructs degrade to plain paragraphs."""
    blocks: list[dict] = []
    for raw_line in md.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": _rich_runs(line[3:])}})
        elif line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": _rich_runs(line[2:])}})
        elif line.startswith("- [x] ") or line.startswith("- [X] "):
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": _rich_runs(line[6:]), "checked": True}})
        elif line.startswith("- [ ] "):
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": _rich_runs(line[6:]), "checked": False}})
        elif line.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rich_runs(line[2:])}})
        elif line.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": _rich_runs(line[2:])}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": _rich_runs(line)}})
    return blocks


def batch_blocks(blocks: list[dict]) -> list[list[dict]]:
    """API limit: ≤100 blocks per append request."""
    return [blocks[i:i + _MAX_BLOCKS_PER_APPEND]
            for i in range(0, len(blocks), _MAX_BLOCKS_PER_APPEND)] or [[]]


def events_for_todo_blocks(source_id: str, page: dict, blocks: list[dict]) -> list[ObservedEvent]:
    """to_do blocks inside an observed page → task events (arch §3.4)."""
    page_eid = external_id_for(source_id, "page", page["id"])
    observed_at = _parsed_when(page)
    events: list[ObservedEvent] = []
    for b in blocks or []:
        if b.get("type") != "to_do":
            continue
        text = _oneline(_plain((b.get("to_do") or {}).get("rich_text")))
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
