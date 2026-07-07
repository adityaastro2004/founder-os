# Architecture — Phase 1 Company State Engine (slice 1: core + Obsidian)

- Date: 2026-07-04
- Status: approved design — ready for `eng-executor`
- Author: eng-architect
- Task: [tasks/active/011-company-state-engine.md](../../../tasks/active/011-company-state-engine.md)
- Inputs: [design spec 2026-06-22](2026-06-22-company-state-engine-design.md) (§4–§7, §9),
  ADR-009 + **ADR-010** (docs/decisions.md), docs/architecture.md,
  standards/{api,security,coding,testing}.md
- Branch: `phase1-state-engine`

> This document is the buildable *how* for task 011. One decision per question; the
> executor implements against this without redesign. Paths below are relative to
> `founder-os/apps/api/` unless noted. **ADR-010 postdates the 06-22 spec:** the
> Obsidian integration is an `IntegrationAdapter` (`app/integrations/obsidian/`),
> not an `app/state/sources/` module — the reconciler consumes `ObservedEvent`s.

## 0. Decision summary

| Question | Decision (one line) |
|---|---|
| ORM placement | New `app/state/models.py` (mirrors the `planner_models_db.py` precedent); do **not** grow `models.py` (ADR-010 measurement note) |
| Migration | `alembic/versions/0002_state_engine.py`, `down_revision = "0001_workflow_engine"` (verified sole head) |
| Reconciler layout | `app/state/{models,reconciler,write_gate,dedup,renderer,mirror,service}.py` |
| Dedup similarity | Reuse the existing embedder (`app/retrieval/embeddings.py`, zero-pad to 1536 is cosine-preserving); cosine ≥ **0.88** merges |
| Write-gate judge | Heuristics first; LLM judge only on borderline, ≤ 10 calls/sync, 30s timeout, fail-open at confidence 0.5 |
| Obsidian parser | `python-frontmatter` (PyYAML already present) + stdlib line regex; **no** markdown-it |
| `external_id` | Path-keyed for notes, `path + sha256(normalized text)[:16]` for checkboxes; renames survive via dedup-merge, not id tracking |
| Managed-folder safety | Single write sink `client.write_managed()` — resolve symlinks then `is_relative_to(managed_root)`; renderer is pure (no IO) |
| API | `app/api/state_routes.py`, prefix `/api/state`, all `require_auth` + `get_or_create_user_id` |
| Sync execution | Always Celery (`default` queue) — F1 lesson: embedding + judge calls are LLM-bound; Redis `SET NX` lock per source |
| RAG mirror idempotency | `knowledge_items.source_url = "state://{source_id}/{external_id}"` as the key; skip when observation `content_hash` unchanged, else delete-and-reingest |

---

## 1. Schema (exact)

### 1.1 Conventions

- User scoping = `user_id UUID FK → users.id ON DELETE CASCADE` (the `models.py` /
  ADR-007 pattern; **not** the legacy `String(100)` Clerk id used by `memory_pages`).
  Routes resolve identity via `app.users.get_or_create_user_id`.
- UUID PKs with `server_default=text("uuid_generate_v4()")`, `created_at`/`updated_at`
  via the `_ts_now()` idiom (copy the private helpers into `app/state/models.py`;
  they are 6 lines — do not import private helpers across model modules).
- Feed values (`observed|user_doc|system`) and all eight entity types are **present in
  CHECK constraints now** so later feeds/Curator land with zero schema change (spec §4).

### 1.2 `state_sources`

| column | type | constraints |
|---|---|---|
| `id` | UUID | PK, `uuid_generate_v4()` |
| `user_id` | UUID | FK `users.id` ON DELETE CASCADE, NOT NULL |
| `type` | String(50) | NOT NULL; CHECK in (`obsidian`,`github`,`stripe`,`slack`,`calendar`,`notion`,`user_doc`,`system`) |
| `name` | String(255) | NOT NULL (default: derived from config, e.g. vault folder name) |
| `config` | JSONB | NOT NULL, server_default `'{}'` — Obsidian: `{"vault_path": str, "managed_folder": "FounderOS", "exclude_dirs": [".obsidian", ".trash", "Templates", "FounderOS"]}` |
| `sync_cursor` | JSONB | nullable — adapter-defined (unused by Obsidian v1; full walk each sync, change detection via observation `content_hash`) |
| `status` | String(50) | NOT NULL, server_default `'active'` — `active|paused|syncing|error` |
| `last_synced_at` | timestamptz | nullable |
| `last_error` | Text | nullable |
| `last_sync_report` | JSONB | nullable — `{observed, unchanged, created, merged, updated, gated, mirrored, rendered_files, duration_s}` |
| `created_at` / `updated_at` | timestamptz | `_ts_now()` |

Constraints/indexes: `UniqueConstraint("user_id", "type", "name")` (multiple vaults per
user allowed, distinct names); `Index("ix_state_sources_user", "user_id")`.

**No secrets in `config` for Obsidian** (local path only). When later adapters need
tokens, those live on the existing `integrations` table / env — never here.

### 1.3 `state_observations` (append-only; the Observe→Remember boundary)

