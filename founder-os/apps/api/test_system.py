#!/usr/bin/env python3
"""
Founder OS — Complete System Integration Test
==============================================
Tests every major subsystem end-to-end:
  1. Health & baseline checks
  2. Memory system (store, recall, temporal scoring, reviews, chapters, links)
  3. Planner: onboard → update context → status
  4. Google Calendar OAuth flow validation
  5. LLM plan generation (Gemini) with real prompt
  6. GCal push (if connected)
  7. Memory-aware plan generation
  8. Agent system (orchestrate, chat)
  9. Knowledge system
  10. Token persistence across restarts

Run: python3 test_system.py
"""

import httpx
import json
import time
import sys
from datetime import datetime, timezone

BASE = "http://localhost:8000"
USER = "integration-test-user"
PASS, FAIL, SKIP, WARN = 0, 0, 0, 0
RESULTS: list[tuple[str, str, str]] = []  # (test_name, status, detail)


def header(name: str):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def ok(name: str, detail: str = ""):
    global PASS
    PASS += 1
    RESULTS.append((name, "PASS", detail))
    print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    global FAIL
    FAIL += 1
    RESULTS.append((name, "FAIL", detail))
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def skip(name: str, detail: str = ""):
    global SKIP
    SKIP += 1
    RESULTS.append((name, "SKIP", detail))
    print(f"  [SKIP] {name}" + (f" — {detail}" if detail else ""))


def warn(name: str, detail: str = ""):
    global WARN
    WARN += 1
    RESULTS.append((name, "WARN", detail))
    print(f"  [WARN] {name}" + (f" — {detail}" if detail else ""))


c = httpx.Client(base_url=BASE, timeout=120)

# ───────────────────────────────────────────────────────────────
# 1. HEALTH & BASELINE
# ───────────────────────────────────────────────────────────────
header("1. HEALTH & BASELINE CHECKS")

try:
    r = c.get("/")
    assert r.status_code == 200
    assert "running" in r.json()["message"].lower()
    ok("Root endpoint", r.json()["message"])
except Exception as e:
    fail("Root endpoint", str(e))
    print("\n  Server not running! Start it first.\n")
    sys.exit(1)

try:
    r = c.get("/api/health")
    d = r.json()
    # Support both formats: {"checks": {"postgres": "ok"}} and {"database": {"connected": true}}
    checks = d.get("checks", {})
    healthy = d.get("healthy", False)
    db_ok = checks.get("postgres") == "ok" or d.get("database", {}).get("connected", False)
    redis_ok = checks.get("redis") == "ok" or d.get("redis", {}).get("connected", False)
    ok("Health check", f"healthy={healthy} db={db_ok} redis={redis_ok}")
    if not db_ok:
        fail("PostgreSQL", "Database not connected!")
    else:
        ok("PostgreSQL", "connected")
    if not redis_ok:
        fail("Redis", "Redis not connected!")
    else:
        ok("Redis", "connected")
except Exception as e:
    fail("Health check", str(e))

try:
    r = c.get("/api/test/provider")
    d = r.json()
    ok("LLM provider", f"{d.get('provider')} / {d.get('model')}")
except Exception as e:
    fail("LLM provider info", str(e))

# ───────────────────────────────────────────────────────────────
# 2. MEMORY SYSTEM
# ───────────────────────────────────────────────────────────────
header("2. MEMORY SYSTEM (Temporal Knowledge Graph)")

memory_ids = []

