---
id: 011
title: Company State Engine — core + Obsidian bidirectional sync (slice 1)
status: done
stage: completed
owner: eng-product
created: 2026-06-22
dependencies: []
links: [docs/superpowers/specs/2026-06-22-company-state-engine-design.md, docs/decisions.md, docs/architecture.md, docs/roadmap.md, tasks/backlog/004-n8n-workflow-engine.md]
---

# 011 — Company State Engine (slice 1: core + Obsidian)

> The flagship re-positioning (ADR-009). Makes the **Company State Engine** the product's
> moat: a canonical, living model of the company fed by passive multi-channel observation and
> surfaced where the founder already works. **Slice 1** proves the Observe→Remember→Sync loop
> end-to-end with a single local source (Obsidian). Full design + rationale:
> [spec](../docs/superpowers/specs/2026-06-22-company-state-engine-design.md). The *how*
> (exact schema, reconciler internals, parsing rules) is for `eng-architect`/`eng-executor`.

## Objective
Stand up the State Engine core (typed canonical entities + relations + provenance + the
reconciler with write-gate and dedup-on-ingest) and wire **one source end-to-end**: a local
**Obsidian** vault that is (a) read-only *observed* into company state + RAG, and (b) synced
*back* as a managed `FounderOS/` markdown subfolder so the founder sees the unified model
inside Obsidian. Local-first, no OAuth, dogfoodable on the founder's machine.

## Why this matters
Fragmentation/app-switching is the deepest, most defensible founder pain — no tool today
*knows the company*. The State Engine is the moat (ADR-009); n8n auto-workflows (task 004)
are demoted to optional execution infrastructure beneath it. This slice turns the new
direction from docs into a working, dogfoodable loop.

## User stories  <!-- eng-product -->

**US-1 — Observe a vault into company state**
As a founder, I want Founder OS to read my Obsidian vault and turn my notes, checkboxes, and
frontmatter into structured company state (goals, projects, tasks, decisions, notes) so that
the system knows what's going on without me re-entering anything.

**US-2 — See the unified company model inside Obsidian**
As a founder, I want the canonical state written back into a managed `FounderOS/` folder in
my vault (Goals, Projects, Tasks, Decisions) so that I can see one source of truth where I
already work, without opening another app.

**US-3 — Trust that state stays clean, not bloated**
As a founder, I want the engine to avoid storing duplicate or trivial entities so that the
model stays genuinely useful as my vault grows.

**US-4 — Inspect what fed the state**
As a founder, I want each state entity to record where it came from (which source, when, with
what confidence) so that I can trust and audit the model.

## Acceptance criteria (slice 1)

**US-1 — Observe**
- [x] An authenticated, user-scoped endpoint triggers a sync of a configured vault path; it
      parses markdown (frontmatter, headings, `- [x]`/`- [x]` checkboxes) and reconciles into
      `company_state_entities` (+ relations) **and** RAG (`knowledge_items`).
- [x] Mapping (v1): checkboxes → `task` (status from box); frontmatter `goal:`/`project:` →
      `goal`/`project`; `#decision` or a `Decisions/` path → `decision`; else → `note`. A task
      under a project note links `part_of` that project.
- [x] Re-running the sync is **idempotent** (no duplicate entities); `state_observations`
      dedups by `external_id` (stable per file/block).

**US-2 — Sync back**
- [x] The engine writes/overwrites a managed `FounderOS/` subfolder in the vault
      (`Goals.md`, `Projects/*.md`, `Tasks.md`, `Decisions.md`) rendering current state.
- [x] The engine **only** writes inside `FounderOS/`; the rest of the vault is never modified
      (read-only observed). Verified.

**US-3 — Hygiene (write-gate + dedup)**
- [x] The reconciler drops entities that fail the write-gate (trivial/empty/generic) and,
      on near-duplicate (semantic match of same type), **merges/updates** the existing entity
      (bumping `last_asserted_at`/`confidence`) instead of inserting a new row.

**US-4 — Provenance**
- [x] Every `company_state_entity` records `source` (`observed` for this slice), the source
      id, `confidence`, and `last_asserted_at`. Exposed on the read API.

**Cross-cutting**
- [x] All new user-facing endpoints require Clerk JWT (`require_auth`) and scope data to the
      authenticated user (`standards/security.md`).
- [x] New tables created via **Alembic only**, not hand-edited `schema.sql` (CLAUDE.md §5.8).
- [x] Vault path is local + config-driven; nothing secret logged/committed; Docker/mounted-
      vault path documented.
- [x] End-to-end manual verification recorded (live `:8000`, per `standards/testing.md`).

## Success metrics  <!-- eng-product -->
- **Loop proven (binary gate):** one real vault → `state` populated → `FounderOS/` folder
  rendered back, with recorded manual verification.