| column | type | constraints |
|---|---|---|
| `id` | UUID | PK |
| `source_id` | UUID | FK `state_sources.id` ON DELETE CASCADE, NOT NULL |
| `user_id` | UUID | FK `users.id` ON DELETE CASCADE, NOT NULL (denormalized for scoped reads) |
| `external_id` | String(512) | NOT NULL (scheme in §3.3) |
| `kind` | String(100) | NOT NULL — `ObservedEvent.kind`, e.g. `obsidian.note`, `obsidian.task` |
| `payload` | JSONB | NOT NULL — the full `ObservedEvent.payload` |
| `content_hash` | String(64) | NOT NULL — sha256 hex of the canonicalized payload (`json.dumps(sort_keys=True, separators=(",",":"))`) |
| `provenance` | String(20) | NOT NULL, server_default `'observed'`; CHECK in (`observed`,`user_doc`,`system`) |
| `observed_at` | timestamptz | NOT NULL |
| `processed_at` | timestamptz | nullable |
| `outcome` | String(50) | nullable — `created|merged|updated|unchanged|gated|error` (audit of what the reconciler did) |
| `entity_id` | UUID | FK `company_state_entities.id` ON DELETE SET NULL, nullable — which entity this fed |
| `created_at` | timestamptz | `_ts_now()` |

Constraints/indexes:
- `UniqueConstraint("source_id", "external_id", "content_hash", name="uq_state_obs_dedup")`
  — **idempotency**: a re-sync of unchanged content inserts nothing
  (`INSERT … ON CONFLICT DO NOTHING`, rowcount 0 → skip reconcile). A real edit
  appends a new row → a bounded change-history audit trail (grows with edits, not
  with re-syncs).
- `Index("ix_state_obs_lookup", "source_id", "external_id", "observed_at")` — latest-
  observation resolution (§2.3 step 1).
- `Index("ix_state_obs_user", "user_id")`.

### 1.4 `company_state_entities`

| column | type | constraints |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK `users.id` ON DELETE CASCADE, NOT NULL |
| `entity_type` | String(50) | NOT NULL; CHECK in (`goal`,`project`,`task`,`decision`,`metric`,`person`,`meeting`,`note`) |
| `title` | Text | NOT NULL |
| `status` | String(50) | NOT NULL, server_default `'active'` — tasks use `open|done`; others `active|archived` |
| `summary` | Text | nullable — canonical short description; the embed text component |
| `attributes` | JSONB | NOT NULL, server_default `'{}'` — type-specific (`path`, `frontmatter`, `aliases[]`, `due`, `tags[]` …) |
| `source` | String(20) | NOT NULL; CHECK in (`observed`,`user_doc`,`system`) — the **feed** (provenance, US-4) |
| `source_id` | UUID | FK `state_sources.id` ON DELETE SET NULL, nullable — which registered source last asserted it |
| `external_ref` | String(512) | nullable — the `external_id` of the observation that created it (hard-idempotency key) |
| `confidence` | Numeric(4,3) | NOT NULL, server_default `'0.700'` (observed default; `user_doc`→0.900, `system`→0.400 later — no schema change) |
| `last_asserted_at` | timestamptz | NOT NULL, server_default NOW() |
| `pinned` | Boolean | NOT NULL, server_default `false` (decay design-for, spec §5.4) |
| `embedding` | Vector(1536) | nullable (`pgvector.sqlalchemy.Vector`, mirrors `memory_pages`) |
| `is_active` | Boolean | NOT NULL, server_default `true` (soft archive for the later Curator) |
| `created_at` / `updated_at` | timestamptz | `_ts_now()` |

Constraints/indexes:
- Partial unique: `Index("uq_state_entities_user_src_ref", "user_id", "source_id", "external_ref", unique=True, postgresql_where=text("external_ref IS NOT NULL"))`
  — the hard backstop that a re-sync can never double-create from the same block even
  if embedding dedup misbehaves.
- `Index("ix_state_entities_user_type", "user_id", "entity_type")`.
- **No ivfflat index in slice 1** — entity cardinality is small (10²–10³); exact scan
  is correct and avoids ivfflat training-on-tiny-table pitfalls. Revisit at ~50k rows.

### 1.5 `state_relations` (mirrors `memory_links`)

| column | type | constraints |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK `users.id` ON DELETE CASCADE, NOT NULL (memory_links lacks this; state reads must be user-scoped in one query) |
| `source_entity_id` | UUID | FK `company_state_entities.id` ON DELETE CASCADE, NOT NULL |
| `target_entity_id` | UUID | FK `company_state_entities.id` ON DELETE CASCADE, NOT NULL |
| `relation_type` | String(50) | NOT NULL, server_default `'mentions'` — `part_of|affects|blocks|mentions|derived_from` |
| `strength` | Numeric(3,2) | NOT NULL, server_default `'0.50'` |
| `metadata_` | JSONB | server_default `'{}'` (column name `metadata_`, DB column `"metadata_"` — the `memory_links` idiom) |
| `created_at` | timestamptz | `_ts_now()` |

Constraints/indexes: `UniqueConstraint("source_entity_id", "target_entity_id", "relation_type")`
(re-asserting a relation is a no-op upsert); `Index("ix_state_relations_user", "user_id")`.

### 1.6 ORM placement — `app/state/models.py` (decision + justification)

ADR-010 recorded that `models.py` (1029 lines / 32 classes) was measured and **not
split** — "revisit when a phase must modify them substantially." We are not modifying
those classes; we are adding a new bounded domain. Adding 4 tables + a Vector import
to `models.py` grows exactly the file the ADR chose to leave alone. The repo already
has the precedent for a domain-scoped ORM module (`planner_models_db.py`), registered
by explicit import in two places. So:

