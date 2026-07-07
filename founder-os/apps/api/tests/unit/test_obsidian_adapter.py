"""ObsidianAdapter (arch §3.1): fixture-vault observation + jailed sync writes."""
import pathlib
import shutil
from unittest.mock import patch

from app.integrations.base import Capability
from app.integrations.obsidian.adapter import ObsidianAdapter, register_adapter
from app.integrations import registry

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "obsidian_vault"
SRC = "99999999-8888-7777-6666-555555555555"


def config_for(vault: pathlib.Path) -> dict:
    return {
        "vault_path": str(vault),
        "managed_folder": "FounderOS",
        "exclude_dirs": [".obsidian", ".trash", "Templates", "FounderOS"],
    }


def test_identity_and_capabilities():
    a = ObsidianAdapter()
    assert a.name == "obsidian"
    for cap in (Capability.OBSERVE, Capability.SYNC, Capability.HEALTH):
        assert cap in a.capabilities


def test_register_adapter_idempotent():
    registry._reset_for_tests()
    try:
        register_adapter()
        register_adapter()  # second call must not raise (S2 lesson)
        assert registry.get("obsidian").name == "obsidian"
    finally:
        registry._reset_for_tests()


async def test_observe_source_emits_expected_events(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE, vault)
    a = ObsidianAdapter()

    events = await a.observe_source(config_for(vault), SRC)

    kinds = sorted(e.kind for e in events)
    # 7 observable notes... minus excluded Templates → 7 files: Goals, Launch v2,
    # Pricing decision, Weekly review, Idea, Idea copy, todo → 7 note events
    assert kinds.count("obsidian.note") == 7
    assert kinds.count("obsidian.goal") == 1
    assert kinds.count("obsidian.project") == 1
    assert kinds.count("obsidian.decision") == 1
    assert kinds.count("obsidian.task") == 5  # 4 in Launch v2 + 1 in Weekly review
    # excluded dir never observed
    assert not any("Templates" in e.external_id for e in events)
    # all provenance-tagged observed, source_id baked into ids
    assert all(e.provenance == "observed" for e in events)
    assert all(f":{SRC}:" in e.external_id or SRC in e.external_id for e in events)


async def test_sync_writes_only_via_write_managed(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE, vault)
    a = ObsidianAdapter()
    files = {"Goals.md": "# G", "Projects/X.md": "# X"}

    with patch("app.integrations.obsidian.adapter.client.write_managed") as wm, \
         patch("app.integrations.obsidian.adapter.client.prune_managed") as pm:
        result = await a.sync("user-1", [{
            "config": config_for(vault), "files": files,
        }])

    assert result.ok and result.pushed == 2
    written = {call.args[2] for call in wm.call_args_list}
    assert written == {"Goals.md", "Projects/X.md"}
    for call in wm.call_args_list:
        assert not str(call.args[2]).startswith("/")  # relative paths only
    pm.assert_called_once()
    assert pm.call_args.kwargs.get("keep") == set(files) or pm.call_args.args[-1] == set(files)


def test_check_source_health(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE, vault)
    a = ObsidianAdapter()

    ok = a.check_source(config_for(vault))
    assert ok.ok is True and "md_files=" in ok.detail

    bad = a.check_source({"vault_path": str(tmp_path / "missing"), "managed_folder": "FounderOS"})
    assert bad.ok is False
    # health must not create the managed folder (never mutates)
    assert not (vault / "FounderOS").exists()
