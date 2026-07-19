# Frontend Revamp — Claude-Style Design System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the entire Founder OS web app (landing, auth, onboarding, shell, all 12 dashboard pages) onto a warm Claude-style design system — ivory paper, terracotta accent, serif display headings — with a small owned UI kit and zero behavior changes.

**Architecture:** Tailwind 4 `@theme` tokens in `globals.css` generate real utilities (`bg-paper`, `text-ink`, `border-line`…); a kit of owned primitives in `app/_components/ui/` replaces ad-hoc markup; every page is swept onto tokens + kit per a fixed class-mapping table. All data fetching, hooks, SSE, and routing are untouched.

**Tech Stack:** Next.js 16 App Router, Tailwind CSS 4, Geist (existing local), Source Serif 4 via `next/font/google`, lucide-react, clsx. **No new npm dependencies.**

**Spec:** `docs/superpowers/specs/2026-07-19-frontend-revamp-claude-design.md` (approved).

## Global Constraints

- No new npm dependencies (Source Serif 4 arrives through `next/font/google`).
- Light theme only; delete the `.dark` token block and all `dark:` utilities.
- Purely presentational: no changes to hooks, data fetching, SSE, routing, or any file outside `founder-os/apps/web/` (plus `docs/`, `tasks/`).
- Sentence case in all UI copy; no decorative emojis anywhere.
- No repo-wide test runner exists for web; verification per task = `npm run lint` + `npm run check-types` (from `founder-os/apps/web/`) + targeted grep + visual pass. Record this as manual verification (CLAUDE.md rule 1: explicit founder-requested revamp).
- Work happens in a worktree branched from `feat/background-chat-runs` HEAD (`cd6286c`) — the sidebar depends on chat-store committed there. Never commit the founder's uncommitted files from the main checkout.
- Commit style: `feat(web): …` / `chore(web): …`, ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Class-mapping table (used by every page-sweep task)

| Old | New |
|---|---|
| `bg-white`, `bg-[var(--color-surface)]` | `bg-surface` |
| `bg-[var(--color-surface-subtle)]` | hover/fills → `bg-surface-muted`; page bg → `bg-paper` |
| `bg-[var(--color-surface-muted)]` | `bg-surface-muted` |
| `border-[var(--color-border)]` | `border-line` |
| `border-[var(--color-border-subtle)]` | `border-line-subtle` |
| `text-[var(--color-text)]` | `text-ink` |
| `text-[var(--color-text-secondary)]` | `text-ink-secondary` |
| `text-[var(--color-text-muted)]` | `text-ink-muted` |
| `bg-[var(--color-accent)]` + fg | `Button` primary, or `bg-accent text-white` |
| `text-[var(--color-success/warning/danger)]` | `text-success` / `text-warning` / `text-danger` |
| `bg-neutral-*`, `text-gray-*`, `bg-gray-*`, `dark:*` | nearest token equivalent; delete `dark:` variants |
| ad-hoc card `div`s (`rounded-lg border bg-white p-*`) | `<Card>` |
| ad-hoc page titles | `<PageHeader title description actions>` |
| bare "No data" blocks | `<EmptyState>` |
| ad-hoc `animate-pulse` gray blocks | `<Skeleton>` |
| uppercase-tracked stat labels | sentence-case labels via `<StatCard>` |

---

### Task 1: Worktree, task file, spec commit

**Files:**
- Create: worktree `feat/frontend-revamp-claude` from `cd6286c`
- Create: `tasks/active/020-frontend-revamp-claude-design.md`
- Add: `docs/superpowers/specs/2026-07-19-frontend-revamp-claude-design.md`, `docs/superpowers/plans/2026-07-19-frontend-revamp-claude-design.md` (copy from main checkout)

**Steps:**

