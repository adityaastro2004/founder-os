---
id: 009
title: PDF ingestion through RAG + blank-only primary_goal auto-fill
status: done
stage: qa
owner: eng-qa
created: 2026-06-11
dependencies: [008]
links: [docs/decisions.md]
---

# 009 — PDF → RAG + goal auto-fill

## Objective
Founders upload company PDFs into the knowledge base; the full RAG pipeline
(extract → chunk → embed → store → retrieved by agents) applies to them. If an
uploaded document clearly states the company's goal AND the founder profile's
`primary_goal` is **blank**, auto-fill it — **never overwrite a user-set value**.
Improves personalization/research/content quality (agents ground on company docs).

## Acceptance criteria
- [ ] A real PDF uploads via `/api/knowledge/ingest/file`, text-extracts, chunks,
      embeds, and is retrievable via search (live test).
- [ ] After PDF ingestion, if `FounderProfile.primary_goal` is blank → filled from
      the doc (LLM-inferred), with `primary_goal_description` noting the source.
- [ ] If `primary_goal` is already set → NEVER changed (live test proves it).
- [ ] Zero LLM cost when the goal is already filled (blank-check before any LLM call).
- [ ] Non-blocking: ingestion latency unaffected (BackgroundTasks).
- [ ] `pdfplumber` added to requirements.txt.

## Architecture (analyze finding)
PDF extraction is already coded in `knowledge_routes.ingest_file` (pdfplumber) but
the dependency was never installed/declared → 501. Fix = install + declare. The
auto-fill is a `BackgroundTasks` hook after successful file ingestion (own session,
swallow-exceptions pattern from onboarding), gated: profile exists AND
`primary_goal` blank → one LLM call → parse → fill + annotate source. Reuses
`_get_llm_generate`. No schema change.

## Build notes  <!-- eng-executor -->
- `pdfplumber==0.11.9` installed + declared in requirements.txt (extraction code in
  `ingest_file` existed but the dependency was never installed → PDFs 501'd).
- `_maybe_autofill_primary_goal(user_id, doc_title, text)` in knowledge_routes:
  blank-check FIRST (zero LLM cost when goal set) → one LLM call → strict-JSON parse
  → fill `primary_goal` (≤100 chars) + cite source in `primary_goal_description`
  (only if that's blank too). Empty/unclear goal from the doc → no fill (don't guess).
- Scheduled as a DETACHED `asyncio.create_task` (strong-ref set + done-callback),
  NOT FastAPI BackgroundTasks — see bug below. Takes the already-resolved users.id.

## Bug found & fixed during build (significant)
**FastAPI BackgroundTasks + yield-dependency ordering rolled back entire requests.**
First implementation used `background_tasks.add_task(...)`: FastAPI commits the
request session (get_db teardown) only AFTER background tasks finish; the task's
`get_or_create_user_id` INSERT lock-waited on the request's own uncommitted users
row → task cancelled (CancelledError bypasses `except Exception`, so no log) →
exception hit teardown → `get_db` rolled back the WHOLE ingestion silently (201
returned, zero rows stored). Confirmed live in pg_stat_activity: request sessions
`idle in transaction` + background INSERTs stuck on `Lock`. Fix: detached task +
pass the resolved id (no identity writes in background). **Lesson for all future
background work: never touch rows the request wrote, never use BackgroundTasks for
DB-writing work; use a detached task with its own session.**

## QA results  <!-- eng-qa -->  — all live against the real server + llama3.1:8b
- Real PDF (831-byte generated doc) uploads → pdfplumber extracts → 1 chunk embedded
  → **retrievable via semantic search** (top hit returns the PDF text). ✓
- Persistence: 2 knowledge_items rows in DB (the rollback bug is gone). ✓
- **Auto-fill when blank**: `primary_goal` = 'Reach $1M ARR by December 2027'
  (verbatim from the PDF) in ~20s; description cites the source document. ✓
- **Never overwrite**: user-set goal 'Reach $100k MRR (user-set)' unchanged after
  uploading a PDF stating a different goal. ✓
- Regressions: RAG 16/16 · evolution 22/22 · prompts 35/35 · specialization 13/13 ·
  e2e 50/50. Test users cleaned up.

## Review/Security  <!-- eng-reviewer / eng-security -->
- Auto-fill writes ONLY `primary_goal`/`primary_goal_description`, only when blank,
  only for the authenticated uploader's own profile (resolved users.id). ✓
- LLM sees only the user's own uploaded document text (first 6k chars). No new
  endpoints; no auth surface change. Best-effort task logs failures, never crashes
  ingestion. **Verdict: Pass.**

---
## Status: DONE — all acceptance criteria verified live.
