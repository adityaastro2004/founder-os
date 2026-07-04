"""
Unit tests for the workflow IR (app/workflows/ir.py) — ADR-008 O-1-AMEND.

Standalone, runnable, no live server / no LLM (per standards/testing.md):
    cd founder-os/apps/api && source .venv/bin/activate && python3 test_workflow_ir.py

Covers the O-1-AMEND HARD RULES:
  - LOW-risk action step passes
  - MEDIUM action step rejected
  - HIGH action step rejected
  - unknown ir_version rejected
  - smuggled `risk` field rejected
  - agent step content-only passes; unknown agent rejected
  - round-trip serialize/deserialize is stable
"""

import sys

from app.workflows.ir import (
    IR_VERSION,
    WorkflowIR,
    get_step,
    parse_ir,
    serialize_ir,
    validate_ir,
)

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


def low_action_ir() -> dict:
    return {
        "ir_version": 1,
        "trigger": {"type": "manual"},
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


def main() -> None:
    print("== validate_ir: LOW-risk action passes ==")
    errs = validate_ir(low_action_ir())
    check("low-risk action IR validates clean", errs == [], detail=str(errs))

    print("== validate_ir: MEDIUM action rejected ==")
    ir = low_action_ir()
    ir["steps"][1]["tool"] = "create_task"  # MEDIUM per TOOL_RISK_MAP
    errs = validate_ir(ir)
    check(
        "MEDIUM action tool rejected",
        any("create_task" in e and "MEDIUM" in e for e in errs),
        detail=str(errs),
    )

    print("== validate_ir: HIGH action rejected ==")
    ir = low_action_ir()
    ir["steps"][1]["tool"] = "send_email"  # HIGH per HIGH_RISK_TOOLS
    errs = validate_ir(ir)
    check(
        "HIGH action tool rejected",
        any("send_email" in e and "HIGH" in e for e in errs),
        detail=str(errs),
    )

    print("== validate_ir: unknown tool (defaults MEDIUM) rejected ==")
    ir = low_action_ir()
    ir["steps"][1]["tool"] = "totally_unknown_mcp_tool"
    errs = validate_ir(ir)
    check("unknown tool rejected (defaults MEDIUM)", errs != [], detail=str(errs))

    print("== validate_ir: unknown ir_version rejected ==")
    ir = low_action_ir()
    ir["ir_version"] = 99
    errs = validate_ir(ir)
    check(
        "unknown ir_version rejected",
        any("ir_version" in e for e in errs),
        detail=str(errs),
    )

    print("== validate_ir: smuggled risk field rejected ==")
    ir = low_action_ir()
    ir["steps"][1]["risk"] = "low"  # attempt to declare risk in the IR (C-8)
    errs = validate_ir(ir)
    check(
        "smuggled risk field rejected",
        errs != [],
        detail=str(errs),
    )

    print("== validate_ir: unknown agent slug rejected ==")
    ir = low_action_ir()
    ir["steps"][0]["agent"] = "not_a_real_agent"
    errs = validate_ir(ir)
    check(
        "unknown agent rejected",
        any("not_a_real_agent" in e for e in errs),
        detail=str(errs),
    )

    print("== validate_ir: duplicate ids and bad depends_on rejected ==")
    ir = low_action_ir()
    ir["steps"][1]["id"] = "s1"  # duplicate
    ir["steps"][1]["depends_on"] = ["sX"]  # unknown predecessor
    errs = validate_ir(ir)
    check("duplicate id + bad depends_on rejected", len(errs) >= 2, detail=str(errs))

    print("== validate_ir: empty steps rejected ==")
    ir = low_action_ir()
    ir["steps"] = []
    errs = validate_ir(ir)
    check("empty steps rejected", errs != [], detail=str(errs))

    print("== validate_ir: cron trigger valid ==")
    ir = low_action_ir()
    ir["trigger"] = {"type": "cron", "cron": "0 3 * * 1", "timezone": "Asia/Kolkata"}
    errs = validate_ir(ir)
    check("cron trigger IR validates clean", errs == [], detail=str(errs))

    print("== round-trip: serialize/deserialize is stable ==")
    raw = low_action_ir()
    parsed: WorkflowIR = parse_ir(raw)
    out = serialize_ir(parsed)
    reparsed = parse_ir(out)
    check("parse → serialize → parse round-trips", serialize_ir(reparsed) == out, detail="mismatch")
    check("ir_version preserved", out["ir_version"] == IR_VERSION, detail=str(out.get("ir_version")))
    check("step count preserved", len(out["steps"]) == 2, detail=str(out))

    print("== get_step: loads authoritative step by id (C-2 / C-8) ==")
    s2 = get_step(raw, "s2")
    check("get_step returns the action step", s2 is not None and s2.id == "s2", detail=str(s2))
    check("get_step tool comes from persisted IR", getattr(s2, "tool", None) == "search_knowledge", detail=str(s2))
    check("get_step returns None for unknown id", get_step(raw, "nope") is None)

    print(f"\n{'=' * 50}")
    print(f"RESULT: {_passed} passed, {_failed} failed")
    print(f"{'=' * 50}")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
