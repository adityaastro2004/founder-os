# Brand — Founder OS

_Status: active_

Warm, calm, editorial. The product should feel like a well-made tool on good
paper — closer to a considered publication than a SaaS template. Inspired by
the Claude/Anthropic aesthetic, adapted for Founder OS.

## Palette

All colors live as Tailwind 4 `@theme` tokens in `app/globals.css`. Use the
generated utilities (`bg-paper`, `text-ink`, `border-line`…) — never raw hex,
never Tailwind's stock grays (`bg-white`, `text-gray-*`, `bg-neutral-*`).

| Token | Value | Use |
|---|---|---|
| `paper` | `#FAF9F5` | App/page background (ivory paper) |
| `surface` | `#FFFFFF` | Cards, inputs, popovers |
| `surface-muted` | `#F0EEE6` | Sidebar, hover fills, code/quote blocks, skeletons |
| `line` | `#E8E6DD` | Default hairline borders |
| `line-subtle` | `#F0EEE6` | Subtle dividers |
| `ink` | `#1F1E1D` | Primary text |
| `ink-secondary` | `#63605B` | Secondary text (AA on paper and surface) |
| `ink-muted` | `#A6A29A` | Placeholders and decorative icons ONLY — below AA for body text |
| `accent` | `#C96442` | Terracotta fills: primary buttons, active states |
| `accent-hover` | `#B04E2F` | Accent hover |
| `accent-text` | `#B04E2F` | Accent as small text/links on paper (AA-safe; `#C96442` text is only for ≥18px) |
| `accent-soft` | `#F1E5DE` | Accent-tinted chips/badges |
| `success` / `-soft` | `#4C8055` / `#E8EFE6` | Positive status |
| `warning` / `-soft` | `#B9741C` / `#F5ECDC` | Caution status |
| `danger` / `-soft` | `#BF4232` / `#F6E4E0` | Errors, destructive actions |

### Dark theme

The same tokens are re-valued under `.dark` on `<html>` (`app/globals.css`) —
components never branch on theme; utilities pick up the override automatically.
The palette keeps the warm hue family: near-black warm charcoal paper, ivory
ink, and a brightened terracotta for contrast on dark.

| Token | Dark value | Notes |
|---|---|---|
| `paper` | `#262624` | Warm charcoal |
| `surface` | `#30302E` | Cards, inputs |
| `surface-muted` | `#3A3835` | Sidebar, hover fills |
| `line` / `line-subtle` | `#423F3A` / `#363430` | Borders |
| `ink` | `#F0EEE6` | Primary text (ivory) |
| `ink-secondary` | `#B8B3AA` | Secondary text (AA on dark paper) |
| `ink-muted` | `#837F77` | Placeholders only |
| `accent` | `#D97757` | Brightened terracotta |
| `accent-hover` / `accent-text` | `#E08B6D` | Hover + AA-safe small text |
| `accent-soft` | `#453029` | Tinted chips |
| `success` / `-soft` | `#7CAB7F` / `#2C3A2E` | |
| `warning` / `-soft` | `#D09A4A` / `#423520` | |
| `danger` / `-soft` | `#E0705C` / `#462B26` | |

Theme choice persists in `localStorage("founder-os-theme")`, defaults to the
OS preference, and is applied pre-paint by an inline script in `app/layout.tsx`.
Toggle lives in the sidebar footer and the landing nav
(`app/_components/theme-toggle.tsx`).

## Typography

- **Display serif** — Source Serif 4 (`font-serif`): page titles, section
  headings, hero copy, empty-state titles. Semibold, tight tracking.
- **Body/UI sans** — Geist (`font-sans`): everything else. Numbers and stat
  values stay sans.
- **Mono** — Geist Mono (`font-mono`): code, kbd, IDs.
- Sentence case everywhere — headings, buttons, labels, nav. Never Title Case,
  never ALL CAPS (tiny tracked section labels in the sidebar are the one
  exception).

## Shape & depth

- Radius: `rounded-card` (12px) for cards/dialogs, `rounded-control` (8px) for
  buttons/inputs.
- Hairline borders carry structure; **no card shadows**. One soft shadow level
  is reserved for overlays (dialogs, popovers, command palette).
- No gradients, no glow, no glassmorphism.

## Motion

- Micro-transitions only: 150ms color/opacity eases on hover/focus.
- No entrance choreography, no parallax. `prefers-reduced-motion` is honored
  globally in `globals.css`.

## Voice

- Human, plain, specific. "No memories yet. They'll accumulate as your agents
  work." — not "No data to display."
- No decorative emojis. No exclamation marks in UI chrome.
- Every empty state: one serif title, one sentence of body, at most one action.

## Components

Compose from the owned kit in `app/_components/ui/` (`Button`, `Card`,
`PageHeader`, `EmptyState`, `Badge`, `StatCard`, `Skeleton`, `Dialog`, `Tabs`,
`Input`, `Kbd`, `Spinner`). One-off styles are allowed only where a primitive
genuinely doesn't fit.
