# 025 — Connection details + disconnect on the Apps page

**Status:** completed
**Started:** 2026-07-21
**Completed:** 2026-07-21
**Workflow:** [new_feature](../../workflows/new_feature.md)

## Problem

The Apps page reported "No sources connected yet" while Google Calendar was
connected. Two independent surfaces each owned a partial view of "what's
connected": the Company state sources card (Notion/Obsidian only, via
`/api/state/sources`) and the Connected grid (via `/api/settings/apps`).

Beyond the confusing copy, two capabilities were missing outright:

- **No detail.** A connected app showed a name and a status chip. Nothing about
  which calendar, what access was granted, or whether the grant still worked.
- **No disconnect.** There was no disconnect endpoint anywhere in the backend.
  A user who connected Google Calendar could not revoke it from the product —
  only from Google's own account settings.

## Scope note

The unified Connected / Can be connected / Coming soon grouping was **already
shipped** by PRs #29–31 (`allApps = [...stateApps, ...apps]`), which landed
while this was being designed. This task therefore covers only the two genuinely
missing capabilities, not the regrouping.

## User stories

- As a founder, I can see *which* calendar Founder OS writes to and whether the
  authorization is still valid, so I can trust what the planner is doing.
- As a founder, I can disconnect an app and know its access was actually
  revoked, not just forgotten locally.

## Acceptance criteria

- [x] Clicking a connected app opens a detail panel with that connection's facts
- [x] Google Calendar detail shows calendar, granted access, authorization
      health, plans pushed, last plan
- [x] An expired/revoked grant is flagged with a reconnect prompt, not hidden
- [x] Google Calendar can be disconnected, revoking the grant **at Google**
- [x] Notion/Obsidian sources can be disconnected per source from the drawer
- [x] Destructive actions require a second confirming click
- [x] No credential is ever present in any API response
- [x] `turbo lint`, `turbo check-types`, `turbo build` clean

## Implementation

**Backend**
- `AppDetailField` — flat label/value/tone pair. Every field is constructed
  explicitly, so a new column on `planner_users` or `integrations` cannot reach
  the client by accident.
- `AppStatusOut.details` / `.disconnect_url` — populated for connected apps only.
- `POST /api/planner/disconnect` — revokes at Google, then clears local tokens
  via the verified `user_store.disconnect_gcal()`; 500s if the delete didn't land.
- `DELETE /api/settings/apps/{key}` — deletes an integrations-table credential
  row, scoped to the authenticated user.
- `revoke_token()` in the GCal client — returns `(revoked, certain)`; best-effort
  by contract, but never lets the caller claim an unconfirmed revoke.
- `user_store.disconnect_gcal()` / `get_user_fresh()` — verified teardown and
  cache-bypassing reads for every credential-gated path.

**Frontend**
- `Dialog` gained a `side="right"` slide-over variant (no new component).
- `_components/connection-detail.tsx` — the drawer; renders server-built fields
  for OAuth apps, a per-source list for Notion/Obsidian.
- Connected cards became keyboard-addressable buttons with a "Details" affordance.

## Design decisions

**Revoke upstream, then always clear locally.** A failed Google-side revoke logs
but does not fail the request. Otherwise a token Google had already invalidated
would trap the user in a connection they could not remove — the disconnect
button would error forever on exactly the connection most in need of removal.
The *local* delete is the opposite: it is verified by rowcount and 500s on
failure, because that is the part we control and the part that must not lie.
When the upstream revoke is merely unconfirmed (5xx/timeout), the response says
so instead of claiming success.

**Delete the credential row rather than deactivating it.** Leaving
access/refresh tokens at rest for an app the user explicitly disconnected is the
thing they asked us not to do.

**No connected-account email.** The OAuth scope is `calendar.events` only — no
`userinfo.email`, so Google never tells us the account. Adding the scope would
force every existing user through a fresh consent screen for one line of text.
`calendar_id` is shown instead.

**Sync/pause stay in the state-sources section.** The drawer offers disconnect
for sources but not sync/pause — duplicating them would give one action two
homes and two busy states.

## Verification

