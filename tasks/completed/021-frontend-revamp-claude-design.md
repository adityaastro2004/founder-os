---
id: 021
title: Frontend revamp — Claude-style design system
status: done
stage: done
owner: eng-qa
created: 2026-07-19
dependencies: []
links:
  - docs/superpowers/specs/2026-07-19-frontend-revamp-claude-design.md
  - docs/superpowers/plans/2026-07-19-frontend-revamp-claude-design.md
---

# 021 — Frontend revamp — Claude-style design system

> Renumbered from 020 on 2026-07-21: task 020 and ADR-014 were claimed on main
> by chat semantic memory while this branch was in flight; this task is 021 and
> its ADR is ADR-015.

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective

Restyle the whole web app (landing, auth, onboarding, shell, all dashboard pages)
onto a warm Claude-style design system — ivory paper, terracotta accent, serif
display headings — with a small owned UI kit and zero behavior changes.

## User stories  <!-- eng-product -->
- As the founder, I want the dashboard to feel calm, warm, and human (not
  template-generic) so the product's craft matches its ambition.
- As a user, I want grouped navigation and consistent page structure so any
  screen is legible at a glance.

## Acceptance criteria
- [x] `npm run lint`, `npm run check-types`, and `npm run build` pass in `apps/web`.
- [x] `grep -rn "bg-white\|text-gray-\|bg-gray-\|bg-neutral-\|dark:\|var(--color-" app lib`
      returns zero hits outside `globals.css` token definitions (verified: 0 hits).
- [x] Visual pass recorded via headless-Chrome screenshots: landing + sign-in
      render fully on the new system (serif display confirmed after the
      `<html>` font-variable fix). Dashboard routes are Clerk-gated, so
      logged-in screens verified via build + shared shell/kit; founder eyeball
      recommended on the preview deploy. Chat/SSE, pulse dots, Clerk flows:
      code untouched (presentational-only diffs).
- [x] No diffs outside `founder-os/apps/web/` (plus docs/ and tasks/).
- [x] `brand.md` exists in `apps/web/` as the brand source of truth.

## Success metrics  <!-- eng-product -->
- Founder sign-off on the visual pass; zero behavioral regressions reported.

## Out of scope
- Dark mode, IA restructure, new pages, State-Engine dashboard redesign,
  backend/API changes, packages/ui extraction.

## Notes
- Approved decisions: full Claude look · whole app · light-only · design system
  + full sweep. See spec for tokens and page treatments.
- Base: origin/main @ 67810f9 (includes background-chat-runs and PR #19
  state-sources.tsx, which joins the Task 14 sweep).

## Review — eng-reviewer (2026-07-19)

Method: `git diff origin/main...HEAD` (44 files, +3268/−2352). Logic verified by
className-stripped logic digests of all 24 changed app files vs origin/main, plus
raw-diff reads of chat, agents, tasks, planner, apps, state-sources, onboarding,
sidebar, layouts, globals.css. Re-ran `npm run lint` (pass, 0 warnings) and
`npm run check-types` (pass) in `apps/web`.

Verified invariants:
- Behavior: hooks, fetch/API calls, SSE/EventSource, chat-store wiring, routing,
  and all disabled/loading gating are logic-equivalent to origin/main. Chat page
  streaming code untouched (indentation-only diffs); sidebar pulse-dot map and
  all 12 nav hrefs identical; onboarding `canNext`/`handleSubmit` byte-identical;
  every action button's disabled semantics preserved (moved to kit `Button
  loading` which sets `disabled`).
- Security: middleware untouched; ClerkProvider `appearance` is cosmetic
  variables only; `hasClerk` fallback and landing `auth()` redirect intact; no
  secrets; package.json/lockfile untouched (no new deps); fragile
  `.cl-internal-b3fm6y` override removed.
- Containment: zero diffs outside `founder-os/apps/web/`, `docs/`, `tasks/`.
- Acceptance greps re-verified: 0 banned utilities, 0 `var(--color-*)` outside
  globals.css, no dangling references to removed tokens (`--color-border`,
  `--color-text*`, `--radius`, …).

Findings:
- **should-fix** — `app/_components/ui/index.ts:2,9,10,12` — `CardHeader`,
  `Dialog`, `Tabs`, `Spinner` are exported but used nowhere. Spec §3 says Dialog
  replaces hand-rolled modals, yet `workflows/page.tsx:282` still rolls its own
  modal and `knowledge/page.tsx` rolls its own ingest tabs. Fix: adopt them
  (workflows modal → Dialog, knowledge ingest tabs → Tabs, Loader2 → Spinner) or
  remove from the kit until first use.
- **nit** — `app/_components/ui/dialog.tsx:24-32` — Escape + initial focus, but
  no focus trap, no focus-restore on close, no body scroll lock. Address when
  Dialog is first adopted.
- **nit** — `app/_components/ui/tabs.tsx:18,28` — `role="tablist"/"tab"` without
  arrow-key roving focus or `aria-controls`; add keyboard support or drop the
  ARIA tab roles.
- **nit** — `tasks/completed/021-frontend-revamp-claude-design.md:5-6` (this file) — still
  `stage: executor`; update stage/owner as it moves through review → QA.
- **nit** — `app/(dashboard)/_components/header.tsx` — search input `type`
  changed `text`→`search` (WebKit renders a native clear affordance). Cosmetic;
  the field is not wired to logic in either version.

Verdict: **Approve** (no blockers) — hand to eng-qa. Dead-export cleanup
(should-fix) can land as a small follow-up before task close.

## QA — 2026-07-21 (post-merge with origin/main)

Re-verified after merging origin/main (PostHog ADR-012, chat semantic memory
ADR-014/task 020, background chat runs PR #22) and resolving the
`layout.tsx` conflict (Clerk `appearance` theming + `PostHogIdentify` both kept):

- `turbo lint check-types --filter=web` — 4/4 tasks successful.
- `turbo build --filter=web` — successful.
- Acceptance grep (`bg-white|text-gray-|bg-gray-|bg-neutral-|dark:|var(--color-`
  in `app lib`, excluding `globals.css`) — **0 hits**.

**PASS.** Founder eyeball on the Vercel preview still recommended before
production deploy (visual pass on logged-in dashboard routes).
