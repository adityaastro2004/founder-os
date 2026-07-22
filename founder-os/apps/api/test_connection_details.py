"""Connection detail / disconnect tests (task 025).

Unlike most test_*.py here these need no live server — they pin the security
property of the feature (credentials must never reach the client) at the unit
level, where it can be checked deterministically.

Run: python3 test_connection_details.py
"""
from __future__ import annotations

import sys
import textwrap
import time

from app.api.settings_routes import AppDetailField, AppStatusOut, _gcal_details
from app.user_store import UserProfile

FAKE_ACCESS = "ya29.FAKE-ACCESS-TOKEN-SHOULD-NEVER-BE-RENDERED"
FAKE_REFRESH = "1//FAKE-REFRESH-TOKEN-SHOULD-NEVER-BE-RENDERED"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{' — ' + detail if detail else ''}")
        failures.append(name)


def connected_user() -> UserProfile:
    user = UserProfile(user_id="test-user", calendar_id="primary")
    user.store_gcal_tokens({
        "access_token": FAKE_ACCESS,
        "refresh_token": FAKE_REFRESH,
        "expires_in": 3600,
    })
    user.plan_count = 7
    user.last_plan_at = "2026-07-20T08:00:00+05:30"
    user.last_plan_events = 12
    return user


print("\n1. _gcal_details never renders a credential")
user = connected_user()
fields = _gcal_details(user)
blob = " ".join(f"{f.label} {f.value}" for f in fields)

check("access token absent", FAKE_ACCESS not in blob)
check("refresh token absent", FAKE_REFRESH not in blob)
check("no bare 'ya29.' prefix", "ya29." not in blob)
check("returns fields", len(fields) > 0, f"got {len(fields)}")
check("all entries are AppDetailField",
      all(isinstance(f, AppDetailField) for f in fields))

print("\n2. Detail content is the useful, non-secret facts")
labels = {f.label for f in fields}
for expected in ("Calendar", "Access", "Authorization", "Plans pushed"):
    check(f"has {expected!r}", expected in labels, f"labels={sorted(labels)}")

by_label = {f.label: f for f in fields}
check("calendar id surfaced", by_label["Calendar"].value == "primary")
check("plan count surfaced", by_label["Plans pushed"].value == "7")
check("valid token reads as success",
      by_label["Authorization"].tone == "success",
      by_label["Authorization"].tone)

print("\n3. Expired grant is flagged, not hidden")
stale = connected_user()
# Expired access token AND no refresh token => has_valid_gcal_tokens() is False.
stale.gcal_tokens = {"access_token": FAKE_ACCESS,
                     "expires_in": 3600,
                     "stored_at": time.time() - 7200}
stale_fields = {f.label: f for f in _gcal_details(stale)}
check("authorization flagged warning",
      stale_fields["Authorization"].tone == "warning",
      stale_fields["Authorization"].tone)
check("expired copy tells user to reconnect",
      "reconnect" in stale_fields["Authorization"].value.lower())

print("\n4. AppStatusOut exposes no credential-shaped field")
payload = AppStatusOut(
    key="google_calendar", display_name="Google Calendar", description="d",
    category="Productivity", icon="calendar", status="connected",
    is_active=True, details=fields,
    disconnect_url="/api/planner/disconnect",
).model_dump()

serialized = str(payload)
check("serialized payload has no access token", FAKE_ACCESS not in serialized)
check("serialized payload has no refresh token", FAKE_REFRESH not in serialized)
for banned in ("access_token", "refresh_token", "token_expires_at", "scopes"):
    check(f"no {banned!r} key on the model", banned not in payload)
check("disconnect_url present when connected",
      payload["disconnect_url"] == "/api/planner/disconnect")

print("\n5. Disconnected calendar offers no disconnect URL")
disconnected = AppStatusOut(
    key="google_calendar", display_name="Google Calendar", description="d",
    category="Productivity", icon="calendar", status="disconnected",
    is_active=False,
).model_dump()
check("no disconnect_url", disconnected["disconnect_url"] is None)
check("no details", disconnected["details"] == [])