- ORM classes `StateSource`, `StateObservation`, `CompanyStateEntity`, `StateRelation`
  live in **`app/state/models.py`** on the shared `app.database.Base`.
- Registration (both are load-bearing, same as `planner_models_db`):
  - `app/main.py`: add `import app.state.models  # noqa: F401` next to the existing model imports.
  - `alembic/env.py`: add `import app.state.models  # noqa: F401, E402`.

### 1.7 Alembic migration

- File: `alembic/versions/0002_state_engine.py`
- `revision = "0002_state_engine"`, `down_revision = "0001_workflow_engine"` (verified:
  `0001_workflow_engine.py` is the only revision and current head).
- These four tables are genuinely new (not in `schema.sql`), so plain `op.create_table`
  in FK order (`state_sources` → `company_state_entities` → `state_observations` →
  `state_relations`; observations FK entities, so entities first), then the indexes.
  Keep the `_has_table` guard from the 0001 idiom around each create for safety on a
  partially-applied DB, but no column-reconcile pass is needed.
- `embedding` uses `from pgvector.sqlalchemy import Vector` (the extension is already
  installed by the pgvector image / base schema; do not `CREATE EXTENSION` here).
- `downgrade()`: drop the four tables in reverse dependency order (they are wholly
  owned by this migration — unlike 0001's shared tables, dropping is correct).
- Per the 0001 precedent, the migration is authoritative; `schema.sql` may be updated
  as a **secondary sync artifact** in the same PR (never the mechanism of change —
  CLAUDE.md §5.8).

---

## 2. Reconciler internals — `app/state/`

### 2.1 Module layout

```
app/state/
├── __init__.py
├── models.py        # ORM (§1)
├── reconciler.py    # Reconciler: ObservedEvent list → entities/relations (DB writes)
├── write_gate.py    # PURE heuristics + judge-boundary classification (no IO)
├── dedup.py         # candidate search (pgvector) + merge semantics
├── renderer.py      # PURE: entities → {relative_path: markdown}; NO filesystem imports
├── mirror.py        # RAG mirroring into knowledge_items (idempotent, §7)
└── service.py       # StateService: run_sync(source, direction) — the one entry point
                     #   used by the Celery task; wires adapter ⇄ reconciler ⇄ mirror ⇄ renderer
```

`service.py` composition (per sync run): loads the `StateSource`, looks the adapter up
via `app.integrations.registry.get("obsidian")` (never ad-hoc import — ADR-010),
builds the embedder once (§2.4), builds the LLM provider **lazily** (only if a
borderline case occurs), and executes: observe → reconcile each event → mirror →
render → adapter.sync → update `state_sources.last_sync_report/last_synced_at/status`.

### 2.2 Reconcile pipeline (per `ObservedEvent`)

```
event
 1. canonicalize payload → content_hash
 2. INSERT state_observations ON CONFLICT (source_id, external_id, content_hash) DO NOTHING
      rowcount 0 → outcome=unchanged, STOP (idempotency: AC US-1.3)
 3. resolve existing entity (hard keys, in order):
      a. latest prior observation with same (source_id, external_id) AND entity_id IS NOT NULL
         → that entity (this is the "same block, content changed" update path)
      b. exact-title match: same user_id + entity_type + casefolded/whitespace-collapsed title
 4. if no hard match → write_gate.evaluate() (§2.3)
      REJECT → outcome=gated, processed_at=now, STOP (never inserted)
 5. if no hard match → dedup.find_similar() (§2.4)
      sim ≥ threshold → merge into match (§2.5); else → create entity with provenance
 6. upsert relations (§3.4 mapping) — ON CONFLICT DO NOTHING on the unique triple
 7. mirror.mirror_entity() for note/decision bodies (§7)
 8. update observation row: processed_at, outcome, entity_id
```

All of steps 2–8 run inside one DB transaction per event (session per sync run,
commit per event) so a mid-sync crash leaves consistent per-event state.

### 2.3 Write-gate (`write_gate.py`) — concrete heuristics

Pure function: `evaluate(candidate: EntityCandidate) -> GateDecision` where
`GateDecision ∈ {ACCEPT, REJECT, BORDERLINE}` plus `reasons: list[str]`.

**Hard rejects (cheap, ordered):**
1. `title.strip()` shorter than **3 chars** → REJECT.
2. `task` candidates: checkbox text (after normalization, §3.3) shorter than **3 chars** → REJECT.
3. `note` candidates: `len(title) + len(body.strip()) < 10` chars → REJECT (empty stubs).
4. Triviality: casefolded title in the filler set
   `{"todo", "to do", "untitled", "new note", "notes", "misc", "temp", "test", "scratch", "asdf", "inbox"}`
   **or** title matching `^\d{4}-\d{2}-\d{2}$` (daily-note stub), **and** body < **40 chars**
   → REJECT. (Filler title + substantive body → BORDERLINE, not reject.)
5. Exact duplicate content is **not** a gate concern — unchanged content already stopped
   at the observation hash (§2.2.2), and exact-title matches took the hard-merge path (§2.2.3b).

**Borderline (the only trigger for the LLM judge):** passed all hard rejects but has
≥ 1 soft flag: (a) `note` with body < **25 words** and no frontmatter keys, no tags,
and no headings; (b) filler-ish title with substantive body (rule 4 carve-out);
(c) title is a bare URL or a bare filename. `task`/`decision`/`goal`/`project`
candidates are never BORDERLINE on brevity alone — a 4-word task is durable by nature.

**LLM judge (bounded, provider-neutral):**
- Fires **only** on BORDERLINE. Call path: `app.agents.llm.create_llm_provider(...)`
  from settings (the same provider-selection idiom as `profile_routes._get_llm_generate`)
  — never a vendor SDK (standards/security.md). One `generate()` call, `temperature=0`,
  `max_tokens≈200`, system prompt returning strict JSON `{"keep": bool, "reason": str}`.
- Bounds (new settings, §11): max **10** judge calls per sync run
  (`STATE_WRITE_GATE_JUDGE_MAX_PER_SYNC`), **30s** timeout per call
  (`STATE_WRITE_GATE_JUDGE_TIMEOUT_S`). On timeout/error/budget-exhausted the item is
  **accepted at confidence 0.5** (fail-open-low: hygiene must never wedge a sync or
  lose founder data; the future Curator prunes low-confidence rows). Judge `keep=false`
  → REJECT (`outcome=gated`, reason recorded in the observation row).

### 2.4 Dedup-on-ingest (`dedup.py`)

- **Embedder: reuse the existing provider** (`app/retrieval/embeddings.py`). Add one
  small factory `get_default_embedder(redis) -> EmbeddingProvider` **in
  `app/retrieval/embeddings.py`** replicating the provider-selection logic currently
  in `knowledge_routes._get_embedder` (that helper stays put in slice 1 — converge
  later; do not import a route module from `app/state/`). Zero-padding nomic-embed
  768→1536 is cosine-preserving (padded dims contribute 0 to both dot product and
  norms), so thresholds are meaningful.
- **Embed text:** `f"{entity_type}: {title}\n{(summary or '')[:500]}"` — one
  `embed_batch` per sync for all new candidates (the Redis-cached wrapper makes
  re-syncs nearly free).
- **Candidate scope:** same `user_id` **and** same `entity_type`, `is_active = true`,
  `embedding IS NOT NULL`. Query: top-5 by cosine distance. **Float-cast lesson (F3):**
  select similarity as an explicit cast —
  `CAST(1 - (embedding <=> CAST(:vec AS vector)) AS float8)` — asyncpg type inference
  on pgvector expressions is the recorded trap.
- **Threshold:** similarity ≥ **0.88** → merge; below → insert new. Configurable via
  `STATE_DEDUP_SIM_THRESHOLD` (§11). Rationale: near-duplicate titles/summaries of the
  same type sit ≥ 0.9 with nomic-embed; 0.88 gives margin without merging siblings
  ("Fix login bug" vs "Fix logout bug" land ~0.8).

### 2.5 Merge semantics (which fields, exactly)

The **existing** (matched) row survives; the incoming candidate folds in:

| field | rule |
|---|---|
| `title` | keep existing (stability for relations/rendering); append incoming title to `attributes.aliases[]` (dedup, cap 5) |
| `summary` | replace iff incoming is > 20% longer than existing, else keep |
| `status` | take incoming iff `observation.observed_at > entity.last_asserted_at` (checkbox toggle wins) |
| `attributes` | shallow merge, incoming wins per key (except `aliases`, which appends) |
| `confidence` | `new = min(0.99, old + (1 - old) * 0.15)` — asymptotic bump, never reaches 1.0 |
| `last_asserted_at` | `max(existing, observation.observed_at)` |
| `source_id` / `source` | set to the asserting source (latest asserter is the provenance shown) |
| `embedding` | re-embed only if `summary` changed, else keep |
| `external_ref` | keep existing (the partial unique index stays stable); the new external_id maps via `state_observations.entity_id` |

Incoming relations attach to the surviving entity; the unique triple dedups.

### 2.6 Renderer (`renderer.py`) — pure

`render(entities, relations) -> dict[str, str]` mapping **relative** paths (under the
managed folder) to markdown. Renders **all** the user's active entities (the unified
company model — US-2), not just this source's:

