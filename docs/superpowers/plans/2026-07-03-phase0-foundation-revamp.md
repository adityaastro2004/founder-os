# Phase 0 Foundation Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Founder OS stack demonstrably work end-to-end (audited + repaired with regression tests), then add the integration adapter framework, pytest harness, `turbo test`, and CI unit tier per the approved spec.

**Architecture:** Three stages. Stage 1 boots the live stack and records a PASS/FAIL/BLOCKED verdict per subsystem in a report (no product-code changes). Stage 2 fixes every FAIL via the repo's bug_fix workflow (failing regression test → fix → re-verify) or defers it with a task file. Stage 3 adds `app/integrations/` (base ABC + registry + Google Calendar migrated as first adapter), a pytest harness at `apps/api/tests/`, wires `turbo test`, and extends CI.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy async; pytest + pytest-asyncio + httpx; Turborepo/npm workspaces; GitHub Actions; Docker (Postgres 16 pgvector, Redis 7, n8n); Ollama `llama3.1:8b` + `nomic-embed-text`.

**Spec:** `docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md`

## Global Constraints

- Git root is `/Users/adityaastro/Documents/GitHub/founder-os`; the monorepo is `founder-os/` inside it; backend cwd is `founder-os/apps/api` (activate `.venv` first).
- All work on branch `phase0-foundation-revamp` (created in Task 1 from the current branch).
- CLAUDE.md rules apply: never weaken Clerk auth or the approval gate; schema changes only via Alembic (none are expected in Phase 0); no product-code change without a test or stated reason; report honestly with real output.
- Stage 1 (Tasks 2–8) makes **no product-code changes** — findings go in the report only.
- The stack for live probes is started with `./start.sh` from `founder-os/founder-os/`; API on :8000, web on :3000, logs in `logs/`. Local auth for probes: header `x-test-user: <id>` (dev-only bypass, hard-gated on `APP_ENV=development` in `app/auth.py:137-151`).
- Every task ends with a commit; commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Audit report lives at `reports/2026-07-03-phase0-audit.md` (git-root relative). Verdicts: **PASS** (probe succeeded, output captured), **FAIL** (probe failed, output captured), **BLOCKED** (needs founder-only access — never guessed).

---

### Task 1: Branch, phase task file, audit report skeleton

**Files:**
- Create: `tasks/active/012-phase0-foundation-revamp.md` (git root)
- Create: `reports/2026-07-03-phase0-audit.md` (git root)

