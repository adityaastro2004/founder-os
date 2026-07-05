"""ObsidianAdapter — the ADR-010 seam for the State Engine (arch §3.1).

Carries NO reconciliation logic: observe_source walks + parses and emits
provenance-tagged ObservedEvents; sync writes rendered files exclusively
through the jailed client.write_managed sink.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.integrations import registry
from app.integrations.base import (
    Capability,
    HealthStatus,
    IntegrationAdapter,
    ObservedEvent,
    SyncResult,
)
from app.integrations.obsidian import client

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDES = [".obsidian", ".trash", "Templates", "FounderOS"]


class ObsidianAdapter(IntegrationAdapter):
    name = "obsidian"
    capabilities = Capability.OBSERVE | Capability.SYNC | Capability.HEALTH

    async def configure(self, settings: dict[str, Any]) -> None:
        # No global credentials; per-source config lives on state_sources rows.
        return None

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="local adapter; per-source checks via check_source")

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        """All active obsidian sources for the user (ADR-010 uniform surface).

        StateService uses observe_source directly for single-source sync runs;
        this aggregate path resolves sources from the DB lazily to stay usable
        from generic adapter tooling.
        """
        from sqlalchemy import select

        from app.database import async_session_factory
        from app.state.models import StateSource

        events: list[ObservedEvent] = []
        async with async_session_factory() as db:
            result = await db.execute(
                select(StateSource).where(
                    StateSource.user_id == user_id,
                    StateSource.type == "obsidian",
                    StateSource.status != "paused",
                )
            )
            for source in result.scalars():
                events.extend(await self.observe_source(source.config, str(source.id)))
        return events

    async def observe_source(self, source_config: dict, source_key: str) -> list[ObservedEvent]:
        settings = get_settings()
        vault = client.validate_vault_path(source_config["vault_path"])
        managed = source_config.get("managed_folder", "FounderOS")
        excludes = list(source_config.get("exclude_dirs") or DEFAULT_EXCLUDES)
        if managed not in excludes:
            excludes.append(managed)  # NEVER observe our own output (feedback loop)

        now = datetime.now(timezone.utc)
        events: list[ObservedEvent] = []
        for rel_path, text in client.walk_vault(
            vault,
            exclude_dirs=excludes,
            max_files=settings.STATE_OBSIDIAN_MAX_FILES,
            max_file_bytes=settings.STATE_OBSIDIAN_MAX_FILE_BYTES,
        ):
            parsed = client.parse_note(rel_path, text)
            events.extend(client.events_for_note(source_key, rel_path, parsed, now))
        return events

    async def sync(self, user_id: str, changes: list[dict[str, Any]]) -> SyncResult:
        """changes: [{"config": <source config>, "files": {rel_path: content}}]."""
        pushed = 0
        errors: list[str] = []
        for change in changes:
            config = change["config"]
            vault = config["vault_path"]
            managed = config.get("managed_folder", "FounderOS")
            files: dict[str, str] = change["files"]
            try:
                for rel_path, content in sorted(files.items()):
                    client.write_managed(vault, managed, rel_path, content)
                    pushed += 1
                client.prune_managed(vault, managed, keep=set(files))
            except client.ManagedFolderViolation as exc:
                # P0 invariant: fail loudly, never silently skip (arch §4.4)
                logger.error("managed-folder violation during sync: %s", exc)
                errors.append(str(exc))
        return SyncResult(ok=not errors, pushed=pushed, errors=errors)

    def check_source(self, source_config: dict) -> HealthStatus:
        """Per-source health (arch §6). Never mutates the vault."""
        try:
            vault = client.validate_vault_path(source_config["vault_path"])
        except ValueError as exc:
            return HealthStatus(ok=False, detail=f"vault_path invalid: {exc}")
        managed = vault / source_config.get("managed_folder", "FounderOS")
        import os
        if managed.exists():
            if not managed.is_dir() or not os.access(managed, os.W_OK):
                return HealthStatus(ok=False, detail="managed folder exists but is not a writable directory")
        elif not os.access(vault, os.W_OK):
            return HealthStatus(ok=False, detail="vault root is not writable (cannot create managed folder)")
        md_count = sum(1 for _ in _capped_md_iter(vault, cap=2000))
        return HealthStatus(ok=True, detail=f"vault ok; md_files={md_count}")


def _capped_md_iter(vault: Path, cap: int):
    n = 0
    for p in vault.rglob("*.md"):
        yield p
        n += 1
        if n >= cap:
            return


def register_adapter() -> None:
    # Idempotent: lifespan can run more than once per process (S2 lesson).
    if "obsidian" in registry.all_adapters():
        return
    registry.register(ObsidianAdapter())
