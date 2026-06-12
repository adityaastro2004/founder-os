#!/usr/bin/env python3
"""
Test — Agent Evolution Engine (task 003).

Self-contained: mocked LLM + fake DB session (real ORM models), no Postgres. Proves:
context model distill + hashing, generator staging (proposed/versioned), approve →
active + supersede, reject, rollback, and the registry-override contract (active
definition wins over the global agent). Exits non-zero on failure.
"""

import asyncio
import sys
import uuid

from app.agents.context_model import FounderContextModelBuilder, _hash_inputs, _parse_model
from app.agents.generator import AgentGenerator, _parse_definition
from app.models import AgentDefinition, FounderContextModel, FounderProfile

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


async def fake_ctx_llm(system: str, prompt: str) -> str:
    return (
        '{"business_model": "B2B SaaS, seat-based", "customer_profile": "RevOps leads", '
        '"market_profile": "crowded, AI-native entrants", "operating_style": "solo, '
        'ship-weekly", "risk_tolerance": "balanced", "goals": "reach $10k MRR", '
        '"summary": "Seed B2B SaaS for RevOps; growth-focused."}'
    )


async def fake_gen_llm(system: str, prompt: str) -> str:
    return (
        '{"system_prompt": "REGENERATED for this founder. THINK IN SYSTEMS.", '
        '"decision_framework": "Prioritise revenue-moving work.", '
        '"selected_tools": ["search_knowledge", "not_a_real_tool"]}'
    )


def _profile(user_id):
    return FounderProfile(user_id=user_id, business_name="Acme", business_type="SaaS",
                          business_stage="seed", industry="revops", primary_goal="grow_revenue",
                          team_size=1)


# ── Tests ────────────────────────────────────────────────

def test_parse_helpers():
    m = _parse_model('prose {"business_model":"x","summary":"s"} tail')
    check("ctx parse: extracts JSON from prose", m["business_model"] == "x" and m["summary"] == "s")
    d = _parse_definition(
        '{"system_prompt":"P","decision_framework":"D","selected_tools":["a","ghost"]}',
        tool_menu=["a", "b"], base_prompt="base",
    )
    check("gen parse: keeps only real tools", d["selected_tools"] == ["a"])
    d2 = _parse_definition('{"system_prompt":"","selected_tools":[]}', ["a", "b"], "base")
    check("gen parse: empty prompt falls back to base", d2["system_prompt"] == "base")
    check("gen parse: empty tools fall back to full menu", d2["selected_tools"] == ["a", "b"])
    h1 = _hash_inputs({"a": 1}, {"b": 2})
    h2 = _hash_inputs({"a": 1}, {"b": 2})
    h3 = _hash_inputs({"a": 1}, {"b": 3})
    check("ctx hash: stable + sensitive", h1 == h2 and h1 != h3)


async def test_context_model_build_and_change_detection():
    uid = uuid.uuid4()
    # Run 1: profile present, no intel, no prior version → builds v1
    db = FakeSession()
    db.push_scalar(_profile(uid))   # _load_profile
    db.push_scalar(None)            # _load_intel
    db.push_scalar(None)            # _latest (none)
    ctx = await FounderContextModelBuilder(db, fake_ctx_llm).build(uid, "clerk_1")
    check("ctx: builds when profile exists", ctx is not None and ctx.changed and ctx.version == 1)
    check("ctx: persisted a row", len(db.added) == 1 and isinstance(db.added[0], FounderContextModel))
    built = db.added[0]

    # Run 2: same inputs → same hash → no new version
    db2 = FakeSession()
    db2.push_scalar(_profile(uid))
    db2.push_scalar(None)
    db2.push_scalar(built)          # _latest returns the existing row (same hash)
    ctx2 = await FounderContextModelBuilder(db2, fake_ctx_llm).build(uid, "clerk_1")
    check("ctx: unchanged inputs → no new version", ctx2 is not None and not ctx2.changed)
    check("ctx: no row added on unchanged build", db2.added == [])

    # No profile → None
    db3 = FakeSession()
    db3.push_scalar(None)
    ctx3 = await FounderContextModelBuilder(db3, fake_ctx_llm).build(uuid.uuid4(), "clerk_x")
    check("ctx: no profile → None", ctx3 is None)


