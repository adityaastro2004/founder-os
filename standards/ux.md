# UX Standards — Founder OS

> How the dashboard (`apps/web`) should feel and behave. Owned in spirit by the
> [product agent](../.claude/agents/eng-product.md); enforced by [reviewer](../.claude/agents/eng-reviewer.md)
> and [QA](../.claude/agents/eng-qa.md). Grounded in the existing Next.js 16 + Tailwind 4 + Clerk
> setup — match it, don't reinvent.

## Product principles (from the vision)

- **One entry point, zero routing.** Users talk to the Orchestrator (the chat); they
  never pick an agent or wire a workflow. New capabilities surface through existing
  flows, not new top-level surfaces. See [docs/vision.md](../docs/vision.md).
- **Founder-grade, low-friction.** The target user is a busy solo founder. Default to
  the fewest clicks; never make them re-supply context the system already has.
- **Human-in-the-loop is visible.** Approval-gated actions
  ([standards/security.md](security.md)) must be surfaced clearly — the user always
  sees what's pending and what was auto-run.

## Interaction & state

- **Always reflect state.** Every async action shows loading, success, empty, and
  error states. Never leave the user staring at a frozen UI (chat/agents stream via
  `useEventSource` / `useStreamingFetch` — show partial progress).
- **Errors are actionable.** Surface a human message + a next step; never a raw stack
  trace or silent failure. Auth expiry routes to re-auth via Clerk, not a dead end.
- **Optimistic where safe, confirmed where not.** Reversible edits can be optimistic;
  destructive/irreversible actions require explicit confirmation (and the approval gate).

## Implementation conventions

- **Reuse the design system.** Tailwind 4 design tokens, `clsx`, `lucide-react`
  icons, shared components in `packages/ui` and `(dashboard)/_components/`. Don't
  introduce a second styling approach or icon set.
- **Server components by default**; `"use client"` only for interactivity. Data via
  the `lib/` hooks (`useApi`, `useEventSource`, `useStreamingFetch`) — see
  [standards/coding.md](coding.md).
- **Accessibility baseline.** Semantic HTML, labelled controls, keyboard-navigable,
  visible focus states, sufficient contrast.
- **Responsive.** The dashboard works on a laptop and a phone; no fixed-width layouts
  that break the founder checking in on mobile. Four rules that have each already
  cost us a real bug — check them in a 320px-wide browser, not by eye:
  1. **Always declare a base `grid-cols-1`.** `grid-cols-N` compiles to
     `repeat(N, minmax(0, 1fr))`; a `grid` with only `sm:`/`lg:` columns falls back
     to an implicit `auto` track that sizes to its content's intrinsic width. An
     `<input>` inside one overflowed a 320px screen by 21px.
  2. **Never `overflow-x: hidden` on `html`/`body`.** It turns the element into a
     scroll container and silently kills every `position: sticky` descendant —
     both site headers were broken this way. Use `overflow-x: clip`.
  3. **Form controls render ≥16px on touch.** Below that, Safari on iOS zooms the
     viewport on focus and never zooms back. Enforced globally in `globals.css`,
     which also covers Clerk's own fields.
  4. **Tap targets ≥24px** (WCAG 2.5.8), 44px for isolated icon buttons via the
     `.tap-target` utility. Don't put `.tap-target` on adjacent buttons — the hit
     areas overlap and one control starts stealing its neighbour's taps.

## Review checklist (UX)

1. Loading / empty / error / success states all handled.
2. No raw errors or silent failures; messages are actionable.
3. Reuses design-system components, tokens, and icons (no one-offs).
4. Approval-gated and destructive actions are clearly surfaced/confirmed.
5. Keyboard-accessible, labelled, responsive.