**Interfaces:**
- Produces: the report skeleton whose section numbers (#1–#11) all Stage 1 tasks fill in.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os
git checkout -b phase0-foundation-revamp
```

- [ ] **Step 2: Create the task file** (follows `tasks/TEMPLATE.md` conventions)

```markdown
# 012 — Phase 0: Foundation Revamp

- **Status:** active
- **Spec:** docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md
- **Plan:** docs/superpowers/plans/2026-07-03-phase0-foundation-revamp.md

## Outcome
Everything verifiably working (audit report with PASS/FAIL + evidence; all FAILs
fixed with regression tests or deferred with task files) + integration adapter
framework, pytest harness, turbo test, CI unit tier.

## Acceptance criteria
Success criteria 1–7 of the spec, verbatim.
```

- [ ] **Step 3: Create the report skeleton**

```markdown
# Phase 0 Audit — 2026-07-03

> Verdicts: PASS / FAIL / BLOCKED. Every verdict has captured output.
> Probe environment: local macOS, Docker, Ollama llama3.1:8b, APP_ENV=development.

| # | Subsystem | Verdict | Evidence section |
|---|-----------|---------|------------------|
| 1 | Boot (Docker, Alembic, uvicorn, Celery, web) | | §1 |
| 2 | Auth path (Clerk + dev bypass + test_routes gating) | | §2 |
| 3 | Orchestrator + agent chat | | §3 |
| 4 | Memory (4-layer + temporal KG) | | §4 |
| 5 | Knowledge / RAG | | §5 |
| 6 | Planner + weekly plan + APScheduler | | §6 |
| 7 | Google Calendar | | §7 |
| 8 | Workflows / automations (AOV + n8n) | | §8 |
| 9 | Approval gate | | §9 |
| 10 | Remaining routers (crawler, billing, settings, activity, history, queue) | | §10 |
| 11 | Frontend | | §11 |

## §1 Boot
(filled by audit)
…(§2–§11 same pattern)…

## Ranked fix list
(filled at end of Stage 1)
```

- [ ] **Step 4: Commit**

```bash
git add tasks/active/012-phase0-foundation-revamp.md reports/2026-07-03-phase0-audit.md
git commit -m "chore(phase0): open task 012 + audit report skeleton"
```

---

### Task 2: Boot audit (report §1)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§1 + summary row)

- [ ] **Step 1: Boot the stack and capture**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os/founder-os
./start.sh 2>&1 | tee /tmp/phase0-boot.log     # let it finish or fail
```

- [ ] **Step 2: Probe health of each piece**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool   # expect {"healthy": true, "checks": {...}}
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000  # expect 200 or 307
docker compose ps                                               # postgres, redis, n8n all Up
cd apps/api && source .venv/bin/activate && alembic current && alembic check 2>&1 | tail -3
tail -20 ../../logs/celery.log                                  # worker ready, queues default,agents,orchestrator
```

- [ ] **Step 3: Record §1** — verdict PASS only if: start.sh exits cleanly, `/health` returns `healthy: true`, all 3 containers Up, `alembic current` shows head, celery worker ready. Paste actual outputs (trim to relevant lines). Any failure → FAIL with the failing output; boot FAILs are fixed FIRST in Task 9 (nothing else can be audited without boot).

- [ ] **Step 4: Commit**

```bash
git add reports/2026-07-03-phase0-audit.md && git commit -m "audit(phase0): §1 boot verdict"
```

---

### Task 3: Auth-path audit (report §2)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§2)

- [ ] **Step 1: Verify the dev bypass is hard-gated.** Read `app/auth.py` `_dev_test_user` (lines ~137–151): confirm it returns `None` unless `settings.APP_ENV == "development"`. Read `app/main.py`: confirm `test_routes` is mounted only under the same `APP_ENV` gate — capture the exact mounting code lines in the report.

- [ ] **Step 2: Prove the gate behaves.** With the running dev server: `curl -s -H "x-test-user: audit-user" http://localhost:8000/api/agents` (or any authed route) → expect 200. Then confirm from code (not by restarting) that `APP_ENV != "development"` short-circuits to `None` before the header is read.

- [ ] **Step 3: Record §2.** PASS = bypass provably gated AND test_routes provably dev-mounted. Any hole (e.g. test_routes mounted unconditionally, bypass reachable in prod paths) → FAIL flagged **security**, fix in Task 9 gets an eng-security review.

- [ ] **Step 4: Commit** (`audit(phase0): §2 auth-path verdict`).

---

### Task 4: Core suites audit — system, memory, RAG, e2e (report §3–§6 partial)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§3, §4, §5, §6)

- [ ] **Step 1: Run the four core live scripts, capturing each**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os/founder-os/apps/api && source .venv/bin/activate
python3 test_system.py       2>&1 | tee /tmp/phase0-system.log   ; echo "exit=$?"
python3 test_memory.py       2>&1 | tee /tmp/phase0-memory.log   ; echo "exit=$?"
python3 test_rag_pipeline.py 2>&1 | tee /tmp/phase0-rag.log      ; echo "exit=$?"
python3 test_e2e_pipeline.py 2>&1 | tee /tmp/phase0-e2e.log      ; echo "exit=$?"
```

- [ ] **Step 2: Record verdicts.** Map: test_system → §1 supplement + §6 planner + §7 OAuth-URL part; test_memory → §4; test_rag_pipeline → §5; test_e2e_pipeline → §3 (orchestrator round-trip). PASS requires exit=0; paste each script's own summary block plus any failing assertion output verbatim.

- [ ] **Step 3: Commit** (`audit(phase0): core suites verdicts (§3–§6)`).

---

### Task 5: Agent-layer audit (report §3 completion)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§3)

- [ ] **Step 1: Run the agent suites**

```bash
python3 test_agent_prompts.py        2>&1 | tee /tmp/phase0-prompts.log ; echo "exit=$?"
python3 test_agent_specialization.py 2>&1 | tee /tmp/phase0-spec.log    ; echo "exit=$?"
python3 test_agent_evolution.py      2>&1 | tee /tmp/phase0-evo.log     ; echo "exit=$?"
python3 -m pytest test_content_agent.py -q 2>&1 | tee /tmp/phase0-content.log ; echo "exit=$?"
```

- [ ] **Step 2: Live chat probe** (structure-asserting only — never assert LLM content quality, `llama3.1:8b` output varies):

```bash
curl -s -X POST http://localhost:8000/api/orchestrator/chat \
  -H "x-test-user: audit-user" -H "Content-Type: application/json" \
  -d '{"message": "List my three most important tasks this week."}' | python3 -m json.tool | head -40
```

(If the chat route path differs, find it: `grep -rn "chat" app/api/*.py | grep -i "post"` — record the actual path used.)

- [ ] **Step 3: Record §3 verdict + commit** (`audit(phase0): §3 agent-layer verdict`).

---

### Task 6: Workflows/automations audit (report §8)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§8)

- [ ] **Step 1: Run the workflow suites**

```bash
python3 test_workflow_ir.py        2>&1 | tail -20 ; echo "exit=$?"
python3 test_workflow_compiler.py  2>&1 | tail -20 ; echo "exit=$?"
python3 test_workflow_generator.py 2>&1 | tail -20 ; echo "exit=$?"
python3 test_workflow_routes.py    2>&1 | tail -20 ; echo "exit=$?"
python3 test_n8n_client.py         2>&1 | tail -20 ; echo "exit=$?"
```

- [ ] **Step 2: Verify n8n itself**: `docker compose ps n8n` (Up?) and `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5678` (port from docker-compose.yml). Record whether the AOV in-process path and the n8n path both work, separately — per ADR-009 the AOV path is the default; n8n failures are lower priority than AOV failures.

- [ ] **Step 3: Record §8 verdict + commit** (`audit(phase0): §8 workflows verdict`).

---

### Task 7: Calendar + approval-gate audit (report §7, §9)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§7, §9)

- [ ] **Step 1: Calendar config + URL generation** (no founder consent needed): confirm `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI` are set in `.env` (names only); hit the auth-URL endpoint (`grep -n "get_auth_url" app/api/planner_routes.py` for the route) with `x-test-user` and confirm a well-formed `accounts.google.com` URL comes back.

- [ ] **Step 2: Live sync probe.** If `test_system.py` §4 reported tokens already in the DB, run its calendar section / call the push endpoint and record real results. If no tokens: mark the push probe **BLOCKED (needs founder OAuth consent)** with the exact one-step instruction for the founder (visit auth URL, approve, re-run probe). Do not fake it.

- [ ] **Step 3: Approval gate probe (§9).** Find the classification path: `grep -rn "HIGH\|MEDIUM" app/agents/approval.py | head`. Trigger a MEDIUM/HIGH-risk action via API (e.g. an agent action that the gate classifies; the e2e script may already cover it — cite it if so) and verify the action is held pending approval server-side, not executed. Record the held-approval row/response as evidence.

- [ ] **Step 4: Record §7 + §9 verdicts + commit** (`audit(phase0): §7 calendar + §9 approval-gate verdicts`).

---

### Task 8: Remaining routers + frontend audit; ranked fix list (report §10, §11, final)

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (§10, §11, ranked fix list, summary table complete)

- [ ] **Step 1: Smoke the remaining routers** (all with `-H "x-test-user: audit-user"`; record `path → status`):

```bash
for p in /api/crawler/status /api/billing/plans /api/settings /api/activity /api/history /api/queue/status; do
  echo -n "$p -> "; curl -s -o /dev/null -w "%{http_code}\n" -H "x-test-user: audit-user" "http://localhost:8000$p"
done
```

(Adjust paths to the real ones: `grep -n "prefix=" app/main.py app/api/*.py | grep -i router`. 200/401-when-unauthed = wired; 404 on a registered prefix or 500 = FAIL.)

- [ ] **Step 2: Frontend smoke**: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/` and `/dashboard`, `/sign-in` (Clerk redirects = OK). Check `logs/web.log` for build/runtime errors. UI click-through is recorded as a founder manual-verification item, not guessed.

- [ ] **Step 3: Complete the summary table; write the ranked fix list** ordered per spec: boot → agents/chat → calendar → workflows → rest. Each entry: `F<n> — subsystem — one-line symptom — evidence §`.

- [ ] **Step 4: Commit** (`audit(phase0): complete — summary + ranked fix list`).

---

### Task 9: Stage 2 — repair loop (repeat per FAIL, in ranked order)

**Files:** determined per fix; regression tests go in `founder-os/apps/api/tests/regression/` once Task 10 exists — until Task 10 lands, put them in the script style at `apps/api/` root and migrate them in Task 10 (note: run Task 10 FIRST if the first fix arrives after Stage 1; ordering between Task 9 and 10 is: Task 10 may be done before or interleaved — the harness does not depend on any repair).

**Protocol for EVERY fix `F<n>` (this is `workflows/bug_fix.md` + TDD, made explicit):**

- [ ] **Step 1: Root-cause.** Reproduce with the audit probe; read the failing code path; state the root cause in one sentence in the report under `F<n>` (no fix without a stated root cause — no "shotgun" patches).
- [ ] **Step 2: Write the failing regression test** that encodes the root cause (unit-tier if reproducible without services, `@pytest.mark.live` otherwise). Run it; confirm it fails for the expected reason; paste the failure output into the commit body.
- [ ] **Step 3: Minimal fix.** No drive-by refactors inside a fix commit.
- [ ] **Step 4: Verify:** regression test passes AND the original audit probe now passes; update the report verdict `FAIL → PASS (fixed, F<n>, commit <sha>)`.
- [ ] **Step 5: Security check:** if the fix touched auth, approval gate, secrets, or external input handling → dispatch eng-security on the diff before commit.
- [ ] **Step 6: Commit** (`fix(phase0): F<n> <symptom> — root cause: <one line>`).

**Deferral path (exceptional):** a FAIL may be deferred ONLY with `tasks/backlog/<next-number>-<slug>.md` containing symptom, evidence, root-cause-so-far, and why not now; report verdict becomes `FAIL (deferred → task <n>)`.

**Exit criteria:** zero FAIL rows without either a fix commit or a deferral task; boot/agents/calendar/workflows (the founder's named pain points) MUST be fixed, not deferred, unless BLOCKED on founder-only access.

---

### Task 10: pytest harness

**Files:**
- Modify: `founder-os/apps/api/requirements.txt` (append)
- Create: `founder-os/apps/api/pytest.ini`
- Create: `founder-os/apps/api/tests/__init__.py`, `tests/unit/__init__.py`, `tests/regression/__init__.py`, `tests/live/__init__.py` (empty files)
- Create: `founder-os/apps/api/tests/conftest.py`
- Create: `founder-os/apps/api/tests/unit/test_app_imports.py`
- Create: `founder-os/apps/api/tests/live/test_live_suites.py`

**Interfaces:**
- Produces: `pytest` (default = unit+regression tiers, no services needed); `pytest -m live` (needs running stack); marker name `live`. Tasks 11–13 add tests under `tests/unit/`; Task 15 CI runs `pytest -m "not live" -q`.

- [ ] **Step 1: Add test deps** — append to `requirements.txt`:

```
# Testing (Phase 0)
pytest>=8.0
pytest-asyncio>=0.24
```

Then `pip install -r requirements.txt` in the venv.

- [ ] **Step 2: pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = -m "not live"
markers =
    live: needs the full stack on localhost:8000 (./start.sh); run with: pytest -m live
```

- [ ] **Step 3: conftest.py** — unit tier must import the app with no services and no real `.env` required (same dummy values CI uses in `.github/workflows/ci.yml`):

```python
"""Test bootstrap: make the unit tier runnable with zero services configured.

Values mirror .github/workflows/ci.yml — they satisfy config parsing only;
unit tests must never open a DB/Redis/LLM connection.
"""
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://founder:founder@localhost:5432/founder_os")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://founder:founder@localhost:5432/founder_os")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_PROVIDER", "ollama")
```

- [ ] **Step 4: First unit test**

```python
"""The FastAPI app must import and register routes without any services running."""


def test_app_imports_and_has_routes():
    from app.main import app

    assert len(app.routes) > 20  # sanity: all routers registered
```

- [ ] **Step 5: Run** `pytest -q` → expect `1 passed` (live tier auto-deselected). If import pulls in a service connection at module scope, that is a real defect: fix it as a Task 9 fix (lazy-init), not by weakening this test.

- [ ] **Step 6: Live wrappers** — every existing root script becomes runnable via pytest without being moved (scripts stay standalone-runnable too; none lost):

```python
"""Wrap the standalone live-server scripts as pytest 'live' tier.

Each script hits localhost:8000 (started via ./start.sh) using the dev
x-test-user bypass. They stay directly runnable: python3 test_system.py.
"""
import pathlib
import subprocess
import sys

import pytest

API_ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPTS = [
    "test_system.py",
    "test_memory.py",
    "test_rag_pipeline.py",
    "test_e2e_pipeline.py",
    "test_agent_prompts.py",
    "test_agent_specialization.py",
    "test_agent_evolution.py",
    "test_workflow_ir.py",
    "test_workflow_compiler.py",
    "test_workflow_generator.py",
    "test_workflow_routes.py",
    "test_n8n_client.py",
]


@pytest.mark.live
@pytest.mark.parametrize("script", SCRIPTS)
def test_live_script(script):
    proc = subprocess.run(
        [sys.executable, str(API_ROOT / script)],
        capture_output=True, text=True, timeout=1800,
    )
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
    assert proc.returncode == 0, f"{script} failed:\n{tail}"


@pytest.mark.live
def test_content_agent_suite():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(API_ROOT / "test_content_agent.py"), "-q"],
        capture_output=True, text=True, timeout=1800,
    )
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
    assert proc.returncode == 0, f"test_content_agent.py failed:\n{tail}"
```

- [ ] **Step 7: Verify tiers**: `pytest -q` (fast, passes with stack down) and, with the stack up, `pytest -m live -q 2>&1 | tail -15` (verdicts should match the audit report — any mismatch means the audit or a repair regressed; resolve before proceeding).

- [ ] **Step 8: Commit** (`test(phase0): pytest harness — unit/regression/live tiers, scripts wrapped`).

---

### Task 11: Integration adapter framework — base + registry (TDD)

**Files:**
- Create: `founder-os/apps/api/app/integrations/base.py`
- Create: `founder-os/apps/api/app/integrations/registry.py`
- Test: `founder-os/apps/api/tests/unit/test_integration_registry.py`

**Interfaces:**
- Produces (consumed by Task 12 and by Phase 1's Obsidian adapter):
  - `Capability` (enum.Flag): `OBSERVE | SYNC | HEALTH`
  - `HealthStatus(ok: bool, detail: str = "")`
  - `ObservedEvent(source: str, kind: str, external_id: str, payload: dict, observed_at: datetime, provenance: str = "observed")`
  - `SyncResult(ok: bool, pushed: int = 0, errors: list[str])`
  - `IntegrationAdapter` ABC: `name: str`, `capabilities: Capability`, `async configure(settings: dict) -> None`, `async health() -> HealthStatus`, `async observe(user_id: str) -> list[ObservedEvent]`, `async sync(user_id: str, changes: list[dict]) -> SyncResult`
  - `registry.register(adapter)`, `registry.get(name)`, `registry.all_adapters()`, `registry._reset_for_tests()`

- [ ] **Step 1: Write the failing tests**

```python
"""Adapter framework contract: registration, lookup, capability defaults."""
from datetime import datetime, timezone

import pytest

from app.integrations import registry
from app.integrations.base import (
    Capability, HealthStatus, IntegrationAdapter, ObservedEvent, SyncResult,
)


class FakeAdapter(IntegrationAdapter):
    name = "fake_tool"
    capabilities = Capability.OBSERVE | Capability.HEALTH

    async def configure(self, settings):
        self.settings = settings

    async def health(self):
        return HealthStatus(ok=True, detail="fake ok")

    async def observe(self, user_id):
        return [ObservedEvent(
            source=self.name, kind="thing.seen", external_id="x1",
            payload={"user": user_id}, observed_at=datetime.now(timezone.utc),
        )]


@pytest.fixture(autouse=True)
def clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def test_register_and_get():
    a = FakeAdapter()
    registry.register(a)
    assert registry.get("fake_tool") is a
    assert registry.all_adapters() == {"fake_tool": a}


def test_register_rejects_duplicates_and_unnamed():
    registry.register(FakeAdapter())
    with pytest.raises(ValueError):
        registry.register(FakeAdapter())          # duplicate name

    class Unnamed(FakeAdapter):
        name = ""
    with pytest.raises(ValueError):
        registry.register(Unnamed())

    with pytest.raises(KeyError):
        registry.get("nope")


async def test_observe_returns_provenance_tagged_events():
    a = FakeAdapter()
    events = await a.observe("user-1")
    assert events[0].provenance == "observed"
    assert events[0].source == "fake_tool"


async def test_unsupported_capabilities_raise():
    a = FakeAdapter()
    with pytest.raises(NotImplementedError):
        await a.sync("user-1", [{"anything": 1}])
```

- [ ] **Step 2: Run to verify failure**: `pytest tests/unit/test_integration_registry.py -q` → FAIL: `ModuleNotFoundError`/`ImportError` (base/registry don't exist).

- [ ] **Step 3: Implement `base.py`**

```python
"""Integration adapter framework (ADR-010).

Every external tool (Google Calendar, Obsidian, Notion, Paperclip, ...) plugs
into Founder OS through exactly one IntegrationAdapter. Adapters carry NO
business logic — they translate between the external tool and Founder OS
types. Reconciliation into canonical company state is the State Engine's job
(ADR-009, Phase 1); adapter output is provenance-tagged "observed" for it.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Capability(enum.Flag):
    OBSERVE = enum.auto()  # pull external events/state into Founder OS
    SYNC = enum.auto()     # push canonical state out to the tool
    HEALTH = enum.auto()   # report connectivity/config status


@dataclass
class HealthStatus:
    ok: bool
    detail: str = ""


@dataclass
class ObservedEvent:
    """One event/state snapshot pulled from an external tool."""

    source: str            # adapter name, e.g. "google_calendar"
    kind: str              # adapter-defined event kind, e.g. "event.upcoming"
    external_id: str       # stable id in the source system (dedup key)
    payload: dict[str, Any]
    observed_at: datetime
    provenance: str = "observed"  # ADR-009 feed 1; adapters never emit other feeds


@dataclass
class SyncResult:
    ok: bool
    pushed: int = 0
    errors: list[str] = field(default_factory=list)


class IntegrationAdapter(ABC):
    """Base class for all tool integrations. Multi-tenant: per-call user_id."""

    name: str = ""
    capabilities: Capability = Capability.HEALTH

    @abstractmethod
    async def configure(self, settings: dict[str, Any]) -> None:
        """Receive credentials/config. Secrets come from env/DB, never literals."""

    @abstractmethod
    async def health(self) -> HealthStatus:
        """Cheap connectivity/config check; must not mutate anything."""

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        raise NotImplementedError(f"{self.name} does not support OBSERVE")

    async def sync(self, user_id: str, changes: list[dict[str, Any]]) -> SyncResult:
        raise NotImplementedError(f"{self.name} does not support SYNC")
```

- [ ] **Step 4: Implement `registry.py`**

```python
"""Process-wide adapter registry. Adapters are registered once at startup
(app.main lifespan) and looked up by name — never imported ad-hoc by callers."""
from __future__ import annotations

from app.integrations.base import IntegrationAdapter

_REGISTRY: dict[str, IntegrationAdapter] = {}


def register(adapter: IntegrationAdapter) -> IntegrationAdapter:
    if not adapter.name:
        raise ValueError("adapter.name must be a non-empty string")
    if adapter.name in _REGISTRY:
        raise ValueError(f"integration adapter already registered: {adapter.name!r}")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> IntegrationAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"no integration adapter named {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def all_adapters() -> dict[str, IntegrationAdapter]:
    return dict(_REGISTRY)


def _reset_for_tests() -> None:
    _REGISTRY.clear()
```

- [ ] **Step 5: Run tests** → `pytest tests/unit/test_integration_registry.py -q` → all PASS. Also `pytest -q` (whole unit tier green).

- [ ] **Step 6: Commit** (`feat(phase0): integration adapter framework — base ABC + registry (ADR-010)`).

---

### Task 12: Migrate Google Calendar onto the framework (behavior-preserving)

**Files:**
- Create: `founder-os/apps/api/app/integrations/google_calendar/__init__.py`
- Move: `app/integrations/calendar_integration.py` → `app/integrations/google_calendar/client.py` (git mv, content unchanged)
- Create: `app/integrations/google_calendar/adapter.py`
- Modify: importers of the old path — `app/scheduler.py:74`, `app/agents/mcp_tools.py` (~11 function-level import sites), `app/api/test_routes.py` (3 sites), `app/api/planner_routes.py` (3 sites)
- Modify: `app/main.py` (register adapter in lifespan)
- Test: `tests/unit/test_google_calendar_adapter.py`

**Interfaces:**
- Consumes: Task 11's `IntegrationAdapter`, `Capability`, `HealthStatus`, `ObservedEvent`, registry.
- Produces: module path `app.integrations.google_calendar.client` exporting the exact same 17 functions/classes (`store_tokens`…`_build_gcal_event`, `CalendarAuthExpired`); `GoogleCalendarAdapter` registered under name `"google_calendar"`.

- [ ] **Step 1: Move the client (no content change)**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os/founder-os/apps/api
mkdir -p app/integrations/google_calendar
git mv app/integrations/calendar_integration.py app/integrations/google_calendar/client.py
printf '"""Google Calendar integration (client + adapter). ADR-010."""\n' > app/integrations/google_calendar/__init__.py
```

- [ ] **Step 2: Rewrite all importers mechanically, then prove zero stragglers**

```bash
grep -rl "app\.integrations\.calendar_integration" app/ --include="*.py" | \
  xargs sed -i '' 's/app\.integrations\.calendar_integration/app.integrations.google_calendar.client/g'
grep -rn "calendar_integration" app/ --include="*.py" | grep -v __pycache__   # expect: only comments/docstrings, fix those too
python -c "from app.main import app; print('imports OK')"
```

- [ ] **Step 3: Write the failing adapter test**

```python
"""GoogleCalendarAdapter: thin, no business logic, fake transport only."""
from unittest.mock import AsyncMock, patch

from app.integrations.base import Capability
from app.integrations.google_calendar.adapter import GoogleCalendarAdapter


def test_identity_and_capabilities():
    a = GoogleCalendarAdapter()
    assert a.name == "google_calendar"
    assert Capability.OBSERVE in a.capabilities
    assert Capability.HEALTH in a.capabilities


async def test_health_reflects_config(monkeypatch):
    a = GoogleCalendarAdapter()
    monkeypatch.setattr(a, "_client_configured", lambda: False)
    status = await a.health()
    assert status.ok is False

    monkeypatch.setattr(a, "_client_configured", lambda: True)
    status = await a.health()
    assert status.ok is True


async def test_observe_wraps_upcoming_events():
    a = GoogleCalendarAdapter()
    fake_events = [{"id": "evt_1", "summary": "Standup", "start": {"dateTime": "2026-07-06T09:00:00Z"}}]
    with patch(
        "app.integrations.google_calendar.adapter.client.list_upcoming_events",
        new=AsyncMock(return_value=fake_events),
    ):
        events = await a.observe("user-1")
    assert len(events) == 1
    assert events[0].source == "google_calendar"
    assert events[0].external_id == "evt_1"
    assert events[0].provenance == "observed"
    assert events[0].payload["summary"] == "Standup"
```

Run: `pytest tests/unit/test_google_calendar_adapter.py -q` → FAIL (`adapter` module missing).

- [ ] **Step 4: Implement `adapter.py`** (adjust the `list_upcoming_events` call signature to the real one in client.py — read it first; the sketch below assumes `(user_id, max_results)`):

```python
"""Adapter facade over the Google Calendar client (ADR-010).

Existing callers (mcp_tools, planner_routes, scheduler) keep calling client
functions directly — unchanged behavior. The adapter is the uniform seam the
State Engine (Phase 1) consumes; per-user OAuth tokens stay in the client's
token store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.integrations import registry
from app.integrations.base import (
    Capability, HealthStatus, IntegrationAdapter, ObservedEvent,
)
from app.integrations.google_calendar import client


class GoogleCalendarAdapter(IntegrationAdapter):
    name = "google_calendar"
    capabilities = Capability.OBSERVE | Capability.HEALTH

    async def configure(self, settings: dict[str, Any]) -> None:
        # OAuth creds come from env via get_settings(); nothing to store here.
        return None

    def _client_configured(self) -> bool:
        s = get_settings()
        return bool(getattr(s, "GOOGLE_CLIENT_ID", "") and getattr(s, "GOOGLE_CLIENT_SECRET", ""))

    async def health(self) -> HealthStatus:
        if not self._client_configured():
            return HealthStatus(ok=False, detail="GOOGLE_CLIENT_ID/SECRET not configured")
        return HealthStatus(ok=True, detail="oauth client configured")

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        raw = await client.list_upcoming_events(user_id, max_results=50)
        now = datetime.now(timezone.utc)
        return [
            ObservedEvent(
                source=self.name,
                kind="event.upcoming",
                external_id=str(e.get("id", "")),
                payload=e,
                observed_at=now,
            )
            for e in raw
        ]


def register_adapter() -> None:
    registry.register(GoogleCalendarAdapter())
```

- [ ] **Step 5: Register at startup** — in `app/main.py` lifespan (read the existing lifespan; add alongside existing startup wiring):

```python
from app.integrations.google_calendar.adapter import register_adapter as register_gcal_adapter
register_gcal_adapter()
```

- [ ] **Step 6: Verify**: `pytest -q` green; `python -c "from app.main import app"` OK; with the stack restarted, re-run the Task 7 calendar probe — identical behavior (same verdicts as the report).

- [ ] **Step 7: Commit** (`refactor(phase0): calendar → integrations/google_calendar + first adapter (behavior-preserving)`).

---

### Task 13: `turbo test` wiring

**Files:**
- Create: `founder-os/apps/api/package.json`
- Modify: `founder-os/turbo.json` (add `test` task)
- Modify: `founder-os/package-lock.json` (regenerated — apps/api joins the `apps/*` workspace automatically)

**Interfaces:**
- Produces: `turbo test` at monorepo root runs the API unit tier. Requires the venv (same precondition `start.sh` already enforces).

- [ ] **Step 1: apps/api/package.json**

```json
{
  "name": "api",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "test": ".venv/bin/python -m pytest -m 'not live' -q"
  }
}
```

- [ ] **Step 2: turbo.json — add after "check-types"**

```json
    "test": {
      "dependsOn": [],
      "cache": false
    },
```

- [ ] **Step 3: Refresh the lockfile and run**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os/founder-os
npm install            # picks up the new workspace member
turbo test 2>&1 | tail -10   # expect the pytest summary, exit 0
```

- [ ] **Step 4: Commit** (`chore(phase0): turbo test → API unit tier`).

---

### Task 14: CI unit tier

**Files:**
- Modify: `.github/workflows/ci.yml` (backend job, after the "Import smoke test" step)

- [ ] **Step 1: Add the step**

```yaml
      - name: Unit tests (pytest, no services needed)
        run: pytest -m "not live" -q
```

(`pytest` is now in `requirements.txt` so the existing install step covers it; the unit tier needs no DB/Redis by design — conftest supplies dummy env.)

- [ ] **Step 2: Verify locally what CI will run**: from `apps/api` with venv: `env -i PATH="$PATH" HOME="$HOME" .venv/bin/python -m pytest -m "not live" -q` → green with no `.env` loaded... if this fails because config demands `.env`, fix conftest defaults (Task 10) rather than skipping.

- [ ] **Step 3: Commit + push branch; confirm the Actions run is green** (`gh run watch` or check `gh run list --branch phase0-foundation-revamp --limit 1`). A red run is a FAIL to fix, not to ignore.

```bash
git add .github/workflows/ci.yml && git commit -m "ci(phase0): run pytest unit tier in backend job"
git push -u origin phase0-foundation-revamp
```

---

### Task 15: Documentation + ADR + roadmap

**Files:**
- Modify: `docs/architecture.md` (new "Integrations framework" + "Testing tiers" sections)
- Modify: `standards/testing.md` (rewrite to pytest reality: tiers, markers, where tests live, how to add one)
- Modify: `docs/decisions.md` (append ADR-010)
- Modify: `docs/roadmap.md` (phase table from the spec; move Phase 0 to `now→done` at close; note measured-split decision)

- [ ] **Step 1: ADR-010 text for `docs/decisions.md`** (append, matching existing ADR format):

```markdown
## ADR-010 — Integration adapter framework (2026-07)

**Context.** Phases 1–4 (Obsidian, Notion, Hermes feed, Paperclip) each need a tool
integration; before Phase 0 there was one ad-hoc module (`calendar_integration.py`)
imported from 4 different places with no common contract.

**Decision.** All external tools integrate via `app/integrations/`: an
`IntegrationAdapter` ABC (`configure/health/observe/sync`, `Capability` flags,
multi-tenant `user_id` per call) + a startup-time registry. Adapter output is
provenance-tagged `observed` `ObservedEvent`s — the State Engine's feed 1 (ADR-009).
Adapters carry no business logic; reconciliation lives in the engine. Google
Calendar is the first adapter; existing callers still use its client functions
directly (behavior-preserving), converging in Phase 1.

**Consequences.** Obsidian (task 011) implements the same ABC. Registry is the
single discovery point (health dashboard later). Rejected: per-tool ad-hoc modules
(status quo — no contract), and a heavyweight plugin system (YAGNI).

**Also decided (Phase 0 measurement).** `models.py` (1029 lines / 32 well-bounded
classes) and `orchestrator.py` (853 lines) were measured and NOT split — clean
boundaries, low churn benefit, high import/Alembic risk. Revisit when a phase
actually has to modify them substantially.
```

- [ ] **Step 2: `standards/testing.md`** — rewrite around: three tiers (`unit` default, `regression`, `live` marker), commands (`pytest`, `pytest -m live`, `turbo test`), file layout (`apps/api/tests/{unit,regression,live}`), rule "every bug fix ships a regression test", CI runs the unit tier.

- [ ] **Step 3: `docs/architecture.md`** — add the integrations section (diagram: adapters → registry → [Phase 1: State Engine reconciler]; today's consumers unchanged) and the testing-tiers section; correct anything the audit proved wrong elsewhere in the doc.

- [ ] **Step 4: `docs/roadmap.md`** — add the 6-phase revamp table under **Now** with Phase 0 `now`, phases 1–5 `next`/`later`; link spec + this plan.

- [ ] **Step 5: Commit** (`docs(phase0): ADR-010, testing standard rewrite, architecture + roadmap update`).

---

### Task 16: Close-out — final verification, task completion, retro

**Files:**
- Modify: `reports/2026-07-03-phase0-audit.md` (final state: every row PASS or FAIL-deferred-with-task or BLOCKED-with-founder-step)
- Move: `tasks/active/012-phase0-foundation-revamp.md` → `tasks/completed/`
- Create: `reports/2026-07-03-phase0-retro.md`
- Modify: `docs/roadmap.md` (Phase 0 → done; Phase 1 → now)

- [ ] **Step 1: Full re-verification (fresh, no stale state)**

```bash
cd /Users/adityaastro/Documents/GitHub/founder-os/founder-os
./start.sh --stop && ./start.sh          # cold restart
cd apps/api && source .venv/bin/activate
pytest -q                                 # unit+regression: ALL green
pytest -m live -q 2>&1 | tail -15         # live tier: matches final report verdicts
cd ../.. && turbo test 2>&1 | tail -5 && turbo lint 2>&1 | tail -5 && turbo check-types 2>&1 | tail -5
gh run list --branch phase0-foundation-revamp --limit 1   # CI green
```

Paste all outputs into the report's final section. Spec success criteria 1–7 each get an explicit ✅/❌ line with evidence — any ❌ blocks close-out.

- [ ] **Step 2: Dispatch eng-reviewer on the full branch diff; then eng-qa against the spec's success criteria.** Findings → fix → re-run Step 1. (Constitution §7 steps 5–6.)

- [ ] **Step 3: Retro per constitution §9** (`reports/2026-07-03-phase0-retro.md`): what slowed us, what knowledge was missing + where it now lives, what should become a skill/agent/workflow. Concrete artifacts only.

- [ ] **Step 4: Move task 012 to completed; roadmap Phase 0 → done, Phase 1 (State Engine + Obsidian, task 011) → now.**

- [ ] **Step 5: Final commit + push** (`chore(phase0): close task 012 — audit final, retro, roadmap advance`). Then present branch-integration options to the founder (merge to main / PR) per superpowers:finishing-a-development-branch.

---

## Self-review notes (done at write time)

- **Spec coverage:** criteria 1 (Task 2/16), 2 (Tasks 1–8), 3 (Task 9), 4 (Tasks 10/13/14), 5 (Tasks 11/12), 6 (Task 15), 7 (global constraints + Task 16). Stage-3c "measure first" resolved: measurements done during planning (models.py 1029/32 classes, orchestrator.py 853, routes.py 57) — decision: no splits, recorded in ADR-010 text (Task 15).
- **Known unknowns, stated honestly:** Stage 2 fixes cannot be pre-coded (audit-dependent) — Task 9 is a fully-specified protocol with exit criteria instead of fake concrete fixes. Route paths in Tasks 5/7/8 include the grep to find the real path where uncertain. Task 12 Step 4 flags the one signature to read before implementing.
- **Type consistency:** `Capability/HealthStatus/ObservedEvent/SyncResult/IntegrationAdapter` signatures identical in Task 11 interfaces, Task 11 code, and Task 12 consumer code. Marker name `live` consistent across Tasks 10/13/14.
