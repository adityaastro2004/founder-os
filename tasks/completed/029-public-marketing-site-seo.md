---
id: 029
title: Public marketing site + full SEO layer
status: done
stage: qa
owner: eng-executor
created: 2026-08-17
dependencies: []
links: [docs/decisions.md#adr-019, apps/web/brand.md]
---

# 029 — Public marketing site + full SEO layer

## Objective
Turn the single-hero landing page into a real, indexable multi-page marketing
site: unique metadata per page, structured data, sitemap/robots, social share
card, legal + about + contact + FAQ + case-study pages, a custom 404, and
mobile-first conversion surfaces.

## User stories
- As a founder who found us on Google, I want the page I land on to answer my
  question and offer one obvious next step, so that I don't bounce.
- As a search crawler, I want one canonical URL per topic with a unique title,
  description and structured data, so that the pages can be indexed and ranked.
- As someone sharing the link in Slack, I want a proper preview card rather than
  a bare URL.
- As a visitor on a phone, I want a call to action always within reach and no
  horizontal scrolling.
- As a prospective customer, I want to know who runs this, how my data is
  handled, and how fast I get a reply before I sign up.

## Acceptance criteria
- [x] Custom 404 page, served with a real HTTP 404, with links back into the site
- [x] Unique `<title>` and meta description on every public page
- [x] Primary CTA above the fold on the home page
- [x] Canonical URL on every page
- [x] Internal links: header nav, footer link map, in-content links, related pages
- [x] Social share image (Open Graph + Twitter `summary_large_image`)
- [x] Thank-you page after contact submission (`noindex`, GA conversion goal)
- [x] Breadcrumbs on every inner page + `BreadcrumbList` schema
- [x] Case studies — 1 index + 3 per-scenario URLs, labelled illustrative
- [x] Alt text policy applied to images (decorative logo `alt=""` beside its text
      label; OG image carries a per-page `alt`)
- [x] FAQ section on home + full `/faq` page with `FAQPage` schema (one block per URL)
- [x] Local schema (`ProfessionalService` + `Organization` with postal address,
      area served and opening hours)
- [x] Response-time promise stated on contact, FAQ, footer and CTA band
- [x] Privacy policy page
- [x] Sticky mobile CTA (phone widths only, footer not overlapped)
- [x] Google Analytics 4, env-gated
- [x] `robots.txt` (authenticated areas disallowed, sitemap referenced)
- [x] Favicon set — `favicon.ico` + `icon.png` 512 + `apple-icon.png` 180 + webmanifest
- [x] Mobile responsive throughout
- [x] ~600-word SEO write-up about the tool on the home page (measured: 634)
- [x] About us, terms & conditions, contact us pages
- [x] `sitemap.xml` covering every indexable URL
- [x] Multi-page architecture (MPA — one server-rendered route per topic)

## Success metrics
- Google Search Console: 11 URLs submitted and indexable, zero soft-404s from
  unknown paths (previously every unknown path 307'd to `/sign-in`).
- Rich-result eligibility for FAQ and breadcrumbs on the relevant pages.
- `/thank-you` reachable as a GA4 conversion event.

## Out of scope
- Pricing page — no public price points to publish yet.
- Blog / content engine.
- A server-side contact inbox (see build notes: the form composes a mail draft).
- Counsel review of the legal pages.

## Requirements / open questions
- Canonical domain: `https://myfounder.vercel.app` (from `readme.md`), overridable
  via `NEXT_PUBLIC_SITE_URL`.
- Contact: `adityaastro.id2004@gmail.com`, New Delhi, India, 24-hour reply on
  business days — confirmed by the founder.
- Case studies: no nameable customers, so authored composites, labelled as such,
  with no invented metrics — confirmed by the founder.

---

## Architecture
See **ADR-019** for the full rationale.

- Data model + Alembic: none — no backend change.
- API: none. `/api/*` remains deny-by-default in `proxy.ts`.
- File placement:
  - `apps/web/app/(marketing)/` — layout + 9 page routes + `_components/`
    (`site-header`, `site-footer`, `sticky-mobile-cta`, `breadcrumbs`,
    `faq-section`, `page-hero`, `cta-band`, `cta-link`, `section`)
  - `apps/web/app/not-found.tsx`, `robots.ts`, `sitemap.ts`, `manifest.ts`,
    `opengraph-image.tsx`, `twitter-image.tsx`
  - `apps/web/app/_components/` — `json-ld.tsx`, `google-analytics.tsx`
  - `apps/web/lib/` — `site.ts` (metadata + schema factory), `og.tsx`,
    `faq.ts`, `case-studies.ts`
  - `apps/web/app/page.tsx` deleted (moved into the route group)
- Integration points: Clerk proxy matcher; ADR-015 design tokens; ADR-012
  analytics posture.
- Risks / trade-offs:
  - `proxy.ts` page protection is now an explicit allowlist — **a new
    authenticated page must be added to `isProtectedPage`**.
  - Legal pages are factual claims about sub-processors; they go stale when
    infrastructure changes.
  - Copy asserts shipping status (Obsidian shipped, Notion in progress).

## Build notes
- Changed files: 25 added, 4 modified (`app/layout.tsx`, `proxy.ts`,
  `.env.local.example`, `app/page.tsx` deleted).
- New env vars, both optional: `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_GA_ID`.
- Contact form has no server inbox: it composes a pre-filled draft in the
  visitor's own mail client and then routes to `/thank-you`, which is honest and
  keeps the visitor a copy. Swapping in a server action later requires no change
  to the fields or the redirect. Backlog candidate.
- Two defects found and fixed during verification:
  1. No `og:image` was emitted — a page exporting its own `openGraph` replaces
     the root layout's, dropping the file-based image. Fixed by referencing
     `/opengraph-image` explicitly in `pageMetadata()`.
  2. Unknown URLs returned `307 → /sign-in` instead of `404`, because the proxy
     was deny-by-default over pages.

## Review findings
- [med] `proxy.ts` — inverting page protection could expose a future
  authenticated page → mitigated with an explicit ⚠️ comment on the matcher and
  a note in ADR-019. API surface unchanged (still deny-by-default).
- [low] duplicate `<meta name="robots">` on the 404 (Next.js emits its own) →
  removed the redundant `robots` key from the not-found metadata.
- Verdict: pass.

## QA results
- `npx turbo check-types --filter=web` → 2 successful, 2 total
- `npx turbo lint --filter=web` → 2 successful, 2 total (`--max-warnings 0`)
- `npx turbo build --filter=web` → compiled successfully; 23/23 static pages;
  routes present: 8 marketing + 3 SSG case studies + `robots.txt` +
  `sitemap.xml` + `manifest.webmanifest` + `opengraph-image` + `twitter-image`
- `next start -p 3100` + curl, per route:
  - `200` for `/`, `/about`, `/features`, `/faq`, `/case-studies`,
    `/case-studies/solo-saas-founder`, `/contact`, `/thank-you`, `/privacy`,
    `/terms`, `/robots.txt`, `/sitemap.xml`, `/manifest.webmanifest`,
    `/opengraph-image`
  - `404` for `/this-does-not-exist` (was `307` before the proxy fix)
  - `307` for `/dashboard` (still protected)
- Head tags: 10/10 pages have a distinct `<title>` and description; canonical on
  all; `noindex, follow` on `/thank-you`; `noindex` + unique title on the 404.
- Structured data present per page: `Organization`, `WebSite`,
  `SoftwareApplication`, `ProfessionalService` site-wide; `FAQPage` on `/faq`
  only; `BreadcrumbList` on every inner page; `Article` on each case study;
  `ContactPage` on `/contact`.
- OG image: `status=200 type=image/png bytes=65426`, 1200×630, per-page `alt`.
- `sitemap.xml`: 11 `<loc>` entries, 1965 bytes, `application/xml`.
- Home SEO section word count: **634**.
- Not verified: rendering on real devices and Lighthouse/PSI scores (needs a
  browser); Google rich-results validation (needs the live domain).

## Security report
- `proxy.ts` — page protection moved from deny-by-default to an explicit
  allowlist (`/dashboard(.*)`, `/onboarding(.*)`). Behaviourally identical for
  every route that exists today; `/dashboard` still 307s anonymously (verified).
  `/api/*` remains deny-by-default with only `/api/webhooks(.*)` public, and the
  FastAPI backend still enforces Clerk JWT independently.
- `JsonLd` uses `dangerouslySetInnerHTML` over `JSON.stringify` of
  developer-authored constants only — no user input — and escapes `<` to
  `<` so a string cannot terminate the script tag.
- GA4 injects nothing without `NEXT_PUBLIC_GA_ID`; the inline `gtag` config
  interpolates only that env value.
- No secrets, no auth logic, no approval-gate code touched.
- Verdict: Pass.
