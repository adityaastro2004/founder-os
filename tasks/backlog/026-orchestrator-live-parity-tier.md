---
id: 026
title: Live parity tier for the durable LangGraph orchestrator
status: backlog          # backlog | in-progress | blocked | review | done
stage: product           # product | planner | architect | executor | reviewer | qa | security
owner: eng-product       # the agent currently responsible
created: 2026-07-27
dependencies: []          # ADR-017 orchestrator shipped in PR #35
links: [docs/superpowers/specs/2026-07-27-langgraph-orchestrator-design.md, docs/superpowers/plans/2026-07-27-langgraph-orchestrator.md, "PR #35"]
---

# 026 — Live parity tier for the durable LangGraph orchestrator

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective
Add a `-m live` parity test that runs the real orchestrator (real models via the
provider fallback, real specialists) and asserts routing quality end-to-end. The
ADR-017 rewrite shipped with strong unit coverage (27 graph/durability/mapping
tests) but the "real models pick the right agents" assertion could not run locally
(no Ollama on the dev box), so it is currently a gap in the safety net.

## User stories  <!-- eng-product -->
- As an engineer, I want a live parity test so that a regression in classify-node
  routing quality (wrong specialist, missing agent) is caught in CI, not in prod.

## Acceptance criteria
- [ ] A `tests/live/test_graph_parity.py` (marked `live`) drives `OrchestratorAgent.run()`
      against a running stack + Ollama over ~8-10 representative requests spanning
      SIMPLE / MULTI_STEP / COMPLEX / approval-needed.
- [ ] Each case asserts the expected specialist(s) were used (via `result.delegations`)
      and that `result.content` is non-empty/coherent.
- [ ] At least one case exercises the approval interrupt → `/orchestrate/resume` round-trip
      against the real Postgres checkpointer.
- [ ] The test is wired into the CI/EC2 live tier (not the default `pytest` run).

## Success metrics  <!-- eng-product -->
- A deliberately broken classifier prompt makes the parity tier go red.

## Out of scope
- Unit-tier coverage (already exists in `tests/unit/test_graph_*`).
- Token-cost assertions (separate optimization task if desired).

## Requirements / open questions  <!-- eng-planner -->
- Needs a fixture that builds the orchestrator the way `agent_routes.orchestrate` does
  (registry + db session + redis) — reuse or extend an existing live fixture.
- Where does the live tier run? Confirm CI has (or can get) an Ollama service, or run
  it as a scheduled EC2 job (see meta/run-nightly-test-sweep.md).
- Routing is probabilistic — assertions should check membership/superset, not exact
  equality, to avoid flakiness.
