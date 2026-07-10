"""Dedup-on-ingest (arch §2.4–2.5): semantic candidate search + merge semantics.

find_similar reuses the existing embedder (zero-padding 768→1536 is
cosine-preserving, so the threshold is meaningful). The F3 lesson applies:
similarity is selected with an explicit float8 CAST — asyncpg type inference
on pgvector expressions is the recorded trap.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_ALIASES = 5


def embed_text_for(entity: Any) -> str:
    """Canonical embed text (arch §2.4): type + title + capped summary."""
    return f"{entity.entity_type}: {entity.title}\n{(entity.summary or '')[:500]}"


async def find_similar(
    db: AsyncSession,
    user_id: uuid.UUID,
    entity_type: str,
    vec: list[float],
    threshold: float,
) -> tuple[uuid.UUID | None, float]:
    """Top match of the same user+type at/above threshold, else (None, best)."""
    sql = text("""
        SELECT id,
               CAST(1 - (embedding <=> CAST(:vec AS vector)) AS float8) AS similarity
        FROM company_state_entities
        WHERE user_id = :uid
          AND entity_type = :etype
          AND is_active = true
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT 5
    """)
    rows = (await db.execute(sql, {
        "vec": str(vec), "uid": str(user_id), "etype": entity_type,
    })).fetchall()
    if not rows:
        return None, 0.0
    best = rows[0]
    if float(best.similarity) >= threshold:
        return best.id, float(best.similarity)
    return None, float(best.similarity)


def merge(existing: Any, candidate: Any, observation: Any, *, hard_match: bool = False) -> dict:
    """Fold a candidate into the existing entity (arch §2.5 + Phase 2 D2).

    hard_match=False (fuzzy dedup): existing title survives, incoming → alias.
    hard_match=True (same external identity — Notion UUID, obsidian
    founderos_id): the incoming title IS the truth → retitle, old title → alias.
    Returns the change-dict; `_reembed` signals an embedding refresh.
    """
    changes: dict = {}
    attrs = dict(existing.attributes or {})
    aliases = list(attrs.get("aliases") or [])

    inc_title = (candidate.title or "").strip()
    if inc_title and inc_title != existing.title:
        if hard_match:
            changes["title"] = inc_title            # D2: retitle is truth
            if existing.title not in aliases:
                aliases.append(existing.title)
        elif inc_title not in aliases:
            aliases.append(inc_title)
    aliases = aliases[:MAX_ALIASES]

    # attributes: shallow merge, incoming wins per key — except aliases (append)
    inc_attrs = dict(getattr(candidate, "attributes", None) or {})
    inc_attrs.pop("aliases", None)
    attrs.update(inc_attrs)
    attrs["aliases"] = aliases
    changes["attributes"] = attrs

    # summary: replace iff incoming > 20% longer
    inc_summary = getattr(candidate, "summary", None)
    if inc_summary and len(inc_summary) > 1.2 * len(existing.summary or ""):
        changes["summary"] = inc_summary
        changes["_reembed"] = True

    # status: incoming wins iff the observation is newer than the last assertion
    inc_status = getattr(candidate, "status", None)
    if inc_status and inc_status != existing.status \
            and observation.observed_at > existing.last_asserted_at:
        changes["status"] = inc_status

    # confidence: asymptotic bump, never reaches 1.0
    old = float(existing.confidence)
    changes["confidence"] = min(0.99, old + (1 - old) * 0.15)

    # recency + provenance takeover (latest asserter is the provenance shown)
    changes["last_asserted_at"] = max(existing.last_asserted_at, observation.observed_at)
    changes["source_id"] = observation.source_id

    return changes
