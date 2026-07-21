# Design — The Company State Engine direction

- Date: 2026-06-22
- Status: approved (brainstorm), pending implementation plan
- Author: engineering org (this session)
- Related: ADR-009 (docs/decisions.md), ADR-008 (n8n), tasks/completed/011-company-state-engine.md

> This spec records a **strategic repositioning** of Founder OS and the **first build
> slice** that proves it. It is the source of truth that `readme.md`, `docs/vision.md`,
> `docs/architecture.md`, `docs/roadmap.md`, and ADR-009 are derived from. Keep them in
> sync with this document, not the other way around.

---

## 1. The shift

**Before:** the headline differentiator was *auto-generated workflows* executed via a
self-hosted **n8n** backend (ADR-008 / task 004).

**After:** the moat is the **Company State Engine** — a canonical, living model of the
company (goals · projects · tasks · decisions · metrics · people · meetings · notes),
fed by **passive multi-channel observation** and **surfaced where the founder already
works** (Obsidian first, Notion later). It is wrapped in the **five loops of autonomy**:
Observe → Remember → Understand → Execute → Learn.

The core founder pain this targets: **fragmentation and app-switching.** Slack knows the
conversation, GitHub knows the code, Stripe knows revenue, Obsidian/Notion know the docs —
**no system knows the company.** Every external tool becomes a *synchronization endpoint*;
the State Engine is the single canonical model they reconcile into and out of.

**n8n is demoted, not deleted.** Dynamic in-process AOV graphs (the existing Orchestrator)
are the default execution model. n8n survives as an *optional, invisible execution backend*
under the State Engine for founders who want a visible/editable flow. ADR-008 and the
in-flight `app/workflows/` code remain valid; their **positioning** changes (see ADR-009).

## 2. The State Engine vs. the layers that already exist (no duplication)

Founder OS already has three memory-ish layers. The State Engine is a **fourth, distinct**
one. Being explicit prevents reinventing existing machinery:

| Layer | Status | Role |
|---|---|---|
| `knowledge_items` (pgvector RAG) | built | unstructured document recall |
| `memory_pages` / `memory_links` (temporal KG) | built | episodic/semantic memory; **decays**; composite scoring |
| 4-layer agent memory (Redis + pg) | built | in-flight context assembled per agent run |
| **Company State Engine** | **NEW** | **structured, canonical, non-decaying "current truth"** — typed entities + typed relations + provenance |

- The State Engine is the authoritative **normalized** model of the company.
- Memory + RAG remain the **recall** substrate.
- **Ingestion feeds both:** a founder note becomes a state `task`/`decision` **and** a RAG
  chunk; a system-learned fact becomes a `memory_page` **and**, if canonical, a state entity.

## 3. Three feeds into the engine

The engine is updated from three kinds of source, each carrying provenance:

1. **`observed`** — passive adapters watching the founder's tools. Obsidian first
   (slice 1); GitHub / Stripe / Slack / Calendar / Notion later.
2. **`user_doc`** — documents the founder hands it (the existing PDF→RAG / knowledge
   ingestion path, extended to also emit state entities). Highest trust, durable.
3. **`system`** — knowledge the system generates itself: memories the agents write and
   **Hermes-style procedural skills** they learn from successful runs. Lowest default
   trust — it must *earn its keep* via the hygiene system (§5).

## 4. Data model (lean, extensible; Alembic-only)

New tables, user-scoped, following existing ORM/migration conventions. Designed so the
later feeds (`user_doc`, `system`) and the Curator need **no schema change** to land.

- **`state_sources`** — a registered source per user: `type` (`obsidian|github|stripe|
  slack|calendar|notion|user_doc|system`), `config` JSONB (e.g. vault path + managed
  subfolder), `sync_cursor`, `status`, `last_synced_at`.
- **`state_observations`** — raw inbound events: `source_id`, `external_id`, `payload`
  JSONB, `observed_at`, `processed_at`. Gives **idempotency** (dedup by `external_id`) and
  a provenance/audit trail. The Observe→Remember boundary.
- **`company_state_entities`** — typed canonical entities: `entity_type`
  (`goal|project|task|decision|metric|person|meeting|note`), `title`, `status`, `attributes`
  JSONB, plus provenance: `source` (one of the three feeds), `confidence`,
  `last_asserted_at`, `pinned`. User-scoped.
- **`state_relations`** — typed edges between entities (`part_of`, `affects`, `blocks`,
  `mentions`, `derived_from`), `strength` 0–1. Mirrors the existing `memory_links` pattern.

## 5. The hygiene system (anti-bloat) — a real mechanism, not a vibe

Founder requirement: *the memories/entities the system keeps must be genuinely useful, not
bloat.* Five mechanisms, layered:

1. **Write-gate (at the source).** Nothing persists unless it passes a usefulness test:
   **novel** (not a near-duplicate of an existing entity/memory), **specific** (not generic
   filler), **durable** (matters beyond this session). Cheap heuristics first (length,
   triviality, exact-match); an LLM judge only on borderline cases to control cost.
