---
id: 031
title: CI guard for the marketing ↔ backend content couplings
status: backlog
stage: product
owner: eng-product
created: 2026-08-19
dependencies: [030]
links: [ADR-020, tasks/completed/030-seo-intent-pages.md]
---

# 031 — CI guard for the marketing ↔ backend content couplings

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective

Task 030 introduced two facts that exist in two places and are kept in step by a
code comment. Comments do not fail builds. Make the drift loud.

## Why this is worth a task

Both couplings fail in ways that are expensive and silent:

- `apps/web/lib/pricing.ts` mirrors the `subscription_plans` seed in
  `apps/api/schema.sql`. `/pricing` publishes those numbers as schema.org
  `Offer` markup. A price that Stripe checkout does not charge is a Google
  **manual action**, not a cosmetic bug, and nothing currently notices.
- `apps/web/lib/integrations.ts` `status` and `writes` mirror the adapter
  `capabilities` flags in `apps/api/app/integrations/*/adapter.py`. The pages
  render "two-way sync" or "read-only" from that field, and `/about` promises
  the site never describes a feature that does not exist. Shipping the Notion
  adapter without flipping `status` breaks that promise quietly.

## User stories

- As the founder, I want CI to fail when the published price stops matching what
  the product charges, so a stale marketing page cannot become a compliance
  problem.
- As an engineer shipping an adapter, I want to be told at PR time that the
  integrations page still says "in progress".

## Acceptance criteria

- [ ] A check parses the `subscription_plans` INSERT in `apps/api/schema.sql` and
      asserts every plan's `price_monthly_usd` / `price_yearly_usd` matches
      `apps/web/lib/pricing.ts`.
- [ ] A check parses `capabilities = ...` from each adapter and asserts
      `lib/integrations.ts` agrees on whether the adapter can write (`SYNC`).
- [ ] Both run in `ci.yml` and fail the build on mismatch, with an error naming
      both files and the specific field.
- [ ] The check is one script — a new failure mode should not need a new job.

## Out of scope

- Serving pricing from the API at request time. `/pricing` must stay statically
  generated and must not depend on the backend being reachable (ADR-020 §1).
- Guarding prose. Only the machine-checkable fields — prices, limits, capability
  flags — are in scope.

## Requirements / open questions

- Where does it live? Options: a pytest under `apps/api/tests/unit/` that reads
  across into `apps/web` (fits the existing runner, awkward directionally), or a
  standalone Node/Python script invoked from `ci.yml` (cleaner boundary, one
  more thing to run locally). Lean toward the latter.
- Stripe price IDs live in env, not in the repo, so the guard can only compare
  the seed to the marketing module — it cannot verify what Stripe actually
  charges. Worth saying so in the script's docstring, so nobody reads a green
  check as proof the checkout is right.

## Self-improvement note  <!-- CLAUDE.md §9 -->

This is the second SEO/marketing pass (ADR-019, ADR-020). A third would justify
a `skills/seo_audit.md` covering the recurring checklist: canonical origin
correctness, one `FAQPage` per URL, render mode of `/`, sitemap completeness,
JSON-LD parse + type assertions against `.next/server/app/`. Not built yet —
per the rule, on the third occurrence.
