---
id: 022
title: Dark mode toggle + chat markdown + onboarding validation + security/overflow sweep
status: done
stage: done
owner: eng-qa
created: 2026-07-21
dependencies: [021]
links:
  - docs/decisions.md (ADR-016)
  - founder-os/apps/web/brand.md
---

# 022 — Dark mode toggle + chat markdown + onboarding validation + security/overflow sweep

## Objective

Founder request (2026-07-21): add a dark mode toggle; make agent chat render
markdown instead of literal `**`; stop onboarding from showing
`[object Object]` on huge numeric input; verify the site against SQL
injection/XSS and text-overflow issues.

## What shipped

- **Dark mode** — `.dark` re-values the `@theme` color tokens in
  `app/globals.css` (see brand.md for the palette). `ThemeProvider` +
  pre-paint inline script (no flash), `ThemeToggle` in sidebar footer +
  landing nav, theme-aware Clerk appearance via `AppClerkProvider`.
- **Chat markdown** — kit `Markdown` component (react-markdown + remark-gfm,
  token-styled, React-tree output — no raw HTML). Assistant messages render
  through it; user/error messages stay plain with `break-words`.
- **`[object Object]` fix** — `apiErrorMessage()` in `lib/api.ts` flattens
  FastAPI string/array/object `detail` shapes to readable text; adopted in
  `apiFetch`, `apiRawFetch`, `chat-store`, `use-streaming-fetch`. Onboarding
  numeric inputs clamped (finite-guard) with `max` attrs; backend
  `FounderProfileCreate` gained `ge/le` bounds so out-of-range ints are a
  clean 422, not a Postgres INTEGER overflow 500.
- **Security sweep** — all raw-SQL `text()`/f-string sites audited
  (user_store, vector_store, memory manager, crawler routes): interpolations
  are server-controlled constants (whitelisted `ASC/DESC`, static clause
  fragments); every user value goes through bound parameters → no SQL
  injection. Only `dangerouslySetInnerHTML` is the constant theme script.
  react-markdown does not render raw HTML → no XSS from model output.
- **Overflow** — `break-words` on chat bubbles, markdown container, and
  onboarding error text; `maxLength` on business name to match the API cap.

## Acceptance criteria

- [x] Toggle switches light/dark instantly, persists across reloads, no
      flash on load (inline pre-paint script), respects OS preference on
      first visit.
- [x] Zero `dark:` variants introduced — grep for banned classes still 0 hits.
- [x] `**bold**`, lists, code blocks, tables render styled in assistant chat.
- [x] `pytest tests/unit` — 206 passed (10 new bounds tests).
- [x] `turbo lint check-types build --filter=web` — 5/5 successful.
- [x] SQLi/XSS audit recorded above — no injectable site found.

## QA — 2026-07-21

All automated gates above run and green in the worktree at HEAD. Visual
dark-mode eyeball on the Clerk-gated dashboard recommended on the deploy.
