"""
Agent Generator (Agent Evolution Engine — task 003).
=====================================================
Regenerates each agent's FULL definition (system prompt + decision framework + tool
selection) for a specific founder, from the Founder Context Model + the agent's role
spec (its code charter, base operational prompt, and tool menu).

This is the leap from task 001's *overlay* to true *definition regeneration*:
  - generate() stages a versioned ``agent_definitions`` row as ``proposed`` — it NEVER
    auto-activates.
  - approve() makes a proposal ``active`` and supersedes the prior active row.
  - reject() discards a proposal; rollback() reactivates the prior version.
The registry prefers the ``active`` per-user definition over the global agents row.

Approval-gated, versioned/reversible, bounded (N LLM calls per context change).
Provider-neutral. See docs/decisions.md ADR-006.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agents import AGENT_CLASSES
from app.models import AgentDefinition

logger = logging.getLogger(__name__)

LLMGenerate = Callable[[str, str], Awaitable[str]]

_SYSTEM = (
    "You regenerate an AI agent's definition so it operates as a specialist for ONE "
    "specific founder's business. You are given the agent's role charter, its base "
    "operational prompt, its available tool menu, and a structured model of the "
    "founder. Produce a tailored definition that PRESERVES the operational/tool "
    "protocol but sharpens the agent's focus, priorities, and decision-making for this "
    "founder's stage, market, customers, goals, and operating style.\n\n"
    "Respond with STRICT JSON and nothing else:\n"
    '{"system_prompt": "<the full regenerated system prompt — strategic + founder-'
    'specialized + preserves operational instructions>", '
    '"decision_framework": "<the agent\'s decision rules for THIS founder, concise>", '
    '"selected_tools": ["<subset of the provided tool menu most relevant to this '
    'founder>"]}'
)


@dataclass
class DefinitionProposal:
    agent_name: str
    version: int
    system_prompt: str
    decision_framework: str
    selected_tools: list[str]


def _parse_definition(raw: str, tool_menu: list[str], base_prompt: str) -> Optional[dict]:
    """Parse the LLM reply into a definition; tolerant of prose-wrapped JSON.

    ``selected_tools`` is intersected with the real tool menu (the LLM cannot invent
    tools). Falls back to the base prompt / full menu when fields are missing.
    """
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None

    system_prompt = str(data.get("system_prompt", "")).strip() or base_prompt
    decision_framework = str(data.get("decision_framework", "")).strip()
    raw_tools = data.get("selected_tools") or []
    if isinstance(raw_tools, list):
        menu = set(tool_menu)
        selected = [t for t in raw_tools if t in menu]
    else:
        selected = []
    if not selected:
        selected = list(tool_menu)  # never strip an agent of all its tools
    return {
        "system_prompt": system_prompt,
        "decision_framework": decision_framework,
        "selected_tools": selected,
    }


class AgentGenerator:
    """Regenerates, approves, and rolls back per-founder agent definitions."""

    def __init__(self, db: AsyncSession, llm_generate: LLMGenerate | None = None) -> None:
        # llm_generate is only needed for generate(); approve/reject/rollback don't use it.
        self._db = db
        self._llm = llm_generate

    # ------------------------------------------------------------------
    # Generate — stage proposals (status=proposed); never auto-activate
    # ------------------------------------------------------------------

    async def generate(
        self,
        user_id: uuid.UUID,
        context_model: dict,
        context_model_version: int | None = None,
    ) -> list[DefinitionProposal]:
        """Regenerate a definition proposal for every active agent. One LLM call each."""
        if self._llm is None:
            raise ValueError("AgentGenerator.generate requires an llm_generate callable.")

        proposals: list[DefinitionProposal] = []
        ctx_json = json.dumps(context_model, indent=2, default=str)

        for slug, cls in AGENT_CLASSES.items():
            base_prompt = (getattr(cls, "default_system_prompt", "") or "").strip()
            tool_menu = list(getattr(cls, "default_tools", []) or [])
            capabilities = list(getattr(cls, "capabilities", []) or [])
            prompt = (
                f"AGENT: {slug}\n"
                f"CAPABILITIES: {capabilities}\n"
                f"TOOL MENU: {tool_menu}\n\n"
                f"BASE OPERATIONAL PROMPT:\n{base_prompt}\n\n"
                f"FOUNDER CONTEXT MODEL:\n{ctx_json}"
            )
            try:
                raw = await self._llm(_SYSTEM, prompt)
            except Exception:
                logger.exception("generator.generate: LLM failed for agent %s", slug)
                continue

            parsed = _parse_definition(raw, tool_menu, base_prompt)
            if parsed is None:
                continue

            version = await self._next_version(user_id, slug)
            row = AgentDefinition(
                user_id=user_id,
                agent_name=slug,
                version=version,
                system_prompt=parsed["system_prompt"],
                decision_framework=parsed["decision_framework"],
                selected_tools=parsed["selected_tools"],
                status="proposed",
                context_model_version=context_model_version,
            )
            self._db.add(row)
            proposals.append(
                DefinitionProposal(
                    agent_name=slug,
                    version=version,
                    system_prompt=parsed["system_prompt"],
                    decision_framework=parsed["decision_framework"],
                    selected_tools=parsed["selected_tools"],
                )
            )

        await self._db.flush()
        logger.info("generator.generate: staged %d proposals for %s", len(proposals), user_id)
        return proposals

    # ------------------------------------------------------------------
    # Approve / reject / rollback
    # ------------------------------------------------------------------

    async def approve(
        self,
        user_id: uuid.UUID,
        agent_name: str,
        system_prompt: str | None = None,
        decision_framework: str | None = None,
        selected_tools: list[str] | None = None,
    ) -> AgentDefinition:
        """Activate a proposed definition (optionally with edits). Supersedes the prior
        active row so exactly one definition is active per (user, agent)."""
        proposal = await self._latest_with_status(user_id, agent_name, "proposed")
        if proposal is None:
            raise ValueError("No proposed definition found for this agent.")

        await self._supersede_active(user_id, agent_name)

        if system_prompt is not None:
            proposal.system_prompt = system_prompt
        if decision_framework is not None:
            proposal.decision_framework = decision_framework
        if selected_tools is not None:
            proposal.selected_tools = selected_tools
        proposal.status = "active"
        proposal.approved_at = datetime.now(timezone.utc)

        await self._db.flush()
        return proposal

    async def reject(self, user_id: uuid.UUID, agent_name: str) -> bool:
        """Discard the pending proposal for an agent. Returns True if one was removed."""
        proposal = await self._latest_with_status(user_id, agent_name, "proposed")
        if proposal is None:
            return False
        await self._db.delete(proposal)
        await self._db.flush()
        return True

    async def rollback(self, user_id: uuid.UUID, agent_name: str) -> Optional[AgentDefinition]:
        """Revert to the previous version: supersede the current active row and
        reactivate the most recent superseded one. Returns the reactivated row, or None
        (caller then falls back to the global agent definition)."""
        current = await self._latest_with_status(user_id, agent_name, "active")
        prior = await self._latest_with_status(user_id, agent_name, "superseded")
        if current is not None:
            current.status = "superseded"
        if prior is not None:
            prior.status = "active"
            prior.approved_at = datetime.now(timezone.utc)
        await self._db.flush()
        return prior

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _next_version(self, user_id: uuid.UUID, agent_name: str) -> int:
        result = await self._db.execute(
            select(AgentDefinition.version)
            .where(AgentDefinition.user_id == user_id, AgentDefinition.agent_name == agent_name)
            .order_by(desc(AgentDefinition.version))
            .limit(1)
        )
        top = result.scalar_one_or_none()
        return (top + 1) if top else 1

    async def _latest_with_status(
        self, user_id: uuid.UUID, agent_name: str, status: str
    ) -> Optional[AgentDefinition]:
        result = await self._db.execute(
            select(AgentDefinition)
            .where(
                AgentDefinition.user_id == user_id,
                AgentDefinition.agent_name == agent_name,
                AgentDefinition.status == status,
            )
            .order_by(desc(AgentDefinition.version))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _supersede_active(self, user_id: uuid.UUID, agent_name: str) -> None:
        active = await self._latest_with_status(user_id, agent_name, "active")
        if active is not None:
            active.status = "superseded"

    async def list_proposals(self, user_id: uuid.UUID) -> list[AgentDefinition]:
        result = await self._db.execute(
            select(AgentDefinition)
            .where(AgentDefinition.user_id == user_id, AgentDefinition.status == "proposed")
            .order_by(AgentDefinition.agent_name)
        )
        return list(result.scalars().all())
