# UX Standards — Founder OS

> How the dashboard (`apps/web`) should feel and behave. Owned in spirit by the
> [product agent](../agents/product.md); enforced by [reviewer](../agents/reviewer.md)
> and [QA](../agents/qa.md). Grounded in the existing Next.js 16 + Tailwind 4 + Clerk
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
  that break the founder checking in on mobile.

## Review checklist (UX)

1. Loading / empty / error / success states all handled.
2. No raw errors or silent failures; messages are actionable.
3. Reuses design-system components, tokens, and icons (no one-offs).
4. Approval-gated and destructive actions are clearly surfaced/confirmed.
5. Keyboard-accessible, labelled, responsive.