- `Goals.md` — all `goal` entities (title, confidence, last_asserted, source note path).
- `Projects/<slug>.md` — one per `project`: summary + its `part_of` tasks (open then done).
- `Tasks.md` — all `task`s grouped by project (via `part_of`), unassigned last; done
  section capped at 50 most recent.
- `Decisions.md` — `decision` entities, newest first, with `last_asserted_at` dates.

Determinism: stable sort (entity_type, title, id) so an unchanged state re-renders
byte-identical files (no vault churn). Every file ends with a footer:
`> Managed by Founder OS — edits here are overwritten. Last synced <UTC ts>.`
Project slug: keep `[A-Za-z0-9 _-]`, collapse whitespace, cap 80 chars, fall back to
`project-<id8>` — and it still passes the write jail (§4) like every other path.
**`renderer.py` imports no filesystem modules** (unit-testable, and enforced by test §9).

---

## 3. Obsidian adapter — `app/integrations/obsidian/`

### 3.1 Files

```
app/integrations/obsidian/
├── __init__.py
├── client.py     # transport = vault filesystem IO: walk, read, parse, write_managed (the ONLY writer)
└── adapter.py    # ObsidianAdapter(IntegrationAdapter) — the ADR-010 seam
```

`adapter.py` (mirrors `google_calendar/adapter.py` shape, incl. the idempotent
`register_adapter()` guard):

