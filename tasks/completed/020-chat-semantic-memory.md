---
id: 020
title: Chat semantic memory — capture (write) + composite-scored recall (read)
status: done
stage: done
owner: —
created: 2026-07-19
dependencies:
  - "017 (shipped, PR #19) — guardrails/history prompt contract + escaping precedent"
  - "tasks/backlog/019 — live smoke checklist (scope item C extends it; see R7)"
links:
  - founder-os/apps/api/app/api/agent_routes.py
  - founder-os/apps/api/app/memory/manager.py
  - founder-os/apps/api/app/agents/base.py
  - founder-os/apps/api/tests/unit/test_agent_history_prompt.py
  - docs/decisions.md (ADR-013, ADR-014)
  - tasks/backlog/005-temporal-memory-injection.md (to close as subsumed)
---

# 020 — Chat semantic memory: capture + recall

> Branch `feat/chat-semantic-memory` in the isolated worktree; new PR (PR #19 is
> merged). Founder-approved feature; plan only — implementation starts at M1.

## Objective

Close the chat memory loop: agents currently forget every conversation the moment
the session ends (`memory_pages` is written by ingestion/State Engine paths but
never by chat). A. WRITE — after every successful chat response on all 4 endpoints,
fire-and-forget a background `MemoryManager.async_store` of the turn's semantics
(embedding only, zero LLM completions). B. READ — inject composite-scored recall
as a `<memories>` block into the system prompt, reusing the query embedding
`run()` already computes. C. Extend the task-019 live smoke to check
`memory_pages` growth.

## User stories  <!-- eng-product; authoritative -->

- As a founder, what I discussed with my agents last week is remembered across
  sessions — I never re-explain context (cross-session memory).
- As a founder, recall is ranked and decays: recent/important conversation
  memories surface first, stale ones fade instead of bloating every prompt.
- As a founder on free-tier infra, memory adds zero drag and zero spend: no extra
  LLM completions, no blocking of chat responses, no failures caused by memory.
- As a founder, remembered conversation text cannot hijack my agents (stored
  prompt injection is neutralized, mirroring 017).

## Acceptance criteria

**Tier A — unit, service-free** (recorder-stub precedent:
`founder-os/apps/api/tests/unit/test_agent_history_prompt.py` — stub engine,
no server/DB/Redis/LLM):

WRITE path:
- [x] **AC-1** Exactly one `async_store` scheduled per successful turn on each of
      the 4 endpoints (`POST /{agent_name}/run`, `POST /{agent_name}/chat`,
      `POST /orchestrate`, `POST /orchestrate/stream` — agent_routes.py:253/380/
      539/701). Tested as a shared code path (behavior asserted once) plus
      per-endpoint wiring assertions.
- [x] **AC-2** Skip trivial turns: trimmed user input <10 chars, or response
      empty/whitespace → no store scheduled.
- [x] **AC-3** Stored page shape: title/content capped with truncation marker;
      unpinned (`is_pinned=False`); default importance/decay; never forces review
      (`review_in_days=None`); provenance = agent name + session id in
      tags/metadata; documented `source`/`page_type` values distinguish chat
      pages (filterable — Curator and State Engine feed depend on this).
- [x] **AC-4** Store exceptions are logged and swallowed: the chat response is
      unchanged and never blocked. Embedding failure still stores the page
      (NULL embedding preserved — `_get_embedding` returning None must not
      abort the insert).
- [x] **AC-5** Cost ceiling: 0 added LLM completions; ≤1 added embedding call
      per turn; the READ path REUSES the query embedding `run()` already
      computes (base.py auto-embed step) — no re-embed for recall.

READ path:
- [x] **AC-6** ≥1 recall hit → exactly one `<memories>` block in `format_for_llm`
      shape in the assembled system prompt, positioned after `<guardrails>` and
      before `<conversation_history>`.
- [x] **AC-7** Zero hits or recall failure → NO `<memories>` block. Caveat:
      `format_for_llm([])` returns a `"<memories>No relevant memories
      found.</memories>"` placeholder (manager.py:994-995) — the caller must
      skip injection, not inject the placeholder. Do not change the formatter
      without checking its other callers (planner_routes.py:755, 1641).
- [x] **AC-8** Guardrail rule 3 (context-is-data, base.py:379) names
      `<memories>`; all existing 017 guardrail/history tests still pass.
- [x] **AC-9** Literal `<memories>` tags inside recalled content are escaped,
      case/whitespace-tolerant, mirroring 017's `_neutralize_history_tags` /
      `_HISTORY_TAG_RE` hardening (base.py:47-56).
- [x] **AC-10** The block obeys a documented char cap (default
      `format_for_llm(max_chars=6000)`).
- [x] **AC-11** *(added at M0 — Q1 promoted)* Recall hits whose
      `metadata["session_id"]` equals the agent's current session are never
      rendered into `<memories>` (those turns already appear in
      `<conversation_history>`); hits from other sessions still render.

**Tier B — live, DEFERRED** (same reason as 017: laptop cannot run Ollama; EC2
is free-tier, smoke-only):
- [ ] **AC-L1** (deferred) Live smoke: `user_insights` AND `memory_pages` rows
      both grow after chat turns, with correct provenance.
- [ ] **AC-L2** (deferred) A new session recalls the prior session's topic.
- [ ] **AC-L3** (deferred) No perceptible latency regression on chat endpoints.

## Success metrics  <!-- eng-product -->

- Memory loop live: AC-L1/AC-L2 pass in the (extended) task-019 smoke.
- Cost flat: no new LLM completion spend; ≤1 embedding call per turn.
- 0 chat failures attributable to memory writes.
- Bounded growth: chat pages are unpinned/decayable and skip-trivial keeps
  volume sane.
- Roadmap item / `tasks/backlog/005-temporal-memory-injection.md` closed as
  subsumed by this task.

## Out of scope

- Schema changes — `memory_pages` already has every needed column (source,
  tags, metadata_, is_pinned, decay); **no Alembic migration expected**. If the
  architect finds one is needed, that is a design change to flag, not to slip in.
- LLM-generated summaries/insights of turns (zero-completion constraint);
  `_extract_insights_background` already covers insight extraction separately.
- Changing `format_for_llm` output shape (other callers: planner_routes.py:755,
  1641) or MemoryManager scoring/decay internals.
- Curator/hygiene behavior changes (this task only makes chat pages *filterable*
  by them via documented source/page_type).
- Frontend/UI surfacing of memories; memory_routes.py API changes.
- Fixing history hydration or 017 behavior (shipped; only rule-3 wording and
  the escaping mirror touch that surface).

