"""Context snapshot & re-hydration for the orchestrator graph.

Two reads of the same underlying sources (the founder profile loader and shared
memory), used at different points in the graph:

- ``snapshot_context`` — a point-in-time read of the *full* surface, taken at
  ``classify`` time. Cheap; routing only needs a snapshot.
- ``hydrate_volatile`` — refreshes only the fast-changing company/task context
  before synthesis and after a resume, so a run that paused for approval and
  resumed hours later reflects the company's state *now*, not when it started.

Both accept the ``OrchestratorAgent`` itself (it exposes ``memory`` and
``_load_founder_profile_context``); no new data source is introduced.
"""

from __future__ import annotations

from typing import Any


async def _shared(agent: Any, key: str) -> str:
    try:
        val = await agent.memory.get_from_shared(key)
        return str(val) if val else ""
    except Exception:
        return ""


async def _task_context(agent: Any) -> str:
    """Assemble the task/working-state block from shared memory."""
    parts: list[str] = []
    for key in ("current_plan", "research_findings", "last_orchestration"):
        val = await _shared(agent, key)
        if val:
            parts.append(f"<{key}>\n{val}\n</{key}>")
    return "\n".join(parts)


async def _profile(agent: Any) -> str:
    try:
        return await agent._load_founder_profile_context()
    except Exception:
        return ""


async def snapshot_context(agent: Any) -> dict[str, str]:
    """Point-in-time read of the full context surface (used at classify time).

    ``company_context`` reuses the founder profile block, which already carries
    ``<founder_business_context>`` (company name/type/stage). Cross-session
    ``<memories>`` recall stays base.py's responsibility at specialist run time,
    so ``memory_context`` is left empty here.
    """
    profile = await _profile(agent)
    return {
        "profile_context": profile,
        "company_context": profile,
        "task_context": await _task_context(agent),
        "memory_context": "",
    }


async def hydrate_volatile(agent: Any) -> dict[str, str]:
    """Refresh only the fast-changing context (company/task) before synthesis / on resume."""
    profile = await _profile(agent)
    return {
        "company_context": profile,
        "task_context": await _task_context(agent),
    }
