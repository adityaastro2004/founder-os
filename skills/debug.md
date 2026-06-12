# Skill — Debug

> Reusable capability. Trigger when investigating a failure, error, crash, flaky
> behavior, or "why is this happening". Native auto-trigger: `.claude/skills/debug/`.

## Goal

Find the **root cause** — not a symptom — and recommend a verified fix. Never guess.

## Process

1. **Reproduce** — get a deterministic repro. For the backend, run the relevant
   `test_*.py` or the failing endpoint via the [CLAUDE.md §6](../CLAUDE.md) commands;
   for the frontend, reproduce in `turbo dev --filter=web`. Capture exact input + error.
2. **Collect evidence** — full stack trace, logs (`logging` output, uvicorn/celery
   console), DB/Redis state, request/response payloads. Note what changed recently
   (`git log`, `git diff`). Don't theorize before you have evidence.
3. **Form hypotheses** — list concrete, falsifiable causes, ordered by likelihood
   given the evidence. Consider this stack's usual suspects: missing `await`/blocking
   IO, Clerk auth/JWKS, async session misuse, Redis/Celery connectivity, LLM
   provider fallback, pgvector/embedding dims, env/config (`config.py`).
4. **Test hypotheses** — isolate one variable at a time (logging, a minimal script,
   a targeted query). Confirm or eliminate each before moving on.
5. **Recommend the fix** — once root cause is proven, propose the minimal change,
   then verify the repro is gone and nothing else broke.

## Never

- Never guess or "try things" without evidence.
- Never declare it fixed without re-running the repro.
- Never mask a symptom (swallow the exception, retry blindly) instead of fixing the cause.

## Output

Root cause (one sentence) → evidence that proves it → the minimal fix →
verification that the repro now passes.
