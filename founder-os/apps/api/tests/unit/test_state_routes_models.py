"""State routes: request validation shapes + router registration (arch §5)."""
import pytest
from pydantic import ValidationError

from app.api.state_routes import (
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


def test_source_create_only_obsidian_in_slice1():
    with pytest.raises(ValidationError):
        SourceCreateRequest(type="notion", config=ObsidianConfig(vault_path="/x"))


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
