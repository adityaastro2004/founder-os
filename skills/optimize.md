# Skill — Optimize

> Reusable capability. Trigger for performance work — slow endpoint, high latency,
> N+1 queries, memory/CPU pressure, slow page, expensive LLM calls. Native
> auto-trigger: `.claude/skills/optimize/`.

## Goal

Make something measurably faster or cheaper **without changing behavior** — driven
by measurement, not guesswork.

## Process

1. **Measure first** — get a baseline number for the specific complaint (endpoint
   latency, query time, page load, token/$ per call). Never optimize on a hunch.
2. **Find the real bottleneck** — profile/trace before touching code. This stack's
   usual suspects: N+1 / unindexed queries (Postgres), missing async / blocking IO,
   serial work that could be parallel (the agent `ExecutionEngine` runs tools in
   parallel), Redis round-trips, oversized pgvector scans, unbatched embeddings,
   redundant or oversized LLM calls, missing caching (e.g. the JWKS cache pattern).
3. **Form a hypothesis** tied to the measurement; predict the expected gain.
4. **Change one thing**, then **re-measure** against the baseline. Keep the win that
   the numbers justify; revert changes that don't move the needle.
5. **Confirm behavior is unchanged** — the existing test/verification still passes
   ([standards/testing.md](../standards/testing.md)).

## Never

- Never optimize without a before/after measurement.
- Never trade correctness, security, or provider neutrality for speed.
- Never micro-optimize a non-bottleneck or add caching that risks stale/leaked data
  (respect per-`user_id` scoping).

## Output

Baseline → bottleneck (with evidence) → the change → after measurement (the gain) →
confirmation behavior is unchanged. Record notable wins/limits in the task file; a
recurring optimization belongs in the [roadmap](../docs/roadmap.md) as tech-debt.