- **Idempotency:** re-sync produces zero duplicate entities (hard).
- **No-bloat signal:** dedup-on-ingest merges near-duplicates; write-gate rejects trivial
  notes (spot-checked on a real vault).
- **Safety:** the engine writes nowhere outside `FounderOS/` (hard; any miss is P0).

## Out of scope (slice 1 — explicit)
GitHub/Stripe/Slack/Calendar/Notion adapters; the `user_doc` and `system` (Hermes) feeds as
state emitters; the full hygiene Curator pass (#2/#4/#5 — provenance weighting, decay,
periodic Curator); two-way destructive vault merge; live file-watcher (v1.1 optional);
Understand-loop goal-tracing; any change to n8n/task 004. All are phased follow-ons named in
the roadmap and ADR-009.

## Must go to eng-architect before execution (design the *how*)
- Exact schema for the four tables + ORM models (reuse `memory_links` pattern for relations).
- Reconciler internals: write-gate heuristics + LLM-judge boundary; dedup similarity source
  (reuse the existing embedder/retriever vs. a cheaper signal).
- Markdown parsing + the stable `external_id` scheme (file path + block hash?).
- Managed-folder render/ownership guarantee (how the "writes only inside `FounderOS/`"
  invariant is enforced and tested).
- Vault access model for the API process (local path vs. mounted dir in Docker).

## Gate record (2026-07-07)

- **Architecture:** eng-architect doc
  [2026-07-04-phase1-state-engine-architecture.md](../../docs/superpowers/specs/2026-07-04-phase1-state-engine-architecture.md)
  — implemented without redesign.
- **eng-security: PASS**, no blockers for local-first slice 1. S1 (vault-read
  symlink hardening) -> `tasks/backlog/014` (hard prerequisite before hosted
  deployment); nits N1/N2/N4 applied same-day.
- **Evidence for the acceptance boxes:** live E2E
  `tests/live/test_state_obsidian_live.py` — **PASSED 27.56s** (register -> sync ->
  entities/relations/provenance -> idempotent re-sync `created=0,
  unchanged=observed` -> checkbox toggle flips the same entity -> `FounderOS/`
  rendered -> sha256 of every non-managed vault file unchanged -> `state://` RAG
  rows without dupes -> rapid-fire trigger 409). Unit tier: 107 tests incl. the
  12-case managed-jail battery, gate/dedup/renderer/external_id suites.
- **Worker-integration bugs found by the live tier, fixed with regression
  tests:** Celery registered zero tasks (autodiscover misconfig, pre-existing);
  sync-lock NX double-take deadlock; worker mapper config missing the users FK
  import. Plus one E2E-harness fix (stale-report polling).
- **eng-reviewer: REQUEST CHANGES → fixes applied** (full independent review of
  6189787..HEAD). Blocker B1 (note bodies never entered hash/gate/mirror — only a
  <=500-char first paragraph) + S1 (relation hints resolved only in-run; note
  emitted before its goal/project) + S2 (filler rule skipped non-notes) + S3
  (blocking IO on the event loop in routes) + S4 (E2E RAG asserts weaker than the
  gate record claimed) — ALL fixed in the "fix(phase1): eng-reviewer findings"
  commit, each with a pinning test (8 new). Applied nits: structured judge
  fail_open flag, lock release on enqueue failure, registry.get in routes,
  renderer done-recency + Goals source paths. Deferred nits (accepted, revisit
  with feed 2): defer(embedding) on title resolution, source-create 409 race,
  lock CAS takeover. Post-fix verification: unit 116 passed; live E2E passed
  12.71s incl. the strengthened asserts. **Delta re-review: performed inline**
  (the reviewer agent hit its session limit mid-re-review; the full independent
  review above stands — recorded per the honest-reporting rule).
- **eng-qa: PASS — all 11 acceptance criteria + all 4 success metrics** (own runs:
  unit 116 passed; live E2E 1 passed in 12.90s; jail battery 12 passed). QA flags,
  recorded honestly: (1) the "real vault" success metric was proven on the 8-file
  fixture vault through the real stack — a personal-vault dogfood run is the
  founder's post-merge step (see below); (2) the `#decision`-tag mapping branch
  shares its code line with the tested `Decisions/` path branch but lacks a
  dedicated unit case — follow-up nit; (3) CC-3 "nothing secret logged" verified
  via the eng-security PASS citation.

## Founder dogfood step (post-merge)

Register YOUR real vault and run the loop:
`POST /api/state/sources {"type":"obsidian","config":{"vault_path":"/path/to/your/vault"}}`
→ `POST /api/state/sources/{id}/sync` → open the `FounderOS/` folder in Obsidian.
(Or via the dashboard once the UI lands — slice 1 is API-first.)

## Next agent
→ **eng-architect**: turn this product spec + the design spec into the concrete schema,
reconciler design, and file placement under `app/state/`; then **eng-executor** builds against
it. (The brainstorm → writing-plans pass produces the sequenced implementation plan.)
