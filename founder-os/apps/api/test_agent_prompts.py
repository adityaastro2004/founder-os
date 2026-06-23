#!/usr/bin/env python3
"""
Test — Agent strategic prompt upgrade + code→DB sync (task 002).

Self-contained: no live LLM, no Postgres (fake session). Verifies that
(1) every agent prompt has the strategic systems-thinking layer AND preserves its
operational instructions, and (2) sync_agents_to_db upserts code→DB idempotently so
the rich prompts actually run. Exits non-zero on failure.
"""

import asyncio
import sys

from app.agents.agents import AGENT_CLASSES
from app.agents.registry import sync_agents_to_db
from app.agents.strategy import STRATEGY_MARKER
from app.models import Agent

RESULTS: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if cond else "FAIL", detail))


# Expected role elevation per agent + an operational substring that MUST survive
# (proves we layered strategy on rather than replacing the working prompt).
EXPECTED = {
    "orchestrator": ("Chief of Staff & Orchestrator", "OPERATING PROTOCOL"),
    "planner": ("Chief Strategy Officer", "MISSION"),
    "research": ("Market Intelligence System", "monitor_competitors"),
    "content": ("Narrative Architecture System", "content strategist"),
    "support": ("Customer Intelligence & Support System", "empathetic"),
}


# ── Fakes ────────────────────────────────────────────────

class FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self):
        self.queue: list[FakeResult] = []
        self.added: list = []
        self.flushes = 0

    def push_scalar(self, v):
        self.queue.append(FakeResult(v))

    async def execute(self, _stmt):
        return self.queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


# ── Tests ────────────────────────────────────────────────

def test_prompts_layered():
    for slug, (role_title, operational) in EXPECTED.items():
        cls = AGENT_CLASSES.get(slug)
        prompt = (getattr(cls, "default_system_prompt", "") or "")
        check(f"{slug}: has strategy marker", STRATEGY_MARKER in prompt)
        check(f"{slug}: has role elevation '{role_title}'", role_title in prompt)
        check(f"{slug}: preserves operational text '{operational}'", operational in prompt,
              "operational instruction was dropped" if operational not in prompt else "")
        check(f"{slug}: has decision framework", "DECISION FRAMEWORK" in prompt)


async def test_sync_inserts_then_idempotent():
    slugs = list(AGENT_CLASSES.keys())

    # Run 1: no existing rows → all inserted
    db = FakeSession()
    for _ in slugs:
        db.push_scalar(None)
    n1 = await sync_agents_to_db(db)
    check("sync: returns count == number of agents", n1 == len(slugs), f"{n1} vs {len(slugs)}")
    check("sync: inserted a row per agent", len(db.added) == len(slugs), f"added {len(db.added)}")
    all_marked = all(STRATEGY_MARKER in (r.system_prompt or "") for r in db.added)
    check("sync: inserted rows carry the strategic prompt", all_marked)
    # The synced row is exactly what runtime loads (base.py:351 prefers DB value).
    by_name = {r.name: r for r in db.added}
    # sync stores the stripped prompt; that stored value is exactly what runtime loads.
    parity = all(
        by_name[s].system_prompt == (AGENT_CLASSES[s].default_system_prompt or "").strip()
        for s in slugs
    )
    check("sync: DB prompt == code prompt (so the rich prompt runs)", parity)

    # Run 2: rows already exist → updated in place, NOT duplicated
    db2 = FakeSession()
    for s in slugs:
        db2.push_scalar(by_name[s])  # existing row returned per agent
    n2 = await sync_agents_to_db(db2)
    check("sync: idempotent count", n2 == len(slugs))
    check("sync: idempotent — no new rows inserted on 2nd run", db2.added == [])
    still_marked = all(STRATEGY_MARKER in (by_name[s].system_prompt or "") for s in slugs)
    check("sync: updated rows still carry the strategic prompt", still_marked)


async def main():
    test_prompts_layered()
    await test_sync_inserts_then_idempotent()


if __name__ == "__main__":
    asyncio.run(main())

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print(f"\n{'=' * 60}")
    print(f"  Agent Prompt Upgrade: {passed} PASS | {failed} FAIL")
    print(f"{'=' * 60}")
    for name, status, detail in RESULTS:
        mark = "✓" if status == "PASS" else "✗"
        line = f"  {mark} {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
    print()
    sys.exit(1 if failed else 0)
