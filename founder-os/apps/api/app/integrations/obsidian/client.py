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