print("\n6. Provider error text is redacted before reaching the client")
from app.api.settings_routes import redact_secrets

leaky = [
    ("query param", f"GET /events?access_token={FAKE_ACCESS} failed", FAKE_ACCESS),
    ("bearer header", "401 {'Authorization': 'Bearer ya29.SEKRIT-VALUE'}", "ya29.SEKRIT-VALUE"),
    ("google refresh", f"refresh failed for {FAKE_REFRESH}", FAKE_REFRESH),
    ("json field", '{"refresh_token": "1//abcdefghijklmnop"}', "1//abcdefghijklmnop"),
    ("notion token", "auth failed: ntn_abc123def456ghi", "ntn_abc123def456ghi"),
    ("client secret", "client_secret=GOCSPX-abc123def456", "GOCSPX-abc123def456"),
]
for name, raw, secret in leaky:
    cleaned = redact_secrets(raw)
    check(f"{name} redacted", secret not in cleaned, f"got {cleaned!r}")

check("benign error text survives",
      redact_secrets("Calendar quota exceeded, retry in 60s")
      == "Calendar quota exceeded, retry in 60s")

print("\n7. Revoke outcomes are distinguishable (never claim an unconfirmed revoke)")
import asyncio
import app.integrations.google_calendar.client as gcal_client


class _FakeResponse:
    def __init__(self, status_code): self.status_code = status_code


def _fake_client(status=None, raises=False):
    class _Ctx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            if raises:
                raise RuntimeError("network down")
            return _FakeResponse(status)
    return lambda *a, **k: _Ctx()


original = gcal_client.httpx.AsyncClient
try:
    gcal_client.httpx.AsyncClient = _fake_client(status=200)
    check("google 200 => revoked & certain",
          asyncio.run(gcal_client.revoke_token("tok")) == (True, True))

    gcal_client.httpx.AsyncClient = _fake_client(status=400)
    check("google 400 => not revoked but certain (already invalid)",
          asyncio.run(gcal_client.revoke_token("tok")) == (False, True))

    gcal_client.httpx.AsyncClient = _fake_client(status=503)
    check("google 5xx => UNCERTAIN, must not claim revoked",
          asyncio.run(gcal_client.revoke_token("tok")) == (False, False))

    gcal_client.httpx.AsyncClient = _fake_client(raises=True)
    check("network failure => UNCERTAIN, must not claim revoked",
          asyncio.run(gcal_client.revoke_token("tok")) == (False, False))
finally:
    gcal_client.httpx.AsyncClient = original

print("\n8. Disconnect teardown is a verified, targeted delete")
import inspect
from app.user_store import disconnect_gcal

src = inspect.getsource(disconnect_gcal)
check("nulls the access token", "gcal_access_token = NULL" in src)
check("nulls the refresh token", "gcal_refresh_token = NULL" in src)
check("clears the token blob", "gcal_token_data" in src)
check("flips gcal_connected false", "gcal_connected = false" in src)
check("checks rowcount rather than assuming", "rowcount" in src)
check("evicts the process-local cache", "_cache.pop" in src)
check("does NOT swallow DB errors",
      "except Exception" not in src,
      "a bare except would let a failed delete report success")

print("\n9. Credential-gated reads bypass the stale process cache")
# Asserted per call site via AST, not by substring: a file-level `"get_user_fresh"
# in body` check passes as soon as ANY line mentions the symbol, which is how
# registry.py's stale guard survived the first sweep.
import ast


def resolves_user_read(path: str, func_name: str) -> tuple[bool, str]:
    """Return (uses_only_fresh, detail) for the named function's user_store reads."""
    tree = ast.parse(open(path).read())
    target = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == func_name),
        None,
    )
    if target is None:
        return False, f"function {func_name!r} not found in {path}"

    imported: list[str] = []
    for node in ast.walk(target):
        if isinstance(node, ast.ImportFrom) and node.module == "app.user_store":
            imported.extend(a.name for a in node.names)
    if not imported:
        return False, "no app.user_store import inside the function"
    stale = [n for n in imported if n == "get_user"]
    if stale:
        return False, f"imports cached {stale} — must use get_user_fresh"
    if "get_user_fresh" not in imported:
        return False, f"imports {imported}, expected get_user_fresh"
    return True, ",".join(imported)


