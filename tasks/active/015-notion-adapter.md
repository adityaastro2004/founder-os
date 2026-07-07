---
id: 015
title: Company State Engine — Notion adapter (Phase 2, second sync surface)
status: in-progress
stage: product
owner: eng-product
created: 2026-07-07
dependencies: [011]
links: [docs/superpowers/specs/2026-06-22-company-state-engine-design.md, docs/superpowers/specs/2026-07-04-phase1-state-engine-architecture.md, tasks/completed/011-company-state-engine.md, docs/decisions.md, docs/roadmap.md]
---

# 015 — Company State Engine: Notion adapter (Phase 2)

> Phase 2 of the revamp (roadmap: `next` → `now` with this task). The second `observed`
> source for the State Engine (design spec §3 feed 1), mirroring the Obsidian slice
> (spec §7) on a remote, API-token workspace instead of a local vault. **Everything
> engine-side already exists and is reused as-is**: the reconciler (write-gate, dedup,
> provenance), the four state tables, the `/api/state` source lifecycle, and the ADR-010
> `IntegrationAdapter` ABC (`app/integrations/obsidian/` is the reference implementation).
> This task defines WHAT and WHY; the *how* (mapping rules, token storage, containment
> mechanism, client choice) is `eng-architect`'s — see the routed questions at the end.

## Objective

Wire **Notion** as the second end-to-end sync surface of the Company State Engine:
(a) passively observe the pages and databases a founder shares with a Notion internal
integration into canonical company state (+ RAG mirror), and (b) render the **unified**
company model (all sources, including Obsidian-fed entities) back into a managed
"Founder OS" page tree inside Notion that the engine owns. Token-pasted, local-first
setup — no OAuth server dance; the founder's explicit page-sharing *is* the consent and
scoping model.

## Why this matters

Notion is where a large share of target founders actually keep docs, tasks, and
roadmaps — for them, slice 1 (Obsidian) proves the loop but doesn't touch their real
workspace. Each tool added to the unified model removes one more reason to app-switch
(ADR-009); Notion is the highest-coverage second surface. It also proves the ADR-010
adapter seam does its job: **a second, remote, rate-limited, structured source lands
with zero reconciler/schema redesign** — the claim the whole adapter architecture was
built on. Structured Notion databases (status, checkbox, date properties) are *richer*
observation signal than markdown checkboxes, so state fidelity should go up, not just
coverage.

## User stories  <!-- eng-product -->

**US-1 — Observe my Notion workspace into company state**
As a founder, I want Founder OS to read the Notion pages and databases I've shared with
it and turn them into structured company state (goals, projects, tasks, decisions,
notes) so that the system knows what's going on without me re-entering anything —
including staying in step when I complete a task or trash a page in Notion.

**US-2 — See the unified company model inside Notion**
As a founder, I want the canonical state — from *all* my sources, not just Notion —
rendered into a managed "Founder OS" page tree in my workspace (Goals, Projects, Tasks,
Decisions) so that I see one source of truth where I already work, while everything
else I've shared stays strictly read-only to the engine.

**US-3 — Connect safely with a token I control**
As a founder, I want to connect Notion by pasting an internal-integration token and
sharing only the pages/databases I choose, so that scope stays under my control, and I
want that token treated as a secret everywhere (never in source config, logs, or API
responses) so a leak of any of those never leaks my workspace.

**US-4 — Structured databases become high-fidelity state**
As a founder, I want rows of my task/roadmap databases to become task entities whose
status tracks the database's checkbox/status property, so that the engine's model is at
least as accurate as Notion itself — richer than what plain markdown could express.

**US-5 — State stays clean and auditable, same as slice 1**
As a founder, I want the same hygiene (no duplicates, no trivial filler) and the same
provenance (which source, when, what confidence) to apply to Notion-fed entities, so
that adding a second source makes the model bigger, not messier.

## Acceptance criteria (Phase 2)

**US-1 — Observe**
- [ ] A Notion source registered through the **existing** `/api/state` source lifecycle
      (`type: "notion"`; no new top-level surface) can be synced; the sync ingests the
      pages and database rows shared with the integration into `state_observations` and
      reconciles them into `company_state_entities` (+ relations) and the RAG mirror,
      all with provenance `observed`.
