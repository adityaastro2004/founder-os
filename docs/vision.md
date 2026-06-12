# Vision — Founder OS

> Source of truth for *why* this product exists. Sourced from the root
> [readme.md](../readme.md). Keep this in sync when the pitch changes.

## One line

An autonomous AI operating system that runs your startup — a multi-agent backend
that acts as a tireless co-founder.

## Target user

Solo founders and tiny teams who need the output of a 10-person ops team but can't
afford one. They are CEO, marketer, researcher, PM, support rep, and ops manager
at once, context-switching dozens of times a day.

## The problem

- Existing AI tools help with *isolated* tasks but don't understand the business
  holistically, don't remember last week, and can't coordinate across domains.
  They're co-pilots, not co-founders.
- Workflow tools (n8n / Zapier / Make) require *you* to design every automation by
  hand and rebuild flows as the company changes. That's more busywork, not less.

## The differentiator

**Auto-generated workflows.** You talk to one **Orchestrator** (inspired by
Stripe's Minions). It analyses the request, decomposes it into subtasks, delegates
to the right specialist agents, and synthesises one coherent answer. You never pick
an agent and never wire a flow — the system figures out what to do from your goals,
data, and history, and evolves workflows automatically as you grow.

## Principles

- **Knows your business** — ingests docs/metrics/integrations into a pgvector
  knowledge base so every agent grounds its work in *your* reality.
- **One entry point, zero routing** — single Orchestrator, agents-as-tools.
- **Delegates internally** — Agent-to-Agent (A2A) protocol; agents talk to each other.
- **Remembers everything** — 4-layer agent memory + temporal knowledge graph
  (composite scoring, spaced-repetition review, entity linking, typed relationships).
- **Plans your week** — weekly planner, ICE-scored priorities, Google Calendar sync,
  Monday-morning auto-generation via APScheduler.
- **Human-in-the-loop** — approval system, 3-tier risk classification (LOW/MEDIUM/HIGH),
  mandatory gating for irreversible actions.
- **Uses your tools** — MCP lets agents connect to external tool servers as
  first-class capabilities.
- **Runs in the background** — Celery task queue with status polling and cancellation.
- **Scales with you** — same system handles a solo founder on day 1 and a small team
  with 10 integrations at month 6.
- **Runs on your terms** — OSS-first, local-first; Ollama default, no vendor lock-in.

## The end state

You wake up, open Founder OS, and your AI team has already triaged support tickets,
drafted the newsletter, flagged a competitor move, updated the roadmap, and prepared
a prioritised task list — with no workflow manually configured.

## How this informs engineering decisions

- Favor **OSS / local-first** defaults; never hard-require a paid provider.
- Keep the **Orchestrator as the single entry point**; new capabilities are agents
  or tools it can compose, not new top-level surfaces.
- Treat **memory and approval gating as load-bearing**, not optional add-ons.
- Preserve **provider pluggability** — no code path may assume a specific LLM vendor.