2. **Provenance trust-weighting.** `user_doc` > `observed` > `system`. System-generated
   items start at lower confidence and are pruned more aggressively.
3. **Dedup-on-ingest.** Before insert, a semantic-similarity check against existing entities
   of the same type; a near-duplicate **merges/updates** the existing row (bumping
   `last_asserted_at` + `confidence`) rather than creating a new one.
4. **Decay + composite scoring.** Reuse the existing `memory_pages` decay/scoring machinery;
   unpinned, low-confidence, rarely-accessed items fade. `user_doc`-sourced canonical
   entities are pin-eligible.
5. **Curator pass (periodic).** A scheduled job (Celery/APScheduler) merges overlapping
   entities and **Hermes skills**, archives stale ones, and surfaces aging-but-important
   items for review (spaced repetition). This is the blueprint's Skill Curator generalized
   to the whole engine.

**Slice 1 ships #1 (write-gate) and #3 (dedup-on-ingest)** inside the reconciler. #2/#4/#5
are *designed-for* now (provenance + confidence fields exist) and built in later phases.

## 6. The reconciler

The Observe→Remember core, reused by every feed:

```
inbound event
  → record state_observation (idempotent by external_id)
  → write-gate (§5.1): drop if not novel/specific/durable
  → dedup-on-ingest (§5.3): match existing entity of same type by semantic similarity
  → match? update entity (merge attributes, bump confidence/last_asserted_at)
    no match? create company_state_entity with provenance
  → infer/maintain state_relations
  → mirror into RAG (knowledge_items) and, where canonical, memory_pages
```

## 7. Slice 1 — Obsidian, end-to-end (the proof)

**Goal:** one local Obsidian vault → state updates → state visible back inside Obsidian,
fully local-first, no OAuth, dogfoodable on the founder's machine.

- **Inbound (Observe → Remember).** Read a configured vault path; parse markdown
  (frontmatter, headings, `- [ ]` checkboxes) → reconcile (§6) into `company_state_entities`
  **and** RAG. v1: a **triggered sync endpoint** (`require_auth`, user-scoped). v1.1
  (optional): a `watchdog` file-watcher for live updates.
- **Outbound (Sync back).** Render canonical state into a **managed `FounderOS/`
  subfolder** in the vault (`Goals.md`, `Projects/*.md`, `Tasks.md`, `Decisions.md`). The
  founder sees the unified company model *inside Obsidian*.
- **Conflict model (deliberately simple for v1).** The engine **owns** the managed
  subfolder (outbound; last-write-wins + provenance). The rest of the vault is **read-only
  observed** (inbound). No destructive two-way merges in v1.
- **Mapping rules (v1):** `- [ ]`/`- [x]` → `task` (status from checkbox); frontmatter
  `goal:` / `project:` → `goal`/`project`; a note tagged `#decision` or under a `Decisions/`
  path → `decision`; otherwise the note → `note`. Relations: a task under a project note →
  `part_of`.

## 8. The five loops → built vs. new

- **Observe** — *new*: source adapters; Obsidian first.
- **Remember** — *exists* (memory + RAG) + *new* state ingestion via the reconciler.
- **Understand** — *evolve*: grow the planner/ICE machinery into goal-tracing over state
  (which entities move which goals).
- **Execute** — *exists*: Orchestrator / dynamic AOV graphs; n8n demoted to optional.
- **Learn** — *partial*: feedback/insight tables exist → add Hermes procedural skills +
  the Curator (§5.5).

## 9. Security & constraints (unchanged invariants)

- Every new user-facing endpoint requires Clerk JWT (`require_auth`) and scopes data to the
  authenticated user (`standards/security.md`).
- Schema changes via **Alembic only**, never hand-edited `schema.sql` (CLAUDE.md §5.8).
- Provider-neutral: the write-gate LLM judge uses the existing pluggable provider layer.
- Vault path is local + config-driven; no secrets logged or committed. A vault outside the
  API process (e.g. Docker) requires a mounted directory — documented in the task.

## 10. Documents this spec drives

1. `readme.md` — reframe the pitch (State Engine + 5 loops headline; n8n a sub-bullet).
2. `docs/vision.md` — new differentiator.
3. `docs/architecture.md` — Company State Engine + Observation layer + relationship to the
   existing memory layers.
4. `docs/roadmap.md` — State Engine becomes the flagship (Phase 1 + Obsidian slice); n8n →
   optional/later.
5. `docs/decisions.md` — **ADR-009** (architecture + positioning shift + n8n demotion).
6. `tasks/completed/011-company-state-engine.md` — the product+plan task file.

## 11. Out of scope (slice 1 — explicit)

GitHub/Stripe/Slack/Calendar/Notion adapters; bidirectional destructive merge; the full
Curator pass (#5); Hermes skill authoring; the `user_doc`→state emitter (RAG ingestion
stays as-is in v1); live file-watcher is optional (v1.1); Understand-loop goal-tracing.
These are phased follow-ons, designed-for but not built in slice 1.
