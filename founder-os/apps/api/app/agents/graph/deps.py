"""``GraphDeps`` — the collaborator bundle the graph nodes close over.

Built from a live ``OrchestratorAgent``, it exposes exactly what the nodes need
(``llm``, ``router``, ``event_bus``, ``user_id``, ``session_id``, model choices)
plus ``snapshot()`` / ``hydrate()`` bound to that agent's memory + profile loader.
Keeping this as a small dataclass means the nodes never touch the full agent and
stay easy to test with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.graph.context import snapshot_context, hydrate_volatile


@dataclass
class GraphDeps:
    llm: Any
    router: Any
    event_bus: Any
    memory: Any
    user_id: Any
    session_id: str
    cheap_model: str | None = None
    main_model: str | None = None
    _agent: Any = None

    @classmethod
    def from_agent(
        cls,
        agent: Any,
        *,
        cheap_model: str | None = None,
        main_model: str | None = None,
    ) -> "GraphDeps":
        return cls(
            llm=agent.llm,
            router=agent.router,
            event_bus=agent.event_bus,
            memory=agent.memory,
            user_id=agent.user_id,
            session_id=getattr(agent, "session_id", "") or "",
            cheap_model=cheap_model,
            main_model=main_model,
            _agent=agent,
        )

    async def snapshot(self) -> dict[str, str]:
        return await snapshot_context(self._agent)

    async def hydrate(self) -> dict[str, str]:
        return await hydrate_volatile(self._agent)
