# Architecture — Phase 2 Company State Engine (Notion adapter)

- Date: 2026-07-07
- Status: approved design — ready for `eng-executor`
- Author: eng-architect
- Task: [tasks/active/015-notion-adapter.md](../../../tasks/active/015-notion-adapter.md)
- Inputs: [Phase 1 as-built architecture](2026-07-04-phase1-state-engine-architecture.md)
  (reused, not redesigned), [design spec 2026-06-22](2026-06-22-company-state-engine-design.md),
  ADR-009 + ADR-010 (docs/decisions.md), docs/architecture.md,
  standards/{api,security,coding,testing}.md, reference adapter
  `app/integrations/obsidian/{client.py,adapter.py}`, live-E2E shape
  `tests/live/test_state_obsidian_live.py`
- Branch: `phase2-notion-adapter`

> The buildable *how* for task 015. One decision per question; the executor implements
> against this without redesign. Paths are relative to `founder-os/apps/api/` unless
> noted. **Everything engine-side is reused as-is** — the reconciler pipeline, write-gate,
> dedup, renderer, mirror, the four state tables, `/api/state` lifecycle, Celery
> `state_sync_task`, and the per-source Redis lock — *except* the seven explicitly named
> contract deltas in §7. Anything not listed there does not change.

## 0. Decision summary — the eight routed questions

| # | Question (task 015) | Decision (one line) | Justification (one line) |
|---|---|---|---|
| 1 | Token storage & wiring | Existing `integrations` table (`user_id + integration_type='notion'` unique, `access_token` column); resolved per-sync by a new `app/integrations/credentials.py` helper; **never** in `state_sources.config` | Table already exists (zero migration), keeps tokens user-scoped and rotatable via PATCH; env var rejected — breaks multi-user scoping and makes rotation a process restart |
| 2 | Notion object → entity mapping | Databases route their rows by explicit `config.database_map` override, else title heuristics; task status derives checkbox > status-group > done-select; archival detected via `archived`/`in_trash` flags plus full-walk disappearance diff confirmed by per-id GET (§3.4–§3.5) | Explicit override beats guessing; the flag is authoritative when we see the object, and search's exclude-trashed semantics make the diff the only way to *learn* about trash |
| 3 | `external_id` scheme | `notion:{source_id}:{page\|block}:{notion_uuid}` — DB rows *are* pages (one kind), to-dos are `block` (§3.6) | Notion UUIDs are stable across renames **and** moves, so identity is hard (observation-trail resolution), unlike Obsidian's probabilistic dedup-based rename survival |
| 4 | Managed-tree ownership guarantee | **Ledger-primary jail**: the engine may only update/archive page ids recorded in `sync_cursor["managed_pages"]` and only create children of the ledger/root; parent verified by GET before every update; single write sink (§4) | Notion has no atomic ancestry guarantee — an ancestry-walk-only jail is TOCTOU-racy *and* costs a request chain per write; the ledger makes "engine-created" a provable property |
| 5 | Rate-limit & pagination | Sequential client, min-interval pacer at `1/STATE_NOTION_MAX_RPS` (default 3 req/s), 429 retried honoring `Retry-After` (max 5), `page_size=100` cursor pagination, object cap 2000; sync-lock TTL raised 900→1800 s (§9) | Sequential + pacing makes the average trivially provable; a 2000-object first walk is ~11–15 min of network alone, which overruns the slice-1 900 s TTL |
| 6 | Client dependency | Raw `httpx` (already a dependency) with a pinned `Notion-Version` header constant (default `2022-06-28`); no `notion-client` SDK | Same standard as the Obsidian parser decision: we use ~8 endpoints, the SDK adds dependency surface and hides the transport seam that `httpx.MockTransport` gives our unit tier for free |
| 7 | Cursor / incremental sync | `state_sources.sync_cursor` (designed-for in Phase 1, unused by Obsidian — now used): search sorted by `last_edited_time` desc, stop at `watermark − 120 s`; full walk on first sync / every `STATE_NOTION_FULL_WALK_EVERY_S` (24 h) / on `full_walk=true`; watermark advances only after a successful inbound pass (§6) | Notion search can sort but not filter by time, so descending-scan-until-watermark is the correct incremental primitive; the 120 s overlap absorbs Notion's minute-granularity timestamps and the observation `content_hash` short-circuit makes overlap free |
| 8 | Churn-free outbound rendering | Reuse `app/state/renderer.py` **unchanged**; the adapter swaps the timestamped footer for a static one, hashes each rendered markdown file, skips any page whose hash matches the ledger, and converts only changed files to native Notion blocks via a pure `md→blocks` converter (§5) | One canonical renderer (no drift between the Obsidian tree and the Notion tree); native blocks keep to-dos interactive — code-block pushing was rejected as unusable, and a second graph→blocks renderer was rejected as duplicated grouping/sorting/cap logic |

Supplementary decisions: `observed_at = Notion last_edited_time` (real event ordering
makes the merge status-wins rule correct across sources, §3.7); payload excludes
volatile metadata so `content_hash` is a pure content signature (§3.7); outbound
managed-tree writes are **not** ApprovalGate-routed — registration + root-page sharing
*is* the founder's standing consent and the ledger jail bounds the blast radius to
engine-owned pages (LOW risk classification; eng-security reviews this with the token
path, §8.4).

---

## 1. Schema & migration — **zero migration (verified)**

