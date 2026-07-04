"""
Unit tests for workflow IR generation (app/workflows/generator.py) — Wave 2b / ADR-008 US-1.

Standalone, runnable, provider-neutral (a STUB LLMProvider — no real calls, no live
server), per standards/testing.md:
    cd founder-os/apps/api && source .venv/bin/activate && python3 test_workflow_generator.py

Covers:
  - a stub returning a known-good IR → generate_workflow_ir returns a VALIDATED IR
  - a stub returning an IR with a HIGH-risk action tool → rejected (not returned)
  - a stub returning an IR with a MEDIUM action tool → rejected
  - a stub returning an IR with a bad agent slug → rejected
  - tolerant parsing (prose-wrapped JSON) works
  - a repair attempt succeeds when the first reply is bad but the second is good
  - the returned IR is exactly what `validate_ir` accepts (the safe-to-persist contract)
"""

import asyncio
import json
import sys

from app.agents.llm import LLMProvider, LLMResponse
from app.workflows.generator import (
    WorkflowGenerationError,
    generate_workflow_ir,
)
from app.workflows.ir import validate_ir

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


class StubLLM(LLMProvider):
    """A provider-neutral stub: returns canned text replies in sequence. No network."""

    provider_name = "stub"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def generate(self, messages, *, system="", tools=None, model=None,
                       temperature=0.7, max_tokens=4096, stop_sequences=None, **kwargs):
        idx = min(self.calls, len(self._replies) - 1)
        self.calls += 1
        return LLMResponse(content=self._replies[idx])


GOOD_IR = {
    "ir_version": 1,
    "trigger": {"type": "cron", "cron": "0 8 * * 1", "timezone": "Asia/Kolkata"},
    "steps": [
        {
            "id": "s1",
            "type": "agent",
            "agent": "research",
            "instruction": "Summarise last week's support tickets.",
            "inputs": {},
            "depends_on": [],
        },
        {
            "id": "s2",
            "type": "action",
            "agent": "support",
            "tool": "search_knowledge",  # LOW per TOOL_RISK_MAP
            "arguments": {"query": "tickets"},
            "depends_on": ["s1"],
        },
    ],
}


def with_action_tool(tool: str) -> dict:
    ir = json.loads(json.dumps(GOOD_IR))
    ir["steps"][1]["tool"] = tool
    return ir


def with_agent_slug(slug: str) -> dict:
    ir = json.loads(json.dumps(GOOD_IR))
    ir["steps"][0]["agent"] = slug
    return ir


async def run() -> None:
    print("== good IR → validated IR returned ==")
    llm = StubLLM([json.dumps(GOOD_IR)])
    ir = await generate_workflow_ir(llm, "Every Monday, summarise tickets")
    check("returns an IR dict", isinstance(ir, dict), detail=str(type(ir)))
    check("returned IR passes validate_ir", validate_ir(ir) == [], detail=str(validate_ir(ir)))
    check("one LLM call for a clean first attempt", llm.calls == 1, detail=str(llm.calls))
    check("trigger preserved", ir["trigger"]["type"] == "cron", detail=str(ir["trigger"]))

    print("== prose-wrapped JSON is recovered ==")
    wrapped = "Sure! Here is your workflow:\n```json\n" + json.dumps(GOOD_IR) + "\n```\nDone."
    ir = await generate_workflow_ir(StubLLM([wrapped]), "summarise tickets")
    check("prose-wrapped JSON parsed + validated", validate_ir(ir) == [], detail=str(validate_ir(ir)))

    print("== HIGH-risk action tool → rejected (never returned) ==")
    llm = StubLLM([json.dumps(with_action_tool("send_email"))])  # HIGH; repair returns same
    raised = False
    try:
        await generate_workflow_ir(llm, "email a summary every Monday")
    except WorkflowGenerationError as exc:
        raised = True
        check("error carries validation messages", any("send_email" in e for e in exc.errors), detail=str(exc.errors))
    check("HIGH-risk action raises WorkflowGenerationError", raised)
    check("repair was attempted (2 LLM calls)", llm.calls == 2, detail=str(llm.calls))

    print("== MEDIUM action tool → rejected ==")
    llm = StubLLM([json.dumps(with_action_tool("create_task"))])  # MEDIUM
    raised = False
    try:
        await generate_workflow_ir(llm, "create a task every Monday")
    except WorkflowGenerationError as exc:
        raised = True
        check("MEDIUM tool flagged in errors", any("create_task" in e for e in exc.errors), detail=str(exc.errors))
    check("MEDIUM-risk action raises WorkflowGenerationError", raised)

    print("== unknown/bad agent slug → rejected ==")
    llm = StubLLM([json.dumps(with_agent_slug("not_a_real_agent"))])
    raised = False
    try:
        await generate_workflow_ir(llm, "do a thing")
    except WorkflowGenerationError as exc:
        raised = True
        check("bad agent flagged in errors", any("not_a_real_agent" in e for e in exc.errors), detail=str(exc.errors))
    check("bad agent slug raises WorkflowGenerationError", raised)

    print("== unparseable reply → rejected (no JSON) ==")
    raised = False
    try:
        await generate_workflow_ir(StubLLM(["I cannot help with that."]), "garble")
    except WorkflowGenerationError:
        raised = True
    check("non-JSON reply raises WorkflowGenerationError", raised)

    print("== repair path: bad first reply, good second reply → succeeds ==")
    llm = StubLLM([json.dumps(with_action_tool("send_email")), json.dumps(GOOD_IR)])
    ir = await generate_workflow_ir(llm, "summarise tickets, then maybe email")
    check("repair yields a valid IR", validate_ir(ir) == [], detail=str(validate_ir(ir)))
    check("repair used exactly 2 LLM calls", llm.calls == 2, detail=str(llm.calls))

    print("== empty goal → rejected before any LLM call ==")
    llm = StubLLM([json.dumps(GOOD_IR)])
    raised = False
    try:
        await generate_workflow_ir(llm, "   ")
    except WorkflowGenerationError:
        raised = True
    check("empty goal raises before calling LLM", raised and llm.calls == 0, detail=str(llm.calls))

    print(f"\n{'=' * 50}")
    print(f"RESULT: {_passed} passed, {_failed} failed")
    print(f"{'=' * 50}")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    asyncio.run(run())