```python
class ObsidianAdapter(IntegrationAdapter):
    name = "obsidian"
    capabilities = Capability.OBSERVE | Capability.SYNC | Capability.HEALTH

    async def configure(self, settings) -> None            # no global creds; per-source config in DB
    async def health(self) -> HealthStatus                 # ok=True, "local adapter; per-source checks at registration/sync"
    async def observe(self, user_id) -> list[ObservedEvent]  # all active obsidian sources for user → observe_source()
    async def sync(self, user_id, changes) -> SyncResult     # changes: [{"source_id": str, "files": {rel_path: content}}]
    # adapter-specific (used by StateService for single-source runs):
    async def observe_source(self, source_config: dict, source_key: str) -> list[ObservedEvent]
    def check_source(self, source_config: dict) -> HealthStatus   # per-source health (§6)
```

The adapter carries **no reconciliation logic** (ADR-010): `observe_source` walks +
parses and emits `ObservedEvent(source="obsidian", kind=..., external_id=...,
payload=..., observed_at=now, provenance="observed")`; `sync` resolves the source's
vault config and writes the rendered files through `client.write_managed` only.

### 3.2 Parser (`client.py`) — dependency decision

**`python-frontmatter>=1.1.0` + stdlib regex.** Add to `requirements.txt`. Justification:
we need exactly three constructs — YAML frontmatter (python-frontmatter is a thin,
battle-tested wrapper over PyYAML, already a dependency), ATX headings
(`^(#{1,6})\s+(.*)$`), and checkboxes (`^(\s*)[-*+]\s\[( |x|X)\]\s+(.*)$` with indent
width captured for nesting). `markdown-it-py` was rejected: a full CommonMark AST does
not model Obsidian-flavored checkboxes/tags any better, and it adds dependency surface
for zero parsing we actually use. Malformed frontmatter (YAML error) → treat the whole
file as body, log at debug, never fail the sync. Inline tags: `(?:^|\s)#([\w/-]+)`.

`parse_note(rel_path, text) -> ParsedNote` (dataclass): `frontmatter: dict`,
`h1: str | None` (first H1), `tags: set[str]` (frontmatter `tags` + inline),
`checkboxes: list[CheckboxItem(text, done, indent, parent_index, ordinal)]`,
`body: str` (frontmatter stripped).

Walk rules (`walk_vault`): only `*.md`; skip `exclude_dirs` from source config
(default includes the **managed folder itself** — the engine must never observe its
own output, or it feeds back); skip files > `STATE_OBSIDIAN_MAX_FILE_BYTES` (1 MiB)
and stop with a report warning at `STATE_OBSIDIAN_MAX_FILES` (5000). Paths normalized
to POSIX separators + Unicode NFC before use in ids.

### 3.3 Stable `external_id` scheme (the concrete answer)

Format: `obsidian:{source_id}:{kind}:{key}` (fits String(512); `source_id` is the
`state_sources.id` UUID so two vaults never collide).

- **Note:** `obsidian:{source_id}:note:{vault-relative-path}` (NFC, POSIX). If the
  frontmatter contains `founderos_id: <value>`, use
  `obsidian:{source_id}:note:id:{value}` instead — an opt-in identity that fully
  survives renames.
- **Checkbox/task:** `obsidian:{source_id}:task:{note-path}:{sha256(norm_text)[:16]}[:{n}]`
  where `norm_text` = the checkbox line with indent, list marker, and the
  **`[ ]`/`[x]` state stripped**, internal whitespace collapsed (case preserved).
  `:{n}` (2, 3, …) is appended only for the 2nd+ occurrence of an *identical*
  `norm_text` within the same note, numbered in document order among identical texts
  — so reordering *distinct* tasks never shifts ids.

Consequences (deliberate):
- **Toggling a checkbox keeps the id** (state is stripped from the key) — the payload
  and thus `content_hash` change → new observation row → status update on the same
  entity. This is what makes "re-sync after checking a box" an update, not a duplicate.
- **Editing task text = new id** → new candidate; if the edit is minor, dedup (§2.4)
  merges it into the old entity; a genuine rewrite is genuinely a new task. Line
  numbers were rejected: any edit above a task would shift every id below it.
- **File rename = new note id.** Survival is delegated to **dedup-on-ingest**: the
  renamed note's title+summary embed ≈ identically → similarity ≥ 0.88 → merge into
  the existing entity (`attributes.path` updated, alias recorded). No inode/watcher
  tracking in v1. Deleted files: entities simply stop being re-asserted
  (`last_asserted_at` ages; Curator handles archiving later — out of scope).

### 3.4 Mapping rules (spec §7 made precise, with edge cases)

| Vault construct | Entity | Details |
|---|---|---|
| Frontmatter `goal: <text>` (str or list) | `goal` per value | title = value; summary = note H1/body first para |
| Frontmatter `project: <name>` OR note under top-level `Projects/` | `project` | title = frontmatter value else filename stem; the note is a *project note* |
| `#decision` tag (inline or frontmatter) OR first path segment `Decisions/` | `decision` | title = H1 else filename stem; summary = first paragraph |
| Any other note | `note` | title = first H1 else filename stem; summary = first 500 chars of body |
| `- [ ]` / `- [x]` line (any nesting depth) | `task` | status `open`/`done` from the box; `attributes.note_path`, `attributes.raw_line` |

Relations (upsert, direction fixed):
- task —`part_of`→ project entity, when the containing note is a project note.
- task —`derived_from`→ the containing note's entity (always, incl. non-project
  notes — the answer to "tasks in non-project notes": they are still tasks, linked to
  their note; no project link).
- nested checkbox —`part_of`→ its parent checkbox's task entity (parent = nearest
  shallower-indent checkbox above it).
