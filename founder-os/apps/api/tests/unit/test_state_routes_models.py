"""State routes: request validation shapes + router registration (arch §5)."""
import pytest
from pydantic import ValidationError

from app.api.state_routes import (
    NotionConfig,
    ObsidianConfig,
    SourceCreateRequest,
    SyncTriggerRequest,
    _validated_config,
)


def test_router_registered_on_app():
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/state/sources" in paths
    assert "/api/state/entities" in paths
    assert "/api/state/sources/{source_id}/sync" in paths


def test_source_create_rejects_unknown_types():
    # Phase 1 pinned "obsidian only"; Phase 2 adds notion — unknown still rejected.
    with pytest.raises(ValidationError):
        SourceCreateRequest(type="slack", config=ObsidianConfig(vault_path="/x"))


def test_managed_folder_name_is_jail_safe_charset():
    with pytest.raises(ValidationError):
        ObsidianConfig(vault_path="/x", managed_folder="../escape")
    with pytest.raises(ValidationError):
        ObsidianConfig(vault_path="/x", managed_folder="a/b")


def test_sync_direction_literal():
    assert SyncTriggerRequest().direction == "both"
    with pytest.raises(ValidationError):
        SyncTriggerRequest(direction="sideways")


async def test_validated_config_rejects_bad_paths_as_422():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _validated_config(ObsidianConfig(vault_path="relative/path"))
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        await _validated_config(ObsidianConfig(vault_path="/nonexistent-vault-xyz"))
    assert exc.value.status_code == 422


async def test_validated_config_appends_managed_folder_to_excludes(tmp_path):
    cfg = await _validated_config(ObsidianConfig(vault_path=str(tmp_path)))
    assert "FounderOS" in cfg["exclude_dirs"]  # never observe our own output


# ── Phase 2 (D6): Notion source type ─────────────────────────────────────

def test_notion_config_token_is_secret_and_absent_from_dumps():
    cfg = NotionConfig(managed_root_page_id="a" * 32, token="ntn_super_secret")
    assert "ntn_super_secret" not in repr(cfg)
    assert "ntn_super_secret" not in str(cfg.model_dump())


def test_source_create_accepts_both_types():
    from app.api.state_routes import SourceCreateRequest

    ok = SourceCreateRequest(type="notion",
                             config=NotionConfig(managed_root_page_id="a" * 32))
    assert ok.type == "notion"
    ok2 = SourceCreateRequest(type="obsidian", config=ObsidianConfig(vault_path="/x"))
    assert ok2.type == "obsidian"
    with pytest.raises(ValidationError):
        SourceCreateRequest(type="github", config=ObsidianConfig(vault_path="/x"))


def test_notion_root_page_id_length_bounds():
    with pytest.raises(ValidationError):
        NotionConfig(managed_root_page_id="short")


def test_database_map_values_constrained():
    with pytest.raises(ValidationError):
        NotionConfig(managed_root_page_id="a" * 32,
                     database_map={"db1": "spaceship"})


def test_sync_trigger_full_walk_default_false():
    from app.api.state_routes import SyncTriggerRequest

    assert SyncTriggerRequest().full_walk is False
    assert SyncTriggerRequest(full_walk=True).full_walk is True
