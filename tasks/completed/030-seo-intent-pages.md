---
id: 030
title: SEO round two — intent-led landing pages, derived structured data, static home
status: done
stage: qa
owner: eng-executor
created: 2026-08-19
dependencies: [029]
links: [ADR-020, ADR-019, tasks/completed/029-public-marketing-site-seo.md]
---

# 030 — SEO round two: intent-led landing pages, derived structured data, static home

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective

Task 029 (ADR-019) built the technical SEO floor and it held. This closes the
gap it left: the site declared keywords it had no page for, and served its
most-crawled URL dynamically.

Note on the canonical origin: this task was scoped when `siteUrl` still
defaulted to `myfounder.vercel.app`, but a concurrent workstream had already
corrected it to `https://myfounderos.com` on `main` (along with `readme.md` and
`scripts/deploy-web.sh`). That fix is **not** part of this change — verified as
already correct rather than re-applied, and the duplicate local edit was dropped
when this branch was rebuilt off `origin/main`.

## User stories

- As a founder searching "Founder OS pricing", I want a page with real prices and
  limits so that I can qualify myself without a sales call.
- As a founder searching "Obsidian AI integration", I want a page that says what
  is read, what is written back, and how to connect it so that I know whether it
  fits before signing up.
- As a founder searching "Notion AI alternative", I want an honest comparison
  that says when Notion AI is the better choice so that I can trust the rest.
- As an answer engine, I want a machine-readable map of the site so that I can
  summarise it without hallucinating outcomes it never claimed.

## Acceptance criteria

- [x] Canonical origin is `https://myfounderos.com` in every canonical tag, OG
      URL, sitemap entry, `robots.txt` `Host` and `llms.txt` link — including
      the new URLs (verified, not changed; see the note under Objective).
- [x] `/pricing` exists, statically generated, with prices matching the
      `subscription_plans` seed, and `Product` + `AggregateOffer` + per-plan
      `Offer` structured data.
- [x] `/integrations` hub + one static page per adapter, each stating real
      adapter status and direction, with `HowTo` setup schema.
- [x] `/compare` hub + one static page per comparison, each carrying a
      "when the alternative wins" section and `Article` schema declaring the
      page vendor-authored.
- [x] `/` renders as `○` (static) in the build table.
- [x] `/llms.txt` served, generated from the same modules the pages render from.
- [x] Search Console / Bing verification is env-gated and emits no tag when unset.
- [x] `sitemap.xml` lists all 20 public URLs with per-page `lastModified`.
- [x] Exactly one `FAQPage` block per URL; every JSON-LD block parses.
- [x] `turbo lint`, `turbo check-types` and `turbo build` pass with no warnings.

## Success metrics

- Search Console can be verified and the sitemap submitted (was blocked: there
  was no verification hook at all).
- Ten new indexable URLs covering the three intent clusters the site's own
  keyword lists already targeted.
- Home page TTFB drops from a server render to an edge-cached static response.

## Out of scope

- Blog / RSS / content engine — a separate ongoing commitment, not a page.
- Product screenshots and demo imagery — `/about` promises no screenshot shows a
  feature that does not exist, and none of the real UI is captured yet.
- `aggregateRating` / `review` markup — nothing has been measured; fabricating
  it is a Google manual action.
- Rewriting site-wide "free tier" CTA copy (see open question below).

## Requirements / open questions

- **Flagged, not resolved:** the `subscription_plans` seed describes the free
  plan as `'Free Trial'` / `'14-day trial with limited features'`, while the
  site says "free tier, no credit card". `/pricing` is written to the seed and
  carries the trial caveat as a note under the price; the site-wide CTA copy was
  left alone because changing the product's positioning is the founder's call,
  not a side effect of an SEO pass.

---

## Architecture  <!-- ADR-020 -->

- Data model + Alembic: none. `lib/pricing.ts` is a declared read-only mirror of
  the `subscription_plans` seed; no schema change.
- API: none. All new routes are static pages plus one `force-static` route
  handler (`app/llms.txt/route.ts`).
- File placement:
  - New data modules `apps/web/lib/{pricing,integrations,comparisons}.ts`.
  - New pages under `apps/web/app/(marketing)/{pricing,integrations,compare}/`,
    reusing the existing `PageHero`, `Section`, `Prose`, `CtaBand`, `CtaLink`,
    `FaqSection` and `JsonLd` primitives — no new layout components.
  - New schema builders (`personSchema`, `itemListSchema`, `howToSchema`) added
    to `lib/site.ts` alongside the existing ones, keeping one structured-data
    module.
- Integration points: `proxy.ts` gains the signed-in `/` redirect;
  `isProtectedPage` unchanged.
- Risks / trade-offs: two content-to-code couplings that rot silently —
  `lib/pricing.ts` ↔ the seed, and `lib/integrations.ts` `status` ↔ adapter
  `capabilities`. Both are commented at the top of their file.