- goal/project asserted from frontmatter: note entity —`mentions`→ goal/project.

Edge cases, decided: **duplicate headings** are irrelevant to identity (headings are
never entities in v1; only the *first* H1 is used as a title). A note that is both a
project note and `#decision`-tagged: project wins for the note entity; the decision
is additionally emitted as its own `decision` entity (both are asserted facts).
One file can emit many events (1 note + N tasks + M frontmatter entities) — each with
its own `external_id`.

---

## 4. Managed-folder safety invariant (US-2 hard requirement)

**Structural rule: exactly one function in the codebase opens vault files for
writing** — `client.write_managed(vault_root: Path, managed_folder: str,
relative_path: str, content: str)`:

1. `managed_root = (Path(vault_root).resolve(strict=True) / managed_folder).resolve()`;
   require `managed_root.is_relative_to(Path(vault_root).resolve())` (a `managed_folder`
   config value of `"../x"` fails here).
2. Reject `relative_path` if it is absolute, contains a `..` segment, a backslash, a
   null byte, or a drive prefix — *before* joining (cheap early errors).
3. `final = (managed_root / relative_path).resolve()`; require
   `final.is_relative_to(managed_root)` **after** `resolve()` — `resolve()` follows
   symlinks, so a symlinked subdirectory inside `FounderOS/` pointing outside the
   vault resolves outside `managed_root` and is rejected.
4. Violations raise `ManagedFolderViolation` (fails the sync with `outcome=error`;
   never a silent skip — the task file marks any miss P0).
5. Stale-file pruning (`prune_managed`) runs the same jail and additionally only
   deletes `*.md` files under `managed_root` that are absent from the just-rendered
   keep-set (so it can only ever delete files the renderer owns).

Complementary structural guarantees: `renderer.py` is pure (returns strings; no
`open`/`os`/`pathlib` writes), `adapter.sync()` contains no file IO except calls to
`write_managed`/`prune_managed`, and inbound `walk_vault` excludes the managed folder
(no feedback loop). Reads are read-only by construction (`open(..., "r")` only).

**Tested by** (unit tier, `tmp_path`): traversal battery — `../escape.md`,
`a/../../b.md`, `/etc/passwd`, `..\\win.md`, `FounderOS/../Notes.md`, empty path,
symlinked subdir inside the managed folder pointing outside the vault, symlinked
vault root (allowed — jail is relative to the *resolved* root), plus a
whole-vault invariant test: snapshot sha256 of every non-managed file, run a full
render+prune, assert zero non-managed hashes changed. And one import-hygiene test:
`app.state.renderer` module has no `open`/`Path.write_text` references.

---

## 5. API surface — `app/api/state_routes.py`

`router = APIRouter(prefix="/api/state", tags=["state"])`, registered in
`app/main.py`. Every endpoint: `user: ClerkUser = Depends(require_auth)`, identity via
`await get_or_create_user_id(user.user_id, db, email=user.email)`, every query
filtered by that UUID (standards/api.md + security.md). Pydantic models defined in the
route module (sibling-route convention).

| Method + path | Purpose | Request → Response |
|---|---|---|
| `POST /api/state/sources` | Register a vault | `SourceCreateRequest{type: Literal["obsidian"], name?: str, config: ObsidianConfig{vault_path: str, managed_folder: str="FounderOS", exclude_dirs?: list[str]}}` → 201 `SourceResponse` (409 on duplicate user+type+name; 422 on path-rule failure §6) |
| `GET /api/state/sources` | List sources | → `SourceListResponse{sources: list[SourceResponse], total}` — each with `health: {ok, detail}` from `check_source()` |
| `GET /api/state/sources/{id}` | Read one | → `SourceResponse` incl. `status`, `last_synced_at`, `last_error`, `last_sync_report` |
| `PATCH /api/state/sources/{id}` | Update config / pause | `SourceUpdateRequest{name?, config?, status?: "active"\|"paused"}` → `SourceResponse` |
| `DELETE /api/state/sources/{id}` | Remove source | → 204 (observations cascade; entities keep provenance with `source_id` NULLed) |
| `POST /api/state/sources/{id}/sync` | Trigger sync (§8) | `SyncTriggerRequest{direction: Literal["both","inbound","outbound"]="both"}` → 202 `SyncSubmittedResponse{task_id, status:"queued", poll:"/api/state/sources/{id}"}`; 409 if a sync is already running (Redis lock); 409 if source `paused` |
| `GET /api/state/entities` | List entities + provenance (US-4) | query: `entity_type?, status?, q? (title ILIKE), include_archived?=false, limit<=100, offset` → `EntityListResponse{entities: list[EntitySummary], total, limit, offset}` |
| `GET /api/state/entities/{id}` | Entity detail | → `EntityDetail` = summary + `attributes` + `relations_out/in: list[RelationOut]` + `recent_observations` (last 5: kind, observed_at, outcome, content_hash) |
| `GET /api/state/relations` | List edges | query: `entity_id?` (matches either end), `relation_type?`, `limit/offset` → `RelationListResponse` |

`EntitySummary` (the provenance contract, US-4): `{id, entity_type, title, status,
summary, source, source_id, source_name, external_ref, confidence: float,
last_asserted_at, pinned, created_at, updated_at}`.

**No entity/relation write endpoints in slice 1** — the reconciler is the only writer
(guardrail §10). Sync errors surface via source `status="error"` + `last_error`;
404s never leak other users' resources (scoped lookups return 404, not 403).