- `state_sources.type` CHECK already includes `'notion'`:
  `app/state/models.py` (`SOURCE_TYPES`, `ck_state_sources_type`) **and**
  `alembic/versions/0002_state_engine.py` line 51. Provenance feeds, entity types, and
  relation types need nothing new. **No Alembic revision is created by this task.**
  Any deviation from this requires an architect-recorded reason per the task AC —
  there is none.
- Token home is the **existing** `integrations` table (`app/models.py::Integration`):
  one row `integration_type='notion'`, `access_token=<token>`, `display_name`
  = workspace/root-page title, `is_active=true`. The `UniqueConstraint(user_id,
  integration_type)` means **one Notion token per user in v1** (all `notion` state
  sources share it — see §14).
- `state_sources.config` for Notion (secrets **never** here — Phase 1 §1.2 rule):

  ```jsonc
  {
    "managed_root_page_id": "<32-hex, dash-normalized>",   // required
    "database_map": {"<db_uuid>": "task|goal|project|decision|note"},  // optional override
    "exclude_page_ids": ["<uuid>", ...]                     // optional extra observation excludes
  }
  ```

- `state_sources.sync_cursor` layout (adapter-owned, service-persisted):

  ```jsonc
  {
    "last_edited_watermark": "2026-07-07T10:32:00Z",  // max last_edited_time fully processed
    "last_full_walk_at": "2026-07-07T09:00:00Z",
    "managed_pages": {                                 // the outbound ledger (§4)
      "Goals.md":            {"id": "<page_uuid>", "hash": "<sha256 of rendered md>"},
      "Tasks.md":            {"id": "...", "hash": "..."},
      "Decisions.md":        {"id": "...", "hash": "..."},
      "Projects":            {"id": "<container page uuid>", "hash": ""},
      "Projects/Launch v2.md": {"id": "...", "hash": "..."}
    }
  }
  ```

  The **seen-set is NOT stored in the cursor** — it is derived from the DB
  (`SELECT DISTINCT external_id FROM state_observations WHERE source_id=:sid AND
  entity_id IS NOT NULL` joined to active entities). Cursor stays O(managed pages),
  not O(workspace).

## 2. Token storage & wiring (question 1, made concrete)

### 2.1 Intake (registration / rotation)

- `POST /api/state/sources` with `type="notion"` carries the token **in the request
  body only**, as `config.token: SecretStr` (Pydantic `SecretStr` — accidental repr/log
  shows `**********`). The route:
  1. pops `token` off the config before anything is persisted or echoed;
  2. upserts the `integrations` row (`user_id`, `integration_type='notion'`,
     `access_token`, `is_active=true`);
  3. performs **one** live validation call (`GET /v1/pages/{managed_root_page_id}`,
     10 s timeout): 401 → `422 "Notion token invalid"`, 404/restricted →
     `422 "managed root page not shared with the integration"`, `archived/in_trash`
     → 422. Fail fast at registration, exactly like Obsidian's vault-path 422.
  4. stores config **without** the token and with the page id dash-normalized.
- `PATCH /sources/{id}` accepts the same optional `config.token` for rotation → same
  upsert; the `SourceResponse.config` never contains a token because one was never
  stored.

### 2.2 Per-sync resolution

New module `app/integrations/credentials.py`:

```python
async def resolve_source_credentials(db: AsyncSession, source: StateSource) -> dict[str, str]:
    """Type-keyed credential lookup. Obsidian → {}. Notion → {"token": ...}.
    Raises CredentialsMissing("no active Notion integration for this user —
    re-register the source with a token") — message NEVER contains the token."""
```

`StateService.run_sync` calls it once per run (contract delta D4) and passes the dict
to the adapter (`observe_source(..., credentials=...)` / inside the `changes` payload
for `sync`). The adapter holds the token only in local scope; the client sets it as an
`Authorization` header and **never logs headers** (its error/repr paths include method,
path, status — nothing else). A revoked token mid-life surfaces as
`NotionAuthError` → sync `status="error"`, `last_error="Notion token invalid or
revoked (401) — rotate it via PATCH /api/state/sources/{id}"` — actionable, never a
crash, never an echo (US-3 AC).

### 2.3 Hygiene invariants (eng-security checklist)

Token appears in exactly two places at rest/flight: the request body of
POST/PATCH (TLS, `SecretStr`) and `integrations.access_token`. Not in:
`state_sources.config` (DB check in E2E), any API response (response-shape check in
E2E), logs (`grep` of `logs/api.log`/`logs/celery.log` in E2E), error strings
(client raises typed errors with status codes only), or Celery task args (task
receives only `source_id/user_id/direction/full_walk`; the worker re-resolves the
token from the DB).

## 3. Notion adapter — `app/integrations/notion/`

### 3.1 Files (mirrors the Obsidian shape; ADR-010)

```
app/integrations/notion/
├── __init__.py
├── client.py    # TRANSPORT ONLY: NotionClient (httpx.AsyncClient), pacing, 429/5xx
│                #   retry, cursor pagination, pinned Notion-Version, typed errors,
│                #   the jailed write sink (§4) — the ONLY module that talks HTTP
├── mapper.py    # PURE: Notion JSON objects → ObservedEvents; status derivation;
│                #   external ids; md→blocks conversion; tombstone diff. No IO,
│                #   no httpx import (unit-tested against fixture JSON)
└── adapter.py   # NotionAdapter(IntegrationAdapter) — the ADR-010 seam; composes
                 #   client + mapper; register_adapter() with the idempotent guard
```

