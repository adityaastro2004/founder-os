# 2026-07-21 — LLM token-usage optimization (product agents)

**Trigger:** per-request token usage was in the thousands even for simple chats.
**Skill:** `skills/optimize.md` (measure → bottleneck → one change at a time → re-measure).

## Baseline (fixed tokens re-sent on EVERY round of the agentic loop; ≈4 chars/tok)

| Agent | Prompt tok | Tool-schema tok | Fixed/round |
|---|---|---|---|
| planner | 2,641 | 2,295 | ~5,100 |
| content | 1,216 | 835 | ~2,200 |
| orchestrator | 2,750 (HEAD) | 707 | ~3,600 |
| research / support | 655 / 447 | 845 / 420 | ~1,700 / ~1,000 |

Plus per request: **uncapped** `<working_memory>`/`<shared_memory>` blocks that
duplicated the same blobs (hooks copied shared→working, both render in the same
prompt — up to ~5k tok); tool results appended **untruncated** and re-billed every
round; two mandatory-but-redundant tool rounds (`get_user_profile`,
`recall_last_orchestration` — both already injected into the system prompt);
orchestrator's `<available_agents>` duplicating its own specialist table; the
prompt/tool table advertising unregistered `ops`/`product` agents (failed
delegations → wasted retry rounds); no Anthropic prompt caching.

## Changes (all in `founder-os/apps/api/app/agents/`)

1. **execution.py** — clip tool results to 8,000 chars before they join the
   message list (`_clip_tool_result`); full output still logged/streamed.
2. **memory.py** — shared `_render_memory_block` renderer with a 1,500-char
   per-key cap for working + shared memory.
3. **agents.py / orchestrator.py** — removed all shared→working copy hooks
   (pure duplication; nothing read those keys programmatically).
4. **agents.py** — planner prompt 10,567 → 3,742 chars, all functional rules
   kept; weekly-plan output template scoped to weekly plans only (was forced on
   every reply). Delegation section dropped (base injects `<delegation_instructions>`).
5. **content_prompts.py** — master prompt 4,865 → 2,583 chars, all rules kept.
6. **orchestrator.py / base.py** — profile + last-orchestration described as
   already-injected (kills 2 redundant tool rounds/request); phantom `ops`/
   `product` removed from the specialist table (their duties mapped to
   research/content); `inject_delegation_context = False` skips the duplicate
   `<available_agents>` block.
7. **mcp_tools.py / builtin_tools.py** — `gcal_smart_delete` schema 1,624 → ~1,100
   chars; `delegate_task` description trimmed + phantom agents removed.
8. **llm.py** — Anthropic `cache_control: ephemeral` on system + last tool:
   rounds 2+ and follow-up turns within TTL re-read the prefix at ~10% input cost.
   (Groq/Gemini cache implicitly — no change needed.)

## After

| Agent | Prompt tok | Fixed/round | Δ fixed/round |
|---|---|---|---|
| planner | 935 | ~3,290 | −36% |
| content | 645 | ~1,660 | −26% |
| orchestrator | 809 | ~1,660 | −54% vs HEAD |

Variable-cost wins are bigger: memory-block duplication (−up to ~5k tok/request),
clipped tool results (bounds the former unbounded worst case), −2 LLM rounds per
orchestrator request, −1 redundant profile round for planner, no failed
`ops`/`product` delegation retries. Output tokens: planner no longer emits the
5-section plan template for one-line calendar ops.

## Verification

- `python -m pytest test_content_agent.py test_agent_prompts.py` → **27 passed**
  (2 assertions updated from decorative headers to functional anchors).
- `test_agent_specialization.py`: 6 passed, 1 pre-existing fixture error —
  identical on stashed HEAD, unrelated.
- Full `import app.main` clean; helpers unit-checked inline.
- Live-server integration suites not run (no stack on :8000) — run
  `./start.sh && python test_system.py` before release.

## Operational notes

- Prompts are code-sourced but served from the DB — `sync_agents_to_db` runs in
  the API lifespan, so the trims take effect **on next API restart/deploy**.
- Users with an **active Agent-Evolution definition** (`AgentDefinition.status
  = "active"`) still get their old regenerated prompt — those are per-user and
  unaffected by the sync. Regenerate or deactivate to pick up the lean prompts.
