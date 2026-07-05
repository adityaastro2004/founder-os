"""Obsidian vault transport (arch §3.2–§3.3, §4, §6).

Parsing: python-frontmatter + stdlib regex — exactly three constructs matter
(YAML frontmatter, ATX headings, checkboxes). Never fails a sync on a malformed
file: YAML errors degrade to plain body.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CHECKBOX_RE = re.compile(r"^(\s*)[-*+]\s\[( |x|X)\]\s+(.*)$")
_INLINE_TAG_RE = re.compile(r"(?:^|\s)#([\w/-]+)")


@dataclass
class CheckboxItem:
    text: str
    done: bool
    indent: int
    parent_index: int | None
    ordinal: int  # 1-based among identical normalized texts in the note


@dataclass
class ParsedNote:
    frontmatter: dict
    h1: str | None
    tags: set[str] = field(default_factory=set)
    checkboxes: list[CheckboxItem] = field(default_factory=list)
    body: str = ""


def _norm_rel_path(rel_path: str) -> str:
    """POSIX separators + Unicode NFC — stable ids across OSes (arch §3.2)."""
    return unicodedata.normalize("NFC", rel_path.replace("\\", "/"))


def normalize_checkbox_text(raw_line: str) -> str:
    """Strip indent, list marker, and the [ ]/[x] state; collapse whitespace.

    The checkbox STATE is deliberately excluded so toggling a box keeps the
    same external_id (arch §3.3) — the payload hash changes instead.
    """
    m = _CHECKBOX_RE.match(raw_line)
    text = m.group(3) if m else raw_line
    return " ".join(text.split())


def parse_note(rel_path: str, text: str) -> ParsedNote:
    text = text.replace("\r\n", "\n")
    try:
        post = frontmatter.loads(text)
        fm = dict(post.metadata) if isinstance(post.metadata, dict) else {}
        body = post.content
    except Exception:
        # Malformed YAML: whole file is body; never fail the sync (arch §3.2).
        logger.debug("malformed frontmatter in %s — treating as body", rel_path)
        fm, body = {}, text

    tags: set[str] = set()
    fm_tags = fm.get("tags")
    if isinstance(fm_tags, str):
        tags.add(fm_tags.strip().lstrip("#"))
    elif isinstance(fm_tags, list):
        tags.update(str(t).strip().lstrip("#") for t in fm_tags)
    tags.update(_INLINE_TAG_RE.findall(body))

    h1: str | None = None
    checkboxes: list[CheckboxItem] = []
    norm_counts: dict[str, int] = {}
    # (indent, index) stack for nesting: parent = nearest shallower-indent box above
    stack: list[tuple[int, int]] = []

    for line in body.split("\n"):
        if h1 is None:
            hm = _HEADING_RE.match(line)
            if hm and len(hm.group(1)) == 1:
                h1 = hm.group(2).strip()
        cm = _CHECKBOX_RE.match(line)
        if cm:
            indent = len(cm.group(1).expandtabs(4))
            done = cm.group(2).lower() == "x"
            txt = " ".join(cm.group(3).split())
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent_index = stack[-1][1] if stack else None
            norm_counts[txt] = norm_counts.get(txt, 0) + 1
            checkboxes.append(CheckboxItem(
                text=txt, done=done, indent=indent,
                parent_index=parent_index, ordinal=norm_counts[txt],
            ))
            stack.append((indent, len(checkboxes) - 1))

    return ParsedNote(frontmatter=fm, h1=h1, tags=tags, checkboxes=checkboxes, body=body)


def walk_vault(
    vault_root: Path,
    *,
    exclude_dirs: list[str],
    max_files: int,
    max_file_bytes: int,
) -> list[tuple[str, str]]:
    """Yield (vault-relative POSIX path, text) for every observable .md file.

    Excludes configured dirs (ALWAYS including the managed folder — the engine
    must never observe its own output) and oversize files. Deterministic order.
    """
    root = Path(vault_root).resolve()
    excluded = set(exclude_dirs)
    out: list[tuple[str, str]] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part in excluded for part in rel.parts[:-1]):
            continue
        try:
            if p.stat().st_size > max_file_bytes:
                logger.warning("skipping oversize vault file: %s", rel)
                continue
            out.append((_norm_rel_path(str(rel)), p.read_text(encoding="utf-8", errors="replace")))
        except OSError as exc:
            logger.warning("unreadable vault file %s: %s", rel, exc)
            continue
        if len(out) >= max_files:
            logger.warning("vault walk stopped at max_files=%d", max_files)
            break
    return out


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Managed-folder write jail (arch §4) ─────────────────────────────────
# Exactly ONE function in the codebase opens vault files for writing. Any
# escape is P0 (task 011 success metric "Safety").


class ManagedFolderViolation(Exception):
    """A write attempted to land outside vault_root/managed_folder."""


def _managed_root(vault_root: Path | str, managed_folder: str) -> Path:
    resolved_vault = Path(vault_root).resolve(strict=True)
    managed = (resolved_vault / managed_folder).resolve()
    # A managed_folder config value like "../x" fails here (step 1).
    if managed != resolved_vault and resolved_vault not in managed.parents:
        raise ManagedFolderViolation(
            f"managed folder {managed_folder!r} escapes the vault root"
        )
    if managed == resolved_vault:
        raise ManagedFolderViolation("managed folder must be a subfolder, not the vault root")
    return managed


def _jail(managed_root: Path, relative_path: str) -> Path:
    # Cheap early rejects BEFORE joining (step 2).
    if (
        not relative_path
        or relative_path.startswith(("/", "\\"))
        or "\\" in relative_path
        or "\x00" in relative_path
        or ".." in Path(relative_path).parts
        or (len(relative_path) > 1 and relative_path[1] == ":")  # drive prefix
    ):
        raise ManagedFolderViolation(f"illegal managed path: {relative_path!r}")
    final = (managed_root / relative_path).resolve()
    # resolve() follows symlinks: a symlinked subdir pointing outside the vault
    # resolves outside managed_root and is rejected here (step 3).
    if managed_root not in final.parents:
        raise ManagedFolderViolation(f"path escapes the managed folder: {relative_path!r}")
    return final


def write_managed(vault_root: Path | str, managed_folder: str, relative_path: str, content: str) -> Path:
    managed = _managed_root(vault_root, managed_folder)
    managed.mkdir(parents=True, exist_ok=True)
    final = _jail(managed, relative_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    # Safety comes from _jail's resolve() above (symlinks followed, escape
    # rejected). Residual TOCTOU between that resolve and this write requires a
    # concurrent local attacker — outside the local-first threat model (N1;
    # revisit with tasks/backlog/014 before any hosted deployment).
    final.write_text(content, encoding="utf-8")
    return final


def prune_managed(vault_root: Path | str, managed_folder: str, keep: set[str]) -> list[str]:
    """Delete ONLY renderer-owned .md files under the managed folder that are
    absent from the just-rendered keep-set. Never touches anything else."""
    managed = _managed_root(vault_root, managed_folder)
    if not managed.exists():
        return []
    keep_final = {_jail(managed, k) for k in keep}
    removed: list[str] = []
    for p in sorted(managed.rglob("*.md")):
        resolved = p.resolve()
        if managed not in resolved.parents:
            continue  # symlinked stray — not ours, never delete through it
        if resolved not in keep_final:
            p.unlink()
            removed.append(str(p.relative_to(managed)))
    return removed


def validate_vault_path(path: str) -> Path:
    """Shared by the POST route (422) and the sync task (last_error). Arch §6."""
    p = Path(path)
    if not p.is_absolute():
        raise ValueError("vault_path must be absolute")
    if not p.exists():
        raise ValueError("vault_path does not exist")
    resolved = p.resolve()
    if not resolved.is_dir():
        raise ValueError("vault_path is not a directory")
    import os as _os
    if not _os.access(resolved, _os.R_OK | _os.X_OK):
        raise ValueError("vault_path is not readable")
    if resolved == Path("/") or resolved == Path.home().resolve():
        raise ValueError("vault_path may not be / or the home directory itself")
    import app as _app_pkg
    project_root = Path(_app_pkg.__file__).resolve().parent.parent
    if resolved == project_root or project_root in resolved.parents or resolved in project_root.parents:
        raise ValueError("vault_path may not contain or be contained by the API project")
    return resolved


# ── external_id scheme (arch §3.3) ──────────────────────────────────────
# Format: obsidian:{source_id}:{kind}:{key}. source_id is the state_sources
# UUID so two vaults never collide. Checkbox STATE is stripped from task keys
# (toggle keeps the id); goal/project identity is their text, vault-wide.

def external_id_for_note(source_id: str, rel_path: str, fm: dict) -> str:
    if fm.get("founderos_id"):
        return f"obsidian:{source_id}:note:id:{fm['founderos_id']}"
    return f"obsidian:{source_id}:note:{_norm_rel_path(rel_path)}"


def external_id_for_task(source_id: str, rel_path: str, norm_text: str, ordinal: int) -> str:
    base = f"obsidian:{source_id}:task:{_norm_rel_path(rel_path)}:{_sha16(norm_text)}"
    return base if ordinal == 1 else f"{base}:{ordinal}"


def _first_paragraph(body: str, cap: int = 500) -> str:
    for block in body.split("\n\n"):
        block = "\n".join(
            l for l in block.split("\n")
            if not _HEADING_RE.match(l) and not _CHECKBOX_RE.match(l)
        ).strip()
        if block:
            return block[:cap]
    return ""


def events_for_note(source_id: str, rel_path: str, parsed: ParsedNote, observed_at):
    """Map one parsed note to ObservedEvents (arch §3.4).

    The note itself always emits obsidian.note; frontmatter goal:/project: and
    decision tag/path emit ADDITIONAL entities with their own identities.
    """
    from app.integrations.base import ObservedEvent

    rel = _norm_rel_path(rel_path)
    stem = rel.rsplit("/", 1)[-1].removesuffix(".md")
    fm = parsed.frontmatter
    events: list = []

    def _ev(kind: str, external_id: str, payload: dict) -> None:
        events.append(ObservedEvent(
            source="obsidian", kind=kind, external_id=external_id,
            payload=payload, observed_at=observed_at,
        ))

    goals = fm.get("goal")
    goal_values = [goals] if isinstance(goals, str) else list(goals or [])
    project_name = fm.get("project") if isinstance(fm.get("project"), str) else None
    if project_name is None and rel.startswith("Projects/"):
        project_name = stem
    is_decision = "decision" in parsed.tags or rel.split("/", 1)[0] == "Decisions"

    note_title = parsed.h1 or stem
    summary = _first_paragraph(parsed.body)
    note_eid = external_id_for_note(source_id, rel, fm)
    mentions = [*goal_values, *( [project_name] if project_name else [] )]
    _ev("obsidian.note", note_eid, {
        "entity_type": "note", "title": note_title, "summary": summary,
        "attributes": {"path": rel, "tags": sorted(parsed.tags), "frontmatter": {k: str(v) for k, v in fm.items()}},
        "relation_hints": {"mentions": mentions},
    })

    for value in goal_values:
        _ev("obsidian.goal", f"obsidian:{source_id}:goal:{_sha16(str(value))}", {
            "entity_type": "goal", "title": str(value), "summary": summary,
            "attributes": {"asserted_in": rel},
            "relation_hints": {},
        })

    if project_name:
        _ev("obsidian.project", f"obsidian:{source_id}:project:{_sha16(project_name)}", {
            "entity_type": "project", "title": project_name, "summary": summary,
            "attributes": {"note_path": rel},
            "relation_hints": {},
        })

    if is_decision:
        _ev("obsidian.decision", f"obsidian:{source_id}:decision:{rel}", {
            "entity_type": "decision", "title": note_title, "summary": summary or parsed.body[:500].strip(),
            "attributes": {"path": rel, "tags": sorted(parsed.tags)},
            "relation_hints": {},
        })

    task_eids: list[str] = []
    for box in parsed.checkboxes:
        eid = external_id_for_task(source_id, rel, box.text, box.ordinal)
        task_eids.append(eid)
        hints: dict = {"derived_from_note": note_eid}
        if project_name:
            hints["part_of_project"] = project_name
        if box.parent_index is not None:
            hints["parent_task_external_id"] = task_eids[box.parent_index]
        _ev("obsidian.task", eid, {
            "entity_type": "task", "title": box.text,
            "status": "done" if box.done else "open",
            "attributes": {"note_path": rel, "raw_line": box.text},
            "relation_hints": hints,
        })

    return events
