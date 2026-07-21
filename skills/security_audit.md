# Skill — Security Audit

> Reusable capability. Trigger for a security review/audit, auth/permissions change,
> or anything touching secrets, the approval gate, or external input. Native
> auto-trigger: `.claude/skills/security_audit/`. Enforces the policy in
> [standards/security.md](../standards/security.md).

## Goal

Find security weaknesses in a change before it ships, tuned to this stack's model
(Clerk JWT auth + 3-tier approval gate + OSS/local-first).

## Checklist

### Authentication & authorization
- Every non-public route depends on `require_auth` (`app/auth.py`); `optional_auth`
  only where genuinely public. No route silently unauthenticated.
- All queries are **scoped to `user.user_id`**. The caller's identity comes from the
  verified JWT, never from a request-body id.
- JWT verification untouched: RS256, issuer check, JWKS validation intact.
- `test_routes.py` (unauthenticated) stays dev-only (`APP_ENV=development`); no
  production logic added to it.

### Approval gate (the load-bearing control)
- MEDIUM/HIGH-risk tool actions route through `ApprovalGate` (`app/agents/approval.py`)
  and respect `approval_preferences`.
- **No path executes a HIGH-risk / irreversible action without human approval.**
  Risk tiers are never downgraded to "make it work".

### Secrets & config
- No secrets, API keys, tokens, or full JWTs in code, logs, or committed files.
- All config via `config.py` / `.env`; `.env` is never committed.

### Input handling
- Request bodies validated by Pydantic. SQL via the ORM / parameterized queries —
  no string-built SQL. User input never interpolated into shell/LLM-tool calls unsafely.
- CORS origins come from settings; not widened to `*` with credentials.

### Provider & dependency
- LLM access via `app/agents/llm.py`; no vendor key leakage or hardcoded endpoints.
- New dependencies justified and from trusted sources.

## Process

1. Identify the attack surface the change touches (auth, data access, tools, input).
2. Walk the checklist against the diff; read the real code, don't assume.
3. For each finding: severity, `file:line`, the risk, and the fix.
4. Confirm no regression to auth or the approval gate.

## Never

- Never weaken auth or bypass the approval gate for convenience.
- Never log or echo secrets to demonstrate a point.
- Never approve a change that introduces an unauthenticated or ungated sensitive action.

## Output

Ranked findings (blocker / should-fix / nit) with `file:line` and fixes, plus an
overall verdict. Feed blockers back to the [executor](../.claude/agents/eng-executor.md).
