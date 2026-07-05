"""Renderer (arch §2.6): pure, deterministic, grouped, footered, no filesystem."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def ent(entity_type, title, *, status=None, summary=None, eid=None,
        confidence=0.7, last_asserted_at=NOW, attributes=None):
    return SimpleNamespace(
        id=eid or uuid.uuid4(), entity_type=entity_type, title=title,
        status=status or ("open" if entity_type == "task" else "active"),
        summary=summary, confidence=confidence, last_asserted_at=last_asserted_at,
        attributes=attributes or {},
    )


def rel(src, tgt, rtype):
    return SimpleNamespace(source_entity_id=src.id, target_entity_id=tgt.id,
                           relation_type=rtype)


def build():
    goal = ent("goal", "Reach $10k MRR", summary="North star")
    project = ent("project", "Launch v2", summary="Ship the new version")
    t_open = ent("task", "Write changelog")
    t_done = ent("task", "Cut release branch", status="done")
    t_orphan = ent("task", "Pay invoice")
    decision = ent("decision", "Use Postgres", summary="Chose Postgres over MySQL")
    rels = [rel(t_open, project, "part_of"), rel(t_done, project, "part_of")]
    return [goal, project, t_open, t_done, t_orphan, decision], rels


def test_renders_expected_files_with_grouping_and_footer():
    from app.state.renderer import render

    entities, rels = build()
    files = render(entities, rels, now=NOW)

    assert set(files) == {"Goals.md", "Tasks.md", "Decisions.md", "Projects/Launch v2.md"}
    assert "Reach $10k MRR" in files["Goals.md"]
    proj = files["Projects/Launch v2.md"]
    assert "Write changelog" in proj and "Cut release branch" in proj
    assert proj.index("Write changelog") < proj.index("Cut release branch")  # open before done
    tasks = files["Tasks.md"]
    assert "Pay invoice" in tasks  # unassigned rendered too
    assert tasks.index("Launch v2") < tasks.index("Pay invoice")  # grouped before unassigned
    assert "Use Postgres" in files["Decisions.md"]
    for content in files.values():
        assert "Managed by Founder OS" in content


def test_rerender_is_byte_identical():
    from app.state.renderer import render

    entities, rels = build()
    a = render(entities, rels, now=NOW)
    b = render(list(reversed(entities)), list(reversed(rels)), now=NOW)
    assert a == b  # stable sort → no vault churn


def test_slug_fallback_for_hostile_project_names():
    from app.state.renderer import render

    import re

    p = ent("project", "../../etc :: <evil>")
    files = render([p], [], now=NOW)
    (path,) = [k for k in files if k.startswith("Projects/")]
    # exactly Projects/<jail-safe-name>.md — no dots, slashes, or specials survive
    assert re.fullmatch(r"Projects/[A-Za-z0-9 _-]+\.md", path), path

    empty = ent("project", ":::")
    files2 = render([empty], [], now=NOW)
    (path2,) = [k for k in files2 if k.startswith("Projects/")]
    assert re.fullmatch(r"Projects/project-[0-9a-f]{8}\.md", path2), path2


def test_renderer_module_is_pure():
    import inspect

    import app.state.renderer as r

    src = inspect.getsource(r)
    for forbidden in ("open(", "write_text", "os.remove", "shutil", "unlink"):
        assert forbidden not in src, f"renderer must not touch the filesystem: {forbidden}"