Registration checklist (`app/main.py`): import + `app.include_router(state_router)`;
lifespan adds `register_obsidian_adapter()` beside the gcal one; model import per §1.6.

## 6. Vault access model

- **Local path via source config** (`config.vault_path`), validated by a shared helper
  `client.validate_vault_path(path) -> Path` used by both the POST route (422 on
  failure) and the sync task (fail with `last_error`):
  1. must be absolute; 2. must exist; 3. must be a directory; 4. must be readable
  (`os.access(R_OK|X_OK)`); 5. must not be `/` or the user's home directory itself;
  6. **must not contain or be contained by the API project root**
  (`Path(app.__file__).resolve().parent.parent` — rejects observing the repo's own
  source tree into company state, and rejects a vault that would let the renderer
  write into the codebase).
- **Docker note (documented in the task + `.env.example` comment):** the API process
  reads the vault path *as seen by the process*. Under docker-compose the founder
  mounts the vault (`- /Users/me/Vault:/vaults/main:rw`) and registers
  `/vaults/main`. `./start.sh` (uvicorn on host) uses the host path directly.
- **`health()`** (adapter-global): trivially ok — no credentials to check.
  **`check_source(config)`** (per-source, surfaced on `GET /sources`): path passes
  `validate_vault_path`; managed folder either exists and is a writable directory or
  its parent (the vault root) is writable (`W_OK`) — health never creates it (must
  not mutate, per the ABC contract); returns `.md` file count from a capped walk.

## 7. RAG mirroring (no double-ingest)

- **What mirrors:** `note` and `decision` bodies (the unstructured recall payload).
  Tasks/goals/project one-liners do **not** mirror — they are structured state, and
  chunk-sized fragments would pollute hybrid search.
- **Idempotency key:** `knowledge_items.source_url = f"state://{source_id}/{external_id}"`
  (existing Text column — no schema change), `category="state_mirror"`,
  `content_type="text_chunk"` via the existing `Ingester`.
- **Algorithm** (`mirror.py`): the observation short-circuit does the heavy lifting —
  if the observation was `unchanged` (§2.2.2) the mirror step never runs. When content
  *did* change: `DELETE FROM knowledge_items WHERE user_id=:u AND source_url=:key`
  then `ingester.ingest_text(...)` fresh. Delete-then-reingest beats per-chunk upsert
  because chunk counts change when the note grows; matching old↔new chunks is
  complexity with no payoff.
- Entities keep the join implicitly through the same key (entity → its observations'
  `external_id` → `source_url`); no FK between state and RAG tables (the layers stay
  decoupled per ADR-009 "no duplication").

## 8. Execution model — Celery, always

