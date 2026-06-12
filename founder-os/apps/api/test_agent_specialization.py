#!/usr/bin/env python3
"""
Test — Agent Specialization Engine (task 001).

Self-contained: mocks the LLM and the DB session (real ORM models, no Postgres),
so it runs in the nightly sweep without infra. Proves generate → stage(disabled) →
approve(enabled) and the LLM-output parsing. Exits non-zero on failure.
"""

import asyncio
import sys
import uuid

from app.agents.specialization import SpecializationEngine, _parse_specialization
from app.models import Agent, FounderProfile, UserAgentConfig

RESULTS: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if cond else "FAIL", detail))


# ── Fakes ────────────────────────────────────────────────

class FakeResult:
    def __init__(self, value=None, items=None):
        self._value = value
        self._items = items or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeSession:
    """Returns pre-seeded results in call order; records add/delete/flush."""

    def __init__(self):
        self.queue: list[FakeResult] = []
        self.added: list = []
        self.deleted: list = []
        self.flushes = 0

    def push_scalar(self, v):
        self.queue.append(FakeResult(value=v))

    def push_list(self, items):
        self.queue.append(FakeResult(items=items))

    async def execute(self, _stmt):
        return self.queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flushes += 1


async def fake_llm(system: str, prompt: str) -> str:
    return '{"custom_instructions": "Prioritise SaaS churn reduction", "tone_adjustments": "Concise, technical"}'


def _agent(name: str) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        name=name,
        display_name=name.title(),
        system_prompt=f"You are the {name} agent.",
        is_active=True,
    )


def _profile(user_id: uuid.UUID) -> FounderProfile:
    return FounderProfile(
        user_id=user_id,
        business_name="Acme",
        business_type="SaaS",
        business_stage="seed",
        industry="devtools",
        primary_goal="grow_revenue",
        team_size=2,
        writing_voice="direct",
    )


# ── Tests ────────────────────────────────────────────────

async def test_generate_stages_disabled():
    user_id = uuid.uuid4()
    agents = [_agent("planner"), _agent("content")]
    db = FakeSession()
    db.push_scalar(_profile(user_id))     # _load_profile
    db.push_list(agents)                  # _active_agents
    db.push_scalar(None)                  # _load_config agent[0] -> new
    db.push_scalar(None)                  # _load_config agent[1] -> new

    engine = SpecializationEngine(db, fake_llm)
    proposals = await engine.generate(user_id)

    check("generate: one proposal per active agent", len(proposals) == 2, f"got {len(proposals)}")
    check("generate: persisted configs added", len(db.added) == 2, f"added {len(db.added)}")
    all_disabled = all(c.is_enabled is False for c in db.added)
    check("generate: proposals staged as is_enabled=False", all_disabled)
    has_text = all(c.custom_instructions for c in db.added)
    check("generate: custom_instructions parsed from LLM", has_text)
    return db, agents, user_id


async def test_no_profile_returns_empty():
    db = FakeSession()
    db.push_scalar(None)  # no profile
    engine = SpecializationEngine(db, fake_llm)
    proposals = await engine.generate(uuid.uuid4())
    check("generate: empty when no FounderProfile", proposals == [] and not db.added)


async def test_approve_enables(db_after_generate):
    db, agents, user_id = db_after_generate
    config = db.added[0]
    fresh = FakeSession()
    fresh.push_scalar(config)  # _load_config in approve
    engine = SpecializationEngine(fresh, fake_llm)

    approved = await engine.approve(user_id, agents[0].id)
    check("approve: flips is_enabled=True", approved.is_enabled is True)
    # The runtime apply path is existing, verified code: registry.py:236 loads the
    # config and base.py:364 injects custom_instructions for is_enabled=True rows.
    live_eligible = approved.is_enabled is True and bool(approved.custom_instructions)
    check("approve: result is runtime-apply-eligible (enabled + has instructions)", live_eligible)


async def test_approve_with_edits():
    user_id, agent_id = uuid.uuid4(), uuid.uuid4()
    config = UserAgentConfig(user_id=user_id, agent_id=agent_id, is_enabled=False)
    db = FakeSession()
    db.push_scalar(config)
    engine = SpecializationEngine(db, fake_llm)
    await engine.approve(user_id, agent_id, custom_instructions="EDITED")
    check("approve: applies edits", config.custom_instructions == "EDITED" and config.is_enabled is True)


async def test_approve_missing_raises():
    db = FakeSession()
    db.push_scalar(None)
    engine = SpecializationEngine(db, fake_llm)
    try:
        await engine.approve(uuid.uuid4(), uuid.uuid4())
        check("approve: missing proposal raises", False, "no error raised")
    except ValueError:
        check("approve: missing proposal raises", True)


async def test_reject_deletes():
    user_id, agent_id = uuid.uuid4(), uuid.uuid4()
    config = UserAgentConfig(user_id=user_id, agent_id=agent_id, is_enabled=False)
    db = FakeSession()
    db.push_scalar(config)
    engine = SpecializationEngine(db, fake_llm)
    removed = await engine.reject(user_id, agent_id)
    check("reject: removes the proposal", removed is True and db.deleted == [config])


def test_parse_variants():
    ci, tone = _parse_specialization('{"custom_instructions": "a", "tone_adjustments": "b"}')
    check("parse: strict JSON", ci == "a" and tone == "b")
    ci, tone = _parse_specialization('Sure! {"custom_instructions": "x", "tone_adjustments": "y"} done')
    check("parse: JSON wrapped in prose", ci == "x" and tone == "y")
    ci, tone = _parse_specialization("just plain text")
    check("parse: non-JSON falls back to custom_instructions", ci == "just plain text" and tone == "")


async def main():
    db_after = await test_generate_stages_disabled()
    await test_no_profile_returns_empty()
    await test_approve_enables(db_after)
    await test_approve_with_edits()
    await test_approve_missing_raises()
    await test_reject_deletes()
    test_parse_variants()


if __name__ == "__main__":
    asyncio.run(main())

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print(f"\n{'=' * 60}")
    print(f"  Agent Specialization: {passed} PASS | {failed} FAIL")
    print(f"{'=' * 60}")
    for name, status, detail in RESULTS:
        mark = "✓" if status == "PASS" else "✗"
        line = f"  {mark} {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
    print()
    sys.exit(1 if failed else 0)
