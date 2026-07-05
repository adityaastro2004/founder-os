"""Managed-folder write jail (arch §4) — any escape is P0 per task 011.

Battery: traversal, absolute paths, backslashes, symlink escapes, prune scope.
"""
import pathlib

import pytest

from app.integrations.obsidian.client import (
    ManagedFolderViolation,
    prune_managed,
    validate_vault_path,
    write_managed,
)

MANAGED = "FounderOS"


@pytest.fixture()
def vault(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "Notes").mkdir()
    (tmp_path / "Notes" / "keep.md").write_text("# untouched")
    return tmp_path


def test_happy_path_writes_inside_managed(vault):
    write_managed(vault, MANAGED, "Goals.md", "# Goals")
    write_managed(vault, MANAGED, "Projects/Launch.md", "# Launch")
    assert (vault / MANAGED / "Goals.md").read_text() == "# Goals"
    assert (vault / MANAGED / "Projects" / "Launch.md").exists()


@pytest.mark.parametrize("bad", [
    "../escape.md",
    "a/../../b.md",
    "/etc/passwd",
    "..\\win.md",
    "FounderOS/../Notes.md",
    "",
])
def test_traversal_battery_rejected(vault, bad):
    with pytest.raises(ManagedFolderViolation):
        write_managed(vault, MANAGED, bad, "x")


def test_managed_folder_config_cannot_escape_vault(vault):
    with pytest.raises(ManagedFolderViolation):
        write_managed(vault, "../outside", "Goals.md", "x")


def test_symlinked_subdir_pointing_outside_rejected(vault, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    managed = vault / MANAGED
    managed.mkdir()
    (managed / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ManagedFolderViolation):
        write_managed(vault, MANAGED, "link/evil.md", "x")


def test_symlinked_vault_root_allowed(vault, tmp_path_factory):
    alias_dir = tmp_path_factory.mktemp("alias")
    alias = alias_dir / "vault-link"
    alias.symlink_to(vault, target_is_directory=True)
    write_managed(alias, MANAGED, "Goals.md", "# via symlinked root")
    assert (vault / MANAGED / "Goals.md").read_text() == "# via symlinked root"


def test_prune_only_deletes_owned_md_absent_from_keepset(vault):
    write_managed(vault, MANAGED, "Goals.md", "g")
    write_managed(vault, MANAGED, "Tasks.md", "t")
    write_managed(vault, MANAGED, "Projects/Old.md", "o")
    (vault / MANAGED / "not-markdown.txt").write_text("keep me")

    prune_managed(vault, MANAGED, keep={"Goals.md"})

    assert (vault / MANAGED / "Goals.md").exists()
    assert not (vault / MANAGED / "Tasks.md").exists()
    assert not (vault / MANAGED / "Projects" / "Old.md").exists()
    assert (vault / MANAGED / "not-markdown.txt").exists()  # non-md never touched
    assert (vault / "Notes" / "keep.md").exists()           # outside managed never touched


def test_validate_vault_path_rules(vault, tmp_path):
    assert validate_vault_path(str(vault)) == vault.resolve()
    with pytest.raises(ValueError):
        validate_vault_path("relative/path")
    with pytest.raises(ValueError):
        validate_vault_path(str(tmp_path / "missing"))
    f = tmp_path / "file.md"
    f.write_text("x")
    with pytest.raises(ValueError):
        validate_vault_path(str(f))          # not a directory
    with pytest.raises(ValueError):
        validate_vault_path("/")             # root refused
    with pytest.raises(ValueError):
        validate_vault_path(str(pathlib.Path.home()))  # home itself refused
    import app as app_pkg
    repo_root = pathlib.Path(app_pkg.__file__).resolve().parent.parent
    with pytest.raises(ValueError):
        validate_vault_path(str(repo_root))  # the codebase is not a vault
