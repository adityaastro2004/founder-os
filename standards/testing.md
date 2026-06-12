# Testing Standards — Founder OS

> Honest state of testing today, plus the convention to follow until a real
> framework is adopted. Never report unverified work as done.

## Current reality

- **No test framework is configured.** `pytest` is not in `requirements.txt`;
  there is no `pytest.ini`, no `jest`/`vitest`.
- **Backend tests are standalone scripts** at `apps/api/test_*.py`, run directly:

  ```bash
  cd founder-os/apps/api && source .venv/bin/activate
  python test_e2e_pipeline.py     # end-to-end agent pipeline (mock LLM)
  python test_system.py           # system tests
  python test_memory.py           # memory system
  python test_rag_pipeline.py     # RAG pipeline
  python test_content_agent.py    # content agent
  python app/crawler/test_crawler.py
  ```

  They use `unittest.mock`, `asyncio`, and manual asserts/printed results.
- **Frontend has no tests.**

## Convention until a framework lands

For any non-trivial change, add or extend verification — don't skip it:

1. **Prefer extending an existing `test_*.py` script** that already covers the area
   (e.g. memory change → `test_memory.py`). Keep the standalone, runnable style:
   `async` where needed, mock the LLM (don't hit a live provider), print a clear
   pass/fail summary, exit non-zero on failure.
2. **New area** → add a new `apps/api/test_<area>.py` following the same shape.
3. **Mock external IO** — LLM providers, network, and (where practical) the DB —
   so tests are deterministic and runnable without paid services.
4. **If automated testing isn't feasible**, do a **manual verification**: run the
   relevant command from [CLAUDE.md §6](../CLAUDE.md), exercise the endpoint/flow,
   and record the observed output in the task file. Say explicitly that it was
   manual.

## Reporting

- Show the actual command and its output. If a test fails, say so and include the
  failure — do not soften or omit it.
- "Done" requires a passing test or a recorded manual verification (see
  [docs/requirements.md](../docs/requirements.md) → Definition of done).

## Target (future task, out of scope now)

Adopt `pytest` + `pytest-asyncio` for the backend and Vitest + React Testing
Library for the frontend, with a `turbo test` task. When that lands, migrate the
standalone scripts and update this file.
