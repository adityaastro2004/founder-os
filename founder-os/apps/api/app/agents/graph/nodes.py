"""Graph node factories for the durable orchestrator.

Each ``make_*_node`` returns an async callable ``node(state) -> dict`` where the
returned dict is a partial state update (LangGraph merges it). Nodes close over a
``deps`` object (see ``app.agents.graph.deps.GraphDeps``) that exposes the
existing orchestrator collaborators — ``llm`` (an ``LLMProvider`` with the 3-tier
fallback), ``router``, ``event_bus`` — plus ``snapshot()`` / ``hydrate()``.

LLM calls go through ``deps.llm.generate(...)`` (never LangChain models), so the
provider fallback in ``app/agents/llm.py`` is preserved unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# The only valid specialist names the classifier may route to.
VALID_AGENTS = ("planner", "research", "content", "support")

_CLASSIFY_SYSTEM = (
    "You are a routing classifier for a founder's AI operations system. You do not "
    "answer the request — you only decide how to route it."
)

_CLASSIFY_PROMPT = """Given the request and the company/task context, return STRICT \
JSON and nothing else:
{{"intent": "SIMPLE|MULTI_STEP|COMPLEX", "agents": [<subset of planner, research, content, support>], "needs_approval": <true|false>}}

Rules:
- SIMPLE: one specialist is enough. MULTI_STEP: 2-3 specialists in sequence.
  COMPLEX: genuinely ambiguous — needs a full LLM routing decision downstream.
- needs_approval: true only if the request implies a destructive or high-stakes
  action (deletions, sending external comms, spending).
- Choose agents by fit: planner=planning/scheduling/tasks, research=market/competitors,
  content=writing/copy/specs, support=customer replies/FAQs.

<company_context>
{company}
</company_context>
<task_context>
{task}
</task_context>
<request>
{request}
</request>

JSON:"""


def _parse_classify(raw: str) -> dict:
    """Extract the routing decision from the model's JSON reply, defensively."""
    try:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start != -1 else {}
    except (ValueError, json.JSONDecodeError):
        logger.warning("classify: could not parse JSON, defaulting to SIMPLE/planner")
        data = {}
    agents = [a for a in data.get("agents", []) if a in VALID_AGENTS]
    intent = (data.get("intent") or "SIMPLE").upper()
    if intent not in ("SIMPLE", "MULTI_STEP", "COMPLEX"):
        intent = "SIMPLE"
    return {
        "intent": intent,
        "planned_agents": agents,
        "needs_approval": bool(data.get("needs_approval", False)),
    }


def make_classify_node(deps: Any):
    """One cheap-tier LLM call that decides routing + snapshots the context surface."""

    async def classify(state) -> dict:
        from app.agents.llm import LLMMessage, Role

        ctx = await deps.snapshot()
        prompt = _CLASSIFY_PROMPT.format(
            company=ctx["company_context"] or "(none)",
            task=ctx["task_context"] or "(none)",
            request=state["user_input"],
        )
        resp = await deps.llm.generate(
            [LLMMessage(role=Role.USER, content=prompt)],
            system=_CLASSIFY_SYSTEM,
            model=deps.cheap_model,
            temperature=0.1,
            max_tokens=256,
        )
        parsed = _parse_classify(resp.content)
        trace = list(state["trace"]) + [
            {"node": "classify", "tokens_used": resp.usage.total, "intent": parsed["intent"]}
        ]
        return {**parsed, **ctx, "trace": trace}

    return classify
