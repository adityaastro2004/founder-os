"""
Shared user-identity resolution.
================================
Maps a Clerk user id to the internal ``users.id`` UUID, creating a minimal users row
on first sight (same semantics as onboarding's _get_or_create_user).

Why this exists: several routes used to derive a *synthetic* UUID
(``uuid5(NAMESPACE_URL, "clerk:<id>")``) that was never inserted into ``users`` — so
any INSERT into an FK-constrained table (knowledge_items, tasks, outputs, …) for a
user who hadn't completed onboarding violated ``*_user_id_fkey`` and 500'd. All
routes/tasks now resolve identity through this helper so reads and writes share one
real key.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_or_create_user_id(
    clerk_user_id: str,
    db: AsyncSession,
    *,
    email: str | None = None,
) -> uuid.UUID:
    """Return the internal ``users.id`` for a Clerk user, creating the row if needed.

    Race-safe: uses ``INSERT … ON CONFLICT (clerk_user_id) DO NOTHING`` then selects.
    """
    result = await db.execute(select(User.id).where(User.clerk_user_id == clerk_user_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    await db.execute(
        pg_insert(User)
        .values(
            clerk_user_id=clerk_user_id,
            email=email or f"{clerk_user_id}@placeholder.local",
        )
        .on_conflict_do_nothing(index_elements=["clerk_user_id"])
    )
    result = await db.execute(select(User.id).where(User.clerk_user_id == clerk_user_id))
    return result.scalar_one()
