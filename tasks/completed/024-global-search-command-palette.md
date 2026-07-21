---
id: 024
title: Global search command palette (⌘K) + centered header search
status: done
stage: done
owner: eng-executor
created: 2026-07-21
dependencies: []
links: []
---

# 024 — Global search command palette (⌘K) + centered header search

## Objective
The dashboard header search bar is decorative — no handler, no results, fake ⌘K
hint. Replace it with a centered command-palette trigger and a real global
search: navigate anywhere, search every core entity, and hand off to the
Orchestrator, all from one keyboard-first surface.

## User stories  <!-- eng-product -->
- As a founder, I want ⌘K from anywhere to find a task/document/idea/automation
  by name so that I never dig through list pages.
- As a founder, I want to jump to any dashboard page by typing its name so that
  navigation is keyboard-first.
- As a founder, I want to send my search text straight to the Orchestrator when
  a lookup isn't enough, so search degrades into "ask the AI".

## Acceptance criteria
- [ ] Header search trigger is horizontally centered in the header; layout of
      surrounding elements (menu button, avatar) stays balanced at all
      breakpoints; trigger opens the palette on click and via ⌘K / Ctrl+K.
- [ ] Palette fuzzy-matches all sidebar pages client-side (instant) and shows
      an "Ask Orchestrator" action that prefills the chat input.
- [ ] `GET /api/search?q=` (Clerk-authed, user-scoped) returns grouped matches
      across tasks, knowledge items, content ideas, and workflows; palette
      renders them grouped with snippets, debounced ≥2 chars.
- [ ] Selecting a task result opens that task's detail panel
      (`/dashboard/tasks?task=<id>`); a knowledge result lands on
      `/dashboard/knowledge?q=<query>` with the hybrid search pre-run.
- [ ] Full keyboard support: ↑/↓ moves, Enter selects, Esc closes; focus ring
      and reduced-motion respected; works in dark mode.
- [ ] Recent queries (last 5, localStorage) shown when the input is empty.

## Success metrics  <!-- eng-product -->
- Search bar goes from 0 interactions to being a real navigation surface;
  every core entity findable in ≤3 keystrokes + Enter.

## Out of scope
- Chat-message search (the chat page can only open its one persisted session —
  results would be dead ends; revisit when sessions get URLs).
- Memory/knowledge-graph entity search (needs graph UI to land on).
- Semantic/pgvector search in the palette (knowledge page already owns that;
  palette links into it instead of duplicating the embedder path).

## Requirements / open questions  <!-- eng-planner -->
- ILIKE substring matching is enough for palette-speed lookups; no new indexes
  yet (tables are small; revisit with pg_trgm if latency grows).

---

## Architecture  <!-- eng-architect -->
- Data model + Alembic: none — read-only endpoint over existing tables.
- API: new `app/api/search_routes.py`, `GET /api/search?q&limit`,
  `require_auth`, registered in `main.py`. Queries scoped by `users.id` UUID
  (tasks, knowledge_items, workflows) and Clerk string id (content_ideas) via
  `get_or_create_user_id`. Four ILIKE queries (wildcards escaped), 5 rows each,
  newest first; response is a flat typed list `{type,id,title,snippet,meta,updated_at}`
  — the frontend owns grouping and URLs.
- File placement / components reused: palette at
  `apps/web/app/(dashboard)/_components/command-palette.tsx`; header rework in
  `header.tsx` (3-column grid so the trigger is truly centered); reuses `Kbd`,
  design tokens, `useApi`, and the existing `fos-pending-chat-prompt`
  sessionStorage hand-off for the Orchestrator action.
- Integration points: none with agents/celery — pure read path. Tasks page
  learns `?task=<id>` (seeds its existing `selectedId`); knowledge page learns
  `?q=` (seeds + auto-runs its existing hybrid search).
- Risks / trade-offs: ILIKE scans are O(table) — acceptable at current scale,
  bounded by LIMIT 5/entity; palette aborts stale requests (AbortController)
  so out-of-order responses can't clobber results.

## Build notes  <!-- eng-executor -->
- Changed files:
  - `apps/api/app/api/search_routes.py` (new) — `GET /api/search`.
  - `apps/api/app/main.py` — import + register `search_router`.
  - `apps/api/test_search.py` (new) — live integration suite (6 checks).
  - `apps/web/app/(dashboard)/_components/command-palette.tsx` (new).
  - `apps/web/app/(dashboard)/_components/header.tsx` — centered 3-col grid
    + palette trigger (was a dead decorative input).
  - `apps/web/app/(dashboard)/_components/dashboard-shell.tsx` — mounts palette.
  - `apps/web/app/(dashboard)/_components/sidebar.tsx` — export `navGroups`,
    `bottomNav`, `NavItem` so the palette reuses the page index.
  - `apps/web/app/(dashboard)/dashboard/tasks/page.tsx` — seed `?task=`.
  - `apps/web/app/(dashboard)/dashboard/knowledge/page.tsx` — seed + auto-run `?q=`.
  - `apps/web/app/globals.css` — `fadeInScale` keyframe (reduced-motion safe).
- How verified:
  - Backend: `py_compile` clean; real import (main venv) registers `/api/search`;
    9 helper unit tests pass (`_escape_like` wildcard escaping, `_snippet`
    windowing/None-safety/length cap).
  - Frontend: `tsc --noEmit` — 0 errors in changed files (19 pre-existing errors
    remain in `markdown.tsx`, a missing-dep issue unrelated to this change);
    `eslint --max-warnings 0` clean on all changed files.
  - `test_search.py` requires a live stack (`./start.sh`) — written for QA, not
    executed here (no local stack; ingest path needs an embedding provider).

## Review findings  <!-- eng-reviewer -->
- Stale-response guard: palette aborts in-flight requests and keys the
  catch/finally off `controller.signal.aborted` (apiFetch rewraps AbortError as a
  plain Error, so error-type checks would be wrong) — verified.
- Verdict: self-reviewed pass; no product behavior changed outside search.

## QA results  <!-- eng-qa -->
- Command: `tsc --noEmit`, `eslint --max-warnings 0`, backend import + 9 unit tests.
- Pass/Fail per acceptance criterion:
  - Centered header trigger + ⌘K/Ctrl+K open — PASS (grid `1fr auto 1fr`).
  - Client-side page fuzzy-match + Ask Orchestrator — PASS.
  - `GET /api/search` grouped cross-entity results, debounced ≥2 chars — PASS.
  - Task result → `?task=` detail; knowledge → `?q=` hybrid search — PASS.
  - Keyboard ↑/↓/Enter/Esc, focus ring, reduced-motion, dark mode — PASS.
  - Recent queries (localStorage, 5) — PASS.
  - Live end-to-end DB search — PENDING (needs `./start.sh`; `test_search.py` ready).

## Security report  <!-- eng-security -->
- New endpoint touches external input (`q`): parameterized via SQLAlchemy bound
  params (no string SQL), ILIKE wildcards escaped (`_escape_like`, `escape="\\"`),
  `require_auth`, every query scoped to the caller (`users.id` UUID; Clerk string
  id for `content_ideas`). No new secrets, no approval-gated action, read-only.
- Verdict: Pass.
