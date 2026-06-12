# Orchestration Runbook — Nightly Test Sweep

> **Level 3 orchestration** (generated from [scaffold-orchestration.md](scaffold-orchestration.md)).
> Wraps the repo's standalone test scripts into a safe, repeatable, unattended run:
> a trigger, a kill switch, cost caps, idempotency, human gates, observability, and
> a failure policy. The work itself is just running tests + the [debug](../skills/debug.md)
> skill — this file is the **guardrails** around running it without you sitting on the trigger.
>
> **Invariant:** this orchestration is **report-only**. It never edits product code,
> never commits/pushes, never auto-fixes. It produces a triaged failure report.

---

## What it does (one pass)

1. Bring up infra and the venv.
2. Run each test script, capturing pass/fail + output.
3. For any failure, run the [debug](../skills/debug.md) skill to root-cause (read-only).
4. Write a dated report to [tasks/](../tasks/) and stop. You wake up to a triaged list.

### The sweep set (real, current)

Run from `founder-os/apps/api/` with `.venv` active:

```
test_e2e_pipeline.py        # end-to-end agent pipeline (mock LLM)
test_system.py              # system tests
test_memory.py              # memory system
test_rag_pipeline.py        # RAG pipeline
test_content_agent.py       # content agent
app/crawler/test_crawler.py # crawler
```

**Excluded:** `app/api/test_routes.py` — that's the dev-only FastAPI *router*, not a
test. Do not run it as a script.

Each script already `sys.exit(1)` on failure, so exit code is the pass/fail signal.

---

## 1. TRIGGER

Unattended recurring run via a cloud cron routine. **You** create it once (the
orchestration can't schedule itself):

```
/schedule create a nightly routine at 02:00 IST that executes
meta/run-nightly-test-sweep.md
```

The routine's prompt is simply: *"Execute the runbook at
meta/run-nightly-test-sweep.md. Follow its caps, idempotency, and report-only rule."*

- **Cadence:** once/night. 02:00 IST avoids the Mon-08:00 weekly-planner scheduler.
- For an in-session ad-hoc run instead: just say *"run the nightly test sweep"*.

## 2. KILL SWITCH

Any one of these stops it immediately:

- **Cancel the routine** — `/schedule` → disable/delete the nightly routine.
- **STOP file** — if `tasks/.sweep-stop` exists, the run aborts at the top of the
  pass before touching infra and writes a one-line "aborted: STOP file" report.
- **Mid-run** — interrupt the session; because the run is report-only and writes
  the report last, a half-run leaves no partial product-code state — only Docker
  containers may be left up (see cleanup below).

## 3. COST CAPS

Halt and report if any cap is hit:

- **1 run per night** (idempotency key below enforces no double-runs).
- **Wall-clock ≤ 20 min** for the whole sweep. If exceeded, kill the current
  script, mark remaining scripts `SKIPPED (cap)`, and write the partial report.
- **Per-script timeout ≤ 5 min** (`timeout 300 python <script>`); a hung script is
  recorded as `TIMEOUT`, not left running.
- **Debug budget:** root-cause at most the **first 3** distinct failures per night
  (the debug skill is read-only but token-costly). List the rest as
  `FAIL (untriaged)`.
- **No live paid LLM/API** — tests mock the LLM; if a script tries to hit a live
  provider, record it as an environment issue, don't spend.

## 4. IDEMPOTENCY

- **Run key** = short `git rev-parse HEAD` + date. Before running, check for an
  existing `tasks/NNN-sweep-<date>.md`; if one exists for the same HEAD, **skip**
  ("no change since last green/known run") and exit.
- Re-running the same night re-uses (overwrites) that day's report rather than
  creating duplicates.
- The sweep has **no side effects** on product data beyond what the tests
  themselves do (they mock IO); it never writes to prod tables.

## 5. HUMAN GATES

- **Report-only, always.** The orchestration **never** applies a fix, edits product
  code, runs Alembic, or commits/pushes. Fixes are your call.
- Any failure whose root cause implies a HIGH-risk / approval-gated change is
  flagged in the report and **left for a human** — consistent with the 3-tier
  approval gate ([docs/requirements.md](../docs/requirements.md),
  [skills/security_audit.md](../skills/security_audit.md)).

## 6. OBSERVABILITY

- **Primary artifact:** `tasks/NNN-sweep-<YYYY-MM-DD>.md` (from
  [tasks/TEMPLATE.md](../tasks/TEMPLATE.md)) containing:
  - run key (HEAD + timestamp), total PASS/FAIL/SKIP/TIMEOUT,
  - per-script result + the tail of failing output,
  - for triaged failures: the debug skill's root cause + suggested fix (no fix applied),
  - caps hit / scripts skipped.
- Set the file `status: done` (all green) or `status: review` (failures to triage).
- Console output during the run is the live log; the task file is the durable record.

## 7. FAILURE POLICY

- **A failing test is the expected output**, not an error — triage and report it.
- **Infra/setup failure** (Docker down, `.venv` missing, import error): do **not**
  retry blindly. Write a report with `status: blocked` naming the setup problem and
  the fix command, then stop.
- **No flaky-retry of product tests** — a failure is reported as-is; re-running to
  "see if it passes" hides real flakiness. If a test is genuinely flaky, note it as
  a finding for a human to stabilize.

---

## Execution checklist (what a run actually does)

```bash
# 0. Kill switch + idempotency
[ -f tasks/.sweep-stop ] && echo "aborted: STOP file" && exit 0
cd founder-os/apps/api && source .venv/bin/activate
HEAD=$(git rev-parse --short HEAD)        # part of the run key

# 1. Infra (tests need Postgres + Redis even with mocked LLM)
( cd .. && docker compose up -d )

# 2. Sweep (5 min/script cap; capture rc)
for t in test_e2e_pipeline.py test_system.py test_memory.py \
         test_rag_pipeline.py test_content_agent.py app/crawler/test_crawler.py; do
  timeout 300 python "$t"   # rc 0=pass, non-zero=fail, 124=timeout
done

# 3. For up to 3 failures → skills/debug.md (read-only root cause)
# 4. Write tasks/NNN-sweep-<date>.md (report-only) and stop.
#    Optionally: ( cd .. && docker compose down )  # if you don't want infra left up
```

> Added to the system index in [CLAUDE.md](../CLAUDE.md) §8. To make it recurring,
> run the `/schedule` command in §1 — until you do, it's a manual "run the nightly
> test sweep" away.