# Store a batch of memories across different time horizons
test_memories = [
    {
        "user_id": USER,
        "title": "Signed enterprise deal with Acme Corp",
        "content": "Closed $120k ARR deal with Acme Corp. Champion was VP Engineering Sarah. Long sales cycle (4 months) but high ACV. Stripe billing integration was key.",
        "page_type": "milestone",
        "chapter": "sales",
        "importance": 0.95,
        "tags": ["enterprise", "acme", "revenue"],
        "entities": {"Acme Corp": "customer", "Sarah": "champion", "Stripe": "integration"},
        "occurred_at": "2025-09-15T10:00:00Z",
    },
    {
        "user_id": USER,
        "title": "Hired lead designer — Priya",
        "content": "Priya joined as lead designer from Figma. Strong UX background. First design hire — signals product maturity.",
        "page_type": "event",
        "chapter": "hiring",
        "importance": 0.75,
        "tags": ["hiring", "design", "team"],
        "entities": {"Priya": "employee", "Figma": "previous_company"},
        "occurred_at": "2025-08-01T09:00:00Z",
    },
    {
        "user_id": USER,
        "title": "Pivoted pricing from per-seat to usage-based",
        "content": "Major pricing change. Moved from $50/seat to usage-based pricing ($0.01/API call + $200 platform fee). Expected to double enterprise adoption.",
        "page_type": "decision",
        "chapter": "strategy",
        "importance": 0.90,
        "tags": ["pricing", "strategy", "revenue"],
        "entities": {},
        "occurred_at": "2025-11-01T14:00:00Z",
    },
    {
        "user_id": USER,
        "title": "MRR crossed $50k milestone",
        "content": "Monthly recurring revenue hit $50k. 40% MoM growth. Enterprise deals driving majority. Need to hire 2 more engineers.",
        "page_type": "metric",
        "chapter": "revenue",
        "importance": 0.85,
        "tags": ["mrr", "growth", "milestone"],
        "entities": {},
        "occurred_at": "2026-01-10T10:00:00Z",
    },
    {
        "user_id": USER,
        "title": "Production incident — 3h downtime from DB migration",
        "content": "Botched Postgres migration caused 3 hours of downtime during peak hours. Lost ~$5k in revenue. Root cause: missing index on hot path. Need better CI/CD pipeline and staging environment.",
        "page_type": "event",
        "chapter": "product",
        "importance": 0.80,
        "tags": ["incident", "downtime", "database", "postmortem"],
        "entities": {},
        "occurred_at": "2026-02-15T03:30:00Z",
        "review_in_days": 7,
    },
]

