"""Managed-folder renderer (arch §2.6). PURE: entities/relations → markdown
strings keyed by managed-relative path. NO filesystem access in this module —
writing happens exclusively through the Obsidian client's jailed write sink.

Determinism: stable sort (entity_type, title, id) so unchanged state
re-renders byte-identical files (no vault churn).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

DONE_CAP = 50
_SLUG_KEEP = re.compile(r"[^A-Za-z0-9 _-]")


def _slug(title: str, entity_id: Any) -> str:
    s = _SLUG_KEEP.sub("", title)
    s = " ".join(s.split()).strip()[:80]
    return s or f"project-{str(entity_id)[:8]}"


def _footer(now: datetime) -> str:
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    return f"\n> Managed by Founder OS — edits here are overwritten. Last synced {ts}.\n"


def _sorted(entities: list) -> list:
    return sorted(entities, key=lambda e: (e.entity_type, e.title, str(e.id)))


def _task_line(t: Any) -> str:
    box = "x" if t.status == "done" else " "
    return f"- [{box}] {t.title}"


def _recent_done(tasks: list) -> list:
    """§2.6: done section = the 50 MOST RECENT (deterministic id tiebreak)."""
    done = [t for t in tasks if t.status == "done"]
    done.sort(key=lambda t: (t.last_asserted_at, str(t.id)), reverse=True)
    return done[:DONE_CAP]


def render(entities: list, relations: list, *, now: datetime) -> dict[str, str]:
    ents = [e for e in _sorted(entities) if getattr(e, "is_active", True)]
    goals = [e for e in ents if e.entity_type == "goal"]
    projects = [e for e in ents if e.entity_type == "project"]
    tasks = [e for e in ents if e.entity_type == "task"]
    decisions = [e for e in ents if e.entity_type == "decision"]

    # task → project via part_of edges (either recorded direction is task→project)
    project_ids = {e.id for e in projects}
    task_project: dict[Any, Any] = {}
    for r in sorted(relations, key=lambda r: (str(r.source_entity_id), str(r.target_entity_id))):
        if r.relation_type == "part_of" and r.target_entity_id in project_ids:
            task_project.setdefault(r.source_entity_id, r.target_entity_id)

    files: dict[str, str] = {}
    footer = _footer(now)

    # Disambiguate colliding project slugs deterministically (security N4:
    # distinct titles like "x!" / "x?" both slug to "x" — suffix with id8).
    slugs: dict[Any, str] = {}
    used: set[str] = set()
    for p in projects:
        s = _slug(p.title, p.id)
        if s in used:
            s = f"{s}-{str(p.id)[:8]}"
        used.add(s)
        slugs[p.id] = s

    lines = ["# Goals", ""]
    for g in goals:
        conf = f"{float(g.confidence):.2f}"
        src_path = (g.attributes or {}).get("asserted_in")
        src_note = f", from `{src_path}`" if src_path else ""
        lines.append(f"- **{g.title}** — confidence {conf}, last asserted "
                     f"{g.last_asserted_at.strftime('%Y-%m-%d')}{src_note}")
        if g.summary:
            lines.append(f"  - {g.summary}")
    files["Goals.md"] = "\n".join(lines) + "\n" + footer

    by_project: dict[Any, list] = defaultdict(list)
    for t in tasks:
        by_project[task_project.get(t.id)].append(t)

    for p in projects:
        plines = [f"# {p.title}", ""]
        if p.summary:
            plines += [p.summary, ""]
        p_tasks = by_project.get(p.id, [])
        open_t = [t for t in p_tasks if t.status != "done"]
        done_t = [t for t in p_tasks if t.status == "done"]
        if open_t or done_t:
            plines.append("## Tasks")
            plines += [_task_line(t) for t in open_t]
            plines += [_task_line(t) for t in done_t]
        files[f"Projects/{slugs[p.id]}.md"] = "\n".join(plines) + "\n" + footer

    tlines = ["# Tasks", ""]
    for p in projects:
        p_tasks = by_project.get(p.id, [])
        if not p_tasks:
            continue
        tlines.append(f"## {p.title}")
        tlines += [_task_line(t) for t in p_tasks if t.status != "done"]
        tlines += [_task_line(t) for t in _recent_done(p_tasks)]
        tlines.append("")
    unassigned = by_project.get(None, [])
    if unassigned:
        tlines.append("## Unassigned")
        tlines += [_task_line(t) for t in unassigned if t.status != "done"]
        tlines += [_task_line(t) for t in _recent_done(unassigned)]
    files["Tasks.md"] = "\n".join(tlines) + "\n" + footer

    dlines = ["# Decisions", ""]
    for d in sorted(decisions, key=lambda e: (e.last_asserted_at, e.title), reverse=True):
        dlines.append(f"## {d.title}")
        dlines.append(f"*{d.last_asserted_at.strftime('%Y-%m-%d')}*")
        if d.summary:
            dlines.append(d.summary)
        dlines.append("")
    files["Decisions.md"] = "\n".join(dlines) + "\n" + footer

    return files