- [ ] Mapping (v1, product-level — exact detection rules are the architect's): rows of a
      database with a checkbox/status property → `task` with `open|done` derived from
      that property; project-like containers (e.g. a projects database or designated
      parent pages) → `project`; decision-marked pages (e.g. a `Decisions` database/page
      or equivalent tag) → `decision`; a goals database/page → `goal`; any other shared
      page → `note`. Containment in Notion (row-in-database, page-under-page) produces
      `part_of` / `derived_from` relations, mirroring the Obsidian rules.
- [ ] Re-running the sync with no workspace changes is **idempotent**: zero new
      entities; the sync report shows `created=0` and `unchanged == observed`.
- [ ] Toggling a task's checkbox/status property in Notion and re-syncing flips the
      status of the **same** entity (same id) — no duplicate (the Notion analogue of
      011's checkbox-toggle criterion).
- [ ] Archival honored: moving an observed page/row to Notion trash and re-syncing
      results in the corresponding entity being archived / no longer asserted — it is
      never resurrected by later syncs.
- [ ] Consent boundary: content **not** shared with the integration never appears in
      observations or entities — verified in E2E by keeping an unshared control page in
      the test workspace and asserting its absence from state.

**US-2 — Sync back (managed page tree)**
- [ ] The engine renders current canonical state (all of the user's active entities,
      across sources) into a managed page tree under a founder-designated root page
      (the Notion equivalent of the `FounderOS/` folder: Goals, Projects, Tasks,
      Decisions), creating/updating pages under that root only.
- [ ] The engine **never writes outside the managed page tree**: verified — the E2E
      snapshots the `last_edited_time` (and/or content) of every other page/database
      shared with the integration before an outbound sync and asserts all are unchanged
      after. Any miss is P0 (same hardness as 011's vault-safety criterion).
- [ ] The managed tree is **excluded from observation** (the engine never ingests its
      own rendered output — no feedback loop), mirroring the Obsidian exclude rule.
- [ ] Re-rendering unchanged state is churn-free: no Notion edits are made when the
      rendered content is identical (protects rate-limit budget and keeps the founder's
      "recently edited" feed and page history free of no-op noise).

**US-3 — Token & consent**
- [ ] Registering a Notion source requires an internal-integration token supplied by
      the founder; an invalid/revoked token produces an actionable error (at
      registration and, if revoked later, as the source's `last_error`) — never a crash
      and never a token echoed back.
- [ ] The token is **never** stored in `state_sources.config` (architecture spec §1.2
      rule), never returned by any API response, and never written to logs — verified
      by a DB/API-response check plus a log scan in the live E2E; eng-security signs
      off on the storage path.
- [ ] Setup docs tell the founder to grant the integration content-only capabilities
      (read/update/insert; no user-information capability) — least privilege consistent
      with comments/users being out of scope.

**US-4 — Structured-signal fidelity**
- [ ] Database property signal survives into state: for a to-do style database, entity
      status comes from the checkbox/status property (not title text), and available
      structured properties (e.g. due date, select/tags) are preserved on the entity's
      attributes for later phases to use.

**US-5 — Hygiene + provenance (reconciler reused, verified not assumed)**
- [ ] Write-gate and dedup-on-ingest apply unchanged to Notion events: a trivial/empty
      page (e.g. an untitled empty stub) is gated; a near-duplicate page of an existing
      entity of the same type merges (bumping `confidence` / `last_asserted_at`) instead
      of inserting — spot-checked in the E2E.
- [ ] Every Notion-fed entity exposes provenance on the existing read API
      (`GET /api/state/entities`): `source=observed`, the Notion source's
      `source_id`/`source_name`, `external_ref`, `confidence`, `last_asserted_at`.

**Cross-cutting**
- [ ] All touched endpoints remain Clerk-JWT-guarded (`require_auth`) and user-scoped;
      the Notion source reuses the existing source lifecycle (register / list / patch /
      delete / trigger-sync / poll) rather than adding parallel routes.
- [ ] Sync stays queue-shaped (async trigger + poll, as slice 1) and is **rate-limit
      resilient**: a full sync of the reference test workspace completes despite
      Notion's ~3 req/s average limit and 100-item pagination — 429s are retried/backed
      off, never a permanent sync failure; the E2E workspace is large enough to force
      at least one paginated request.
- [ ] Any schema change goes through Alembic only; the expectation is **none or
      near-none** (the four state tables, feed values, and `state_sources.type
      = 'notion'` already exist) — a deviation needs an architect-recorded reason.
- [ ] Live E2E recorded against a real Notion workspace through the live stack
      (`:8000`, per `standards/testing.md`): register → sync → entities/relations/
      provenance asserted → idempotent re-sync → status toggle → trash-archival →
      managed tree rendered → outside-tree safety snapshot → token-hygiene log scan.
      Testability note for planner/QA: this requires a dedicated test workspace +
      token via env (e.g. `NOTION_TEST_TOKEN`); the live test may skip when the env is
      absent, but **this task's gate record requires an actual recorded run**, not a
      skip. Unit tier covers mapping/containment/pagination logic against recorded or
      faked API payloads (no network).

## Success metrics  <!-- eng-product -->
- **Loop proven (binary gate):** one real Notion workspace → state populated → managed
  "Founder OS" page tree rendered back inside Notion, with recorded live verification.
- **Idempotency (hard):** re-sync of an unchanged workspace creates zero entities
  (`created=0`, `unchanged == observed`).
- **Safety (hard; any miss is P0):** zero writes outside the managed page tree, and
  zero ingestion of unshared content or of the managed tree itself.
- **Secret hygiene (hard; any miss is P0):** token absent from `state_sources.config`,
  API responses, and logs.
- **Fidelity signal:** database status round-trip proven (property toggle → same
  entity flips, no duplicate).
- **Adapter-seam claim validated:** lands with no reconciler redesign and no (or
  architect-justified minimal) schema change — the measurable payoff of ADR-010.

## Out of scope (Phase 2 — explicit)
- **OAuth public-integration flow** — v1 is a pasted internal-integration token
  (local-first; no callback server, no token exchange). OAuth is a hosted-deployment
  concern (Phase 5+).
- **Real-time webhooks / Notion webhook subscriptions** — triggered sync only, matching
  slice 1. Scheduled periodic polling is a named fast-follow (the sync path must stay
  queue-shaped so a scheduler reuses it unchanged, which it already is).
- **Two-way edits of founder content** — everything outside the managed tree is
  read-only observed; no destructive merges; the managed tree is engine-owned
  last-write-wins (same conflict model as slice 1).
- **Comments and users/people ingestion** (and permissions mirroring) — content only.
- **Media/file block ingestion** (images, files, embeds) — text-bearing content only in v1.
- **Other phases' feeds and features** — `user_doc`/`system` emitters, Hermes skills
  (Phase 3), Paperclip/MCP (Phase 4), Curator/decay/trust-weighting, Understand-loop
  goal-tracing, other observation adapters (GitHub/Stripe/Slack/Calendar).
- **Dashboard UI for Notion connect** — API-first like slice 1; UI is a follow-on.

## Must go to eng-architect before execution (design the *how*)
1. **Token storage & wiring:** where the internal-integration token lives — the existing
   `integrations` table (`access_token`, unique `user_id+integration_type`) vs env — and
   how the `state_sources` row references that credential. Binding constraint from the
   Phase 1 architecture §1.2: **tokens never live in `state_sources.config`.**
2. **Notion object → entity mapping (incl. databases):** precise rules for pages,
   database containers, database rows, to-do blocks inside pages, and which properties
   (checkbox/status/select/date) drive `status`/`attributes`; how goal/project/decision
   detection works in v1; and **how archival is detected** (per-object `archived`/
   `in_trash` flag vs disappearance from listings — the API's search-vs-retrieve
   semantics differ).
3. **`external_id` scheme from Notion UUIDs:** e.g.
   `notion:{source_id}:{kind}:{notion_uuid}` — Notion's stable object UUIDs remove the
   Obsidian rename problem, but block-level ids (to-dos inside pages) and
   database-row-vs-page identity need a decided scheme that keeps the toggle-updates-
   same-entity property.
4. **Managed-tree ownership guarantee:** the Notion analogue of the Obsidian write-jail —
   parent-page containment (every write's ancestor chain must terminate at the managed
   root page id), a single write-sink function structural rule, how pruning of stale
   managed pages works (archive orphans), and how the founder designates/creates the
   managed root at registration.
5. **Rate-limit & pagination strategy:** request budget under ~3 req/s average,
   `Retry-After`-honoring 429 backoff, 100-item pagination, batching; expected sync
   duration bounds and whether the slice-1 sync-lock TTL needs adjusting.
6. **Client dependency choice:** official `notion-client` SDK vs raw `httpx` against the
   versioned REST API (`Notion-Version` header pinning), judged by the same
   dependency-surface standard used for the Obsidian parser decision.
7. **Cursor/incremental sync via `last_edited_time`:** first sync full-walk vs
   incremental re-syncs using the existing `state_sources.sync_cursor` JSONB + the
   observation `content_hash` short-circuit; correctness under clock/cursor edge cases.
8. **Churn-free outbound rendering:** how "no write when rendered content is identical"
   is achieved (rendered-content hashing, block-diff, or equivalent) given markdown →
   Notion-blocks conversion.

## Founder dogfood step (post-merge)
Create a Notion internal integration (content capabilities only), share your real
pages/databases plus a "Founder OS" root page with it, register the source through
`/api/state`, trigger a sync, and open the managed tree in Notion. Mirrors the 011
dogfood step; API-first.

## Next agent
→ **eng-architect**: answer the eight questions above and produce the buildable design
(mirroring the Phase 1 architecture doc's rigor — decision table, safety-invariant test
battery, live-E2E skeleton), reusing the reconciler, the four state tables, the ADR-010
ABC, and `app/integrations/obsidian/` as the reference adapter; then **eng-executor**
builds against it without redesign.