## Build notes  <!-- eng-executor -->

Changed files:

- New: `lib/pricing.ts`, `lib/integrations.ts`, `lib/comparisons.ts`,
  `app/llms.txt/route.ts`, `app/(marketing)/pricing/page.tsx`,
  `app/(marketing)/integrations/page.tsx`,
  `app/(marketing)/integrations/[slug]/page.tsx`,
  `app/(marketing)/compare/page.tsx`, `app/(marketing)/compare/[slug]/page.tsx`
- Edited: `lib/site.ts` (nav, footer, `founderName`, `personSchema`,
  `itemListSchema`, `howToSchema`, `AggregateOffer`), `lib/faq.ts`,
  `app/layout.tsx` (verification, `max-snippet`), `app/sitemap.ts`,
  `app/robots.ts`, `app/manifest.ts`, `app/not-found.tsx`, `proxy.ts`,
  `app/(marketing)/{page,about,faq,features,case-studies}/…`,
  `app/(marketing)/_components/site-footer.tsx`, `.env.local.example`
  (verification vars only)
- Docs: ADR-020, `docs/architecture.md`, `docs/roadmap.md`, `CLAUDE.md` §3
- Not touched: `scripts/deploy-web.sh`, `readme.md` and the `siteUrl` default —
  already correct on `main`.

How verified: see QA below.

## Review findings  <!-- eng-reviewer -->

- [med] `app/layout.tsx` — an `alternates.canonical` added to root metadata is
  inherited by every route, tagging the 404 and auth pages as duplicates of `/`.
  → removed; canonicals come only from `pageMetadata()`. Comment left in place
  so it is not re-added.
- [med] `integrations/[slug]` — the metadata title suffix said "two-way company
  state sync" for every adapter, which is false for read-only Google Calendar.
  → derived from `integration.writes.length`.
- [low] `app/manifest.ts` — a `192x192` icon entry pointed at `logo-mark.png`,
  which is 175×256. A declared size that does not match the file makes Chrome
  pick the wrong icon. → entry removed; remaining `sizes` verified with `sips`.
  A real maskable variant with safe-zone padding is still outstanding (TODO in
  file).
- Verdict: pass.

## QA results  <!-- eng-qa -->

Command: `npx turbo lint check-types build --filter=web --force` — 3/3 tasks
successful, no errors, no warnings (`eslint --max-warnings 0`).

Per criterion, asserted against the prerendered output in `.next/server/app/`:

- Canonicals: `pricing`, `integrations`, `compare`, `integrations/obsidian`,
  `compare/founder-os-vs-chatgpt` and `/` all emit
  `rel="canonical" href="https://myfounderos.com/…"`. Pass.
- `robots.txt`: `Host: https://myfounderos.com`,
  `Sitemap: https://myfounderos.com/sitemap.xml`, private paths disallowed for
  both the `*` rule and the named answer-engine rule. Pass.
- `sitemap.xml`: 20 `<loc>` entries, all on the custom domain, including the 6
  new static pages and the 6 new detail pages. Pass.
- JSON-LD: every block on 9 sampled pages parses as JSON; type sets are as
  designed (`Product` + `FAQPage` on `/pricing`, `ItemList` on the three hubs,
  `Person` + `AboutPage` on `/about`, `HowTo` on integration pages, `Article` on
  comparisons). No page carries more than one `FAQPage`. Pass.
- Render mode: build table shows `┌ ○ /` (was `ƒ /`). All 10 new URLs are `○` or
  `●`. Pass.
- `/llms.txt`: served, content derived from the data modules, prices and
  integration statuses rendered correctly. Pass.
- Verification tags: unset locally → no `google-site-verification` meta emitted.
  Pass.

Not covered: no automated regression guards these — the web app has no test
runner. The couplings in Architecture ↑ are enforced by comment only.

## Security report  <!-- eng-security -->

Change touches `proxy.ts`, so a review was required.

- `isProtectedPage` / `isApiRoute` / `isPublicApiRoute` matchers: unchanged. The
  auth gate is byte-identical.
- Added branch runs **only** when `pathname === "/"`, a route that is public to
  anonymous visitors before and after. It redirects signed-in users to
  `/dashboard` — the same behaviour previously in the page component, moved one
  layer out. No route became reachable that was not reachable before.
- `await auth.protect()` now `return`s immediately, so the new branch cannot run
  for a protected route. Verified by inspection: the branch is unreachable for
  any path other than `/`.
- No secrets added. The two new env vars are public verification tokens
  (`NEXT_PUBLIC_*`), designed to be served in a meta tag, and are absent-safe.
- `llms.txt` renders only module constants — no user input, no request data, no
  auth state.
- Verdict: Pass.
