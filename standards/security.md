# Security Standards — Founder OS

> The **policy** (the rules every change must satisfy). The audit *process* that
> enforces it is [skills/security_audit.md](../skills/security_audit.md); the
> [security agent](../agents/security.md) runs it. Non-negotiable.

## Authentication & authorization

- Every user-facing route depends on `require_auth` (`app/auth.py`). `optional_auth`
  only for genuinely public endpoints, with a stated reason.
- The caller's identity is the **verified JWT `sub`** (`ClerkUser.user_id`) — never
  an id taken from the request body/query. Scope every query by `user_id`.
- JWT verification stays RS256 with issuer + JWKS validation. Don't disable
  `verify_aud` unless `CLERK_AUDIENCE` is intentionally unset.
- `app/api/test_routes.py` is unauthenticated and **dev-only** (`APP_ENV=development`).
  Never add production logic there or enable it in prod.

## Approval gate (load-bearing control)

- MEDIUM/HIGH-risk tool actions route through `ApprovalGate` (`app/agents/approval.py`)
  and honor `approval_preferences` (always_allow / ask / always_deny).
- **No code path may execute a HIGH-risk / irreversible / externally-visible action
  without human approval.** Risk tiers are never downgraded to unblock a flow.

## Secrets & configuration

- No secrets, API keys, tokens, or full JWTs in code, logs, error messages, or
  committed files. `.env` is never committed.
- All config flows through `app/config.py` (`pydantic-settings`); never read
  `os.environ` ad hoc or hardcode credentials/URLs/model names.

## Input handling

- Validate request bodies with Pydantic. Use the ORM / parameterized queries — no
  string-built SQL. Never interpolate untrusted input into shell or LLM-tool calls
  unsafely.
- CORS origins come from settings; never `allow_origins=["*"]` together with
  `allow_credentials=True`.

## Provider & dependencies

- All LLM access via `app/agents/llm.py`; no vendor SDK in business logic, no
  hardcoded endpoints, no key leakage across providers.
- New dependencies must be justified and from trusted sources; prefer what's already
  in `requirements.txt` / `package.json`.

## Severity & gating

- Findings are ranked **blocker / should-fix / nit**. A **blocker** fails the
  security gate and blocks [release](../workflows/release.md).
- The [QA](../agents/qa.md) and [reviewer](../agents/reviewer.md) also check these,
  but a sensitive change gets a dedicated [security](../agents/security.md) pass.

See also: [docs/requirements.md](../docs/requirements.md) (the 3-tier model and
known gaps).
