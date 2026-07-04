---
id: 010
title: Knowledge tab — File/PDF upload option in the dashboard
status: done
stage: qa
owner: eng-qa
created: 2026-06-12
dependencies: [009]
links: [tasks/completed/009-pdf-rag-goal-autofill.md]
---

# 010 — Knowledge tab File/PDF upload

## Objective
Add a "File / PDF" ingestion option to the dashboard Knowledge tab alongside the
existing Text and URL modes, wired to `/api/knowledge/ingest/file` (made fully
functional for PDFs in task 009 — including the blank-only goal auto-fill).

## Build notes  <!-- eng-executor -->
- **`lib/api.ts`** — `apiFetch` hardcoded `Content-Type: application/json`, which
  breaks multipart uploads (browser must set the boundary). Now skipped when the
  body is `FormData`; JSON behavior unchanged for all existing calls.
- **`knowledge/page.tsx`** —
  - `ingestMode` extended to `"text" | "url" | "file"`; third toggle button
    ("File / PDF", `FileUp` icon) styled identically to Text/URL.
  - Dashed-border file picker (hidden input + label) showing the chosen file name
    and size; accepts `.pdf,.txt,.md,.csv,.json` (matches the backend allowlist,
    10 MB max noted in the placeholder).
  - `handleIngest` file branch: `FormData` (file/title/category) POST with a 120s
    timeout (PDF extract + embed); success message shows filename + chunks; file
    input cleared via ref; list refreshes.
  - Submit-disabled logic is mode-aware (file mode requires a chosen file).
  - Courtesy cleanup: removed 3 pre-existing unused icon imports from this file.

## QA results  <!-- eng-qa -->
- `npx turbo check-types --filter=web` → **passes**.
- `npx eslint knowledge/page.tsx lib/api.ts` → **0 problems** (repo-wide `lint`
  still fails on PRE-EXISTING warnings in other files — not introduced here).
- Backend endpoint already live-proven with real PDFs (task 009: extract → chunk →
  embed → searchable; goal auto-fill verified both ways).
- Proxy path: `/api/:path*` rewrite confirmed in next.config.js; a curl through
  the user's running dev server (port 3000) got Clerk's 307 → /sign-in, proving the
  route is auth-guarded as designed. **Remaining manual step (needs a Clerk
  login, which only the founder has): open the Knowledge tab in the browser,
  pick the File/PDF mode, upload a PDF, confirm the chunks message.** The dev
  server hot-reloads, so the new UI is already live at :3000.

## Review/Security
- No new endpoints; upload goes through the existing authenticated route. The
  Content-Type change only affects FormData bodies. **Pass.**

## Status: DONE (one founder-side browser click-through pending, noted above).
