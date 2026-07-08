"""RAG mirroring (arch §7): note/decision bodies → knowledge_items, idempotent.

Key: knowledge_items.source_url = "state://{source_id}/{external_id}". The
unchanged-content short-circuit happens upstream (observation hash), so when
this runs the content really changed: delete-then-reingest (chunk counts shift
when notes grow; matching old↔new chunks is complexity with no payoff).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

def kind_mirrors(kind: str) -> bool:
    """D3 (Phase 2): suffix rule, not a per-source set — adapter #3 needs zero
    mirror change. Only unstructured recall payloads mirror."""
    return kind.endswith((".note", ".decision"))


def mirror_key(source_id, external_id: str) -> str:
    return f"state://{source_id}/{external_id}"


async def purge_mirror(db: AsyncSession, *, user_id: uuid.UUID, source_id, external_id: str) -> None:
    """Tombstoned entities take their recall rows with them (D1)."""
    await db.execute(
        text("DELETE FROM knowledge_items WHERE user_id = :u AND source_url = :k"),
        {"u": str(user_id), "k": mirror_key(source_id, external_id)},
    )


async def mirror_entity(
    db: AsyncSession,
    ingester,
    *,
    user_id: uuid.UUID,
    source_id,
    external_id: str,
    kind: str,
    title: str,
    body: str,
) -> bool:
    """Mirror one changed note/decision body. Returns True if re-ingested."""
    if not kind_mirrors(kind) or not body.strip():
        return False
    key = mirror_key(source_id, external_id)
    await db.execute(
        text("DELETE FROM knowledge_items WHERE user_id = :u AND source_url = :k"),
        {"u": str(user_id), "k": key},
    )
    await ingester.ingest_text(
        user_id=user_id,
        content=body,
        title=title,
        category="state_mirror",
        source_url=key,
    )
    return True