gated = [
    ("app/integrations/google_calendar/client.py", "get_tokens", "every Google API call"),
    ("app/agents/agents.py", "_push_plan_to_gcal_if_applicable", "calendar push guard"),
    ("app/agents/mcp_tools.py", "get_providers", "calendar provider guard"),
    ("app/agents/registry.py", "_check_conflicts_impl", "conflict-check guard"),
]
for path, func, what in gated:
    ok, detail = resolves_user_read(path, func)
    check(f"{what} ({func}) reads fresh", ok, detail)

print("\n10. Credential columns have exactly two writers")
# The real fix for token resurrection: the generic upsert must not write gcal_*,
# or any stale UserProfile held across slow work restores the tokens.
store_src = open("app/user_store.py").read()
upsert_bodies = []
tree = ast.parse(store_src)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "upsert" in node.name:
        upsert_bodies.append((node.name, ast.get_source_segment(store_src, node) or ""))

check("found the upsert function(s)", len(upsert_bodies) > 0, str(len(upsert_bodies)))
GCAL_COLS = ["gcal_connected", "gcal_access_token", "gcal_refresh_token",
             "gcal_token_expiry", "gcal_token_data"]
for name, body in upsert_bodies:
    # The INSERT may carry them (new row); ON CONFLICT DO UPDATE must not.
    conflict = body.split("ON CONFLICT", 1)[1] if "ON CONFLICT" in body else ""
    leaked = [c for c in GCAL_COLS if f"{c} = EXCLUDED.{c}" in conflict]
    check(f"{name} does not rewrite gcal_* on conflict", not leaked, f"rewrites {leaked}")

from app.user_store import store_gcal_tokens
writer_src = inspect.getsource(store_gcal_tokens)
check("store_gcal_tokens is a targeted UPDATE", "UPDATE planner_users" in writer_src)
check("store_gcal_tokens reports success", "rowcount" in writer_src)
check("store_gcal_tokens evicts the cache", "_cache.pop" in writer_src)
check("disconnect evicts cache even if the UPDATE raises",
      "finally" in inspect.getsource(disconnect_gcal))

print("\n11. Failure branches don't blow up on a missing helper")
# The first remediation called sl() in planner_routes without importing it, so
# the disconnect failure path raised NameError instead of the intended 500.
import app.api.planner_routes as planner_routes
check("planner_routes has sl imported", hasattr(planner_routes, "sl"))
import app.api.settings_routes as settings_routes
check("settings_routes has sl imported", hasattr(settings_routes, "sl"))

print("\n12. Provider error text is never published verbatim")
apps_src = inspect.getsource(settings_routes.list_connected_apps)
apps_tree = ast.parse(textwrap.dedent(apps_src))


def _mentions_sync_error(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Attribute) and n.attr == "sync_error"
        for n in ast.walk(node)
    )


# Precise: sync_error may be LOGGED (that's where operators need it), but must
# never become the value of a field we ship to the browser.
detail_values_with_error = [
    kw.value
    for node in ast.walk(apps_tree)
    if isinstance(node, ast.Call)
    and getattr(node.func, "id", None) == "AppDetailField"
    for kw in node.keywords
    if kw.arg == "value" and _mentions_sync_error(kw.value)
]
check("sync_error never becomes a client-visible field value",
      not detail_values_with_error,
      f"{len(detail_values_with_error)} AppDetailField(value=...) reference it")
check("a fixed message is shown instead", "Last sync failed" in apps_src)

logged = [
    node for node in ast.walk(apps_tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and getattr(node.func.value, "id", None) == "logger"
    and _mentions_sync_error(node)
]
check("the raw text is still logged for operators", len(logged) >= 1)

print(f"\n{'=' * 52}")
if failures:
    print(f"FAILED — {len(failures)} check(s): {failures}")
    sys.exit(1)
print("All connection-detail checks passed.")
