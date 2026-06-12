"""
Founder Context Model builder (Agent Evolution Engine — task 003).
==================================================================
Distils the founder's hard facts (FounderProfile) and soft signals (UserProfileIntel)
into a single structured model that the AgentGenerator consumes to regenerate agent
definitions:

    {business_model, customer_profile, market_profile, operating_style,
     risk_tolerance, goals, summary}

Versioned per founder; a new version is only written when the source inputs change
(detected via a content hash), so regeneration is triggered by real context changes —
not on every call. Provider-neutral (takes an async ``llm_generate(system, prompt)``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FounderContextModel, FounderProfile, UserProfileIntel

logger = logging.getLogger(__name__)

LLMGenerate = Callable[[str, str], Awaitable[str]]

_SYSTEM = (
    "You are a startup strategist building a structured model of a founder's business "
    "so specialist agents can be tailored to it. From the facts and signals provided, "
    "infer a concise, specific model. Respond with STRICT JSON and nothing else:\n"
    '{"business_model": "<how they make money / GTM>", '
    '"customer_profile": "<who they serve>", '
    '"market_profile": "<market shape, competition, dynamics>", '
    '"operating_style": "<how this founder works / cadence / constraints>", '
    '"risk_tolerance": "<conservative|balanced|aggressive + why>", '
    '"goals": "<the founder\'s primary goals, prioritized>", '
    '"summary": "<2-3 sentence strategic summary>"}'
)

_KEYS = (
    "business_model", "customer_profile", "market_profile",
    "operating_style", "risk_tolerance", "goals", "summary",
)


@dataclass
class ContextModel:
    user_id: uuid.UUID
    version: int
    model: dict
    source_hash: str
    changed: bool  # True if this build produced a new version


def _profile_facts(p: FounderProfile | None) -> dict:
    if p is None:
        return {}
    return {
        k: v for k, v in {
            "business_name": p.business_name,
            "business_type": p.business_type,
            "stage": p.business_stage,
            "industry": p.industry,
            "target_audience": p.target_audience,
            "primary_goal": p.primary_goal,
            "primary_goal_description": p.primary_goal_description,
            "current_mrr": str(p.current_mrr) if p.current_mrr is not None else None,
            "current_users": p.current_users,
            "team_size": p.team_size,
            "writing_voice": p.writing_voice,
        }.items() if v not in (None, "")
    }


def _intel_signals(intel: UserProfileIntel | None) -> dict:
    if intel is None:
        return {}
    return {
        k: v for k, v in {
            "preferred_tone": intel.preferred_tone,
            "communication_style": intel.communication_style,
            "likes": intel.likes,
            "dislikes": intel.dislikes,
            "pain_points": intel.pain_points,
            "goals": intel.goals,
            "topics_of_interest": intel.topics_of_interest,
            "profile_summary": intel.profile_summary,
        }.items() if v
    }


def _hash_inputs(facts: dict, signals: dict) -> str:
    blob = json.dumps({"facts": facts, "signals": signals}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _parse_model(raw: str) -> dict:
    """Extract the structured model from an LLM reply (tolerant of prose-wrapped JSON)."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return {k: str(data.get(k, "")).strip() for k in _KEYS}
        except (json.JSONDecodeError, ValueError):
            pass
    # Fallback: stash the raw text in summary so nothing is silently lost.
    return {**{k: "" for k in _KEYS}, "summary": text[:500]}


class FounderContextModelBuilder:
    """Builds and versions a founder's structured context model."""

    def __init__(self, db: AsyncSession, llm_generate: LLMGenerate) -> None:
        self._db = db
        self._llm = llm_generate

    async def build(self, user_id: uuid.UUID, clerk_user_id: str) -> Optional[ContextModel]:
        """Build the context model for a founder.

        ``user_id`` is the internal ``users.id`` (keys FounderProfile + storage);
        ``clerk_user_id`` keys UserProfileIntel (which stores the Clerk id).
        Returns None if there is no FounderProfile yet. Only writes a new version when
        the source inputs changed since the latest stored version.
        """
        profile = await self._load_profile(user_id)
        if profile is None:
            logger.info("context_model.build: no FounderProfile for %s; skipping", user_id)
            return None

        intel = await self._load_intel(clerk_user_id)
        facts = _profile_facts(profile)
        signals = _intel_signals(intel)
        source_hash = _hash_inputs(facts, signals)

        latest = await self._latest(user_id)
        if latest is not None and latest.source_hash == source_hash:
            return ContextModel(user_id, latest.version, latest.model, source_hash, changed=False)

        prompt = (
            f"FOUNDER FACTS:\n{json.dumps(facts, indent=2, default=str)}\n\n"
            f"BEHAVIOURAL SIGNALS:\n{json.dumps(signals, indent=2, default=str)}"
        )
        try:
            raw = await self._llm(_SYSTEM, prompt)
        except Exception:
            logger.exception("context_model.build: LLM failed for %s", user_id)
            return None

        model = _parse_model(raw)
        next_version = (latest.version + 1) if latest is not None else 1
        row = FounderContextModel(
            user_id=user_id,
            version=next_version,
            model=model,
            source_hash=source_hash,
        )
        self._db.add(row)
        await self._db.flush()
        logger.info("context_model.build: wrote v%d for %s", next_version, user_id)
        return ContextModel(user_id, next_version, model, source_hash, changed=True)

    async def latest(self, user_id: uuid.UUID) -> Optional[FounderContextModel]:
        return await self._latest(user_id)

    # -- DB helpers --------------------------------------------------------

    async def _load_profile(self, user_id: uuid.UUID) -> Optional[FounderProfile]:
        result = await self._db.execute(
            select(FounderProfile).where(FounderProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _load_intel(self, clerk_user_id: str) -> Optional[UserProfileIntel]:
        result = await self._db.execute(
            select(UserProfileIntel).where(UserProfileIntel.user_id == clerk_user_id)
        )
        return result.scalar_one_or_none()

    async def _latest(self, user_id: uuid.UUID) -> Optional[FounderContextModel]:
        result = await self._db.execute(
            select(FounderContextModel)
            .where(FounderContextModel.user_id == user_id)
            .order_by(desc(FounderContextModel.version))
            .limit(1)
        )
        return result.scalar_one_or_none()
