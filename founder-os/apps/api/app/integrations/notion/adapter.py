"""NotionAdapter — the ADR-010 seam for the State Engine (arch §3.1, §6).

Composes client (transport) + mapper (pure). No reconciliation logic, no DB
writes: cursor/ledger state returns to StateService via the observe_source
tuple and SyncResult.data (D5).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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
from app.integrations.notion import mapper
from app.integrations.notion.client import (
    ManagedTreeViolation,
    NotionAPIError,
    NotionClient,
)

logger = logging.getLogger(__name__)

WATERMARK_OVERLAP_S = 120


def _client_for(credentials: dict, settings) -> NotionClient:
    return NotionClient(
        credentials["token"],
        api_version=settings.STATE_NOTION_API_VERSION,
        max_rps=settings.STATE_NOTION_MAX_RPS,
        max_retries=settings.STATE_NOTION_MAX_RETRIES,
        timeout_s=settings.STATE_NOTION_TIMEOUT_S,
    )


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class NotionAdapter(IntegrationAdapter):
    name = "notion"
    capabilities = Capability.OBSERVE | Capability.SYNC | Capability.HEALTH

    async def configure(self, settings: dict[str, Any]) -> None:
        return None  # no globals: per-source config + DB-resolved token

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="remote adapter; per-source checks at registration/sync")

    def check_source(self, source_config: dict, *, has_token: bool = True) -> HealthStatus:
        """NON-network (arch §8.2): list endpoints must stay fast."""
        if not has_token:
            return HealthStatus(ok=False, detail="no active Notion integration token — re-register with a token")
        if not source_config.get("managed_root_page_id"):
            return HealthStatus(ok=False, detail="managed_root_page_id missing from config")
        return HealthStatus(ok=True, detail="token present; root configured (connectivity verified at registration/sync)")

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        """Aggregate ADR-010 surface (mirrors Obsidian's)."""
        from sqlalchemy import select

        from app.database import async_session_factory
        from app.integrations.credentials import resolve_source_credentials
        from app.state.models import StateSource

        events: list[ObservedEvent] = []
        async with async_session_factory() as db:
            result = await db.execute(
                select(StateSource).where(
                    StateSource.user_id == user_id,
                    StateSource.type == "notion",
                    StateSource.status != "paused",
                )
            )
            for source in result.scalars():
                creds = await resolve_source_credentials(db, source)
                evs, _cursor = await self.observe_source(
                    source.config, str(source.id),
                    credentials=creds, sync_cursor=source.sync_cursor,
                )
                events.extend(evs)
        return events

    # ── inbound (arch §3.3, §6) ──────────────────────────────────────────

    async def observe_source(
        self,
        source_config: dict,
        source_key: str,
        *,
        credentials: dict | None = None,
        sync_cursor: dict | None = None,
        full_walk: bool = False,
        seen_external_uuids: set[str] | None = None,
    ) -> tuple[list[ObservedEvent], dict]:
        if not credentials or not credentials.get("token"):
            from app.integrations.credentials import CredentialsMissing

            raise CredentialsMissing("Notion source has no resolved token")

        settings = get_settings()
        cursor = dict(sync_cursor or {})
        now = datetime.now(timezone.utc)
        do_full = (
            full_walk
            or not cursor.get("last_edited_watermark")
            or not cursor.get("last_full_walk_at")
            or (now - _parse_iso(cursor["last_full_walk_at"])).total_seconds()
            > settings.STATE_NOTION_FULL_WALK_EVERY_S
        )

        client = _client_for(credentials, settings)
        try:
            managed_ids = {v["id"] for v in (cursor.get("managed_pages") or {}).values()}
            managed_ids.add(mapper.normalize_uuid(source_config["managed_root_page_id"]))
            excludes = {mapper.normalize_uuid(x) for x in source_config.get("exclude_page_ids") or []}

            watermark = cursor.get("last_edited_watermark")
            cutoff = (
                _parse_iso(watermark) - timedelta(seconds=WATERMARK_OVERLAP_S)
                if (watermark and not do_full) else None
            )
            if cutoff is not None:
                # S1: incremental = newest-first scan that STOPS at the
                # watermark window — O(edits), not O(workspace).
                objects = await client.search_since(
                    _iso(cutoff), max_objects=settings.STATE_NOTION_MAX_OBJECTS)
            else:
                objects = await client.search_all(
                    max_objects=settings.STATE_NOTION_MAX_OBJECTS)

            db_schemas: dict[str, dict] = {}
            events: list[ObservedEvent] = []
            walked_page_uuids: set[str] = set()
            max_edited: datetime | None = None

            pages = [o for o in objects if o.get("object") == "page"]
            for db_obj in (o for o in objects if o.get("object") == "database"):
                db_schemas[mapper.normalize_uuid(db_obj["id"])] = db_obj

            # S2: transitive exclusion — any page whose parent CHAIN reaches the
            # managed root/ledger is engine output (or founder content placed
            # inside it) and must never be observed (feedback loop).
            parent_of = {
                mapper.normalize_uuid(o["id"]):
                    mapper.normalize_uuid((o.get("parent") or {}).get("page_id") or "")
                for o in objects if o.get("object") == "page"
            }
            # S2: titles pre-pass — heuristics like "parent titled Decisions"
            # must not depend on search iteration order.
            page_titles = {
                mapper.normalize_uuid(o["id"]): mapper.title_of(o)
                for o in objects if o.get("object") == "page"
            }
            def _under_managed(pid: str, _seen=None) -> bool:
                _seen = _seen or set()
                while pid and pid not in _seen:
                    if pid in managed_ids:
                        return True
                    _seen.add(pid)
                    pid = parent_of.get(pid, "")
                return False

            for page in pages:
                pid = mapper.normalize_uuid(page["id"])
                edited = _parse_iso(page["last_edited_time"])
                if max_edited is None or edited > max_edited:
                    max_edited = edited
                if pid in excludes or _under_managed(pid):
                    continue
                if page.get("archived") or page.get("in_trash"):
                    events.append(mapper.tombstone_event(
                        source_key, "page", pid, reason="trashed", observed_at=edited))
                    continue
                walked_page_uuids.add(pid)
                if cutoff and edited < cutoff:
                    continue  # incremental: older than watermark window

                parent = page.get("parent") or {}
                schema = None
                if parent.get("type") == "database_id":
                    dbid = mapper.normalize_uuid(parent["database_id"])
                    schema = db_schemas.get(dbid)
                    if schema is None:
                        schema = await client.get_database(dbid)
                        db_schemas[dbid] = schema

                # body fetch only for body-bearing objects (arch §3.3)
                blocks: list[dict] = []
                needs_body = parent.get("type") != "database_id" or (
                    (source_config.get("database_map") or {}).get(
                        mapper.normalize_uuid(parent.get("database_id", ""))) == "decision"
                    or (schema and mapper.plain_text(schema.get("title")).casefold().strip()
                        in mapper.DECISION_DB_TITLES)
                )
                if needs_body:
                    blocks = await client.get_blocks_recursive(page["id"], depth=3)

                event = mapper.event_for_object(
                    source_key, page,
                    db_schemas=db_schemas,
                    database_map=source_config.get("database_map") or {},
                    blocks=blocks,
                    parent_titles=page_titles,
                )
                events.append(event)
                events.extend(mapper.events_for_todo_blocks(source_key, page, blocks))

            # full-walk disappearance diff (arch §3.6.2)
            if do_full and seen_external_uuids:
                for missing in sorted(seen_external_uuids - walked_page_uuids):
                    try:
                        obj = await client.get_page(missing)
                    except NotionAPIError as exc:
                        obj = None if exc.status in (404, 400) else {}
                        if obj == {}:
                            continue  # transient — do not tombstone on uncertainty
                    reason = mapper.classify_tombstone(obj)
                    if reason:
                        events.append(mapper.tombstone_event(
                            source_key, "page", missing, reason=reason, observed_at=now))

            # emission order: goal/project/decision before note/task (S1 lesson)
            order = {"notion.goal": 0, "notion.project": 1, "notion.decision": 2,
                     "notion.note": 3, "notion.task": 4, "notion.tombstone": 5}
            events.sort(key=lambda e: order.get(e.kind, 9))

            new_cursor: dict = {}
            if max_edited is not None:
                new_cursor["last_edited_watermark"] = _iso(max_edited)
            elif watermark:
                new_cursor["last_edited_watermark"] = watermark
            if do_full:
                new_cursor["last_full_walk_at"] = _iso(now)
            new_cursor["_counters"] = dict(client.counters)
            return events, new_cursor
        finally:
            await client.close()

    # ── outbound (arch §5) ───────────────────────────────────────────────

    async def sync(self, user_id: str, changes: list[dict[str, Any]]) -> SyncResult:
        """changes: [{"config":…, "files": {path: md}, "credentials":…, "ledger":…}]."""
        settings = get_settings()
        pushed = 0
        skipped = 0
        errors: list[str] = []
        ledger_out: dict = {}
        for change in changes:
            config = change["config"]
            root = mapper.normalize_uuid(config["managed_root_page_id"])
            ledger = dict(change.get("ledger") or {})
            client = _client_for(change["credentials"], settings)
            try:
                files: dict[str, str] = change["files"]
                prepared = {k: mapper.prepare_managed_markdown(v) for k, v in files.items()}
                # ensure the Projects container exists when project pages do
                needs_container = any(k.startswith("Projects/") for k in prepared)
                if needs_container and "Projects" not in ledger:
                    await client.write_managed_page(
                        ledger, root, "Projects", "Projects", [],
                        content_hash="",
                    )
                for key in sorted(prepared):
                    md = prepared[key]
                    if not mapper.should_write(ledger, key, md):
                        skipped += 1
                        continue
                    title = key.rsplit("/", 1)[-1].removesuffix(".md")
                    parent_key = "Projects" if key.startswith("Projects/") else None
                    await client.write_managed_page(
                        ledger, root, key, title, mapper.md_to_blocks(md),
                        parent_key=parent_key,
                        content_hash=mapper.should_write.hash_of(md),
                    )
                    pushed += 1
                keep = set(prepared) | ({"Projects"} if needs_container else set())
                await client.prune_managed_pages(ledger, keep=keep, managed_root_id=root)
                ledger_out = ledger
            except ManagedTreeViolation as exc:
                logger.error("managed-tree violation during notion sync: %s", exc)
                errors.append(str(exc))
                ledger_out = ledger   # S2b: persist partial appends — created ids
            except NotionAPIError as exc:
                errors.append(str(exc))
                ledger_out = ledger   # S2b: never orphan engine-created pages
            finally:
                await client.close()
        return SyncResult(
            ok=not errors, pushed=pushed, errors=errors,
            data={"managed_pages": ledger_out, "pages_written": pushed,
                  "pages_skipped_unchanged": skipped},
        )


def register_adapter() -> None:
    if "notion" in registry.all_adapters():
        return
    registry.register(NotionAdapter())