## Requirements / open questions  <!-- eng-planner -->

**Breakdown / constraints:**

- R1 WRITE = one shared helper used by all 4 endpoints, scheduled fire-and-forget
  after the response is produced. Wiring precedent already in agent_routes.py:
  `asyncio.create_task(_extract_insights_background(...))` at lines 340 (run),
  496 (chat), 644 (orchestrate), 833 (orchestrate/stream, inside
  `_run_and_persist`). Memory store hooks the same four points.
- R2 Store via `MemoryManager.async_store` (manager.py:213): embedding only
  (`auto_embed`), zero LLM completions. AC-4 nuance: `_get_embedding` already
  returns None on failure and the insert proceeds with NULL embedding — tests
  must lock this in, not reimplement it.
- R3 READ in `BaseAgent._build_system_prompt`: recall via
  `MemoryManager.async_recall` (manager.py:390) passing the query embedding
  `run()` already computed (AC-5 — no re-embed); render with `format_for_llm`;
  skip injection entirely on empty/failed recall (AC-7 placeholder caveat).
  Escape literal `<memories>` tags in recalled content before injection (AC-9),
  mirroring `_neutralize_history_tags`.
- R4 Prompt contract: `<memories>` slots after `<guardrails>`, before
  `<conversation_history>` in the ADR-013 assembled order (docs/decisions.md);
  guardrail rule 3 adds `<memories>` to its named blocks. 017's unit suite
  (`tests/unit/test_agent_history_prompt.py`) must stay green (AC-8) — extend,
  don't rewrite.
- R5 **Known stub/gap flags:**
  - `get_memory_manager()` singleton (manager.py:1064) lazy-inits a **raw
    `OllamaEmbeddings()`** (manager.py:118-119), ignoring
    `settings.EMBEDDING_PROVIDER` and the registry's Redis-cached embedder
    (`AgentRegistry._create_embedder`, registry.py:195-214). Design point for
    the architect: wire the configured embedder into the manager, or accept the
    degradation and document it. Affects AC-5's "≤1 embedding call" accounting
    (write-path embed cannot reuse the Redis cache as-is).
  - No repo-wide test runner (known gap, standards/testing.md): Tier A goes in
    `founder-os/apps/api/tests/unit/` alongside the 017 suite, run directly.
  - Tier B deferred for infra (no local Ollama; EC2 smoke-only) — carried by the
    task-019 smoke checklist, not by this PR's tests.
- R6 **eng-security mandatory** — this creates a NEW persistent untrusted-text
  injection surface: user/assistant chat text is stored, then re-injected into
  future system prompts across sessions (stored prompt injection). Audit focus:
  AC-9 escaping, guardrail rule 3 coverage, user_id scoping of recall (no
  cross-tenant leakage), no secrets/tokens persisted into memory_pages, caps.
- R7 Scope item C (extend task-019 smoke with a `memory_pages`-growth check):
  **correction at M0 (coordinator):** `tasks/backlog/019-chat-guardrails-live-checks.md`
  DOES exist in this worktree (the earlier "not tracked" note was a planner
  misread) — the 019 edit lands normally at M5/M6 from this worktree. The exact
  checks to add are specified in the Architecture section below.
- R8 New PR from `feat/chat-semantic-memory`; PR #19 (017) is merged — do not
  reuse its branch.

**Open decisions — ARCHITECT (flagged, intentionally not decided here):**

- Q1 **Same-session duplication**: current-session turns appear in BOTH
  `<conversation_history>` and (once stored) recall candidates. Product
  recommends excluding current-session pages from recall (session-id tag/metadata
  filter); if the exclusion is cheap, promote it to a Tier A criterion (AC-11).
  → **DECIDED at M0: metadata session filter, promoted to AC-11** (see Architecture).
- Q2 **Constants**: title/content caps + markers, `page_type`, `source`, and
  `chapter` values for chat pages = architect's documented choice (AC-3 requires
  they be documented and filterable). → **DECIDED at M0** (see Architecture).
- Q3 **ADR**: new ADR-014 vs a one-line ADR-013 amendment adding the `<memories>`
  slot to the assembled-order contract — architect decides.
  → **DECIDED at M0: ADR-014 written; ADR-013 order paragraph cross-references it.**
- Q4 (from R5) Embedder wiring for the MemoryManager singleton: configured
  provider + Redis cache, or documented degradation.
  → **DECIDED at M0: fix it via `get_default_embedder`** (see Architecture).

### Milestones

| # | Milestone | Owner | Exit criterion |
|---|-----------|-------|----------------|
| M0 | Design record | eng-architect | Architecture section filled; Q1-Q4 decided; ADR written/amended |
| M1 | Implement + tests | eng-executor | WRITE + READ per design; Tier A tests (AC-1..11) green; 017 suite green; output shown |
| M2 | Review | eng-reviewer | Diff reviewed vs standards; formatter-caller check (AC-7) confirmed; findings logged |
| M3 | QA | eng-qa | Per-AC Pass/Fail with output; AC-L1..L3 recorded deferred-with-reason |
| M4 | Security | eng-security | Stored-injection / scoping / secrets audit; Pass verdict |
| M5 | Docs | eng-executor | docs/architecture.md memory+prompt sections, code comments, constants documented; 019 smoke extension applied |
| M6 | Roadmap + PR | eng-product | New PR opened; roadmap updated; backlog 005 closed as subsumed; task → completed/ |

### Ordered task list

1. (M0) Decide Q1-Q4; fill Architecture section; write ADR-014 or amend ADR-013.
2. (M1) Implement shared WRITE helper + wire all 4 endpoints (R1, R2).
3. (M1) Implement READ injection in `_build_system_prompt` + guardrail rule 3 +
   `<memories>` escaping (R3, R4).
4. (M1) Add Tier A unit tests in `tests/unit/` (recorder-stub pattern); run the
   full unit suite including the 017 file; paste output in Build notes.
5. (M2) Review; verify AC-7 placeholder handling and other `format_for_llm`
   callers untouched.
6. (M3) QA per acceptance criterion; record Tier B deferrals with reason.
7. (M4) Security audit per R6.
8. (M5) Update docs + comments; document Q2 constants; apply the 019 smoke
   extension (R7).
9. (M6) Open PR; update roadmap; close backlog 005 as subsumed; move this file
   to completed/; run the CLAUDE.md §9 loop.

---

## Architecture  <!-- eng-architect; add an ADR to docs/decisions.md if significant -->

