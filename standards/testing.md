# Testing Standards — Founder OS

> The testing contract as of Phase 0 (2026-07-03, task 012). pytest is real now.
> Never report unverified work as done.

## The three tiers

Backend tests live in `founder-os/apps/api/tests/` and run with pytest
(`pytest.ini`: `asyncio_mode = auto`, `testpaths = tests`, live tier deselected
by default).

| Tier | Where | Needs | Run |
|------|-------|-------|-----|
| **unit** | `tests/unit/` | nothing — no DB/Redis/LLM (`tests/conftest.py` supplies CI-mirror env defaults) | `pytest` |
| **regression** | `tests/regression/` | one per fixed bug; unit-style when possible, `@pytest.mark.live` when the bug needs real services (e.g. F3 needed Postgres type inference) | `pytest` / `pytest -m live` |
| **live** | `tests/live/` + live-marked regressions | the full stack on `localhost:8000` (`./start.sh`), Ollama, `APP_ENV=development` | `pytest -m live` |

`tests/live/test_live_suites.py` wraps all 13 standalone `apps/api/test_*.py`
scripts (they remain directly runnable: `python3 test_system.py`). The scripts
authenticate via the dev-only `x-test-user` bypass (hard-gated on
`APP_ENV=development` in `app/auth.py`).

## Commands

```bash
cd founder-os/apps/api && source .venv/bin/activate
pytest                    # unit + non-live regression (fast, no services)
pytest -m live            # full live tier — start the stack first (./start.sh)
# From the monorepo root:
turbo test                # runs the API unit tier via apps/api package.json
```

CI (`.github/workflows/ci.yml`, backend job) runs the unit tier on every run;
the live tier is local-only (needs Ollama + Docker).

## Rules

1. **Every bug fix ships a regression test** that failed before the fix and passes
   after — named/documented with the audit/bug id (e.g. `F3`). No fix commits
   without one.
2. **New features**: unit tests for logic; a live test (or live-suite extension)
   when the behavior spans services.
3. **Unit tier must stay service-free** — if an import drags in a connection at
   module scope, that's a defect to fix (lazy-init), never a reason to mark the
   test live.
4. **LLM-dependent assertions test structure, not content quality** — local model
   output varies (e.g. assert round-trip fields exist, never prose contents).
5. **Timeouts must be provider-aware** — local Ollama is 10–30× slower than hosted
   APIs (measured: 486s for the 2-call plan pipeline on `llama3.1:8b` vs 15–30s
   hosted). Read the provider from `/api/agents/system` where a test must wait.
6. **If automated testing isn't feasible**, record a manual verification (command +
   observed output) in the task file and say explicitly that it was manual.

## Reporting

- Show the actual command and its output. If a test fails, say so and include the
  failure — do not soften or omit it.
- "Done" requires a passing test or a recorded manual verification (see
  [docs/requirements.md](../docs/requirements.md) → Definition of done).

## Still open (roadmap)

- Frontend has no tests yet (Vitest + React Testing Library — roadmap `later`).
- Migrate the 13 standalone scripts' bodies into native pytest modules over time;
  the wrapper keeps them counted meanwhile.