Obsidian keeps parsing inside `client.py` because its transport *is* the filesystem;
here transport is HTTP, so the pure mapping layer gets its own module — same
testability principle, cleaner seam for `httpx.MockTransport`.

```python
class NotionAdapter(IntegrationAdapter):
    name = "notion"
    capabilities = Capability.OBSERVE | Capability.SYNC | Capability.HEALTH

    async def configure(self, settings) -> None          # no globals; per-source config + DB token
    async def health(self) -> HealthStatus               # ok=True, "remote adapter; per-source checks at registration/sync"
    async def observe(self, user_id) -> list[ObservedEvent]   # aggregate path, mirrors Obsidian's
    # adapter-specific (StateService single-source runs):
    async def observe_source(self, source_config, source_key, *,
                             credentials=None, sync_cursor=None,
                             full_walk=False) -> tuple[list[ObservedEvent], dict]
                                                          # (events, new_cursor_fields)
    async def sync(self, user_id, changes) -> SyncResult  # changes: [{"config":…, "files":…,
                                                          #   "credentials":…, "ledger":…}];
                                                          #   SyncResult.data returns updated ledger (D5)
    def check_source(self, source_config, has_token: bool) -> HealthStatus  # NON-network (§8.2)
```

### 3.2 Client (`client.py`) — transport rules

- One `httpx.AsyncClient(base_url="https://api.notion.com", timeout=STATE_NOTION_TIMEOUT_S)`
  per sync run; headers `Authorization: Bearer <token>`,
  `Notion-Version: settings.STATE_NOTION_API_VERSION` (**pinned constant, default
  `"2022-06-28"`** — deliberately pre-dates the 2025 data-source split; single-constant
  upgrade path, named risk §13).
- Endpoints used (complete list): `POST /v1/search`, `GET /v1/pages/{id}`,
  `GET /v1/databases/{id}`, `GET /v1/blocks/{id}/children`, `POST /v1/pages`,
  `PATCH /v1/pages/{id}` (archive + properties), `PATCH /v1/blocks/{id}`,
  `DELETE /v1/blocks/{id}`.
- **Pacing:** requests are sequential; before each request the client sleeps to keep
  `now − last_request_start ≥ 1/STATE_NOTION_MAX_RPS` (monotonic clock, injectable for
  tests). No token-bucket burst logic — sequential + min-interval provably satisfies
  the ~3 req/s average and is 10 lines.
- **Retry:** 429 → sleep `Retry-After` (fallback exponential 1/2/4/8/16 s when the
  header is absent), max `STATE_NOTION_MAX_RETRIES=5`, then raise; 502/503/504 →
  retry twice with backoff; 401/403 → `NotionAuthError` immediately (no retry);
  400/404 → typed error, no retry. Counters `api_requests` and `rate_limit_waits`
  accumulate into the sync report.
- **Pagination:** every list call passes `page_size=100` and follows
  `next_cursor`/`has_more`. The walk stops at `STATE_NOTION_MAX_OBJECTS` (2000) with a
  report warning — the Obsidian `MAX_FILES` idiom.

### 3.3 Observation walk

**Full walk:** `POST /v1/search` (empty query) enumerates every page and database
shared with the integration — DB rows appear as pages with `parent.type ==
"database_id"`, so one paginated search covers containers, rows, and plain pages.
For each distinct parent database id, `GET /v1/databases/{id}` once (memoized per
run) to learn the property schema (which property is checkbox/status/select).
**Block fetch** (`GET /v1/blocks/{id}/children`, recursing into text-bearing children,
depth cap 3): only for **body-bearing** objects — plain pages, decision rows, and the
managed-root ancestry check cache. Rows of task/goal/project databases are
properties-only (title/status/date/select) — no block fetch, which is what keeps the
request budget ≈ `O(pages_with_bodies)`, not `O(rows)`.

**Exclusions (never observed):** any id in the managed ledger, any object whose
memoized parent-walk reaches `managed_root_page_id` (the engine never ingests its own
output — no feedback loop), and `config.exclude_page_ids`. Unshared content simply
never appears in search — the consent boundary is Notion's, verified in E2E with the
unshared control page.

### 3.4 Mapping rules (question 2, precise)

| Notion construct | Entity | Detection (in order) | Notes |
|---|---|---|---|
| Row of a database routed `goal` | `goal` | `database_map[db_id]=="goal"`, else DB title casefolds to `goals` | title = title property; `attributes.properties` keeps simplified props |
| Row of a database routed `project` | `project` | override, else DB title in {`projects`, `roadmap`} | |
| Row of a database routed `decision` | `decision` | override, else DB title in {`decisions`, `decision log`} | body fetched (mirrors to RAG) |
| Row of any other database **with** a checkbox/status/done-select property | `task` | override, else property-schema sniff | status per §3.5; `attributes.due` from first date prop, `attributes.tags` from select/multi-select |
| Row of a database with none of the above | `note` | fallback | |
| Plain page under a parent page titled `Decisions` | `decision` | parent-title heuristic (the `Decisions/` folder analogue) | |
| Any other plain page | `note` | fallback | title = title property, else write-gate handles untitled stubs |
| `to_do` block inside an observed page | `task` | block type | status from `checked`; the Obsidian checkbox analogue |
| Database container itself | **no entity** | — | containers are routing metadata in v1, not state |