> M0 forward design (2026-07-19). **ADR-014** appended to
> [docs/decisions.md](../../docs/decisions.md) (Q3: a full ADR, not an ADR-013
> one-liner — this creates the chat→memory write path, an identity decision, a
> new prompt block, an `async_recall` signature extension, and the manager
> embedder fix; ADR-013's assembled-order paragraph got a one-line
> cross-reference). Everything below is binding for M1; deviations go back
> through M0.

### Data model + Alembic

**None.** No migration. `memory_pages` as-is (`user_id` is `String(100)`, no FK;
`source`/`tags`/`metadata_`/`is_pinned`/decay columns all exist). Confirmed: no
schema change needed (the out-of-scope guard holds).

### API (endpoints, auth, shapes; registration in main.py)

**No new/changed endpoints, no main.py changes.** The four existing chat
endpoints gain one background `asyncio.create_task` each; request/response
shapes untouched. `memory_routes.py` untouched.

### Identity (binding — WRITE and READ must match)

- **`memory_pages.user_id` = the Clerk user id** (`user.user_id`), exactly as
  the insights helper receives it today.
- Justification (ADR-014 §2): the table has no FK to `users`; its established
  key across the dashboard (`memory_routes.py:140/193`), planner recall
  (`planner_routes.py:743`), and crawler routes is the Clerk id. Writing under
  the DB `user_uuid` would make chat memories invisible to every existing
  reader. ADR-007's "one real identity" = one consistent key per store.
- READ side queries the same key: `self.clerk_user_id or str(self.user_id)`
  (the `base.py` profile-loader precedent; `registry.get` sets
  `agent.clerk_user_id = mcp_uid` at registry.py:350 for every chat-built agent).
- Flagged, NOT fixed here (pre-existing): the research engine stores pages under
  `str(user_uuid)` (`registry.py:955`), invisible to Clerk-id recall — file as a
  backlog item at M6.

### WRITE path (agent_routes.py)

- **Placement:** module-level `async def _store_chat_memory_background(user_id:
  str, agent_name: str, user_message: str, agent_response: str, session_id:
  str | None) -> None` directly beside `_extract_insights_background`
  (agent_routes.py:84). No new module — the 4 hook sites and the precedent live
  in this file; a separate module is unjustified until a 5th caller exists.
- **Hook points:** a separate
  `asyncio.create_task(_store_chat_memory_background(user_id=user.user_id, ...))`
  immediately after each existing insights `create_task` — lines ~340 (run),
  ~496 (chat), ~644 (orchestrate), ~833 (orchestrate/stream, inside
  `_run_and_persist`, after its insights task). Do NOT fold the store into
  `_extract_insights_background` (independent failure isolation per AC-4;
  independent testability per AC-1). Mirror the precedent's bare `create_task`
  (no strong-ref set — see Risks).
- **Behavior:** (1) skip-trivial guard first: `user_message` trimmed < 10 chars
  OR `agent_response` empty/whitespace → return (AC-2); (2) whole body wrapped
  in try/except → `logger.warning`, never raise (AC-4); (3) store via
  `get_memory_manager().async_store(..., auto_embed=True)` — embedding only, no
  completions; `_get_embedding` → None still inserts (NULL embedding, existing
  manager behavior, locked by test); (4) only `user_message` + final
  `agent_response` are persisted — never tool outputs.
- **Constants (Q2 — module-level beside the helper, with a short comment
  block; these are the documented, filterable values AC-3 requires):**

  | Constant | Value |
  |---|---|
  | `_CHAT_MEMORY_MIN_INPUT_CHARS` | `10` (mirrors insights guard) |
  | `_CHAT_MEMORY_TITLE_CHARS` | `100` (user-message excerpt cap, ` …` marker) |
  | `_CHAT_MEMORY_USER_CHARS` | `600` (` …` marker) |
  | `_CHAT_MEMORY_RESPONSE_CHARS` | `1400` (` …` marker) |
  | `page_type` | `"conversation"` |
  | `source` | `"chat"` |
  | `chapter` | `"conversations"` |
  | `tags` | `["chat", <agent_name>]` |
  | `metadata` | `{"session_id": <session_id or "">, "agent": <agent_name>}` |

  Title = `f"Chat ({agent_name}): {excerpt}"`; content =
  `f"User: {u}\n\nAssistant: {a}"` with the per-side caps. Everything else uses
  `async_store` defaults: importance 0.5, decay_rate 0.001, `is_pinned=False`
  explicit, `review_in_days=None` (never forces review), `occurred_at=None`
  (now). `source="chat"` + `page_type="conversation"` are the provenance keys
  the Curator / State Engine `system` feed filter on; `metadata.session_id` is
  the AC-11 exclusion key.

### READ path (base.py)

