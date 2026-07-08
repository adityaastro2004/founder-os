"""Per-source credential resolution (Phase 2 arch §2.2).

Tokens live on the existing `integrations` table — NEVER in
state_sources.config, never in logs, never in error messages.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class CredentialsMissing(Exception):
    """No active credential row for this source's type. Message is token-free."""


async def resolve_source_credentials(db: AsyncSession, source) -> dict[str, str]:
    """Type-keyed lookup. Obsidian → {}. Notion → {"token": <access_token>}."""
    if source.type != "notion":
        return {}

    from app.models import Integration

    row = (await db.execute(
        select(Integration).where(
            Integration.user_id == source.user_id,
            Integration.integration_type == "notion",
            Integration.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if row is None or not row.access_token:
        raise CredentialsMissing(
            "no active Notion integration for this user — re-register the "
            "source with a token (PATCH /api/state/sources/{id})"
        )
    return {"token": row.access_token}
