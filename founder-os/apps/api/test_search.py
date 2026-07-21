#!/usr/bin/env python3
"""
Founder OS — Global Search endpoint integration test
====================================================
Exercises GET /api/search (the ⌘K command-palette backend, task 024):
  1. Auth is required (401 without identity)
  2. Empty / too-short query is rejected (422)
  3. An ingested knowledge item is found by a unique token
  4. Title matches rank above body-only matches
  5. LIKE wildcards in the query are escaped (a literal "%" matches nothing)
  6. Results are scoped to the caller (a second user can't see user 1's doc)

Requires a LIVE server on :8000 with APP_ENV=development (x-test-user bypass).
Run: python3 test_search.py
"""

import sys
import uuid

import httpx

BASE = "http://localhost:8000"
USER = f"search-test-{uuid.uuid4().hex[:8]}"
OTHER = f"search-other-{uuid.uuid4().hex[:8]}"
TOKEN = f"zzqx{uuid.uuid4().hex[:10]}"  # unique, won't collide with real content

PASS, FAIL = 0, 0


def ok(name: str, detail: str = ""):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


c = httpx.Client(base_url=BASE, timeout=60, headers={"x-test-user": USER})
other = httpx.Client(base_url=BASE, timeout=60, headers={"x-test-user": OTHER})
anon = httpx.Client(base_url=BASE, timeout=60)

# ── 0. Server up? ────────────────────────────────────────────
try:
    r = c.get("/")
    r.raise_for_status()
except Exception as e:  # noqa: BLE001
    print(f"\n  Server not running on {BASE}: {e}\n  Start it first (./start.sh).\n")
    sys.exit(1)

# ── 1. Auth required ─────────────────────────────────────────
try:
    r = anon.get("/api/search", params={"q": "hello"})
    if r.status_code in (401, 403):
        ok("Auth required", f"status={r.status_code}")
    else:
        fail("Auth required", f"expected 401/403, got {r.status_code}")
except Exception as e:  # noqa: BLE001
    fail("Auth required", str(e))

# ── 2. Empty / too-short query rejected ──────────────────────
try:
    r = c.get("/api/search", params={"q": ""})
    if r.status_code == 422:
        ok("Empty query rejected", "status=422")
    else:
        fail("Empty query rejected", f"expected 422, got {r.status_code}")
except Exception as e:  # noqa: BLE001
    fail("Empty query rejected", str(e))

# ── 3. Seed a knowledge item, then find it by the unique token ─
try:
    r = c.post(
        "/api/knowledge/ingest/text",
        json={
            "content": f"Quarterly strategy note mentioning {TOKEN} as a keyword.",
            "title": f"Strategy {TOKEN}",
            "category": "strategy",
        },
    )
    r.raise_for_status()
    ok("Seed knowledge item", f"token={TOKEN}")
except Exception as e:  # noqa: BLE001
    fail("Seed knowledge item", str(e))

try:
    r = c.get("/api/search", params={"q": TOKEN})
    r.raise_for_status()
    body = r.json()
    hits = [x for x in body["results"] if x["type"] == "knowledge"]
    if any(TOKEN in (x["title"] or "") or TOKEN in (x.get("snippet") or "") for x in hits):
        ok("Find ingested doc", f"{len(hits)} knowledge hit(s)")
    else:
        fail("Find ingested doc", f"token not in results: {body}")
except Exception as e:  # noqa: BLE001
    fail("Find ingested doc", str(e))

# ── 4. Title match ranks above body-only match ───────────────
try:
    # Title-only doc and body-only doc sharing a second unique token.
    tok2 = f"zzqx{uuid.uuid4().hex[:10]}"
    c.post(
        "/api/knowledge/ingest/text",
        json={"content": "no keyword in the body here", "title": f"{tok2} headline"},
    ).raise_for_status()
    c.post(
        "/api/knowledge/ingest/text",
        json={"content": f"body mentions {tok2} deep inside", "title": "unrelated title"},
    ).raise_for_status()
    r = c.get("/api/search", params={"q": tok2})
    r.raise_for_status()
    kn = [x for x in r.json()["results"] if x["type"] == "knowledge"]
    if len(kn) >= 2 and tok2 in (kn[0]["title"] or ""):
        ok("Title match ranks first", kn[0]["title"])
    elif len(kn) >= 2:
        fail("Title match ranks first", f"first was: {kn[0]['title']}")
    else:
        fail("Title match ranks first", f"expected >=2 hits, got {len(kn)}")
except Exception as e:  # noqa: BLE001
    fail("Title match ranks first", str(e))

# ── 5. LIKE wildcards escaped — "%" matches nothing literal ──
try:
    r = c.get("/api/search", params={"q": "%"})
    r.raise_for_status()
    body = r.json()
    # Our seeded docs contain no literal "%", so an escaped LIKE returns none of them.
    leaked = [x for x in body["results"] if TOKEN in (x["title"] or "")]
    if not leaked:
        ok("Wildcard escaped", f"'%' returned {body['total']} (no wildcard blowup)")
    else:
        fail("Wildcard escaped", "literal '%' matched seeded docs — not escaped")
except Exception as e:  # noqa: BLE001
    fail("Wildcard escaped", str(e))

# ── 6. Results are user-scoped ───────────────────────────────
try:
    r = other.get("/api/search", params={"q": TOKEN})
    r.raise_for_status()
    leaked = [x for x in r.json()["results"] if TOKEN in (x["title"] or "")]
    if not leaked:
        ok("User scoping", "other user cannot see user 1's doc")
    else:
        fail("User scoping", "cross-user leak!")
except Exception as e:  # noqa: BLE001
    fail("User scoping", str(e))

print(f"\n{'='*50}\n  RESULTS: {PASS} passed, {FAIL} failed\n{'='*50}")
sys.exit(1 if FAIL else 0)