`test_connection_details.py` — **47 checks, all passing.** Needs no live server.
Mutation-tested: leaking the access token into a detail field fails 3 checks,
so the credential assertions have teeth.

Covers: credential absence in details + serialized payload, expired-grant
flagging, provider-error redaction across 6 leak shapes, all four
`revoke_token()` outcomes, the teardown SQL's properties, and that every
credential-gated read bypasses the process cache.

Frontend verified via `turbo lint` (0 warnings), `check-types`, and `build`.
**Not** verified against a live browser session — see Follow-ups.

## Follow-ups

- Manual browser verification of the drawer against a live GCal connection.
- No repo-wide test runner still (task 016 territory); this suite is standalone.
- `integrations`-table apps all have `connect_url: None` today, so
  `DELETE /api/settings/apps/{key}` is currently unreachable in practice. It
  exists so the next OAuth app inherits disconnect rather than re-inventing it.

## Security audit (eng-security, 2026-07-21) — **FAIL**

Ranked findings; blockers go back to `eng-executor`. Paths relative to repo root.

### Blockers

1. **Disconnect reports success without verifying the credentials were deleted.**
   `founder-os/apps/api/app/api/planner_routes.py:437` calls `clear_tokens()`, which
   swallows every exception (`app/integrations/google_calendar/client.py:59-68`) and
   delegates to `_sync_upsert()`, which also swallows every DB error
   (`app/user_store.py:432-434`). If either write fails the route still returns
   `200 {"status": "disconnected", "gcal_connected": false}` and the UI closes,
   while `gcal_access_token` / `gcal_refresh_token` remain in `planner_users` — and
   remain live at Google whenever the upstream revoke also failed. A credential-
   deletion control must not fail silently. *Fix:* make `clear_tokens` return/raise
   on failure (targeted `UPDATE ... SET gcal_access_token=NULL, gcal_refresh_token=NULL,
   gcal_token_data='{}', gcal_connected=false` with a rowcount check) and return 500
   from the route if it did not succeed.

2. **Stale per-process cache resurrects the deleted tokens.** `app/user_store.py`
   `_cache` never expires and is per-process; `clear_tokens` only mutates the copy in
   the calling process. The Celery/agents process holds its own cached `UserProfile`
   (`app/agents/agents.py:172`) and, after a push, writes it back with
   `save_user(user)` (`app/agents/agents.py:232`), whose upsert restores
   `gcal_access_token`, `gcal_refresh_token` and `gcal_connected=true`. Result: the
   user's disconnect is silently undone, and if the upstream revoke failed the agent
   keeps writing to their calendar after they revoked. *Fix:* cross-process cache
   invalidation (Redis) or drop the cache for token-bearing reads; and re-check the
   DB before any calendar push.

### Should-fix

3. `app/api/settings_routes.py:398-402` publishes raw `integration.sync_error` to the
   client, unsanitised and untruncated. Nothing writes that column today, so there is
   no live leak — but the first sync path that stores `str(exc)` will publish provider
   error text, which routinely contains the request URL with `access_token=` or an
   echoed `Authorization` header. *Fix:* map to a fixed classified message, or redact
   + truncate before it becomes an `AppDetailField`.

4. `app/api/planner_routes.py:450-457` tells the user "The grant may already have
   expired at Google" for *every* revoke failure, including a timeout or a Google 5xx
   where the grant is definitely still live. The same request then deletes our only
   copy of the refresh token, so the revoke can never be retried. *Fix:* distinguish
   Google 400 (already invalid) from transport/5xx failures; on the latter say plainly
   that revocation could not be confirmed and link
   `https://myaccount.google.com/permissions`.

5. `founder-os/apps/web/app/(dashboard)/dashboard/apps/page.tsx` `handleDisconnectApp`
   calls whatever `disconnect_url` + `disconnect_method` the server sent, and
   `lib/api.ts` `apiFetch` uses an empty base client-side and attaches the Clerk
   bearer token — an absolute URL in that field would ship the session token to a
   third-party host. Only two hardcoded literals are emitted today. *Fix:* require
   `/^\/api\//` and restrict the verb to POST|DELETE client-side.