- [ ] **1.1** Create the worktree: `git worktree add <scratch>/revamp -b feat/frontend-revamp-claude cd6286c` (or the native EnterWorktree tool). All subsequent work happens there.
- [ ] **1.2** Copy the spec + this plan into the worktree (they only exist in the main checkout's untracked files).
- [ ] **1.3** Write `tasks/active/020-frontend-revamp-claude-design.md` following `tasks/TEMPLATE.md`: goal = spec §Decisions, acceptance = spec §7, status = active.
- [ ] **1.4** Commit: `docs(revamp): spec + plan + task 020 for the Claude-style frontend revamp`

### Task 2: Design tokens, fonts, brand.md

**Files:**
- Modify: `founder-os/apps/web/app/globals.css` (full rewrite)
- Modify: `founder-os/apps/web/app/layout.tsx` (add Source Serif 4)
- Create: `founder-os/apps/web/brand.md`

**Interfaces (produces):** utilities `bg-paper bg-surface bg-surface-muted border-line border-line-subtle text-ink text-ink-secondary text-ink-muted bg-accent bg-accent-hover bg-accent-soft text-success text-warning text-danger rounded-card rounded-control font-serif` — every later task consumes these.

- [ ] **2.1** Rewrite `globals.css`:

```css
@import "tailwindcss";

@theme {
  --color-paper: #faf9f5;
  --color-surface: #ffffff;
  --color-surface-muted: #f0eee6;
  --color-line: #e8e6dd;
  --color-line-subtle: #f0eee6;
  --color-ink: #1f1e1d;
  --color-ink-secondary: #63605b;
  --color-ink-muted: #a6a29a;
  --color-accent: #c96442;
  --color-accent-hover: #b04e2f;
  --color-accent-soft: #f1e5de;
  --color-success: #4c8055;
  --color-warning: #b9741c;
  --color-danger: #bf4232;
  --radius-card: 12px;
  --radius-control: 8px;
  --font-serif: var(--font-source-serif), georgia, serif;
  --font-sans: var(--font-geist-sans), system-ui, sans-serif;
  --font-mono: var(--font-geist-mono), monospace;
}

:root { color-scheme: light; --sidebar-width: 248px; }

html, body { max-width: 100vw; overflow-x: hidden; }
body {
  color: var(--color-ink);
  background: var(--color-paper);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
* { border-color: var(--color-line); }

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-line); border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: var(--color-ink-muted); }

*:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; border-radius: 4px; }
::selection { background: var(--color-accent-soft); color: var(--color-ink); }
```

(The `.dark` block and `.cl-*` overrides are deleted; Clerk theming moves to the `appearance` prop in Task 6.)

- [ ] **2.2** In `app/layout.tsx` add:

```tsx
import { Source_Serif_4 } from "next/font/google";
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
});
```

and add `${sourceSerif.variable}` to the `<body>` className. Keep Geist local fonts as-is.

- [ ] **2.3** Write `founder-os/apps/web/brand.md`: palette table (from spec §1), typography rules (serif = display only, numbers stay sans), voice rules (sentence case, no emojis, human empty-state copy, one action per empty state), do/don't list (no gradients, no glow, no card shadows, hairlines carry structure).
- [ ] **2.4** Verify: `npm run check-types` passes; `npm run dev` renders `/` on ivory paper (old pages will look half-migrated — expected until Tasks 4–14).
- [ ] **2.5** Commit: `feat(web): claude-style design tokens, serif display font, brand.md`

### Task 3: UI kit — `app/_components/ui/`

**Files:**
- Create: `founder-os/apps/web/app/_components/ui/{button,card,input,badge,page-header,empty-state,skeleton,stat-card,dialog,tabs,kbd,spinner}.tsx` and `index.ts` barrel.

**Interfaces (produces):**
- `Button({ variant?: "primary"|"secondary"|"ghost"|"danger", size?: "sm"|"md", loading?: boolean, ...buttonProps })`
- `Card({ className?, children })` — surface, hairline, `rounded-card`
- `Input`, `Textarea`, `Select` — styled pass-throughs of native props
- `Badge({ tone?: "neutral"|"accent"|"success"|"warning"|"danger", children })`
- `PageHeader({ title, description?, actions? })` — serif `<h1>`
- `EmptyState({ icon?: LucideIcon, title, body, action? })`
- `Skeleton({ className? })`
- `StatCard({ label, value, sub?, loading? })`
- `Dialog({ open, onClose, title, children, footer? })`
- `Tabs({ tabs: {id,label}[], active, onChange })`
- `Kbd({ children })`, `Spinner({ className? })`

Representative implementations (all others follow the same idiom — clsx + tokens, client components only where interactivity requires):

```tsx
// button.tsx
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

const variants = {
  primary: "bg-accent text-white hover:bg-accent-hover",
  secondary: "bg-surface text-ink border border-line hover:bg-surface-muted",
  ghost: "text-ink-secondary hover:bg-surface-muted hover:text-ink",
  danger: "bg-danger text-white hover:opacity-90",
};
const sizes = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-4 text-sm" };

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
};

export function Button({ variant = "primary", size = "md", loading, disabled, className, children, ...props }: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-control font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50",
        variants[variant], sizes[size], className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}
```

```tsx
// page-header.tsx
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-ink-secondary">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

```tsx
// empty-state.tsx
import type { LucideIcon } from "lucide-react";

export function EmptyState({ icon: Icon, title, body, action }: { icon?: LucideIcon; title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-line-subtle bg-surface px-6 py-16 text-center">
      {Icon && <Icon className="mb-4 h-6 w-6 text-ink-muted" strokeWidth={1.5} />}
      <p className="font-serif text-lg font-medium text-ink">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-ink-secondary">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
```

- [ ] **3.1** Write all 12 primitive files + `index.ts` barrel exporting everything.
- [ ] **3.2** Verify: `npm run lint && npm run check-types` pass (kit compiles unused).
- [ ] **3.3** Commit: `feat(web): owned ui kit (button, card, page-header, empty-state, …)`

### Task 4: App shell — sidebar, header, content container

**Files:**
- Modify: `app/(dashboard)/_components/sidebar.tsx`, `header.tsx`, `dashboard-shell.tsx`

- [ ] **4.1** Sidebar: `bg-surface-muted` aside with `border-line` right hairline; terracotta logo mark (`bg-accent`), `font-serif` wordmark; nav regrouped:

```tsx
const navigation = [
  { section: null, items: [{ name: "Dashboard", href: "/dashboard", icon: LayoutDashboard }] },
  { section: "Work", items: [Chat, Agents, Tasks, Planner] },        // existing entries unchanged
  { section: "Knowledge", items: [Memory, Knowledge, ContentIdeas] }, // "Content ideas" label sentence-cased
  { section: "System", items: [Automations, Apps] },
];
```

Section labels: `px-3 pt-5 pb-1 text-[11px] font-medium tracking-wide text-ink-muted`. Active item: `bg-surface text-ink shadow-none rounded-control` pill; inactive: `text-ink-secondary hover:bg-paper/60 hover:text-ink`. **Keep `useChatStore` pulse-dot logic byte-for-byte.** Bottom nav (Billing, Settings) unchanged structurally.
- [ ] **4.2** Header: `bg-paper/80 backdrop-blur-md border-b border-line`; search input → kit `Input` styling with `Kbd`; keep `UserButton`.
- [ ] **4.3** Shell: root `bg-paper`; main becomes `<main className="flex-1 px-5 py-6 md:px-8 lg:px-10"><div className="mx-auto w-full max-w-6xl">{children}</div></main>`.
- [ ] **4.4** Verify: lint + types; visual — grouped warm sidebar, centered content on ivory.
- [ ] **4.5** Commit: `feat(web): warm grouped sidebar, paper shell, centered content column`

### Task 5: Landing page

**Files:** Modify: `app/page.tsx`

- [ ] **5.1** Apply mapping table; hero `<h1>` → `font-serif` (keep size scale); badge pill copy "AI-powered" → drop the pill or make it quiet text (no fake status dot); CTAs → `Button` idiom (primary terracotta "Start for free", secondary "Sign in"); feature pills → plain `border-line text-ink-secondary` chips with sentence case ("7 AI agents", "Smart scheduling", "Long-term memory", "MCP integrations", "Human-in-the-loop"); footer `text-ink-muted border-line`.
- [ ] **5.2** Verify visually at `/` logged out; lint + types.
- [ ] **5.3** Commit: `feat(web): landing page on the paper/serif system`

### Task 6: Auth + onboarding + Clerk appearance

**Files:** Modify: `app/(auth)/layout.tsx`, `app/(auth)/sign-in/[[...sign-in]]/page.tsx`, `app/(auth)/sign-up/[[...sign-up]]/page.tsx`, `app/(onboarding)/layout.tsx`, `app/(onboarding)/onboarding/page.tsx`, `app/layout.tsx`

- [ ] **6.1** In root `layout.tsx`, pass a shared appearance to `ClerkProvider`:

```tsx
<ClerkProvider appearance={{
  variables: { colorPrimary: "#c96442", colorText: "#1f1e1d", borderRadius: "8px", fontFamily: "var(--font-geist-sans), system-ui, sans-serif" },
}}>
```

- [ ] **6.2** Auth layout: `bg-paper`, serif wordmark, tagline sentence-cased.
- [ ] **6.3** Onboarding: mapping table + serif headings + kit `Button`/`Input`/`Card`.
- [ ] **6.4** Verify: sign-in page renders terracotta Clerk form on paper; lint + types.
- [ ] **6.5** Commit: `feat(web): auth + onboarding on the paper system, clerk themed via appearance prop`

### Tasks 7–14: Page sweeps

Same recipe for every page — listed as separate tasks so each is independently verifiable and committable. For each: apply the class-mapping table; add `PageHeader` (serif title + one-line description); replace ad-hoc cards/empty/loading with kit `Card`/`EmptyState`/`Skeleton`/`Badge`/`Button`; delete `dark:` variants; sentence-case labels; keep all hooks/handlers/SSE untouched.

- [ ] **Task 7:** `dashboard/page.tsx` (421 ln) — StatCards, agent status list, activity feed. Empty-state copy: activity → "Nothing yet today. Agent activity will stream in here as it happens." Commit: `feat(web): dashboard home sweep`
- [ ] **Task 8:** `dashboard/chat/page.tsx` (314 ln) — centered `max-w-3xl` column; user msgs `bg-surface-muted rounded-2xl px-4 py-2.5` right-aligned chips; assistant msgs bare on paper with tight prose styles; composer = `Card` with `Textarea` + terracotta send `Button`. SSE/streaming code untouched. Commit: `feat(web): chat on the claude-style column`
- [ ] **Task 9:** `dashboard/agents/page.tsx` (1012 ln) — largest file; sweep + kit; agent chat panel gets same message treatment as Task 8. Commit: `feat(web): agents page sweep`
- [ ] **Task 10:** `dashboard/tasks/page.tsx` (946 ln) — replace `bg-neutral-*` agent color map with token map: `{ orchestrator: "bg-ink", planner: "bg-ink-secondary", content: "bg-accent", research: "bg-success", support: "bg-warning", default: "bg-ink-muted" }`; delete `dark:` variants. Commit: `feat(web): tasks page sweep`
- [ ] **Task 11:** `dashboard/planner/page.tsx` (861 ln). Commit: `feat(web): planner sweep`
- [ ] **Task 12:** `dashboard/memory/page.tsx` (527) + `dashboard/knowledge/page.tsx` (509). Memory empty state: "No memories yet. They'll accumulate as your agents work." Commit: `feat(web): memory + knowledge sweep`
- [ ] **Task 13:** `dashboard/content-ideas/page.tsx` (348) + `dashboard/workflows/page.tsx` (350) + `workflows/[id]/page.tsx` + `automations/page.tsx` (8 ln redirect — verify no styling). Commit: `feat(web): content ideas + workflows sweep`
- [ ] **Task 14:** `dashboard/apps/page.tsx` (630) + `billing/page.tsx` (558) + `settings/[[...rest]]/page.tsx` (settings hosts Clerk `UserProfile` — appearance already themed via provider). Commit: `feat(web): apps + billing + settings sweep`

Each task N: **N.1** sweep → **N.2** `npm run lint && npm run check-types` + `grep -n "bg-white\|text-gray\|bg-neutral\|dark:\|var(--color-" <file>` returns nothing → **N.3** visual check of the route → **N.4** commit.

### Task 15: Acceptance sweep + docs

- [ ] **15.1** Repo-wide acceptance: from `apps/web/`, `grep -rn "bg-white\|text-gray-\|bg-gray-\|bg-neutral-\|dark:\|var(--color-" app lib` → zero hits (except `globals.css` token definitions). `npm run lint && npm run check-types` pass. `npm run build` passes.
- [ ] **15.2** Visual pass: screenshot every route (landing, sign-in, onboarding, all 12 dashboard pages) via the run skill/dev server; confirm chat streaming, sidebar pulse dots, and Clerk flows still behave.
- [ ] **15.3** Docs: ADR in `docs/decisions.md` ("Claude-style design system + owned UI kit — why: founder-approved revamp; tokens via Tailwind @theme; no component library dependency"); update `docs/roadmap.md`; move task 020 to `tasks/completed/`.
- [ ] **15.4** Commit: `docs(revamp): adr, roadmap, task 020 completed`

### Task 16: Review gates + PR

- [ ] **16.1** Dispatch `eng-reviewer` on the branch diff; fix findings.
- [ ] **16.2** Dispatch `eng-qa` against spec §7 acceptance; record Pass/Fail with output. (`eng-security` not required: no auth/secrets/input-handling changes — Clerk appearance prop is cosmetic.)
- [ ] **16.3** Push branch, open PR to `main` titled `feat(web): claude-style frontend revamp` noting it must merge **after** `feat/background-chat-runs`; body ends with the standard generated-with footer.

## Self-review

- **Spec coverage:** tokens (T2), typography (T2), kit (T3), shell + nav grouping (T4), landing (T5), auth/onboarding/Clerk (T6), all 12 dashboard pages (T7–14), brand.md (T2.3), acceptance greps (T15), branch note (T1/Global), task 020 (T1.3), ADR/docs (T15.3). No gaps.
- **Placeholders:** page sweeps intentionally carry the mapping table + per-page specifics instead of full rewritten files (a full rewrite of 6.5k lines in-plan would be noise, the mapping table is deterministic); unique decisions (agent color map, chat chips, empty-state copy) are spelled out.
- **Type consistency:** kit prop names in Interfaces blocks match usage in Tasks 4–14 (`variant`, `tone`, `title/description/actions`, `icon/title/body/action`).
