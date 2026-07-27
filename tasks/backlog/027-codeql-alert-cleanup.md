---
id: 027
title: Resolve pre-existing CodeQL alerts (critical SSRF + cleanup)
status: backlog          # backlog | in-progress | blocked | review | done
stage: security          # product | planner | architect | executor | reviewer | qa | security
owner: eng-security      # the agent currently responsible
created: 2026-07-27
dependencies: []
links: [standards/security.md, skills/security_audit.md, "https://github.com/adityaastro2004/founder-os/security/code-scanning"]
---

# 027 — Resolve pre-existing CodeQL alerts (critical SSRF + cleanup)

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective
The repo carries ~20 open CodeQL code-scanning alerts that predate the ADR-017
orchestrator work (surfaced while triaging PR #35's CodeQL check). Triage and clear
them so the CodeQL results check goes green and can be promoted to a required gate.
The headline item is a **critical `py/partial-ssrf`** in the Gemini fallback path.

## User stories  <!-- eng-product -->
- As the founder, I want the critical SSRF alert triaged so an attacker can't coerce
  the backend into requesting attacker-controlled URLs via the LLM provider path.

## Acceptance criteria
- [ ] **Critical**: `app/agents/llm.py:823` `py/partial-ssrf` — confirm whether the URL
      is attacker-influenced; fix (allowlist/validate host) or dismiss with a written
      justification if it is a false positive (base URL is config-only).
- [ ] **Medium**: `py/log-injection` (`settings_routes.py:526`, `approval.py:381`) and
      `py/stack-trace-exposure` (`routes.py:36`, `planner_routes.py:1336`) — sanitize
      via the existing `log_sanitize`/`sl` helper or scrub the response.
- [ ] **Low/notes**: `py/file-not-closed`, `py/unused-import`, `py/empty-except`,
      `py/implicit-string-concatenation-in-list` — fix or dismiss in bulk.
- [ ] The CodeQL results check is green on a clean PR (no open non-dismissed alerts).

## Success metrics  <!-- eng-product -->
- CodeQL results check passes; consider adding it to branch protection alongside
  `ci-success`.

## Out of scope
- Dependabot dependency alerts (separate track; dependency-review already gates new
  high+ vulnerable deps in CI).
- Anything introduced by ADR-017 (that PR added zero new alerts — verified).

## Requirements / open questions  <!-- eng-planner -->
- Run the [security_audit](../../skills/security_audit.md) skill for the SSRF item;
  cross-check against the 2026-07-16 SSRF guard (memory: security-hardening) — the
  guard may already cover this, making the alert dismissible.
- Decide dismiss-vs-fix per alert; record dismissals with a reason in the GitHub UI.
- Batch the low/note fixes into one PR; keep the SSRF fix isolated for review.

---

## Security report  <!-- eng-security; required if change touches auth/secrets/approval/input -->
- [critical] app/agents/llm.py:823 — py/partial-ssrf → validate/allowlist the request host, or dismiss if base URL is config-only.
- Verdict (Pass/Fail): (pending audit)