**Decision: `POST /sync` always enqueues** a Celery task on the existing `default`
queue and returns 202 — never inline. Justification: markdown parsing is CPU-light,
but a first sync of a real vault is embedding-bound (one `embed_batch` covering every
new entity — hundreds of Ollama calls' worth of vectors) and the write-gate judge is
LLM-bound (Phase 0 F1 measured **486s for just two Ollama generations**). An endpoint
that is "usually fast" but minutes-slow on first run is exactly the F1 trap; one
consistent async behavior is simpler than a dual inline/queued path.

- Task: `app/tasks/state_tasks.py::state_sync_task(source_id: str, user_id: str,
  direction: str)` — follows the `agent_tasks.py` pattern verbatim (sync Celery shell,
  `asyncio.run`, own engine/session/redis, cleanup in `finally`); routes to `default`
  (no new queue; sync is neither an agent run nor an orchestration).
- **Overlap guard:** Redis `SET NX EX 900` on `state_sync:{source_id}`; the route
  returns 409 when held; the task releases it in `finally`. Source row transitions
  `active → syncing → active|error` for cheap UI polling (`GET /sources/{id}`).
- **LLM cost bound:** judge ≤ 10 calls × 30s timeout (§2.3) ⇒ the LLM-dependent
  portion of a sync is bounded at ~5 min worst case even on local Ollama; embedding is
  batched + Redis-cached (re-syncs hit cache).
- v1.1 `watchdog` file-watcher (out of scope) will reuse `state_sync_task` unchanged —
  another reason the trigger path must already be queue-shaped.

## 9. Test plan skeleton

**Unit tier** (`tests/unit/`, service-free — conftest already supplies env):

| File | Covers |
|---|---|
| `test_obsidian_parser.py` | frontmatter (incl. malformed YAML → body fallback), headings, checkbox states, nesting/indent parents, inline+frontmatter tags, CRLF, empty file |
| `test_obsidian_external_id.py` | checkbox toggle → same id; text edit → new id; identical-text ordinals stable when *distinct* tasks reorder; NFC/POSIX normalization; `founderos_id` override; rename → new note id (documented) |
| `test_state_write_gate.py` | table-driven ACCEPT/REJECT/BORDERLINE per §2.3 rules 1–5; judge fires only on BORDERLINE (fake LLM); per-sync budget respected; timeout → accept @ 0.5 |
| `test_state_dedup.py` | fake embedder (deterministic vectors): ≥/< threshold behavior; full merge-semantics table §2.5 (confidence formula asserted numerically, `last_asserted_at` max, alias cap) |
| `test_state_renderer.py` | pure render: deterministic byte-identical re-render; grouping (tasks under projects); footer present; no-filesystem-imports assertion on the module |
| `test_obsidian_managed_jail.py` | the §4 traversal + symlink battery against `tmp_path` vaults |
| `test_state_routes_models.py` | Pydantic request validation (bad vault paths → 422 shapes), `import app.state.models` registers 4 tables on `Base.metadata` (extends `test_app_imports.py`) |

**Live tier** (`tests/live/test_state_obsidian_live.py`, `@pytest.mark.live`,
`x-test-user` dev auth against `:8000`): build the fixture vault in a temp dir →
`POST /sources` → `POST /sync` → poll source status → assert entities/relations/
provenance via `GET /entities` → **re-sync and assert zero new entities and
`last_sync_report.unchanged == observed`** (idempotency AC) → toggle one checkbox →
re-sync → status flipped on the same entity id → assert `FounderOS/` rendered and the
before/after hash of every non-managed file is identical (safety AC) → assert
`knowledge_items` rows exist for the note bodies with `state://` source_url and don't
duplicate on re-sync. LLM-dependent assertions test structure only
(standards/testing.md rule 4); timeouts provider-aware (rule 5).

**Fixture vault** (checked in under `tests/fixtures/obsidian_vault/`):

```
obsidian_vault/
├── Goals.md                      # frontmatter goal: "Reach $10k MRR"
├── Projects/
│   └── Launch v2.md              # frontmatter project: Launch v2; 2 open + 1 done checkbox, one nested child
├── Decisions/
│   └── Pricing decision.md       # #decision tag + body
├── Notes/
│   └── Weekly review.md          # plain note containing 1 task (non-project-note case)
├── Idea.md                       # substantive note
├── Idea copy.md                  # near-duplicate body of Idea.md → dedup merge case
├── todo.md                       # filler title + empty body → write-gate reject
└── Templates/
    └── Daily.md                  # excluded dir — must never appear in state
```

## 10. Out-of-scope guardrails (restated, binding on the executor)

Not built in slice 1 — but the schema already accommodates them (no migration needed
later): **no** `watchdog` file-watcher (triggered sync only; v1.1); **no** Curator /
decay / trust-weighted pruning (columns `pinned`, `confidence`, `is_active` exist and
are populated); **no** `user_doc`/`system` feed emitters (CHECK constraints and
`state_sources.type` values already accept them); **no** destructive two-way merge
(managed folder = engine-owned last-write-wins; rest of vault read-only observed);
**no** entity/relation write API; **no** GitHub/Stripe/Slack/Calendar/Notion state
adapters; **no** Understand-loop goal-tracing; **no** change to n8n/task 004.

## 11. Config, dependencies, wiring (delta checklist)

- `app/config.py` (`Settings`): `STATE_DEDUP_SIM_THRESHOLD: float = 0.88`,
  `STATE_WRITE_GATE_JUDGE_MAX_PER_SYNC: int = 10`,
  `STATE_WRITE_GATE_JUDGE_TIMEOUT_S: int = 30`,
  `STATE_OBSIDIAN_MAX_FILES: int = 5000`,
  `STATE_OBSIDIAN_MAX_FILE_BYTES: int = 1_048_576`.
- `requirements.txt`: `python-frontmatter>=1.1.0` (only new dependency; §3.2).
- `app/main.py`: `import app.state.models`; include `state_router`; lifespan
  `register_obsidian_adapter()` (idempotent guard like gcal).
- `alembic/env.py`: `import app.state.models`.
- `app/retrieval/embeddings.py`: add `get_default_embedder()` factory (§2.4) — the
  only touch to an existing product file besides `main.py`/`config.py`/`env.py`.
- Docs step (workflow §7): update `docs/architecture.md` State Engine section from
  "planned" wording to as-built module list; `.env.example` Docker-mount comment.

## 12. Risks & trade-offs

- **Rename handling is probabilistic** (dedup-merge, not identity tracking). A rename
  *plus* heavy simultaneous edit can duplicate a note entity. Accepted for v1: the
  duplicate is exactly what the Curator merges later, and `founderos_id` frontmatter
  is the opt-out. Mitigation cost of the alternative (watcher/inode tracking) is a
  whole subsystem.
- **Write-gate fail-open at 0.5 confidence** trades bloat risk for durability of
  founder data + sync robustness when the LLM is down. Bounded by the judge budget
  and later pruned by confidence — consistent with hygiene §5's trust-weighting design.
- **Append-only observations grow with real edits.** Bounded per vault-edit, not per
  re-sync; a retention/compaction pass belongs to the Curator phase.
- **Full-vault walk per sync** (no cursor) is O(files) stat+read; with the Redis
  embedding cache and hash short-circuit, re-sync cost is dominated by file reads.
  Fine to 5k files (capped); incremental cursors come with the watcher.
- **Rendering all-user state into every vault**: with multiple vaults registered, each
  managed folder shows the same unified model (intended — the moat is one company
  model), but a founder may expect per-vault filtering later; `state_sources.config`
  can grow a `render_filter` without schema change.
- **`external_ref` maps only the creating observation**; subsequent asserters resolve
  via `state_observations.entity_id`. Trade-off: two-step resolution in exchange for a
  stable unique index (no churn on merge).

## 13. Open questions (non-blocking)

1. Managed-folder filename set (`Goals.md`, `Tasks.md`, `Decisions.md`, `Projects/*`)
   is fixed in v1 — confirm nobody wants it configurable before v1.1 (default: fixed).
2. Multiple vaults per user are permitted by the unique constraint
   (`user_id, type, name`) — confirm product intent; nothing in the design depends on
   single-vault (default: permitted).
