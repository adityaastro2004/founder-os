# Frontend revamp — Claude-style design system

- **Date**: 2026-07-19
- **Status**: Approved (design approved by founder in-session; scope decisions below)
- **Scope**: `founder-os/apps/web` only. Purely presentational — no behavior, data-fetching, routing, or backend changes.

## Decisions (founder-approved)

1. **Aesthetic**: Full Claude/Anthropic look — warm ivory paper, terracotta accent, serif display headings, warm grays.
2. **Surface area**: Whole app — landing, sign-in/sign-up, onboarding, dashboard shell, and all 12 dashboard pages.
3. **Theme**: Light only. The existing `.dark` token block and stray `dark:` utilities are removed (nothing toggles dark mode today).
4. **Depth**: Design system + full page sweep, including light sidebar regrouping. No pages added or removed; no IA restructure beyond nav grouping.

## 1. Design tokens

Defined in `app/globals.css` via Tailwind 4 `@theme` so real utilities are generated (e.g. `bg-surface`, `text-ink-secondary`, `border-line`). Pages stop using `bg-[var(--color-…)]` arbitrary values and hardcoded `bg-white`/`text-gray-*`/`bg-neutral-*` (53 `bg-white` instances exist today — all die in the sweep).

| Token | Value | Use |
|---|---|---|
| `--color-paper` | `#FAF9F5` | App/page background (ivory paper) — utility `bg-paper` |
| `--color-surface` | `#FFFFFF` | Cards, inputs, popovers |
| `--color-surface-muted` | `#F0EEE6` | Hover states, sidebar, code/quote blocks, skeletons |
| `--color-line` | `#E8E6DD` | Default hairline borders |
| `--color-line-subtle` | `#F0EEE6` | Subtle dividers |
| `--color-ink` | `#1F1E1D` | Primary text |
| `--color-ink-secondary` | `#63605B` | Secondary text |
| `--color-ink-muted` | `#A6A29A` | Muted text, placeholder, icons at rest |
| `--color-accent` | `#C96442` | Terracotta: primary buttons, active nav, links, focus rings |
| `--color-accent-hover` | `#B04E2F` | Accent hover |
| `--color-accent-soft` | `#F1E5DE` | Accent-tinted backgrounds (badges, selected chips) |
| `--color-success` | `#4C8055` | Muted warm green |
| `--color-warning` | `#B9741C` | Warm amber |
| `--color-danger` | `#BF4232` | Warm red |

- **Radius**: 12px cards / 8px controls (`--radius-card`, `--radius-control`).
- **Depth**: hairline borders carry structure; one soft shadow level reserved for popovers/dialogs. No card shadows.
- **Focus**: 2px accent-colored focus-visible ring (replaces gray ring).
- **Selection**: accent-soft background, ink text (replaces inverted black).

## 2. Typography

- **Display serif**: Source Serif 4 via `next/font/google`, exposed as `--font-serif`. Used for page titles (`PageHeader`), section headings, landing hero, auth/onboarding headings, and empty-state titles. Numbers and stat values stay sans.
- **Body/UI**: Geist Sans (existing local font) everywhere else.
- **Mono**: Geist Mono (existing) for code/kbd.
- Sentence case everywhere. No decorative emojis. The existing uppercase-tracked stat labels become sentence-case small labels.

## 3. Shared UI kit — `app/_components/ui/`

Small owned primitives, no new runtime dependencies (Source Serif 4 arrives through `next/font`; no shadcn, no framer-motion):

- `Button` — primary (terracotta), secondary (surface + hairline), ghost, danger; sm/md sizes; loading state.
- `Card` — surface + hairline + 12px radius; optional header/footer rows.
- `Input`, `Textarea`, `Select` — surface bg, hairline border, accent focus ring.
- `Badge` — status-colored (success/warning/danger/neutral/accent-soft).
- `PageHeader` — serif title + optional description + actions slot; used at the top of every dashboard page.
- `EmptyState` — icon, serif title, one human sentence, one action. Replaces every bare "No data" today.
- `Skeleton` — warm muted shimmer.
- `StatCard` — label + value + sub, on `Card`.
- `Dialog` — the one shadowed element; used where pages roll their own modals today.
- `Tabs`, `Kbd`, `Spinner`.