Relation hints reuse the **existing** reconciler vocabulary unchanged
(`derived_from_note`, `part_of_project`, `parent_task_external_id`, `mentions`):
`to_do` block → `derived_from` its containing page's event; a child page →
`derived_from` its parent page's event (when the parent is observed); a task row whose
database sits under a project page/row → `part_of_project` = that project's title.
Notion **relation properties** are preserved raw in `attributes.properties` but not
traversed in v1 (deferred; no reconciler support needed today). Event ordering mirrors
the Obsidian S1 lesson: goal/project/decision events are emitted before notes/tasks so
hints resolve within the run.

Event kinds: `notion.goal`, `notion.project`, `notion.decision`, `notion.note`,
`notion.task`, `notion.tombstone`.

### 3.5 Task-status derivation (question 2b)

Precedence over the row's property schema: (1) first **checkbox** property → `done`
iff checked; (2) **status** property → `done` iff its group is `Complete`;
(3) **select** property named `status` (casefold) → `done` iff value casefolds into
`{done, complete, completed, shipped}`; else `open`. `to_do` blocks: `checked` flag.
The winning property's name is recorded in `attributes.status_property` so US-4's
"status comes from the property, not title text" is auditable.

### 3.6 `external_id` scheme + archival (questions 3 + 2c)

Format: `notion:{source_id}:{kind}:{notion_uuid}` with `kind ∈ {page, block}` and the
UUID dash-normalized. DB rows are pages in Notion's object model — they share the
`page` kind (a row keeps its UUID even if the founder converts it to a standalone
page, and identity survives). `source_id` is the `state_sources.id` UUID, so two Notion
sources can never collide (same rule as Obsidian).

**What UUID stability buys vs Obsidian:** rename or move → *same* `external_id` →
the reconciler's hard path (a) (observation trail) resolves the same entity
deterministically. No reliance on the ≥0.88 dedup merge that Obsidian needs for
renames — the "rename + heavy edit may duplicate" risk from Phase 1 §12 does not exist
for Notion. To make renames also *retitle* the entity (not just alias), the hard-match
merge takes the incoming title — contract delta **D2**, flag-gated so the fuzzy dedup
path keeps Phase 1 semantics exactly.

**Archival (`is_active=false` transition):**
1. Whenever any retrieve/walk returns an object with `archived: true` or
   `in_trash: true` → emit `notion.tombstone` for its external_id.
2. **Full walks only:** diff `seen-set (from DB, §1) − walked ids`; for each missing
   id, one confirming `GET /v1/pages/{id}` — `in_trash/archived` → tombstone
   (`reason: "trashed"`); 404/restricted → tombstone (`reason: "unshared"` — content
   the founder un-shared must stop being asserted, same consent rule as ingestion).
   Incremental syncs cannot see disappearance (search excludes trash), which is why
   the full-walk cadence exists and why the E2E forces `full_walk=true` (§6, §10).

Tombstone event shape (the **reconciler contract delta D1**, specified in §7):

```python
ObservedEvent(source="notion", kind="notion.tombstone",
              external_id="notion:{source_id}:page:{uuid}",
              payload={"tombstone": True, "reason": "trashed"},  # or "unshared"
              observed_at=<confirming GET time>, provenance="observed")
```

### 3.7 Payload & hash discipline

Payloads carry **content only** — title, body text, simplified properties, status,
parent id, `entity_type`, `relation_hints` — and exclude `last_edited_time` /
`created_time` / URLs-with-tokens, so `content_hash` is a pure content signature:
an unchanged page re-walked (incremental overlap or full walk) hits the
`ON CONFLICT DO NOTHING` short-circuit and reports `unchanged` (idempotency AC).
`observed_at` = the object's `last_edited_time` (true event time → the Phase 1 merge
rule "status: take incoming iff `observed_at > last_asserted_at`" orders correctly
across sources; minute granularity is acceptable). Simplified properties = plain
strings/bools/ISO dates keyed by property name — no raw rich-text objects, keeping the
canonical JSON hash stable.

## 4. Managed-tree jail (question 4 — the Notion write-jail)

**Structural rule (Obsidian §4 analogue): exactly one code path performs Notion
mutations** — `client.write_managed_page()` / `client.archive_managed_page()` /
`client.replace_page_blocks()`, all funnelled through a private `_jail()` check:

1. **Create** is legal only with `parent = managed_root_page_id` or a page id already
   in the ledger. The new page's id is appended to the ledger before anything else
   happens.
2. **Update/archive** is legal only for ids present in the ledger — the engine can
   only ever touch pages it created (the "only-operate-on-ids-the-engine-created"
   model; primary jail).
3. **Parent verification (belt-and-braces):** before each update, the page is
   GET-ed (a request we need anyway for block replacement) and its `parent` must be
   the managed root or another ledger id, and `archived == false`. A founder-moved
   page fails this → it is dropped from the ledger, a warning is logged, and a fresh
   page is created under the root. The engine **never follows a moved page outside
   the tree** — so even the non-atomic ancestry situation can't produce an
   outside-tree write.
