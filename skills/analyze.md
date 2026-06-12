# Skill — Analyze

> Reusable capability. Trigger when you need to understand a subsystem before
> changing it, or to assess risk/coupling/health. Native auto-trigger:
> `.claude/skills/analyze/`.

## Goal

Produce a clear, evidence-based map of a subsystem: how it works, where it's
coupled, and where the risks are — so a change can be planned safely.

## Process

1. **Scope** — name the subsystem and the question (e.g. "how does the approval
   gate interact with Celery tasks?"). Start from [docs/architecture.md](../docs/architecture.md).
2. **Map the surface** — entry points (routes in `app/api/`, agents in
   `app/agents/`, pages/hooks in `apps/web/`), the data it reads/writes
   (`models.py`, `schema.sql`), and external deps (Redis, Postgres, LLM, Clerk).
3. **Trace key flows** — follow one or two representative paths end-to-end
   (request → auth → handler → agent/tool → DB/Redis → response).
4. **Surface coupling & risk** — shared state, implicit ordering, missing tests,
   stubs ([docs/requirements.md](../docs/requirements.md) known gaps), security
   touchpoints (auth, approval, secrets), provider coupling, performance hotspots.
5. **Report** — concise findings with `file:line` evidence; rank risks; recommend
   next steps (and a [tasks/](../tasks/) item if action is warranted).

## Never

- Never assert how something works without reading the actual code.
- Never modify code — analysis is read-only (use the [debug](debug.md) or
  [refactor](refactor.md) skills to act).
- Never bury the conclusion — lead with the answer.

## Output

A short structured report: **summary → flow trace(s) → coupling/risks (ranked) →
recommended next steps**, each claim backed by a `file:line` reference.