Rule: pages compose these primitives; one-off styles inside pages are allowed only where a primitive genuinely doesn't fit.

## 4. App shell

- **Sidebar** (`app/(dashboard)/_components/sidebar.tsx`): warm muted background (`#F0EEE6` family) distinct from the ivory content area; terracotta logo mark; serif "Founder OS" wordmark. Nav grouped with quiet small-caps section labels:
  - *(ungrouped, top)* Dashboard
  - **Work** — Chat, Agents, Tasks, Planner
  - **Knowledge** — Memory, Knowledge, Content ideas
  - **System** — Automations, Apps
  - *(bottom, pinned)* Billing, Settings
  - Active item: ivory/surface pill + ink text. The running-agent pulse dot behavior is preserved exactly (chat-store wiring untouched).
- **Header**: ivory blur (`bg`-tinted, not white), warm search field, ⌘K kbd kept, Clerk `UserButton` kept.
- **Content area** (`dashboard-shell.tsx`): page content wrapped in a `max-w-6xl` centered container with generous padding.

## 5. Page treatments (all presentational only)

- **Landing** (`app/page.tsx`): serif hero on paper, terracotta primary CTA, quiet secondary CTA, honest human copy, restrained feature row. No gradients, no glow, no emoji.
- **Auth** (`(auth)/layout.tsx` + Clerk pages): paper background; Clerk styled via the `appearance` prop (variables: `colorPrimary` terracotta, radius, font) — the fragile `.cl-internal-b3fm6y` override in globals.css is deleted.
- **Onboarding**: same paper treatment, serif headings, kit controls.
- **Dashboard home**: `PageHeader`, `StatCard` row, agent status list and activity feed on `Card`s with `Badge`s; skeletons via kit.
- **Chat**: closest to claude.ai — centered conversation column, user messages as warm muted chips, assistant messages on bare paper (no bubble), rounded composer card with terracotta send button. Streaming/SSE logic untouched.
- **Agents, Tasks, Planner, Memory, Knowledge, Content ideas, Workflows (+`[id]`), Apps, Billing, Settings**: swept onto the kit — `PageHeader`, cards, badges, empty states, skeletons; remove per-page hardcoded palettes (e.g. `bg-neutral-*` agent color map in tasks becomes token-based).

## 6. Mechanics & guardrails

- `founder-os/apps/web/brand.md` written as the brand source of truth (palette, typography, voice, do/don't) for all future frontend work.
- Tokens live in `@theme`; the old `:root`/`.dark` blocks and Clerk internal-class hacks are removed from `globals.css`.
- **No new npm dependencies.**
- **Branch note**: the sidebar/root layout currently depend on uncommitted `feat/background-chat-runs` work (ChatProvider, chat-store). Implementation builds on top of that branch (or after it merges) — not off `origin/main`.
- Task file: `tasks/completed/021-frontend-revamp-claude-design.md` (was 020 at planning time; renumbered — 020 was claimed on main by chat semantic memory).

## 7. Verification / acceptance

- `turbo lint` (max-warnings 0) and `turbo check-types` pass.
- `grep -rn "bg-white\|text-gray\|bg-neutral" app` returns zero hits in page/component code.
- Visual pass: every route renders on the new system (screenshots recorded); no behavioral regressions in chat streaming, sidebar pulse dots, Clerk auth flows.
- No diffs outside `founder-os/apps/web/` (plus task/docs files).

## Out of scope

- Dark mode, IA restructure, new pages, State-Engine dashboard redesign, backend/API changes, packages/ui extraction.
