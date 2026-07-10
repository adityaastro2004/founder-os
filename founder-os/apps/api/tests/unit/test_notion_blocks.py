"""md→blocks conversion + churn-free rendering (arch §5)."""
from app.integrations.notion.mapper import (
    md_to_blocks,
    prepare_managed_markdown,
    should_write,
)

MD = """# Tasks

## Launch v2
- [ ] Write the changelog
- [x] Cut release branch
- plain bullet

**bold** and *italic* text paragraph.

> Managed by Founder OS — edits here are overwritten. Last synced 2026-07-08 10:00 UTC.
"""


def test_footer_swapped_static_and_hash_stable():
    a = prepare_managed_markdown(MD)
    b = prepare_managed_markdown(MD.replace("2026-07-08 10:00", "2026-07-09 22:31"))
    assert a == b  # timestamped footer replaced by the static one
    assert "Last synced" not in a
    assert "Managed by Founder OS" in a


def test_should_write_skips_on_matching_ledger_hash():
    md = prepare_managed_markdown(MD)
    ledger = {"Tasks.md": {"id": "p1", "hash": should_write.hash_of(md)}}
    assert should_write(ledger, "Tasks.md", md) is False
    assert should_write(ledger, "Tasks.md", md + "\nnew line") is True
    assert should_write({}, "Tasks.md", md) is True


def test_md_to_blocks_dialect():
    blocks = md_to_blocks(prepare_managed_markdown(MD))
    types = [b["type"] for b in blocks]
    assert types[0] == "heading_1"
    assert "heading_2" in types
    todos = [b for b in blocks if b["type"] == "to_do"]
    assert len(todos) == 2
    assert todos[0]["to_do"]["checked"] is False
    assert todos[1]["to_do"]["checked"] is True
    assert any(b["type"] == "bulleted_list_item" for b in blocks)
    assert any(b["type"] == "quote" for b in blocks)
    para = next(b for b in blocks if b["type"] == "paragraph")
    annots = [(r.get("annotations") or {}) for r in para["paragraph"]["rich_text"]]
    assert any(a.get("bold") for a in annots) and any(a.get("italic") for a in annots)


def test_batching_at_100_blocks():
    md = "\n".join(f"- bullet {i}" for i in range(250))
    blocks = md_to_blocks(md)
    from app.integrations.notion.mapper import batch_blocks

    batches = batch_blocks(blocks)
    assert all(len(b) <= 100 for b in batches)
    assert sum(len(b) for b in batches) == len(blocks)


def test_long_rich_text_split_at_2000():
    md = "x" * 4500
    blocks = md_to_blocks(md)
    runs = blocks[0]["paragraph"]["rich_text"]
    assert all(len(r["text"]["content"]) <= 2000 for r in runs)
    assert "".join(r["text"]["content"] for r in runs) == md