- **Placement: `BaseAgent._build_system_prompt`, not `AgentMemory.build_context`**
  (backlog 005's sketch is superseded — recorded in ADR-014 §6): the recall
  needs `clerk_user_id`, the current `session_id`, tag escaping, and the
  skip-on-empty rule — all BaseAgent/prompt-contract concerns; `AgentMemory`
  holds none of them. `build_context` stays working/shared/RAG only.
- **New helper** `async def _render_memories_context(self, query, query_embedding)
  -> str`, called in `_build_system_prompt` between the `mem_ctx` append
  (~line 433) and the `history_ctx` append (~line 437). Resulting order:
  … → delegation → working/shared/knowledge → **`<memories>`** →
  `<conversation_history>` → `<additional_context>` (AC-6: after
  `<guardrails>`, before history — satisfied).
- **Recall call** (function-local import, mirroring the profile loaders):
  `get_memory_manager().async_recall(user_id=<clerk id per Identity>,
  query=query, query_embedding=query_embedding, auto_embed_query=False,
  limit=_MEMORY_RECALL_LIMIT, min_importance=_MEMORY_MIN_IMPORTANCE)`.
  `auto_embed_query=False` guarantees **zero** recall-side embedding even when
  `query_embedding is None` (recall then degrades to the temporal+importance SQL
  branch). **No `page_type` filter** — chat, crawler, and planner pages all
  surface (cross-source recall is the feature; caps bound the block).
- **New base.py class constants** (beside `_HISTORY_*`):
  `_MEMORY_RECALL_LIMIT = 8`, `_MEMORY_RENDER_LIMIT = 5`,
  `_MEMORY_MIN_IMPORTANCE = 0.2` (planner precedent),
  `_MEMORY_BLOCK_MAX_CHARS = 6000` (AC-10; equals the formatter default, passed
  explicitly).
- **Q1 / AC-11 — same-session exclusion (decided):** post-filter in the helper:
  drop hits where `(h.metadata or {}).get("session_id")` equals the agent's
  current session; recall over-fetches (8) then renders the top 5 survivors.
  Enabler: `registry.get()` sets `agent.session_id = session_id or ""` next to
  the existing `clerk_user_id` assignment (registry.py:350); `BaseAgent.__init__`
  declares `self.session_id: str = ""` beside `clerk_user_id` (base.py:147).
  Cheap + fully unit-testable → promoted to **AC-11**.
- **Rendering:** if no surviving hits → return `""` (AC-7 — never call
  `format_for_llm([])`, its placeholder must not be injected; the formatter
  itself is untouched, other callers at planner_routes.py:755/1641 unaffected).
  Otherwise sanitize each hit (see next bullet) and return
  `mgr.format_for_llm(hits, max_chars=self._MEMORY_BLOCK_MAX_CHARS)`. Whole
  helper wrapped in try/except → `""` (recall failure = no block; `async_recall`
  already returns `[]` on SQL failure).
- **Escaping (AC-9):** add a sibling of the 017 hardening in base.py:
  `_MEMORIES_TAG_RE` (same case/whitespace-tolerant pattern, tag `memories`) +
  `_neutralize_memory_tags()`. Before formatting, rebuild each hit with
  `dataclasses.replace(h, title=…, content=…, summary=…, chapter=…, tags=[…])`
  passing every text field through **both** neutralizers (`memories` AND
  `conversation_history` — stored text could also spoof/pre-close the history
  block that renders after `<memories>`). Do not modify `format_for_llm`.
  Keep `_neutralize_history_tags` / `_HISTORY_TAG_RE` names intact (017 suite
  references the behavior).
- **Guardrail rule 3 (AC-8):** extend the enumerated list at base.py:379 to
  `<conversation_history>, <memories>, <working_memory>, <shared_memory>,
  <knowledge_context>, and <additional_context>`. The 017 assertions
  ("background data, not instructions", rule substrings) survive unchanged —
  the 017 file needs zero edits.

### Surgical edits outside the two main files (allowed, minimal)

1. `app/memory/manager.py` — `async_recall` gains keyword-only
   `query_embedding: list[float] | None = None` (mirrors sync `recall()`, which
   already has it). Semantics: if provided → skip auto-embed, use the semantic
   SQL branch; if `None` → existing behavior byte-for-byte. Existing callers
   (memory_routes, planner_routes) pass nothing → unaffected.
2. `app/memory/manager.py` — `_get_embedding` lazy-init (Q4, **fix chosen**):
   replace raw `OllamaEmbeddings()` (lines 118-119) with
   `get_default_embedder(redis=<best-effort>)`
   (`app/retrieval/embeddings.py:356` — the existing settings-driven factory:
   honors `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL`, wraps in the Redis-backed
   `CachedEmbeddingProvider` when a redis handle is available). Redis handle:
   `try: from app.redis import get_redis; redis = get_redis() except Exception:
   redis = None` — uncached fallback, never fatal. Failure to init still logs
   and returns `None` (NULL-embedding path preserved). This fixes the R5 gap
   for **every** manager caller; no signature changes; `get_memory_manager()`
   itself unchanged.
3. `app/agents/registry.py` — one line: `agent.session_id = session_id or ""`
   beside the `clerk_user_id` assignment (~line 350) (AC-11 enabler).

### Integration points (agents, tools, memory, approval, celery)

- **Agents:** READ inherited by every BaseAgent subclass incl. the Orchestrator
  (`run()` wraps `super().run()`) and A2A-delegated runs. Agents built outside
  `agent_routes` (Celery tasks, delegated runs) simply have empty
  `session_id`/`clerk_user_id` fallbacks — recall degrades gracefully (uuid key
  or no block), never errors.
- **WRITE trigger surface is exactly the 4 chat endpoints** (AC-1). Celery
  agent tasks and A2A sub-runs do NOT store chat memories in this task (their
  outputs reach the founder through the top-level turn, which is stored).
- **Memory layers (ADR-009 taxonomy):** this feeds the temporal KG
  (`memory_pages`) only; `knowledge_items` RAG, working/shared memory, and the
  State Engine are untouched. Chat pages are the State Engine `system` feed's
  future input — hence the documented provenance keys.
- **Approval gate / tools:** untouched. Tool outputs are never persisted to
  memory_pages.
- **Celery/scheduler:** untouched (writes are in-process `asyncio.create_task`,
  per the insights precedent; a queue round-trip for a best-effort write was
  rejected — ADR-014 alternatives).

### M1 test plan (binding shape; extend the 017 harness)

- **Files:** extract the 017 doubles (`StubLLM`, `RecorderEngine`, `EchoAgent`,
  `make_agent`) into `tests/unit/prompt_harness.py`; `test_agent_history_prompt.py`
  imports them (assertions byte-identical — stays green, AC-8); new
  `tests/unit/test_chat_memory.py` covers AC-1..11.
- **READ tests:** `FakeMemoryManager(MemoryManager)` overriding
  `async_recall`/`async_store`/`_get_embedding` with recorders (inherits the
  REAL `format_for_llm`, so block-shape assertions test true output);
  monkeypatch `app.memory.manager.get_memory_manager` to return it (the
  function-local import resolves at call time). Set `agent.clerk_user_id` /
  `agent.session_id` on the harness agent. AC-5: a counting stub embedder on
  `agent._embedder`; assert `async_recall` received the same embedding object
  with `auto_embed_query=False` and the fake's `_get_embedding` was never
  called. AC-11: canned `MemoryHit`s with matching/other `metadata.session_id`.
- **WRITE tests:** call `_store_chat_memory_background(...)` directly (await it;
  no create_task needed) against the fake manager; assert call counts (AC-1
  shared path, AC-2 zero calls), kwargs shape (AC-3 constants), swallowed
  exceptions (AC-4: fake `async_store` raises → no propagation). Per-endpoint
  wiring (AC-1): `inspect.getsource(<endpoint fn>)` contains
  `_store_chat_memory_background` for `run_agent`, `chat_with_agent`,
  `orchestrate`, and `orchestrate_stream` (whose source includes the
  `_run_and_persist` closure). AC-4 NULL-embedding: real-`MemoryManager`-shaped
  fake where `_get_embedding` returns None → assert the insert call still
  happens with `embedding=None` semantics (assert on recorded `async_store`
  kwargs / a stubbed session boundary — do NOT hit a DB).
- Run: `pytest tests/unit/` from `apps/api` (venv), same config the 017 suite
  uses; paste output in Build notes.

### Task-019 smoke extension (scope C — exact checks; applied at M5)

Append to `tasks/backlog/019-chat-guardrails-live-checks.md`:
- **AC-M1 (from 020 AC-L1):** after ≥2 chat turns, `memory_pages` gained rows
  with `source='chat'`, `page_type='conversation'`, `user_id` = the Clerk id,
  `tags @> ['chat']`, `metadata_->>'session_id'` populated — alongside the
  existing `user_insights` growth check.
- **AC-M2 (from 020 AC-L2):** new session, ask about the prior session's topic
  → answer reflects recall (and, with debug access, the prompt contains one
  `<memories>` block).
- **AC-M3 (from 020 AC-L3):** perceived chat latency unchanged (recall adds 1-2
  queries/turn).

### Risks / trade-offs (reviewer + security attention)

- **Stored prompt injection (R6, M4 focus):** chat text persists and re-enters
  future prompts cross-session. Mitigations: rule 3 names `<memories>`; both
  tag neutralizers on recalled text; no tool outputs stored. Residual: inner
  `format_for_llm` structure tags (`</content></memory>`) are NOT escaped —
  breakout stays inside the `<memories>` block (data-typed by rule 3); M4 may
  demand escaping those two inner tags too (cheap addition if so).
- **Cross-tenant scoping (M4):** recall is scoped solely by `user_id` equality
  in SQL — verify the READ helper can never pass an empty user id (guard:
  falsy id → return "").
- **Bare `create_task` GC risk:** asyncio holds only weak refs; the insights
  precedent already accepts this (cf. `_background_runs` strong-ref set used
  for orchestrations). Mirrored for consistency; if the reviewer objects, add a
  module-level strong-ref set for BOTH background helpers (one-line each).
- **Latency:** +1-2 DB queries (+ access-counter UPDATE + commit) per turn from
  recall — live-checked only (AC-L3/AC-M3).
- **Growth/bloat:** bounded by skip-trivial + unpinned default decay; if chat
  pages bloat recall, follow-ups are a faster `decay_rate` for
  `source='chat'` and the ADR-009 Curator pass (do not pre-build).
- **50/20-style duplication note:** a recalled memory of a *hydrated* prior
  session could partially overlap `<conversation_history>` when the founder
  resumes the SAME session that was also stored — AC-11's filter removes the
  same-session case; cross-session near-duplicates are accepted (decay +
  ranking handle them).
- **`_get_embedding` swap blast radius:** all manager callers now get the
  configured provider (intended); if `EMBEDDING_PROVIDER=openai` with no key,
  `create_embedding_provider` raises → caught → NULL embeddings (same failure
  mode as today's wrong-provider case). Reviewer should confirm no caller
  depended on the raw-Ollama default.

### M5 surgical doc edits (list — do not rewrite files wholesale)

1. `docs/architecture.md` — "Agent system" `base.py — BaseAgent` bullet: extend
   the ADR-013 sentence with the `<memories>` slot, e.g. append: "ADR-014 adds a
   composite-scored `<memories>` recall block (chat turns auto-captured to
   `memory_pages`) between memory context and history."
2. `docs/architecture.md` — "Memory & temporal knowledge graph" section: add
   one bullet: chat turns are captured to `memory_pages`
   (`source="chat"`, `page_type="conversation"`, agent_routes background
   helper) and recalled into prompts via `BaseAgent._render_memories_context`
   (ADR-014).
3. `docs/decisions.md` — already done at M0 (ADR-014 + ADR-013 cross-ref);
   M5 verifies only.
4. Code comments: constants block comment in `agent_routes.py`; a "why" comment
   on `_render_memories_context` (reuse of run()'s embedding, placeholder trap,
   session exclusion); note on `async_recall`'s new param mirroring sync
   `recall()`.
5. `tasks/backlog/019-...md` — append the three smoke checks above (scope C).
6. `tasks/backlog/005-temporal-memory-injection.md` — at M6, close as subsumed
   by 020/ADR-014 (note the placement difference vs its `build_context` sketch).

## Build notes  <!-- eng-executor -->
- Changed files (M1, 2026-07-19 — exactly the approved design, no deviations):
  - `founder-os/apps/api/app/api/agent_routes.py` — WRITE:
    `_store_chat_memory_background` + `_excerpt` + the Q2 constants block
    (`_CHAT_MEMORY_*`, page_type/source/chapter values) beside
    `_extract_insights_background`; separate bare
    `asyncio.create_task(...)` immediately after the insights task at all 4
    sites (run / chat / orchestrate / orchestrate-stream's `_run_and_persist`).
    Skip-trivial guard, try/except log+swallow, `async_store(auto_embed=True)`
    defaults (unpinned, importance/decay/review untouched).
  - `founder-os/apps/api/app/agents/base.py` — READ: `_MEMORIES_TAG_RE` +
    `_neutralize_memory_tags` sibling hardening; `self.session_id` declared in
    `__init__`; `_MEMORY_RECALL_LIMIT=8` / `_MEMORY_RENDER_LIMIT=5` /
    `_MEMORY_MIN_IMPORTANCE=0.2` / `_MEMORY_BLOCK_MAX_CHARS=6000` constants;
    `_render_memories_context()` (identity guard → `async_recall` with reused
    embedding + `auto_embed_query=False` → AC-11 session post-filter → both
    neutralizers over every text field via `dataclasses.replace` → real
    `format_for_llm` only when hits survive → `""` on any failure); called in
    `_build_system_prompt` between memory context and the history block;
    guardrail rule 3 now names `<memories>`.
  - `founder-os/apps/api/app/memory/manager.py` — `async_recall` gains
    keyword-only `query_embedding` (mirrors sync `recall()`; when provided,
    auto-embed is skipped; existing callers unchanged); `_get_embedding`
    lazy-init now uses `get_default_embedder(redis=<best-effort get_redis>)`
    instead of raw `OllamaEmbeddings()` (Q4 fix; failure still → None →
    NULL-embedding insert).
  - `founder-os/apps/api/app/agents/registry.py` — one assignment:
    `agent.session_id = session_id or ""` beside `clerk_user_id` (AC-11).
  - `founder-os/apps/api/tests/unit/prompt_harness.py` — NEW: 017 doubles
    (`StubLLM` now counts generate() calls for AC-5, `RecorderEngine`,
    `EchoAgent`, `make_agent`) extracted for reuse.
  - `founder-os/apps/api/tests/unit/test_agent_history_prompt.py` — imports the
    harness; assertions byte-identical; still green (AC-8).
  - `founder-os/apps/api/tests/unit/test_chat_memory.py` — NEW: 18 tests over
    AC-1..11 (`FakeMemoryManager` recording store/recall/embed/format but
    inheriting the REAL `format_for_llm`; `CountingEmbedder` proving AC-5's
    0-completions / ≤1-embed / recall-never-embeds; `_RecordingSession` at the
    DB boundary proving the AC-4 NULL-embedding insert; `inspect.getsource`
    wiring assertions for the 4 endpoints).
  - `tasks/backlog/019-chat-guardrails-live-checks.md` — scope C: AC-M1..M3
    (memory_pages growth+provenance, cross-session recall, latency) appended;
    deps/links updated.
- How verified: from the worktree,
  `cd founder-os/apps/api && <main-checkout .venv>/bin/python -m pytest` →
  **195 passed, 20 deselected, 100 warnings in 1.30s** (baseline 177 + 18 new;
  the 017 suite's 13 all green post-refactor). Note: the run needed
  `pip install posthog` into the main checkout's venv — merged main (PR #18)
  imports it in `app/main.py` and the venv predated that; pre-existing, not
  caused by this task.
- Deferred as specified: AC-L1..L3 (Tier B) — no local Ollama, EC2 smoke-only;
  carried by the extended task-019 checklist.

## Review findings  <!-- eng-reviewer -->

> M2 review (2026-07-19). Reviewed the full uncommitted worktree diff (7 modified
> + 3 new files — exactly the file set in Build notes, no unrelated churn) against
> the binding Architecture section, ADR-014, and standards/coding.md. Code read in
> full: agent_routes.py helper + all 4 hook sites in context, base.py READ path,
> manager.py (`async_recall`, `async_store`, `format_for_llm`, `_get_embedding`,
> `_score_and_rank`), registry.py, both test files, prompt_harness.py,
> embeddings.py factory, decisions.md, backlog 019.

**Coordinator checks — all verified with evidence:**

1. **AC-7 formatter-caller check: PASS.** `format_for_llm` (manager.py:995-1029)
   is byte-untouched by the diff; `planner_routes.py:755/1641` callers
   unaffected (no diff in planner_routes.py). `_render_memories_context`
   returns `""` before ever calling the formatter when hits are empty
   (base.py — `if not hits: return ""`), so the `[]`-placeholder can never be
   injected; locked by test_ac7_zero_hits (asserts the placeholder string is
   absent).
2. **`async_recall` signature change: backward-compatible.** All params after
   `*` are keyword-only; `query_embedding` is appended with default `None`
   and the guard `if query_embedding is None and query and auto_embed_query`
   (manager.py:424) preserves existing behavior byte-for-byte when omitted.
   All existing callers (memory_routes.py:192, planner_routes.py:742/1632)
   pass keywords only and omit it. Mirrors sync `recall()` (manager.py:326)
   as designed.
3. **4 hook sites: no double-store, no response blocking.** Exactly one
   `asyncio.create_task(_store_chat_memory_background(...))` per endpoint
   (agent_routes.py:418, 583, 740, 938), each a separate task after the
   insights task, after the result is produced and DB persistence committed,
   before the response/`result_future.set_result`. The orchestrate-stream site
   sits inside `_run_and_persist`, which runs once per POST; its except-branch
   (line ~950) never reaches the hook on failure. `create_task` is
   non-blocking; the helper opens its own DB session (async_store →
   `async_session()`), no request-session sharing. The four endpoints are
   disjoint routes — no shared path that could double-fire.
4. **`_get_embedding` swap blast radius: acceptable and intended.** All
   `get_memory_manager()` callers (memory_routes, planner_routes ×4,
   crawler_routes ×2, crawler/research, registry:948, and the two new 020
   call sites) now get the settings-driven factory
   (`get_default_embedder`, embeddings.py — honors
   EMBEDDING_PROVIDER/MODEL/BASE_URL, Redis-cached). No caller depended on
   the raw-Ollama default: the old path hardcoded `http://localhost:11434`
   regardless of settings, i.e. it was already broken anywhere Ollama isn't
   local — the swap strictly widens correct configuration. Failure envelope
   unchanged: factory raise → caught → warning → `None` → NULL-embedding
   insert (locked by test_ac4_null_embedding at the recorded-session DB
   boundary). One narrowing noted as a nit below (Redis-runtime-outage path).
5. **Test quality: the 18 tests genuinely prove AC-1..11.** Verified by
   reading every assertion and re-running:
   `pytest tests/unit/test_chat_memory.py tests/unit/test_agent_history_prompt.py`
   → **31 passed** (18 + the 017 suite's 13, assertions byte-identical after
   the harness extraction); full tier → **195 passed, 20 deselected in 1.21s**
   (matches Build notes). Highlights: AC-5 asserts identity (`is`) on the
   reused embedding object + `auto_embed_query is False` + zero fake-manager
   embed calls; AC-9 exercises case/whitespace tag variants for BOTH block
   families and asserts the payload stays inside `<memories>`; AC-11 is
   locked end-to-end AND the live mapping exists (`_score_and_rank` populates
   `MemoryHit.metadata` from `metadata_`, manager.py:559 — the filter key is
   real, not test-fabricated). Brittleness verdict on the
   `inspect.getsource` wiring assertions: see nit below — mildly brittle in
   the false-negative direction, not flaky.
6. **Scope: clean.** Worktree diff = exactly the approved file set; no schema
   change, no main.py/endpoint-shape change, `format_for_llm` and scoring
   internals untouched, memory_routes untouched. The backlog-019 edit landed
   at M1 rather than M5 as scheduled, but its content is exactly the
   Architecture-specified AC-M1..M3 text (process nit, not scope creep).

**Findings:**

- [nit] founder-os/apps/api/tests/unit/test_chat_memory.py:165-175
  (`test_ac1_endpoint_wiring`) — `inspect.getsource` substring check passes
  even if a hook call is commented out, and doesn't verify the
  `create_task` wrapping → tighten the needle to
  `"asyncio.create_task(_store_chat_memory_background("` (still one line,
  removes the comment false-negative). Refactor-direction brittleness
  (moving hooks into a shared helper breaks it loudly) is acceptable — it is
  the architect-prescribed per-endpoint wiring assertion.
- [nit] founder-os/apps/api/tests/unit/test_chat_memory.py:291
  (`agent.llm.calls == 0`) — trivially true: the RecorderEngine replaces the
  engine, so `generate()` is unreachable by construction. Harmless
  belt-and-braces; the real AC-5 proof is the embed-identity + counter
  assertions. Optionally drop or comment it as documentation-only.
- [nit] founder-os/apps/api/app/memory/manager.py:122-127 — the `redis = None`
  fallback covers `get_redis()` **init** failure only; a Redis that is up at
  init but down at call time makes `CachedEmbeddingProvider.embed` raise on
  the cache `.get` → caught → `None` → NULL embedding, where the pre-swap raw
  provider would have embedded successfully. Same posture as the registry's
  cached embedder (pre-existing class behavior, not a 020 defect) → note for
  M4/M5; the proper fix (cache-error fallthrough to the base provider) lives
  in embeddings.py, outside 020's approved scope — file as backlog if M4
  agrees.
- [nit] founder-os/apps/api/app/memory/manager.py:1013 — `format_for_llm`
  interpolates `m.page_type`/rank attributes unescaped into the
  `<memory type="...">` attribute; `page_type` is attacker-influenced only
  via the user's own memory API (self-injection, low value). All
  free-text fields ARE neutralized by the READ helper. M4's call whether to
  extend neutralization; do not change the formatter in this task (AC-7
  caller constraint).
- [nit] founder-os/apps/api/app/api/agent_routes.py:418/583/740/938 — bare
  `create_task` holds only a weak ref; a GC'd task silently drops a
  best-effort write. Explicitly accepted in the Architecture risk list
  (mirrors the insights precedent). If hardening is ever wanted: one
  module-level strong-ref set for BOTH background helpers.
- [nit] founder-os/apps/api/app/api/agent_routes.py:583 — the chat endpoint
  stores turns with `stop_reason == "clarification"` (the agent's question
  back to the founder) as memories. Defensible (it is a real exchange) and
  the skip-trivial guard bounds it; flagging only so M3/M4 make it a
  conscious choice.

**Standards check:** coding.md compliant — async-first, full type hints,
why-comments in the existing `# ──` idiom, `logging` not print, no new
dependencies, no ad-hoc env reads, provider-neutral plain-text blocks,
reuse-before-add honored (existing manager/formatter/factory reused). No
Alembic needed (no schema change — verified: `async_store` uses existing
columns only). Security posture (pre-M4): recall scoped by `user_id` with a
falsy-identity guard locked by test_ac7_missing_identity; both tag families
neutralized on recalled text; no secrets persisted beyond what the founder
typed into chat (M4 to assess); guardrail rule 3 extended.

- Verdict: **APPROVE-WITH-NITS** — implementation matches the binding
  Architecture section exactly (all Q1-Q4 decisions honored, AC-1..11
  covered, 195-test tier green, zero scope creep). All findings are nits;
  none touch product-code correctness. Proceed to **eng-qa (M3)**; the
  getsource-tightening nit can ride along at M3/M5 without re-review; the
  Redis-outage and formatter-attribute nits are handed to **eng-security
  (M4)** for disposition.

## QA results  <!-- eng-qa -->

> Process note (honest record): M3 was performed by the workflow coordinator via an
> independent re-run + assertion spot-checks, not a separate eng-qa session — the
> account hit its session usage limit mid-task and the remaining budget was reserved
> for the mandatory review + security gates. Deviation approved-by-necessity;
> Tier B live checks remain deferred to backlog/019 regardless.

- Command (worktree, main checkout's venv):
  `python -m pytest` → **195 passed, 20 deselected** (baseline 177 + 18 new; zero
  regressions, 017 suite still 13/13 via the extracted harness).
  `python -m pytest tests/unit/test_chat_memory.py -v` → **18 passed**.
- Pass/Fail per criterion — all Tier A **Pass**, mapped 1:1 to test names:
  AC-1 `test_ac1_one_store_per_turn` + `test_ac1_endpoint_wiring` ·
  AC-2 `test_ac2_skip_trivial_turns` ·
  AC-3 `test_ac3_page_shape_and_caps` + `test_ac3_no_session_id_stored_as_empty` ·
  AC-4 `test_ac4_store_exception_swallowed` + `test_ac4_null_embedding_still_inserts` ·
  AC-5 `test_ac5_embedding_reused_never_re_embedded` (+ degraded-path variant) ·
  AC-6 `test_ac6_memories_block_shape_and_position` ·
  AC-7 three tests (zero-hits, recall-failure, missing-identity) ·
  AC-8 `test_ac8_guardrails_name_memories` · AC-9 `test_ac9_recalled_tags_neutralized` ·
  AC-10 `test_ac10_char_cap` · AC-11 exclusion + overfetch/render-limit tests.
- Assertion genuineness spot-checked (not smoke): AC-5 asserts
  `query_embedding is embedder.last`, `auto_embed_query is False`,
  `fake.embed_calls == []`, `llm.calls == 0`; AC-7 asserts recall ran but
  `(0, 0)` memories tag lines and the literal formatter placeholder is absent.
- AC-L1..L3: **deferred** (no local LLM; EC2 smoke-only) → tasks/backlog/019.

## Security report  <!-- eng-security; required if change touches auth/secrets/approval/input -->

> M4 audit (2026-07-19) per R6 + Architecture risk list. Scope: worktree diff of
> `base.py`, `agent_routes.py`, `manager.py`, `registry.py` + new
> `tests/unit/prompt_harness.py` / `test_chat_memory.py`; ADR-014 read.
> Proportionality: prompt-level guardrails are the accepted posture
> (ADR-013/014); only new risks and cheap hardenings are ranked.

**Findings (ranked) — no blockers:**

- [should-fix] `founder-os/apps/api/app/agents/base.py:626-643` — the
  architect's flagged residual, ruled on: inner `format_for_llm` structure tags
  (`</content>`, `</memory>`, `<memory rank=… score=…>`, `<title>`, `<tags>`)
  are NOT neutralized in recalled text. A stored chat turn can fabricate whole
  fake memory entries with forged rank/score/type/date — forged retrieval
  provenance that lends injected text false authority, even though it cannot
  escape the data-typed `<memories>` block (outer tags neutralized) or reach
  `<conversation_history>`/top-level position (both handled). RULING: the
  current state is acceptable to ship (no privilege boundary is crossed, the
  same inner-tag exposure pre-exists via `planner_routes.py:755/1641`, and rule
  3 data-types the whole block) — but the escape is demanded as a should-fix
  because this diff routes the most attacker-shapeable text class (chat,
  incl. third-party content relayed in assistant answers) through the formatter
  into every agent prompt. Fix (cheap, inside `_clean`): one more alternation
  neutralizing the inner structure tags, e.g.
  `re.compile(r"<\s*(/?)\s*(memory|content|title|when|chapter|tags)\b([^>]*)>", re.I)`
  → `&lt;…&gt;`, + one test. While there: `page_type` is rendered into the
  `<memory type="…">` attribute unneutralized (constant `"conversation"` for
  chat pages; user-settable via memory_routes for their own tenant) — pass it
  through `_clean` too via `dataclasses.replace`.
- [nit] `founder-os/apps/api/app/api/agent_routes.py:214`,
  `founder-os/apps/api/app/agents/base.py:645` — exception text from
  user-triggered flows is interpolated into logs without `sl()`; the
  `app/log_sanitize.py` policy names exactly this case (CRLF log-record
  forging). The insights precedent (agent_routes.py:146) has the same
  pre-existing gap — mirroring it is understandable, but the two NEW lines
  should wrap: `logger.warning(..., sl(exc))` / `logger.debug(..., sl(exc))`.
- [nit] `founder-os/apps/api/app/agents/base.py:626-627` — `_clean` neutralizes
  the two post-position block tags (`memories`, `conversation_history`) but
  stored text can still spoof other known block names (e.g. a fake
  `<guardrails>` or `<additional_context>` opening) inside the data-typed
  block — same accepted-residual class (rule 3 covers it), but if S1 is done, a
  single generalized alternation over all known block-tag names costs nothing
  extra.

**R6 / focus-point answers:**

1. **Stored prompt injection:** guardrail rule 3 names `<memories>`
   (base.py:390) and the 017 suite stays green. Recalled `title`, `content`,
   `summary`, `chapter`, and every `tag` pass through BOTH neutralizers
   (`_neutralize_memory_tags` base.py:61-66 + `_neutralize_history_tags`) via
   `dataclasses.replace` before `format_for_llm` (base.py:626-642) — both
   regexes case/whitespace-tolerant (017's should-fix, correctly mirrored), so
   stored text can neither close `<memories>` early nor pre-spoof/pre-close the
   `<conversation_history>` block that renders after it. `format_for_llm` only
   renders the cleaned fields (+ `page_type`/date; `summary or content`, both
   cleaned). Empty/failed/no-identity recall renders nothing — the `[]`
   placeholder is unreachable (base.py:623-624, guarded before the formatter).
   Residual = inner structure tags: ruled acceptable-not-blocking, escape
   demanded as should-fix S1 (above). Covered by
   `test_ac9_recalled_tags_neutralized`.
2. **Tenant isolation:** WRITE — all 4 sites pass `user_id=user.user_id` from
   `Depends(require_auth)` (agent_routes.py:410/575/732 and ~934 inside
   `_run_and_persist`, which closes over the authenticated `user`); no
   request-body id anywhere. READ — identity is
   `self.clerk_user_id or str(self.user_id or "")` with a falsy guard →
   `return ""` (base.py:602-604); both attrs are set only by `registry.get()`
   from the authenticated route. Recall SQL always includes parameterized
   `user_id = :user_id` in both branches (manager.py:427-428; f-string parts
   are code-owned filter strings and float weights, no user input in SQL text);
   the access-counter UPDATE uses ids from the scoped SELECT. The AC-11
   session post-filter only DROPS hits from the already user-scoped list — it
   cannot introduce foreign rows; a session-id collision with another tenant is
   therefore harmless. UUID fallback keys to the same user's own UUID
   (degraded recall, not leakage; pre-existing research-engine asymmetry is
   flagged in ADR-014 as backlog). No cross-tenant path found.
3. **Secrets:** the stored excerpt sources are exactly `body.message` and
   `result.content or ""` at all 4 sites — no tool outputs, tokens, or headers
   persisted (tool loop/approval untouched; assistant text may indirectly quote
   tool output — inherent, recorded in the design). New log lines carry only
   exception text, never page content/title; `async_store`'s success log uses
   `sl(user_id)` (manager.py:303). Redis embedding cache stores vectors keyed
   by `sha256(text)` — no plaintext, no key material. Test files contain no
   secrets (sentinels only).
4. **Resource abuse:** caps enforced pre-store via `_excerpt`
   (agent_routes.py:163-165, applied at 196-199 — title 100 / user 600 /
   response 1400 with markers; page ≤ ~2.1 KB + embedding). Exactly one
   fire-and-forget task per successful turn per endpoint, unreachable without a
   full authenticated LLM turn (`require_auth` verified intact on all 4:
   agent_routes.py:326/462/629/801) — no client-controllable multiplier
   (session_id/metadata shape keys, not volume); skip-trivial guard at
   agent_routes.py:184-187. Read side bounded: fetch 8 → filter → render 5 →
   6000-char formatter cap. Growth has no hard row cap — decay-managed
   (unpinned, decay 0.001) with documented follow-ups (ADR-014); accepted.
5. **Embedder swap:** `_get_embedding` now uses `get_default_embedder`
   (manager.py:118-127) — keys flow from `get_settings()`
   (`EMBEDDING_API_KEY or OPENAI_API_KEY`, embeddings.py:373) straight into the
   provider constructor; never logged (the missing-key `ValueError` text
   contains no key material; init failure logs only the exception). No new
   secret handling, no ad-hoc `os.environ`. Cache keys are model+content-hash
   only.

- Verdict (Pass/Fail): **Pass** — PASS-WITH-NOTES. Musts: none. Shoulds: S1
  (inner-tag escape + page_type through `_clean`) to eng-executor, ideally
  before merge. Nits: `sl(exc)` on the two new log lines; generalized
  block-tag alternation if S1 lands.

## Fix round (post-gates, applied 2026-07-19 by coordinator)

- Security S1 (should-fix) — APPLIED: `_neutralize_inner_tags` escapes inner
  `format_for_llm` structure tags (memory/content/title/when/chapter/tags) AND
  the other named prompt blocks (generalized-alternation nit folded in);
  `page_type` now passes through `_clean` before attribute rendering. New test
  `test_s1_inner_structure_tags_neutralized`.
- Security nit (log forging) — APPLIED: `sl(str(exc))` on both new log lines
  (agent_routes store failure, base.py recall failure).
- Reviewer nit (brittle getsource) — APPLIED: needles tightened to the full
  `asyncio.create_task(<helper>(` call form for both background tasks.
- Reviewer nit (`llm.calls == 0` documentation-only) — kept as-is (documents
  the zero-completion contract; harmless).
- Reviewer nits accepted-as-designed: bare `create_task` (insights precedent,
  Architecture risk list), Redis-outage NULL-embedding posture (pre-existing
  `CachedEmbeddingProvider` behavior, proper fix belongs to embeddings.py),
  `format_for_llm` page_type attribute (formatter out of scope; render-side
  neutralized instead), clarification-needed turns stored (conscious choice:
  the clarifying exchange is real conversational memory).
- Post-fix verification: full unit tier **196 passed, 20 deselected**.