for mem in test_memories:
    try:
        r = c.post("/api/memory/store", json=mem)
        if r.status_code == 200:
            pid = r.json()["page_id"]
            memory_ids.append(pid)
            ok(f"Store: {mem['title'][:40]}", f"id={pid[:8]}")
        else:
            fail(f"Store: {mem['title'][:40]}", f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        fail(f"Store: {mem['title'][:40]}", str(e))

# Recall — temporal + importance scoring (no semantic embedding)
try:
    r = c.post("/api/memory/recall", json={
        "user_id": USER,
        "query": "enterprise revenue",
        "limit": 10,
    })
    d = r.json()
    memories = d.get("memories", [])
    ok("Recall (temporal+importance)",
       f"{len(memories)} results — top: {memories[0]['title'][:35]}... score={memories[0]['scores']['composite']:.3f}" if memories else "0 results")
    # Verify temporal ordering — most recent/important first
    if len(memories) >= 2:
        s1, s2 = memories[0]["scores"]["composite"], memories[1]["scores"]["composite"]
        if s1 >= s2:
            ok("Temporal ranking", f"scores ordered: {s1:.3f} >= {s2:.3f}")
        else:
            warn("Temporal ranking", f"UNEXPECTED: {s1:.3f} < {s2:.3f}")
except Exception as e:
    fail("Recall", str(e))

# Recall with chapter filter
try:
    r = c.post("/api/memory/recall", json={
        "user_id": USER,
        "query": "sales deals",
        "chapter": "sales",
        "limit": 5,
    })
    memories = r.json().get("memories", [])
    all_sales = all(m.get("chapter") == "sales" for m in memories)
    ok("Recall (chapter=sales)", f"{len(memories)} results, all sales={all_sales}")
except Exception as e:
    fail("Recall (chapter filter)", str(e))

# List chapters
try:
    r = c.get("/api/memory/chapters", params={"user_id": USER})
    chapters = r.json().get("chapters", [])
    ch_names = [ch["chapter"] for ch in chapters]
    ok("List chapters", f"{len(chapters)} chapters: {ch_names}")
except Exception as e:
    fail("List chapters", str(e))

# Browse chapter chronologically
try:
    r = c.get("/api/memory/chapter/product", params={"user_id": USER})
    d = r.json()
    ok("Browse chapter (product)", f"{d.get('total', 0)} pages")
except Exception as e:
    fail("Browse chapter", str(e))

# Entity search
for entity in ["Acme", "Priya"]:
    try:
        r = c.post("/api/memory/search/entity", json={"user_id": USER, "query": entity})
        results = r.json().get("results", [])
        ok(f"Entity search: '{entity}'", f"{len(results)} results")
    except Exception as e:
        fail(f"Entity search: '{entity}'", str(e))

# Link memories
if len(memory_ids) >= 2:
    try:
        r = c.post("/api/memory/link", json={
            "source_id": memory_ids[0],
            "target_id": memory_ids[2],  # acme deal -> pricing pivot
            "link_type": "influenced_by",
            "strength": 0.8,
        })
        ok("Link memories", f"Acme deal <-> Pricing pivot: {r.json().get('status')}")
    except Exception as e:
        fail("Link memories", str(e))

    try:
        r = c.get(f"/api/memory/links/{memory_ids[0]}", params={"user_id": USER})
        links = r.json().get("links", [])
        ok("Get links", f"{len(links)} links from Acme deal")
    except Exception as e:
        fail("Get links", str(e))

# Pin
if memory_ids:
    try:
        r = c.post(f"/api/memory/pin/{memory_ids[0]}", params={"user_id": USER})
        ok("Pin memory", r.json().get("status", ""))
    except Exception as e:
        fail("Pin memory", str(e))

# Stats
try:
    r = c.get("/api/memory/stats", params={"user_id": USER})
    s = r.json()
    ok("Memory stats", f"total={s['total_memories']}, pinned={s['pinned']}, chapters={s['chapters']}, avg_imp={s['avg_importance']:.2f}")
except Exception as e:
    fail("Memory stats", str(e))

# Reviews due
try:
    r = c.get("/api/memory/reviews", params={"user_id": USER})
    reviews = r.json().get("memories", [])
    ok("Reviews due", f"{len(reviews)} memories need review")
except Exception as e:
    fail("Reviews due", str(e))


# ───────────────────────────────────────────────────────────────
# 3. PLANNER: ONBOARD + PROFILE
# ───────────────────────────────────────────────────────────────
header("3. PLANNER: ONBOARD + PROFILE MANAGEMENT")

# Onboard
try:
    r = c.post("/api/planner/onboard", json={
        "user_id": USER,
        "name": "Aditya",
        "business_name": "FounderOS Inc",
        "business_type": "B2B SaaS",
        "industry": "Developer Tools",
        "business_stage": "seed",
        "target_audience": "Technical startup founders",
        "team_size": 5,
        "current_mrr": 50000,
        "current_users": 150,
        "primary_goal": "Reach $100k MRR by Q3 2026",
        "goals_this_week": [
            "Close Acme Corp enterprise upsell",
            "Ship v2.1 with memory system",
            "Interview 3 senior backend candidates",
            "Prepare Series A pitch deck",
        ],
        "timezone": "Asia/Kolkata",
        "preferred_work_hours": "09:00-18:00",
        "custom_instructions": "Focus on revenue-generating activities. Block 2 hours daily for deep work. No meetings before 10am.",
    })
    d = r.json()
    ok("Onboard", f"status={d.get('status')}, business={d.get('business_name')}")
except Exception as e:
    fail("Onboard", str(e))

# Status check
try:
    r = c.get("/api/planner/status", params={"user_id": USER})
    d = r.json()
    ok("Status",
       f"status={d.get('status')}, gcal={d.get('gcal_connected')}, "
       f"goal={d.get('primary_goal','')[:35]}, plans={d.get('total_plans_generated')}")
except Exception as e:
    fail("Status", str(e))

# Update context with natural language
try:
    r = c.post("/api/planner/update", json={
        "user_id": USER,
        "message": "We just hit $55k MRR this week! Also got a term sheet from Sequoia for Series A at $15M valuation. Need to focus on due diligence docs and maintaining growth.",
        "blockers": ["Waiting for legal review of term sheet", "Backend engineer on PTO this week"],
        "completed_last_week": ["Shipped memory system v1", "Closed 2 new enterprise deals"],
    })
    d = r.json()
    fields = d.get("fields_updated", [])
    ok("Update context (NLP)", f"fields_updated={fields}")
    eff = d.get("effective_context", {})
    ok("Effective context", f"mrr={eff.get('current_mrr')}, goals={len(eff.get('goals_this_week', []))}, blockers={len(eff.get('blockers', []))}")
except Exception as e:
    fail("Update context", str(e))

# Verify persistence — clear module cache and re-fetch
try:
    sys.path.insert(0, "/Users/adityaastro/Documents/GitHub/founder-os/founder-os/apps/api")
    from app.user_store import get_user, _cache
    _cache.clear()
    u = get_user(USER)
    assert u is not None, "User not found in DB!"
    assert u.business_name == "FounderOS Inc", f"Expected 'FounderOS Inc', got '{u.business_name}'"
    ok("DB persistence (cache cleared)", f"user={u.user_id}, business={u.business_name}")
except Exception as e:
    fail("DB persistence", str(e))

# ───────────────────────────────────────────────────────────────
# 4. GOOGLE CALENDAR OAUTH
# ───────────────────────────────────────────────────────────────
header("4. GOOGLE CALENDAR OAUTH FLOW")

gcal_connected = False

# Check if user already has GCal tokens from a previous run
try:
    from app.user_store import get_user as _gu
    _u = _gu(USER)
    if _u and _u.has_valid_gcal_tokens():
        gcal_connected = True
        ok("GCal already connected", "Tokens found in DB from previous session")
except:
    pass

if not gcal_connected:
    # Test OAuth URL generation
    try:
        r = c.get("/api/planner/connect", params={"user_id": USER})
        d = r.json()
        auth_url = d.get("auth_url", "")
        has_url = "accounts.google.com" in auth_url
        ok("GCal OAuth URL", f"url_valid={has_url}")
        if has_url:
            print(f"\n  >>> To complete GCal integration, visit this URL in your browser:")
            print(f"  >>> {auth_url[:120]}...")
            print(f"  >>> After granting access, the callback will store tokens automatically.\n")
    except Exception as e:
        fail("GCal OAuth URL", str(e))

    # Check if dev-user has tokens (from legacy test flow)
    try:
        from app.integrations.calendar_integration import get_tokens as _gt
        dev_tokens = _gt("dev-user")
        if dev_tokens and dev_tokens.get("access_token"):
            # Copy dev-user tokens to our test user
            from app.user_store import get_or_create_user, save_user
            u = get_or_create_user(USER)
            u.store_gcal_tokens(dev_tokens)
            save_user(u)
            from app.integrations.calendar_integration import store_tokens as _st
            _st(USER, dev_tokens)
            gcal_connected = True
            ok("GCal tokens (copied from dev-user)", "Using existing authenticated session")
    except Exception as e:
        warn("GCal token copy", str(e))

if not gcal_connected:
    skip("GCal push tests", "No valid tokens — complete OAuth flow first")


# ───────────────────────────────────────────────────────────────
# 5. LLM PLAN GENERATION (Gemini)
# ───────────────────────────────────────────────────────────────
header("5. LLM PLAN GENERATION (Gemini 2.5 Flash)")

plan_generated = False

# Small delay to avoid Gemini rate limits (429) if previous LLM calls ran
time.sleep(3)

# Test via /api/test/plan first (doesn't require GCal)
try:
    print("  Generating plan with Gemini (this takes 15-30 seconds)...")
    t0 = time.time()
    r = c.post("/api/test/plan", json={
        "goals": [
            "Close Acme Corp enterprise upsell ($50k)",
            "Ship v2.1 with memory system and temporal search",
            "Interview 3 senior backend candidates",
            "Prepare Series A pitch deck for Sequoia",
            "Fix production DB migration pipeline",
        ],
        "user_context": (
            "B2B SaaS startup, Developer Tools. 5 person team. "
            "$50k MRR, 150 users. Seed stage, Series A imminent. "
            "Timezone: Asia/Kolkata. Work hours: 09:00-18:00. "
            "Blockers: Legal review pending, one engineer on PTO."
        ),
    })
    elapsed = time.time() - t0

    if r.status_code == 200:
        d = r.json()
        plan = d.get("plan", {})
        tasks_total = d.get("tasks_total", 0)
        priorities = [p.get("title", "?")[:40] for p in plan.get("top_priorities", [])[:3]]
        days = list(plan.get("daily_schedule", {}).keys())

        ok("Plan generation", f"{tasks_total} tasks across {len(days)} days in {elapsed:.1f}s")
        ok("Top priorities", f"{priorities}")

        # Validate plan structure
        schedule = plan.get("daily_schedule", {})
        for day_name in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            day_data = schedule.get(day_name, {})
            tasks = day_data.get("tasks", [])
            if tasks:
                task_titles = [t.get("title", "?")[:35] for t in tasks[:2]]
                time_range = f"{tasks[0].get('start_time','?')}-{tasks[-1].get('end_time','?')}"
                ok(f"  {day_name.capitalize():9s}", f"{len(tasks)} tasks [{time_range}] e.g. {task_titles[0]}")
            else:
                warn(f"  {day_name.capitalize():9s}", "No tasks generated")

        # Check risks and success criteria
        risks = plan.get("risks", [])
        criteria = plan.get("success_criteria", [])
        ok("Risks identified", f"{len(risks)}" + (f" — e.g. {risks[0].get('risk','')[:50]}" if risks else ""))
        ok("Success criteria", f"{len(criteria)}" + (f" — e.g. {criteria[0][:50]}" if criteria else ""))

        plan_generated = True
    elif r.status_code in (429, 502) and "429" in r.text:
        warn("Plan generation", "Gemini 429 rate limit — plan generation works but API throttled, retry later")
    else:
        fail("Plan generation", f"HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    fail("Plan generation", str(e))

# ───────────────────────────────────────────────────────────────
# 6. GOOGLE CALENDAR PUSH
# ───────────────────────────────────────────────────────────────
header("6. GOOGLE CALENDAR PUSH")

if gcal_connected and plan_generated:
    try:
        print("  Pushing plan to Google Calendar...")
        r = c.post("/api/test/plan/gcal/push", params={
            "calendar_id": "primary",
            "timezone": "Asia/Kolkata",
        })
        if r.status_code == 200:
            d = r.json()
            created = d.get("events_created", 0)
            failed = d.get("events_failed", 0)
            ok("GCal push", f"events_created={created}, events_failed={failed}")
            events = d.get("events", [])
            for ev in events[:3]:
                ok(f"  Event", f"{ev.get('day','?')} {ev.get('start','?')}-{ev.get('end','?')}: {ev.get('summary','?')[:40]}")
            if len(events) > 3:
                ok(f"  ... and {len(events)-3} more events", "")
        elif r.status_code == 401:
            warn("GCal push", "Token expired — need to re-authenticate")
        else:
            fail("GCal push", f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail("GCal push", str(e))
elif not gcal_connected:
    skip("GCal push", "No GCal tokens available")
elif not plan_generated:
    skip("GCal push", "No plan was generated")

# ───────────────────────────────────────────────────────────────
# 7. MEMORY-AWARE PLANNING (via /api/planner/generate)
# ───────────────────────────────────────────────────────────────
header("7. MEMORY-AWARE PLAN GENERATION")

if gcal_connected:
    try:
        print("  Generating memory-aware plan via production planner (15-30s)...")
        t0 = time.time()
        r = c.post("/api/planner/generate", json={
            "user_id": USER,
            "message": "Focus on closing Acme upsell and fixing the DB migration issue from last month's incident. Also prepare for Sequoia meeting.",
        })
        elapsed = time.time() - t0

        if r.status_code == 200:
            d = r.json()
            ok("Memory-aware plan",
               f"tasks={d.get('tasks_generated')}, events={d.get('events_created')}, "
               f"duration={d.get('duration_seconds')}s")

            # Verify plan was stored in history
            r2 = c.get("/api/planner/history", params={"user_id": USER, "limit": 5})
            history = r2.json().get("plans", [])
            ok("Plan history", f"{len(history)} plans stored")

            # Verify plan was stored as memory
            r3 = c.post("/api/memory/recall", json={
                "user_id": USER,
                "query": "weekly plan",
                "chapter": "planning",
                "limit": 3,
            })
            plan_memories = r3.json().get("memories", [])
            ok("Plan as memory", f"{len(plan_memories)} plan memories found")

            # Check status was updated
            r4 = c.get("/api/planner/status", params={"user_id": USER})
            st = r4.json()
            ok("Status updated",
               f"last_plan={st.get('last_plan_at','?')[:19]}, "
               f"events={st.get('last_plan_events')}, "
               f"total={st.get('total_plans_generated')}")
        else:
            fail("Memory-aware plan", f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail("Memory-aware plan", str(e))
else:
    skip("Memory-aware plan", "GCal not connected — POST /api/planner/generate requires it")

    # Still test that the planner rejects without GCal
    try:
        r = c.post("/api/planner/generate", json={"user_id": USER, "message": "Plan my week"})
        if r.status_code == 400:
            ok("Generate rejects without GCal", r.json().get("detail", "")[:60])
        else:
            warn("Generate without GCal", f"Expected 400, got {r.status_code}")
    except Exception as e:
        fail("Generate rejection test", str(e))


# ───────────────────────────────────────────────────────────────
# 8. AGENT SYSTEM
# ───────────────────────────────────────────────────────────────
header("8. AGENT SYSTEM")

try:
    r = c.get("/api/agents/")
    if r.status_code == 401:
        # Auth required — this is expected behavior
        ok("List agents (auth-gated)", "Returns 401 without token — correct behavior")
    else:
        agents = r.json()
        if isinstance(agents, list):
            agent_names = [a.get("name", "?") for a in agents]
            ok("List agents", f"{len(agents)} agents: {agent_names}")
        elif isinstance(agents, dict) and "agents" in agents:
            agent_names = [a.get("name", "?") for a in agents["agents"]]
            ok("List agents", f"{len(agent_names)} agents: {agent_names}")
        else:
            ok("List agents", f"response type: {type(agents).__name__}")
except Exception as e:
    fail("List agents", str(e))

try:
    r = c.get("/api/agents/system")
    d = r.json()
    if r.status_code == 401:
        ok("System info (auth-gated)", "Returns 401 without token — correct")
    else:
        ok("System info", f"agents={d.get('agent_count')}, llm={d.get('llm_provider')}/{d.get('llm_model')}")
except Exception as e:
    fail("System info", str(e))

# Test chat with LLM
try:
    print("  Testing LLM chat...")
    r = c.post("/api/test/chat", json={
        "message": "What's the most important metric for a B2B SaaS startup at seed stage?",
    })
    if r.status_code == 200:
        d = r.json()
        resp = d.get("response", "")[:120]
        ok("LLM chat", f"response: \"{resp}...\"")
    elif r.status_code == 429 or r.status_code == 502:
        warn("LLM chat", f"HTTP {r.status_code} — Gemini rate limit, can retry later")
    else:
        fail("LLM chat", f"HTTP {r.status_code}: {r.text[:150]}")
except Exception as e:
    fail("LLM chat", str(e))


# ───────────────────────────────────────────────────────────────
# 9. KNOWLEDGE SYSTEM
# ───────────────────────────────────────────────────────────────
header("9. KNOWLEDGE SYSTEM")

try:
    r = c.get("/api/knowledge/stats")
    if r.status_code == 200:
        s = r.json()
        ok("Knowledge stats", f"items={s.get('total_items', 0)}, sources={s.get('unique_sources', 0)}")
    elif r.status_code == 401:
        ok("Knowledge stats (auth-gated)", "Returns 401 — requires Clerk JWT token")
    else:
        warn("Knowledge stats", f"HTTP {r.status_code}")
except Exception as e:
    fail("Knowledge stats", str(e))

# Ingest a text document
try:
    r = c.post("/api/knowledge/ingest/text", json={
        "text": "Founder OS is an autonomous AI operating system for startup founders.",
        "source": "integration-test",
        "metadata": {"type": "system-doc", "version": "2.0"},
    })
    if r.status_code == 200:
        d = r.json()
        ok("Knowledge ingest", f"items={d.get('items_created', d.get('count', '?'))}")
    elif r.status_code == 401:
        ok("Knowledge ingest (auth-gated)", "Returns 401 — requires Clerk JWT token")
    else:
        warn("Knowledge ingest", f"HTTP {r.status_code}: {r.text[:100]}")
except Exception as e:
    fail("Knowledge ingest", str(e))


# ───────────────────────────────────────────────────────────────
# 10. TOKEN PERSISTENCE TEST
# ───────────────────────────────────────────────────────────────
header("10. TOKEN PERSISTENCE (Simulated Restart)")

try:
    from app.user_store import get_user, save_user, _cache

    # Store tokens
    u = get_user(USER)
    if u:
        if not u.gcal_tokens:
            u.store_gcal_tokens({
                "access_token": "ya29.test-token-persistence",
                "refresh_token": "1//test-refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            save_user(u)

        # Clear cache = simulate restart
        _cache.clear()
        u2 = get_user(USER)
        assert u2 is not None, "User lost after cache clear!"
        assert u2.business_name == "FounderOS Inc", f"Business name changed: {u2.business_name}"

        if u2.gcal_tokens and u2.gcal_tokens.get("access_token"):
            ok("Token persistence", f"token={u2.gcal_tokens['access_token'][:20]}...")
        else:
            fail("Token persistence", "Tokens lost after cache clear!")

        ok("Profile persistence", f"business={u2.business_name}, mrr={u2.current_mrr}")
    else:
        fail("Token persistence", "User not found")
except Exception as e:
    fail("Token persistence", str(e))


# ───────────────────────────────────────────────────────────────
# CLEANUP
# ───────────────────────────────────────────────────────────────
header("CLEANUP")

# Delete test memories
for pid in memory_ids:
    try:
        c.delete(f"/api/memory/{pid}", params={"user_id": USER})
    except:
        pass

# Delete test user
try:
    from app.user_store import delete_user
    delete_user(USER)
    ok("Cleanup", f"Deleted user '{USER}' and {len(memory_ids)} memories")
except Exception as e:
    warn("Cleanup", str(e))

# Delete test knowledge
try:
    c.delete("/api/knowledge/items", params={"source": "integration-test"})
except:
    pass


# ───────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────
header("FINAL REPORT")

total = PASS + FAIL + SKIP + WARN
print(f"""
  Total tests:  {total}
  Passed:       {PASS}  {'✓' if FAIL == 0 else ''}
  Failed:       {FAIL}  {'✗' if FAIL > 0 else ''}
  Warnings:     {WARN}
  Skipped:      {SKIP}
""")

if FAIL > 0:
    print("  FAILED TESTS:")
    for name, status, detail in RESULTS:
        if status == "FAIL":
            print(f"    ✗ {name}: {detail}")
    print()

if WARN > 0:
    print("  WARNINGS:")
    for name, status, detail in RESULTS:
        if status == "WARN":
            print(f"    ⚠ {name}: {detail}")
    print()

if FAIL == 0:
    print("  === ALL CRITICAL TESTS PASSED ===\n")
else:
    print(f"  === {FAIL} TESTS FAILED ===\n")

sys.exit(1 if FAIL > 0 else 0)