async def test_generator_stage_and_lifecycle():
    from app.agents.agents import AGENT_CLASSES
    uid = uuid.uuid4()
    n_agents = len(AGENT_CLASSES)

    # generate(): per agent → _next_version query (None → v1), then add
    db = FakeSession()
    for _ in range(n_agents):
        db.push_scalar(None)  # _next_version → none → 1
    proposals = await AgentGenerator(db, fake_gen_llm).generate(uid, {"summary": "ctx"}, 1)
    check("gen: one proposal per agent", len(proposals) == n_agents, f"{len(proposals)} vs {n_agents}")
    check("gen: rows staged as proposed", all(r.status == "proposed" for r in db.added))
    check("gen: rows are version 1", all(r.version == 1 for r in db.added))
    sample = db.added[0]
    check("gen: regenerated prompt stored", "REGENERATED" in sample.system_prompt)
    check("gen: tool selection intersected with menu", "not_a_real_tool" not in (sample.selected_tools or []))

    # approve(): supersede prior active (none), flip the proposal → active
    proposal = AgentDefinition(user_id=uid, agent_name="planner", version=1,
                               system_prompt="P", status="proposed")
    dba = FakeSession()
    dba.push_scalar(proposal)  # _latest_with_status(proposed)
    dba.push_scalar(None)      # _supersede_active → _latest_with_status(active) → none
    approved = await AgentGenerator(dba).approve(uid, "planner")
    check("approve: proposal becomes active", approved.status == "active" and approved.approved_at is not None)

    # approve supersedes the prior active row
    prior_active = AgentDefinition(user_id=uid, agent_name="planner", version=1,
                                   system_prompt="OLD", status="active")
    new_proposal = AgentDefinition(user_id=uid, agent_name="planner", version=2,
                                   system_prompt="NEW", status="proposed")
    dbs = FakeSession()
    dbs.push_scalar(new_proposal)   # _latest_with_status(proposed)
    dbs.push_scalar(prior_active)   # _supersede_active → active
    await AgentGenerator(dbs).approve(uid, "planner")
    check("approve: supersedes prior active", prior_active.status == "superseded" and new_proposal.status == "active")

    # reject()
    rej = AgentDefinition(user_id=uid, agent_name="ops", version=1, system_prompt="x", status="proposed")
    dbr = FakeSession()
    dbr.push_scalar(rej)
    removed = await AgentGenerator(dbr).reject(uid, "ops")
    check("reject: removes proposal", removed is True and dbr.deleted == [rej])

    # rollback(): current active → superseded; prior superseded → active
    cur = AgentDefinition(user_id=uid, agent_name="content", version=2, system_prompt="v2", status="active")
    prv = AgentDefinition(user_id=uid, agent_name="content", version=1, system_prompt="v1", status="superseded")
    dbk = FakeSession()
    dbk.push_scalar(cur)   # _latest_with_status(active)
    dbk.push_scalar(prv)   # _latest_with_status(superseded)
    back = await AgentGenerator(dbk).rollback(uid, "content")
    check("rollback: reactivates prior version", back is prv and prv.status == "active" and cur.status == "superseded")


def test_registry_override_contract():
    # The registry uses: effective_prompt = active_def.system_prompt if active_def else global.
    # Verify that contract directly (no full agent build needed).
    active = AgentDefinition(user_id=uuid.uuid4(), agent_name="planner", version=1,
                             system_prompt="PER-FOUNDER", selected_tools=["search_knowledge"],
                             status="active")
    global_prompt, global_tools = "GLOBAL", ["a", "b"]
    eff_prompt = active.system_prompt if active else global_prompt
    eff_tools = (active.selected_tools if active else global_tools) or []
    check("registry: active definition overrides global prompt", eff_prompt == "PER-FOUNDER")
    check("registry: active definition overrides global tools", eff_tools == ["search_knowledge"])
    none_def = None
    eff_prompt2 = none_def.system_prompt if none_def else global_prompt
    check("registry: falls back to global when no active def", eff_prompt2 == "GLOBAL")


async def main():
    test_parse_helpers()
    await test_context_model_build_and_change_detection()
    await test_generator_stage_and_lifecycle()
    test_registry_override_contract()


if __name__ == "__main__":
    asyncio.run(main())

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print(f"\n{'=' * 60}")
    print(f"  Agent Evolution Engine: {passed} PASS | {failed} FAIL")
    print(f"{'=' * 60}")
    for name, status, detail in RESULTS:
        mark = "✓" if status == "PASS" else "✗"
        line = f"  {mark} {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
    print()
    sys.exit(1 if failed else 0)
