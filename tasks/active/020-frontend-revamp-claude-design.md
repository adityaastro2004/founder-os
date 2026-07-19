---
id: 020
title: Frontend revamp — Claude-style design system
status: in-progress
stage: executor
owner: eng-executor
created: 2026-07-19
dependencies: []
links:
  - docs/superpowers/specs/2026-07-19-frontend-revamp-claude-design.md
  - docs/superpowers/plans/2026-07-19-frontend-revamp-claude-design.md
---

# 020 — Frontend revamp — Claude-style design system

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
- [ ] `npm run lint`, `npm run check-types`, and `npm run build` pass in `apps/web`.
- [ ] `grep -rn "bg-white\|text-gray-\|bg-gray-\|bg-neutral-\|dark:\|var(--color-" app lib`
      returns zero hits outside `globals.css` token definitions.
- [ ] Every route renders on the new system (visual pass recorded); chat
      streaming, sidebar pulse dots, and Clerk flows behave unchanged.
- [ ] No diffs outside `founder-os/apps/web/` (plus docs/ and tasks/).
- [ ] `brand.md` exists in `apps/web/` as the brand source of truth.

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
