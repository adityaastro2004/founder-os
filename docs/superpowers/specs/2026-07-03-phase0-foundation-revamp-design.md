# Phase 0 — Foundation Revamp (Audit → Repair → Reshape)

- **Date:** 2026-07-03
- **Status:** Approved by founder (this session)
- **Owner:** engineering meta-layer
- **Related:** ADR-009 (Company State Engine), task 011, [docs/roadmap.md](../../roadmap.md)

## Context: the full revamp decomposition

The founder asked for a whole-system revamp: everything working, properly modular,
easy for future Claude sessions to operate, with Obsidian / Notion / Hermes-skills /
Paperclip integrations and working calendar + automations — i.e. reach the vision
(Company State Engine, ADR-009). That is too large for one spec, so it was decomposed
with the founder into sequential phases, **each getting its own design → plan →
implementation cycle**:

| Phase | Outcome | Status |
|-------|---------|--------|
| **0** | Foundation revamp — everything verifiably working + integration seam (this spec) | approved |
| 1 | State Engine core + Obsidian bidirectional sync (task 011 slice 1, already specced) | next |
| 2 | Notion adapter on the same engine | later |
| 3 | Hermes skills feed (`system` feed: agent memories + learned procedural skills → engine) | later |
| 4 | Paperclip integration ([paperclip.ing](https://paperclip.ing) — open-source agent-company platform; REST API + MCP server, rides existing MCP support) | later |
| 5 | Deployment — Docker images, deploy runbook, step-by-step shippability | later |

Founder-confirmed identifications: **Hermes** = the Hermes-style procedural-skills
concept already in the readme/vision (not an external app). **Paperclip** = the
external product at paperclip.ing / github.com/paperclipai/paperclip.

## Phase 0 goal

Make the existing system **demonstrably work end-to-end**, then make it **modular
where the next phases need it** — without a big-bang restructure. Approach chosen by
the founder: **A) Audit-first → targeted repair → surgical reshape** (over big-bang
restructure and minimal-repair alternatives).

The founder reported calendar, automations, and agents/chat as suspect and confirmed
the stack has not been fully run recently; the audit treats *everything* as unverified.

## Success criteria (definition of done)

1. `./start.sh` boots the full stack cleanly from a fresh checkout; steps documented.
2. `reports/2026-07-03-phase0-audit.md` exists with a PASS/FAIL/BLOCKED verdict and
   real captured output for every subsystem listed in Stage 1.
3. Every FAIL is either **fixed with a regression test** or **deferred as a
   `tasks/backlog/` file with a stated reason**. Nothing silently dropped.
4. `pytest` runs the API test suite from `founder-os/apps/api/`; `turbo test` works at
   the monorepo root; CI runs the unit tier green.
5. `app/integrations/` adapter framework exists; Google Calendar is migrated onto it
   behavior-preservingly as the first adapter.
6. `docs/architecture.md` and `standards/testing.md` updated; a new ADR in
   `docs/decisions.md` records the integrations framework.
7. All work honestly reported per CLAUDE.md rule 7 (failing output shown, no
   unverified "done").

## Stage 1 — Live audit (read/probe only; no product-code changes)

Boot via `./start.sh` and probe each subsystem end-to-end, in dependency order:

| # | Subsystem | Probe |
|---|-----------|-------|
| 1 | Boot: Docker (Postgres+Redis), Alembic migrations, uvicorn, Celery, web | start.sh logs; `/health`-style endpoints; migration head vs. models |
| 2 | Auth path | How `test_*.py` scripts pass Clerk; whether a dev bypass exists (**security finding if so**); why `app/api/test_routes.py` ships in the app |
| 3 | Orchestrator + agent chat | Real round-trip through Ollama `llama3.1:8b`; delegation to ≥1 specialist |
| 4 | Memory (4-layer + temporal KG) | Write/read across layers; `memory_pages` scoring paths |
| 5 | Knowledge / RAG | PDF ingest → chunk/embed (`nomic-embed-text`) → retrieval grounding |
| 6 | Planner + weekly plan | Plan generation; APScheduler job registration |
| 7 | Google Calendar | OAuth config validity; plan→calendar sync (founder-assisted for real consent) |
| 8 | Workflows / automations | AOV in-process graph execution; whether n8n is provisioned at all (docker-compose?), `n8n_client` reachability |
| 9 | Approval gate | 3-tier classification enforced server-side on a MEDIUM/HIGH action |
| 10 | Crawler, billing, settings, activity, history, queue routes | Smoke each router |
| 11 | Frontend | Boot, auth flow, dashboard / knowledge / workflows pages against live API |

Output: `reports/2026-07-03-phase0-audit.md` — verdict + evidence per row, ranked
fix list at the end. Audit makes **no product-code changes**.

## Stage 2 — Repair

- Each FAIL becomes a fix via [workflows/bug_fix.md](../../../workflows/bug_fix.md):
  root cause (systematic debugging) → failing regression test → fix → live re-verify.
- **Priority order:** boot blockers → agents/chat → calendar → workflows/automations
  → remaining routes/frontend.
- Fixes touching auth, approval gate, secrets, or external input additionally get an
  eng-security pass (CLAUDE.md §7 step 6).
- Where verification needs founder-only access (e.g. real Google OAuth consent,
  Clerk dashboard), ship a mocked automated test + a short recorded manual
  verification step for the founder in the audit report.
- Deferral rule: a FAIL may be deferred only with a `tasks/backlog/` file naming the
  failure, evidence, and why it is not fixed now.

## Stage 3 — Structural reshape (surgical, behavior-preserving)

### 3a. Integration adapter framework — the seam for Phases 1–4

New package `app/integrations/` (existing module refactored into it):

```
app/integrations/
├── base.py          # IntegrationAdapter ABC
├── registry.py      # register/lookup; settings-driven enablement
└── google_calendar/ # first adapter: calendar_integration.py migrated here
```

`IntegrationAdapter` (sketch — final signatures set at architecture step):

- `name: str`, `capabilities: set[Capability]`  (`OBSERVE`, `SYNC`, `HEALTH`)
- `async configure(settings) -> None` — creds/config; secrets stay in env/DB per
  standards/security.md
- `async health() -> HealthStatus`
- `async observe() -> list[ObservedEvent]` — pull external events/state, tagged
  provenance `observed`, shaped to feed the State Engine reconciler in Phase 1
  (interface designed against the task 011 / ADR-009 spec so Obsidian drops in)
- `async sync(changes) -> SyncResult` — push canonical state outward

Rules: adapters own **no business logic** (reconciliation lives in the engine,
Phase 1); adapters are registered, not imported ad-hoc; each adapter independently
testable with a fake transport. Recorded as an ADR in `docs/decisions.md`.

### 3b. Test harness

- `apps/api/tests/` with `unit/` and `integration/`; pytest + pytest-asyncio + httpx.
- Live-server tests marked `@pytest.mark.live` (need `./start.sh` stack); unit tier
  runs anywhere with no services.
- Existing root `test_*.py` scripts migrated into the tree (or wrapped) — none lost.
- `turbo test` task added; CI (existing GitHub Actions) runs lint + typecheck +
  unit tier.

### 3c. Targeted splits only

Measure first; split only files that are demonstrably oversized/tangled — candidates:
`models.py`, `orchestrator.py`, `api/routes.py`. Each split: suite green before →
move → suite green after, no behavior change. No wholesale re-layout (explicitly
rejected big-bang option B).

### 3d. Documentation

- `docs/architecture.md`: integrations framework + test-harness sections.
- `standards/testing.md`: rewritten to the pytest reality.
- ADR: integration adapter framework.
- Roadmap: Phase table from this spec reflected in `docs/roadmap.md`.

## Out of scope for Phase 0

- The State Engine itself (Phase 1, task 011) — Stage 3a only builds the seam.
- Obsidian / Notion / Paperclip adapters; Hermes skills feed (Phases 1–4).
- Deployment/productionization (Phase 5).
- Replacing tool stubs (`web_search`, `get_business_metrics`) — stays on roadmap.
- New features of any kind.

## Risks & mitigations

- **Clerk auth blocks live probing** → audit item #2 resolves how first; if a dev
  bypass exists it becomes a security finding with a proper test-auth design.
- **Founder-only external accounts (Google OAuth, Clerk)** → mocked tests + recorded
  manual verification steps; audit marks these BLOCKED rather than guessed.
- **`llama3.1:8b` quality makes agent tests flaky** → agent tests assert on
  structure/round-trip success, not response content quality.
- **n8n may not be provisioned at all** → audit verifies; if absent, workflows are
  validated on the in-process AOV path (the default per ADR-009) and n8n provisioning
  is deferred to the task-004 backlog item, not hacked in.
- **Scope creep during repair** → deferral rule above; reshape limited to 3a–3d.
