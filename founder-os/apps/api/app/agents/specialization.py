"""
Agent Specialization Engine
===========================
Turns a founder's business profile into per-agent specialization proposals so the
product's runtime agents behave as specialists for *this* founder's business.

Design (see docs/decisions.md ADR-003):

  - One LLM call per active agent produces a `custom_instructions` + `tone_adjustments`
    overlay tailored to the FounderProfile (stage / industry / goal / audience / voice).
  - Proposals are staged as ``UserAgentConfig`` rows with ``is_enabled=False`` — the
    runtime loader (registry.py ``_load_user_config``) only applies ``is_enabled=True``
    rows, so a proposal is invisible to agents until the founder approves it.
  - Approval flips the row to ``is_enabled=True``; the existing apply path
    (registry.py:236 → base.py:364 ``<user_custom_instructions>``) does the rest.

Provider-neutral: takes an async ``llm_generate(system, prompt) -> str`` callable,
the same DI shape as ``ProfileIntelligence``.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, FounderProfile, UserAgentConfig

logger = logging.getLogger(__name__)

LLMGenerate = Callable[[str, str], Awaitable[str]]


@dataclass
class Proposal:
    """A staged (not-yet-live) specialization for one agent."""

    agent_id: uuid.UUID
    agent_name: str
    custom_instructions: str
    tone_adjustments: str


_SYSTEM = (
    "You tune an AI business agent to a specific founder's company. "
    "Given the agent's base role and the founder's profile, write a concise overlay "
    "that makes the agent behave as a specialist for THIS business — its stage, "
    "industry, goal, audience, and voice. Do not restate the base role; add only "
    "what specializes it. Respond with STRICT JSON and nothing else:\n"
    '{"custom_instructions": "<= 120 words of concrete guidance", '
    '"tone_adjustments": "<= 40 words on voice/tone"}'
)


def _profile_facts(p: FounderProfile) -> str:
    """Render the founder profile as compact facts for the prompt."""
    fields = {
        "business_name": p.business_name,
        "business_type": p.business_type,
        "stage": p.business_stage,
        "industry": p.industry,
        "target_audience": p.target_audience,
        "primary_goal": p.primary_goal,
        "current_mrr": str(p.current_mrr) if p.current_mrr is not None else None,
        "current_users": p.current_users,
        "team_size": p.team_size,
        "writing_voice": p.writing_voice,
    }
    return "\n".join(f"- {k}: {v}" for k, v in fields.items() if v not in (None, ""))


def _parse_specialization(raw: str) -> tuple[str, str]:
    """Extract (custom_instructions, tone_adjustments) from an LLM reply.

    Tolerant of providers that wrap JSON in prose: grabs the first ``{...}`` block.
    Falls back to using the whole reply as custom_instructions.
    """
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            ci = str(data.get("custom_instructions", "")).strip()
            tone = str(data.get("tone_adjustments", "")).strip()
            if ci or tone:
                return ci, tone
        except (json.JSONDecodeError, ValueError):
            pass
    return text, ""


class SpecializationEngine:
    """Generate, approve, and reject per-founder agent specializations."""

    def __init__(self, db: AsyncSession, llm_generate: LLMGenerate | None = None) -> None:
        # llm_generate is only needed for generate(); approve/reject/list don't use it.
        self._db = db
        self._llm = llm_generate

    # ------------------------------------------------------------------
    # Generate — stage proposals (is_enabled=False)
    # ------------------------------------------------------------------

    async def generate(self, user_id: uuid.UUID) -> list[Proposal]:
        """Generate a staged specialization proposal for every active agent.

        ``user_id`` is the internal ``users.id`` UUID (not the Clerk id).

        Re-running re-proposes (overwrites the overlay and sets ``is_enabled=False``).
        Note: re-tuning an agent that already had a *live* config moves it back to
        pending until re-approved — a deliberate "re-tune pauses the old tuning"
        behavior (ADR-003). On first run (onboarding) no live rows exist, so this is
        unambiguous.
        """
        if self._llm is None:
            raise ValueError("SpecializationEngine.generate requires an llm_generate callable.")

        profile = await self._load_profile(user_id)
        if profile is None:
            logger.info("specialization.generate: no FounderProfile for %s; skipping", user_id)
            return []

        facts = _profile_facts(profile)
        proposals: list[Proposal] = []

        for agent in await self._active_agents():
            prompt = (
                f"AGENT BASE ROLE ({agent.display_name}):\n{agent.system_prompt}\n\n"
                f"FOUNDER PROFILE:\n{facts}"
            )
            try:
                raw = await self._llm(_SYSTEM, prompt)
            except Exception:  # provider/network failure — skip this agent, keep going
                logger.exception("specialization.generate: LLM failed for agent %s", agent.name)
                continue

            custom_instructions, tone = _parse_specialization(raw)
            if not custom_instructions and not tone:
                continue

            await self._upsert_proposal(user_id, agent.id, custom_instructions, tone)
            proposals.append(
                Proposal(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    custom_instructions=custom_instructions,
                    tone_adjustments=tone,
                )
            )

        await self._db.flush()
        logger.info("specialization.generate: staged %d proposals for %s", len(proposals), user_id)
        return proposals

    # ------------------------------------------------------------------
    # Approve / reject
    # ------------------------------------------------------------------

    async def approve(
        self,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
        custom_instructions: str | None = None,
        tone_adjustments: str | None = None,
    ) -> UserAgentConfig:
        """Approve a staged proposal (optionally with edits): set ``is_enabled=True``."""
        config = await self._load_config(user_id, agent_id)
        if config is None:
            raise ValueError("No specialization proposal found for this agent.")

        if custom_instructions is not None:
            config.custom_instructions = custom_instructions
        if tone_adjustments is not None:
            config.tone_adjustments = tone_adjustments
        config.is_enabled = True

        await self._db.flush()
        return config

    async def reject(self, user_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
        """Discard a staged proposal. Returns True if one was removed."""
        config = await self._load_config(user_id, agent_id)
        if config is None:
            return False
        await self._db.delete(config)
        await self._db.flush()
        return True

    async def list_proposals(self, user_id: uuid.UUID) -> list[UserAgentConfig]:
        """All pending (not-yet-live) proposals for this user."""
        result = await self._db.execute(
            select(UserAgentConfig).where(
                UserAgentConfig.user_id == user_id,
                UserAgentConfig.is_enabled == False,  # noqa: E712 (SQL boolean)
            )
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _load_profile(self, user_id: uuid.UUID) -> Optional[FounderProfile]:
        result = await self._db.execute(
            select(FounderProfile).where(FounderProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _active_agents(self) -> list[Agent]:
        result = await self._db.execute(select(Agent).where(Agent.is_active == True))  # noqa: E712
        return list(result.scalars().all())

    async def _load_config(
        self, user_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Optional[UserAgentConfig]:
        result = await self._db.execute(
            select(UserAgentConfig).where(
                UserAgentConfig.user_id == user_id,
                UserAgentConfig.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def _upsert_proposal(
        self,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
        custom_instructions: str,
        tone_adjustments: str,
    ) -> None:
        config = await self._load_config(user_id, agent_id)
        if config is None:
            config = UserAgentConfig(user_id=user_id, agent_id=agent_id)
            self._db.add(config)
        config.custom_instructions = custom_instructions
        config.tone_adjustments = tone_adjustments
        config.is_enabled = False  # staged — invisible to the runtime loader
