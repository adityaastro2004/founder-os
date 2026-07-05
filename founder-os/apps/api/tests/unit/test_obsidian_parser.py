"""Obsidian parser (arch §3.2): frontmatter, headings, checkboxes, tags, walk rules."""
import pathlib

import pytest

from app.integrations.obsidian.client import parse_note, walk_vault


def test_frontmatter_and_h1_and_body():
    text = "---\ngoal: Reach $10k MRR\ntags: [q3, focus]\n---\n# The Plan\n\nBody text here.\n"
    note = parse_note("Notes/plan.md", text)
    assert note.frontmatter["goal"] == "Reach $10k MRR"
    assert note.h1 == "The Plan"
    assert "q3" in note.tags and "focus" in note.tags
    assert "Body text here." in note.body
    assert "goal:" not in note.body  # frontmatter stripped


def test_malformed_yaml_falls_back_to_body():
    text = "---\n: not: [valid yaml\n---\n# Still Readable\ncontent\n"
    note = parse_note("bad.md", text)
    assert note.frontmatter == {}
    assert "Still Readable" in note.body or note.h1 == "Still Readable"


def test_checkbox_states_and_nesting():
    text = (
        "# Tasks\n"
        "- [ ] parent task\n"
        "    - [x] child done\n"
        "- [X] upper done\n"
        "* [ ] star marker\n"
        "not a checkbox - [ ] inline\n"
    )
    note = parse_note("t.md", text)
    boxes = note.checkboxes
    assert [(b.text, b.done) for b in boxes] == [
        ("parent task", False),
        ("child done", True),
        ("upper done", True),
        ("star marker", False),
    ]
    assert boxes[1].parent_index == 0          # nested under parent task
    assert boxes[0].parent_index is None
    assert boxes[3].parent_index is None


def test_inline_and_frontmatter_tags_merge():
    text = "---\ntags: decision\n---\nWe chose #postgres over #mysql/legacy\n"
    note = parse_note("d.md", text)
    assert {"decision", "postgres", "mysql/legacy"} <= note.tags


def test_crlf_and_empty_file():
    note = parse_note("crlf.md", "# Title\r\n- [ ] task one\r\n")
    assert note.h1 == "Title"
    assert note.checkboxes[0].text == "task one"
    empty = parse_note("empty.md", "")
    assert empty.h1 is None and empty.checkboxes == [] and empty.body == ""


def test_walk_vault_excludes_and_caps(tmp_path: pathlib.Path):
    (tmp_path / "Notes").mkdir()
    (tmp_path / "Notes" / "a.md").write_text("# A")
    (tmp_path / "FounderOS").mkdir()
    (tmp_path / "FounderOS" / "Goals.md").write_text("# managed — never observed")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "conf.md").write_text("x")
    (tmp_path / "big.md").write_text("x" * 2_000_000)
    (tmp_path / "not_md.txt").write_text("x")

    files = walk_vault(
        tmp_path,
        exclude_dirs=[".obsidian", ".trash", "Templates", "FounderOS"],
        max_files=100,
        max_file_bytes=1_048_576,
    )
    rels = sorted(rel for rel, _ in files)
    assert rels == ["Notes/a.md"]  # excluded dirs, oversize, non-md all skipped