4. Violations raise `ManagedTreeViolation` → sync `outcome=error` (never a silent
   skip; any miss is P0 per the task's safety metric).
5. **Pruning:** managed pages whose ledger key is absent from the just-rendered file
   set are **archived** (`archived: true` via `PATCH /v1/pages/{id}`), never deleted —
   reversible-by-founder, and only ever ids the ledger owns (the `prune_managed`
   keep-set idiom).

Ancestry-walk-as-primary was rejected: Notion gives no atomic parent-chain guarantee
(a move between check and write is unobservable — same residual TOCTOU class as
Obsidian's N1, accepted under the local-first threat model), and a per-write ancestry
walk costs a request chain against the 3 req/s budget. The ledger turns the invariant
into local state we control; the single GET per *changed* page is the cheap
verification layer on top.

**Root designation:** the founder creates the "Founder OS" page, shares it with the
integration, and passes its id as `config.managed_root_page_id` at registration
(validated live, §2.1). The managed subtree (ledger ∪ parent-walk-to-root) is excluded
from observation (§3.3) — no feedback loop.

**Unit-tested with a fake transport** (`httpx.MockTransport`, no network): update of a
non-ledger id → `ManagedTreeViolation`; create with an out-of-tree parent →
violation; fake returns a founder-moved parent → recreate-under-root not update;
prune archives only ledger ids absent from the keep-set; the recorded request log
contains **zero** mutating calls to any id outside ledger ∪ root (the fake-transport
equivalent of the vault hash snapshot).

## 5. Outbound rendering (question 8 — renderer contract delta: **none**)

- `StateService._outbound` and `app/state/renderer.py` are **unchanged**: the adapter
  receives the same `{relative_path: markdown}` dict (`Goals.md`, `Tasks.md`,
  `Decisions.md`, `Projects/<slug>.md`) rendering ALL the user's active entities — the
  unified model (US-2), including Obsidian-fed entities.
- Mapping to Notion: one child page per rendered file under the managed root; a
  `Projects` container page holds the per-project pages; page title = path stem;
  **ledger key = the rendered file path** (the renderer's path contract becomes the
  logical page key — zero new naming scheme).
- **Churn-free (`mapper.py`, pure):** replace the timestamped footer line with the
  static `> Managed by Founder OS — edits here are overwritten.` (sync recency lives
  on the `/api/state` source row instead — any per-sync timestamp would defeat
  churn-freedom by definition), then `sha256(markdown)`; if it equals
  `ledger[key].hash` → **skip entirely** (no request at all: protects the rate budget
  and the founder's "recently edited" feed — the AC). Only changed files proceed.
- **`md→blocks` (`mapper.py`, pure):** converts exactly the closed dialect our own
  renderer emits — `#`/`##` headings, `- ` bullets, `- [ ]`/`- [x]` → interactive
  `to_do` blocks, `**bold**`/`*italic*` rich-text annotations, the blockquote footer —
  nothing else (unknown constructs degrade to plain paragraphs). Respects API limits:
  ≤100 blocks per append request (split batches), ≤2000 chars per rich-text element
  (split runs).
- **Write strategy for a changed page:** wholesale replace — list existing children,
  `DELETE` each block, append the new batch. Cost is bounded by the renderer's own
  caps (`DONE_CAP=50`); a per-block diff was rejected as complexity with no payoff at
  this size (revisit if managed pages grow). Ledger hash updates only after a
  successful replace; the updated ledger returns to the service via
  `SyncResult.data` (D5) and is persisted into `sync_cursor`.

## 6. Cursor & incremental sync (question 7, precise algorithm)

```
inbound(source, cursor, full_walk):
  if full_walk or cursor missing or now − last_full_walk_at > STATE_NOTION_FULL_WALK_EVERY_S:
      ids, events = full_search_walk()                         # §3.3
      events += tombstones(seen_set_from_db − ids)             # §3.6.2
      new_cursor.last_full_walk_at = now
  else:
      events = search sorted last_edited_time DESC, paginate until
               object.last_edited_time < (last_edited_watermark − 120s)
      # trashed/unshared pages are invisible here — archival is full-walk-only
  new_cursor.last_edited_watermark = max(last_edited_time seen)   # Notion clock, never local
  return events, new_cursor        # service persists ONLY after a successful pass
```

Correctness cases, decided: **minute-granularity timestamps** → the 120 s overlap
re-fetches boundary objects; the observation hash short-circuit makes that free
(`unchanged`). **Clock skew** → watermark compares Notion timestamps to Notion
timestamps only. **Mid-sync failure** → cursor not persisted; next run re-scans from
the old watermark (idempotent by construction). **Cursor corruption / operator
escape hatch** → `POST /sync {"full_walk": true}` (D6) forces a walk; the live E2E
uses it to make trash-archival deterministic. First sync is always a full walk.

## 7. Contract deltas — the complete list (nothing else changes)

Engine modules explicitly **unchanged**: `write_gate.py`, `dedup.py::find_similar`,
`renderer.py`, the four ORM models, the schema, `mirror.py`'s delete-then-reingest
algorithm, the reconcile pipeline order, all entity/relation read endpoints.

| # | File | Delta | Why it is genuinely source-agnostic |
|---|---|---|---|
| D1 | `app/state/reconciler.py` | **Tombstone branch**: if `payload.get("tombstone")` → resolve by observation trail **only** (path (a); never title-match — too risky for a destructive transition), set `is_active=False`, `status="archived"` for non-tasks, outcome=`archived`, new `SyncCounters.archived`, delete the entity's `state://` mirror rows, skip gate/dedup/relations. **Reactivation**: a normal event resolving to an inactive entity with `observed_at` newer than the archival re-activates it (restore-from-trash). Re-walks never resurrect (trashed pages never re-appear in walks — AC) | Any future adapter (GitHub closed-and-deleted, Slack, Calendar cancels) needs the same "source says gone" transition; `tombstone` is a payload contract, not a Notion special case |
| D2 | `app/state/dedup.py::merge` | New flag `hard_match: bool = False`; when True, `title` takes the incoming value (existing title → `aliases`) | A hard external-id match is definitionally the same object — retitle is truth, alias-forever was only correct for fuzzy matches; also fixes Obsidian `founderos_id` note renames |
| D3 | `app/state/mirror.py` | `MIRRORED_KINDS` set → suffix rule: mirror kinds ending `.note`/`.decision` | The set hardcodes `obsidian.*` — a measured source-coupling gap; the suffix rule means adapter #3 needs zero mirror change |
| D4 | `app/state/service.py` | (a) register the Notion adapter beside Obsidian (worker has no lifespan); (b) resolve credentials via `credentials.py` (§2.2); (c) pass `credentials`/`sync_cursor`/`full_walk` to `observe_source`, unpack the optional `(events, new_cursor)` tuple, persist cursor after a successful inbound pass; (d) include `credentials` + ledger in the `changes` dict for `sync`, merge `SyncResult.data` into `sync_cursor` + report | The service is the composition point — Phase 1 designed `sync_cursor` for exactly this; obsidian returns a bare list and `None` cursor, unchanged behavior |
| D5 | `app/integrations/base.py` | `SyncResult` gains `data: dict = field(default_factory=dict)` (additive, defaulted) | Outbound adapters need a channel to return cursor-ish state (the ledger) without writing state tables themselves (ADR-010: no business/DB logic in adapters) |
| D6 | `app/api/state_routes.py` | `type: Literal["obsidian", "notion"]`; `config: ObsidianConfig \| NotionConfig` with per-type validation dispatch in `_validated_config`; `NotionConfig{managed_root_page_id, token: SecretStr \| None, database_map?, exclude_page_ids?}` (token popped/upserted per §2.1); `list_sources` health looks the adapter up by `s.type` (currently hardcodes `registry.get("obsidian")`) and calls Notion's non-network `check_source`; `SyncTriggerRequest` gains `full_walk: bool = False` | The AC mandates reusing the existing lifecycle — these are the minimum edits that make the routes source-polymorphic; no new endpoints |
| D7 | `app/tasks/state_tasks.py` | `LOCK_TTL_S` 900→1800; `soft_time_limit=1740`, `time_limit=1770`; task signature passes `full_walk` through | A capped 2000-object first walk is ~11–15 min of paced network before embedding — the slice-1 TTL demonstrably cannot hold it; harmless for Obsidian (lock still outlives the task) |
| D8 | `app/integrations/obsidian/adapter.py` | `observe_source(...)` accepts and ignores `credentials=None, sync_cursor=None, full_walk=False` | Keeps the service's call shape uniform — a 1-line signature widening, no behavior change |
| D9 | `app/main.py` | lifespan: `register_notion_adapter()` beside the Obsidian one (idempotent guard) | Standard ADR-010 registration |

Sync-report additions (JSONB — additive, no consumer breaks): `archived`,
`api_requests`, `rate_limit_waits`, `search_pages`, `pages_written`,
`pages_skipped_unchanged`.

## 8. API surface — deltas only (registered routes unchanged)

### 8.1 Registration example

```
POST /api/state/sources            (require_auth, user-scoped — unchanged)
{ "type": "notion", "name": "acme-workspace",
  "config": { "managed_root_page_id": "1f2e3d4c...", "token": "ntn_..." } }
→ 201 SourceResponse   # config echoed WITHOUT token; name defaults to root-page title
→ 422 invalid token / root page not shared / archived root
→ 409 duplicate (user, type, name)
```

### 8.2 Health

`GET /sources` health for Notion is **non-network** (list must stay fast; Obsidian's
capped walk is local, a Notion round-trip per source per list is not):
`ok = active integrations row exists AND managed_root_page_id present`; detail says
which is missing. Real connectivity truth lives where it is fresh: registration
validation (§2.1) and sync `last_error`.

### 8.3 Everything else

Sources CRUD, 202 sync trigger + Redis-lock 409, poll via `GET /sources/{id}`,
entities/relations read-only with provenance — all reused verbatim. Notion-fed
entities surface `source="observed"`, `source_id`, `source_name`, `external_ref`,
`confidence`, `last_asserted_at` through the existing `EntitySummary` with zero
changes (US-5 AC).

### 8.4 Security posture (for the mandated eng-security pass)

`require_auth` + `get_or_create_user_id` scoping on every touched endpoint
(unchanged); token path per §2; Notion payloads are untrusted input — they flow only
into parameterized ORM inserts and Pydantic-validated responses (no HTML rendering, no
shell, no LLM-tool interpolation); outbound writes are ledger-jailed and classified
LOW (standing consent = registration + root-page share), so no ApprovalGate insertion
— **explicitly a security-review item, not a silent assumption**.

## 9. Execution model & sync-time expectations (question 5)

Unchanged shape: always Celery on `default`, per-source Redis `SET NX` lock, route 409
while held, source `active → syncing → active|error`. With pacing at 3 req/s,
sequential:

| Scenario | Requests (≈) | Network time | Total (with Ollama embedding) |
|---|---|---|---|
| First sync, 300 shared objects (~40 body pages, 3 DBs) | 3 search + 3 schema + ~45 block fetches ≈ 55 | ~20 s | dominated by embedding: minutes (same F1 profile as Obsidian) |
| First sync at the 2000-object cap | ~20 search + schemas + ~300 block fetches + outbound | **~11–15 min** | up to ~25 min → **TTL 1800 (D7)** |
| Incremental, 5 edited pages | 1–2 search + ≤5 block fetches + ≤2 page rewrites | < 10 s | seconds (hash + embed cache) |
| Idempotent re-sync, nothing changed | 1–2 search, **0 writes** | < 5 s | `pages_skipped_unchanged == managed pages` |

The report records `api_requests`/`rate_limit_waits` so the E2E can assert the
pagination AC (`search_pages ≥ 2`) and rate-limit resilience factually.

## 10. Test plan skeleton (mirrors Phase 1 §9)

### 10.1 Unit tier (`tests/unit/`, service-free, **fake transport — no network**)

The fake is `httpx.MockTransport` fed by checked-in fixture JSON — the decisive reason
for the raw-httpx choice (§0 Q6).

| File | Covers |
|---|---|
| `test_notion_mapper.py` | fixture objects → events: plain page → note; task-DB rows checkbox/status-group/select variants (§3.5 precedence, incl. `status_property` audit attr); goals/projects/decisions routing + `database_map` override beating heuristics; `to_do` blocks with hints; untitled/empty page candidate (gate input shape); properties preserved simplified; payload excludes volatile fields (hash stability across identical re-fetch) |
| `test_notion_external_id.py` | scheme format; rename/move → same id (documented contrast to Obsidian); row-vs-page same kind; dash normalization; toggle keeps id while payload hash changes |
| `test_notion_client.py` | pagination follows `next_cursor` at `page_size=100`; 429 honors `Retry-After` then succeeds; missing header → exponential fallback; max-retries raises; 401 → `NotionAuthError` (message contains no token); pacing respects min interval (injected clock); `Notion-Version` pinned on every recorded request |
| `test_notion_managed_jail.py` | the §4 battery: non-ledger update rejected; out-of-tree create rejected; founder-moved page → recreate; prune archives only ledger orphans; zero mutating requests outside ledger ∪ root in the recorded log |
| `test_notion_blocks.py` | md→blocks over the renderer dialect (headings/bullets/to_dos/bold/footer); >100-block append batching; >2000-char rich-text splitting; static-footer swap; hash-skip decision function (`ledger hash equal → no requests`) |
| `test_notion_tombstone_diff.py` | pure diff: seen-set − walked ids → confirm classification (`trashed` vs `unshared`); reactivation predicate (`observed_at` newer than archival ⇒ reactivate) |
| `test_state_routes_models.py` (extend) | `NotionConfig` validation (bad page id → 422 shape); token is `SecretStr` and absent from `SourceResponse` serialization; `Literal` accepts both types |

Reconciler D1/D2 behavior that needs a DB is exercised in the live tier (Phase 1
precedent — reconciler internals were never unit-mocked); the pure predicates above
keep the logic unit-covered.

**Fixture set** (`tests/fixtures/notion_workspace/*.json`): `search_page_1.json` +
`search_page_2.json` (forces pagination), `db_tasks.json` + `db_tasks_rows.json`
(checkbox + status + select variants), `db_projects.json`, `db_goals.json`,
`db_decisions.json` + rows, `page_note.json` + `page_note_blocks.json`,
`page_with_todos_blocks.json`, `page_trashed.json` (`in_trash: true`),
`page_untitled_empty.json`, `managed_root_page.json`, `rate_limit_429.json`.

### 10.2 Live tier (`tests/live/test_state_notion_live.py`, `@pytest.mark.live`)

**Gating (decided):** module-level
`pytest.mark.skipif(not os.environ.get("NOTION_TEST_TOKEN") or not os.environ.get("NOTION_TEST_ROOT_PAGE_ID"), reason="NOTION_TEST_TOKEN / NOTION_TEST_ROOT_PAGE_ID not set — SKIPPED, but task 015's gate record REQUIRES a recorded real run; a skip does NOT satisfy the gate")`.
Restated binding rule: the suite may skip on missing env for CI hygiene, **but the
task-015 QA gate record requires an actual recorded run against a real workspace** —
the recorded report is the artifact, not the green skip.

Test workspace (documented in the test docstring; seeded once): Goals DB (1 goal),
Projects DB ("Launch v2"), tasks DB (2 open + 1 done, checkbox), Decisions DB
(1 pricing decision), one substantive note page, one near-duplicate note (dedup),
one untitled empty page (gate), one **unshared control page**, the shared
"Founder OS" root, plus ~105 tiny filler pages bulk-seeded via the API under a `Bulk`
parent (idempotent seed step) so `search_pages ≥ 2` is guaranteed (pagination AC).

Flow (`x-test-user` dev auth against `:8000`, the `trigger_and_wait` fresh-report
idiom from the Obsidian E2E — including its stale-report lesson):

1. register (token in body) → 201; response config has **no** token
2. sync #1 → entities/relations/provenance asserted (goal/project/task/decision
   present, `source="observed"`, `source_name`, structured `attributes.due`/`tags`
   on a task row); unshared control page **absent** from entities *and* observations;
   `report.search_pages ≥ 2`; gate + dedup spot-checks (untitled gated; near-dupe
   merged); managed tree exists under root (Goals/Tasks/Decisions/Projects children)
3. **safety snapshot**: with an independent client on the same token, record
   `last_edited_time` of every non-managed shared object → after sync #2 assert all
   unchanged (any miss is P0)
4. sync #2 (no changes) → `created==0`, `unchanged==observed`; **churn-free**: managed
   pages' `last_edited_time` unchanged, `pages_skipped_unchanged > 0`
5. toggle the checkbox property on one task row (via the test's own API call) →
   sync #3 → **same entity id** flips to `done`, `created==0`
6. trash the substantive note page → `POST /sync {"full_walk": true}` → its entity
   `is_active==false` (absent from default listing, present with
   `include_archived=true`), never resurrected by a further re-sync; its `state://`
   mirror rows gone
7. **token hygiene**: `GET /sources` + `GET /sources/{id}` responses contain no token
   substring; scan `logs/api.log` + `logs/celery.log` for the token literal (skip the
   scan with a recorded note if logs are not on disk); DB check of
   `state_sources.config` via the API-returned config
8. rate-limit resilience is implicit (the seeded workspace forces pagination and the
   run completes); `report.rate_limit_waits` recorded in the gate artifact

## 11. Config, dependencies, wiring (delta checklist — Phase 1 §11 style)

- `app/config.py` (`Settings`): `STATE_NOTION_MAX_RPS: float = 3.0`,
  `STATE_NOTION_MAX_RETRIES: int = 5`, `STATE_NOTION_TIMEOUT_S: int = 30`,
  `STATE_NOTION_MAX_OBJECTS: int = 2000`,
  `STATE_NOTION_FULL_WALK_EVERY_S: int = 86_400`,
  `STATE_NOTION_API_VERSION: str = "2022-06-28"`.
- `requirements.txt`: **no new dependency** (`httpx>=0.27.0` already present).
- `app/main.py`: lifespan `register_notion_adapter()` beside the Obsidian one (D9).
  Router/model imports unchanged (no new router, no new models).
- `app/api/state_routes.py`: D6. `app/state/{service,reconciler,dedup,mirror}.py`:
  D1–D4. `app/integrations/base.py`: D5. `app/tasks/state_tasks.py`: D7.
  `app/integrations/obsidian/adapter.py`: D8 (signature only).
- New files: `app/integrations/notion/{__init__,client,mapper,adapter}.py`,
  `app/integrations/credentials.py`, unit tests + fixtures per §10.
- Alembic: **nothing** (§1).
- Docs step (workflow §7): flip `docs/architecture.md`'s "GitHub/Stripe/Slack/
  Calendar/Notion later" wording to record Notion as shipped; `.env.example` comment
  for `NOTION_TEST_TOKEN`/`NOTION_TEST_ROOT_PAGE_ID` (live-test-only — the product
  token is never env); founder setup doc: internal integration with **content-only
  capabilities** (read/update/insert; no user-information — least privilege, US-3).

## 12. Out-of-scope guardrails (restated, binding on the executor)

**No** OAuth public-integration flow (pasted internal token only; hosted OAuth is
Phase 5+); **no** webhooks / real-time subscriptions (triggered sync only; scheduled
polling is a named fast-follow and reuses `state_sync_task` unchanged — the path is
already queue-shaped); **no** two-way edits of founder content (outside the managed
tree = read-only observed; managed tree = engine-owned last-write-wins); **no**
comments/users/permissions ingestion; **no** media/file/embed blocks (text-bearing
only); **no** relation-property graph traversal (attributes-preserved only); **no**
Curator/decay/trust-weighting, `user_doc`/`system` emitters, other adapters, or
dashboard UI (API-first, like slice 1).

## 13. Risks & trade-offs

- **API-version pin (`2022-06-28`) vs Notion's data-source evolution.** Pinning
  pre-dates the 2025 multi-source database split, keeping v1's object model simple;
  the version is one settings constant and the client is one module — a bounded
  upgrade when Notion forces it. Named, accepted.
- **Archival latency is full-walk-bound** (default ≤24 h; `full_walk=true` on demand).
  Incremental search physically cannot see trash. Accepted: archival is a hygiene
  transition, not a freshness-critical read; webhooks (out of scope) are the real fix.
- **Ledger lives in `sync_cursor`** → `DELETE /sources` orphans the managed pages
  inside Notion (they stay, engine-marked, founder-deletable). Consistent with
  Obsidian leaving `FounderOS/` behind; reaching into the workspace on source
  deletion would itself be a scary write. Documented in the founder doc.
- **One Notion token per user** (existing `integrations` unique constraint) → one
  workspace per user in v1. A second workspace needs a schema-level decision later;
  nothing in this design blocks it (`state_sources` already allows multiple `notion`
  rows).
- **Wholesale block replacement** on changed managed pages costs O(blocks) requests;
  bounded by renderer caps and mitigated by hash-skip (unchanged pages cost zero).
  Block-level diffing is deliberate future work.
- **Full-body fetch budget**: body-bearing pages dominate request count; rows are
  properties-only by design. A workspace of thousands of long notes hits the 2000
  object cap first — the cap is the protection, with a report warning.
- **Fail-open write-gate + tombstone interplay**: a gated (never-created) page that is
  later trashed produces a tombstone that resolves no entity — the branch must treat
  that as a no-op (`outcome=archived`, `entity_id NULL`), not an error. Specified here
  so the executor doesn't invent behavior.

## 14. Open questions (target zero — defaults bind unless overridden)

1. Managed-tree page set is fixed (`Goals`, `Tasks`, `Decisions`, `Projects/*`) —
   same as Phase 1 Q1. **Default: fixed in v1.**
2. Multiple Notion sources per user share the single per-user token and each render
   the full unified model under their own root. **Default: permitted, single token;
   revisit only if a real founder needs two workspaces.**