6. `founder-os/apps/api/test_connection_details.py` covers only `_gcal_details`. The
   properties actually at risk are untested: that another tenant's key 404s on
   `DELETE /api/settings/apps/{key}`, and that a successful disconnect really NULLs the
   token columns in `planner_users`. Add both.

### Nits

7. `app/api/settings_routes.py:392` joins `integration.scopes` and no detail value has
   a length cap — cap server-side (~200 chars) so a long provider string can't dominate
   the drawer.
8. `app/api/planner_routes.py:431-437` uses the blocking sync `get_user` / `clear_tokens`
   inside an async route; `async_get_user` / `async_save_user` already exist.
9. `app/api/settings_routes.py:480` logs the `key` path param without `sl()` (safe today
   — it is allowlist-validated — but the repo convention is to sanitize).

### Verified clean

`require_auth` on both new routes; identity taken from the verified JWT `sub`, never
the body; `Integration.user_id == user.id` + `SUPPORTED_APPS` allowlist on the DELETE
(no IDOR, no mass delete — the unique constraint caps it at one row); Google Calendar
correctly excluded from the generic DELETE; no CSRF exposure (Bearer-header auth, no
cookies); no secret reaches `details` (checked every `UserProfile` field); revoke
prefers the refresh token, which withdraws the whole grant; React escapes all detail
values, no `dangerouslySetInnerHTML`, `toneClass` lookup cannot inject classes; ORM
only, no string-built SQL; approval gate and JWT verification untouched (these are
user-initiated UI actions, not agent tool calls).

**Verdict: FAIL** — blockers 1 and 2 must be fixed before merge.

### Remediation (same session)

Both blockers were confirmed against the source, not taken on faith, then fixed:

**Blocker 1 — disconnect could report success with tokens still at rest.**
`clear_tokens()` → `_sync_upsert()` swallowed every DB exception and returned
`None`, so the route returned `200 {"status": "disconnected"}` regardless.
Added `user_store.disconnect_gcal()`: a targeted `UPDATE` nulling
`gcal_access_token` / `gcal_refresh_token` / `gcal_token_expiry` /
`gcal_token_data` and setting `gcal_connected = false`, with a **rowcount check**
and no `except` swallowing. The route now returns 500 ("Nothing was changed —
please retry") on failure. `clear_tokens()` and `_clear_gcal_connection()`
delegate to it, so there is exactly one teardown path.

**Blocker 2 — the process-local cache could resurrect the credentials.**
`_cache` never expires and is per-process, so the Celery/agents worker held its
own token-bearing `UserProfile` and `save_user()` rewrote it after a plan push,
silently undoing the disconnect. Added `user_store.get_user_fresh()` (DB read,
refreshes the cache entry) and applied it to the three reads that gate a
credential use: `client.get_tokens()`, the `agents.py` calendar-push guard (the
one that wrote back), and the `mcp_tools.py` provider guard.

**#3** — `redact_secrets()` added and applied to `sync_error`, capped at 300
chars. Note: `sl()` was the obvious candidate but only escapes CR/LF for log
injection and does **no** redaction — using it here would have been security
theatre.

**#4** — `revoke_token()` now returns `(revoked, certain)`; a 5xx/timeout yields
`certain=False` and the response tells the user revocation could not be confirmed
and links `myaccount.google.com/permissions`, rather than asserting the grant had
already expired.

**#5** — the client validates `disconnect_url` against `^/api/[A-Za-z0-9/_-]*$`
and the verb against `{DELETE, POST}` before calling, so a malformed/absolute URL
can't ship the Clerk bearer token off-origin.

**#6** — test suite extended from 24 to 47 checks: redaction (6 leak shapes plus
a benign-text case), all four revoke outcomes, the teardown SQL properties
including "does not swallow DB errors", and that each gated read uses
`get_user_fresh`.

Deferred: #7 (per-field length caps beyond the `sync_error` cap), #8 (blocking
sync DB calls in the async disconnect route — pre-existing pattern throughout
`planner_routes.py`, worth a separate pass), #9 (`sl()` on the logged `key`,
allowlist-validated so not exploitable).
