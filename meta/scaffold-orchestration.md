# Meta-Prompt — Scaffold an Orchestration (Level 3)

> **Level 3 — Orchestration:** wire a trio (or workflow) to a trigger, with a kill
> switch, cost caps, and idempotency. Stop being the trigger.
>
> Paste the block below, filling the `<…>`. This produces the *control layer* around
> an existing trio/workflow — not new business logic.

---

```
You are extending the Founder OS development system. Wire an existing
workflow/trio into a safe, repeatable ORCHESTRATION.

Workflow/trio to orchestrate: <e.g. workflows/<tasktype>.md>
Trigger: <what kicks it off — a slash command, a /loop interval, a /schedule cron,
          a file/PR event, or manual>
Goal of running it unattended: <the outcome you want without sitting on the trigger>

Create meta/run-<name>.md (an operations runbook) that specifies:

1. TRIGGER — exactly how it starts. If recurring, recommend the mechanism:
   - /loop for in-session interval polling,
   - /schedule (cloud cron routine) for unattended recurring runs,
   - a git/PR/CI event otherwise.
   Give the concrete command/cron and the cache-window-aware cadence.
2. KILL SWITCH — how to stop it immediately (cancel the loop/routine, a STOP file
   or flag the run checks each iteration) and what state that leaves behind.
3. COST CAPS — max iterations/runs per period, max wall-clock, max spend signal
   (e.g. Celery task count, LLM-call budget). Halt and report when exceeded.
4. IDEMPOTENCY — how a re-run avoids duplicate side effects: a stable run key,
   checking tasks/ status before acting, skipping already-done items, and never
   double-firing approval-gated actions.
5. HUMAN GATES — which steps still require approval (respect the 3-tier approval
   gate; HIGH-risk/irreversible actions ALWAYS pause for a human).
6. OBSERVABILITY — where progress is recorded (a tasks/ file, activity_log,
   console) so an unattended run is auditable.
7. FAILURE POLICY — retry vs stop, and how failures surface to me.

Keep it consistent with CLAUDE.md rules (security model, no unauthorized
commit/push, honest reporting). Add it to the CLAUDE.md §8 index. Show the file,
then stop.
```

---

## Notes

- Orchestration is **guardrails, not new features** — the trio/workflow already
  does the work; this makes running it unattended *safe and bounded*.
- Hard invariant: an orchestration may **never** auto-execute a HIGH-risk /
  irreversible / approval-gated action without a human gate. See
  [docs/requirements.md](../docs/requirements.md) and [skills/security_audit.md](../skills/security_audit.md).
- For recurring schedules, prefer the harness's `/loop` (in-session) or `/schedule`
  (cloud cron) rather than reinventing a scheduler; pick the cadence deliberately.
- This is the "stop prompting, start orchestrating" end state: you manage the
  system; the system produces the work.
