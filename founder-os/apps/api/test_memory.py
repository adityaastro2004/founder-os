#!/usr/bin/env python3
"""Quick test script for Founder OS Memory System."""

import httpx
import json
import sys

BASE = "http://localhost:8000/api/memory"

def main():
    client = httpx.Client(timeout=30)
    
    # ── Store memories ──────────────────────────────────────────
    memories = [
        {
            "user_id": "default-user",
            "title": "Hired first backend engineer - Priya",
            "content": "Priya joined as senior backend engineer. Strong in Python/FastAPI. Previously at Stripe.",
            "page_type": "event", "importance": 0.7, "chapter": "hiring",
            "tags": ["hiring", "team-growth"], "entities": {"people": ["Priya"]},
            "review_in_days": 14, "occurred_at": "2024-11-01T09:00:00+00:00",
        },
        {
            "user_id": "default-user",
            "title": "Product launch v2.0 with AI features",
            "content": "Launched v2.0 with AI analytics. 200 signups in first week. Some bugs in billing module.",
            "page_type": "milestone", "importance": 0.85, "chapter": "product",
            "tags": ["launch", "v2", "ai"], "entities": {"tools": ["AI Analytics"]},
            "review_in_days": 7, "occurred_at": "2025-01-15T10:00:00+00:00",
        },
        {
            "user_id": "default-user",
            "title": "MRR crossed 25k milestone",
            "content": "Monthly recurring revenue hit 25000. Growth rate 15% MoM. Top channels: organic and partner referrals.",
            "page_type": "metric", "importance": 0.8, "chapter": "revenue",
            "tags": ["mrr", "growth", "milestone"], "is_pinned": True,
            "review_in_days": 30, "occurred_at": "2025-02-01T08:00:00+00:00",
        },
        {
            "user_id": "default-user",
            "title": "Decided to pivot from SMB to enterprise",
            "content": "Focus on enterprise customers. Higher LTV 50k vs 5k. Need SSO, RBAC, audit logs.",
            "page_type": "decision", "importance": 0.95, "chapter": "strategy",
            "tags": ["pivot", "enterprise", "strategy"], "is_pinned": True,
            "review_in_days": 60, "occurred_at": "2025-03-10T14:00:00+00:00",
        },
        {
            "user_id": "default-user",
            "title": "Bug in payment processing caused revenue loss",
            "content": "Stripe webhook handler had a race condition. Lost 15 transactions. Fixed with idempotency keys.",
            "page_type": "event", "importance": 0.6, "chapter": "product",
            "tags": ["bug", "payments", "incident"], "entities": {"tools": ["Stripe"]},
            "review_in_days": 7, "occurred_at": "2025-04-05T16:00:00+00:00",
        },
    ]
    
    print("=== STORING MEMORIES ===")
    stored_ids = []
    for m in memories:
        r = client.post(f"{BASE}/store", json=m)
        if r.status_code != 200:
            print(f"  FAIL  {m['title']}: {r.status_code} {r.text[:200]}")
            continue
        d = r.json()
        stored_ids.append(d["page_id"])
        print(f"  OK  {d['title']} -> {d['page_id'][:8]}")
    
    print(f"\nStored {len(stored_ids)} memories\n")

    # ── Recall (no query — pure temporal + importance) ──────────
    print("=== RECALL (temporal + importance, no semantic) ===")
    r = client.post(f"{BASE}/recall", json={
        "user_id": "default-user",
        "limit": 10,
    })
    d = r.json()
    print(f"Total results: {d['total_results']}")
    for m in d["memories"]:
        print(f"  {m['scores']['composite']:.4f}  [{m['page_type']:10}]  {m['title']}")
        print(f"           temporal={m['scores']['temporal']:.4f}  imp={m['scores']['importance']:.4f}  acc={m['scores']['access']:.4f}")

    # ── Recall with chapter filter ──────────────────────────────
    print("\n=== RECALL (product chapter only) ===")
    r = client.post(f"{BASE}/recall", json={
        "user_id": "default-user",
        "chapter": "product",
        "limit": 5,
    })
    for m in r.json()["memories"]:
        print(f"  {m['scores']['composite']:.4f}  {m['title']}")

    # ── Reviews due ─────────────────────────────────────────────
    print("\n=== REVIEWS DUE ===")
    r = client.get(f"{BASE}/reviews", params={"user_id": "default-user"})
    d = r.json()
    print(f"Reviews due: {d['reviews_due']}")
    for m in d["memories"]:
        print(f"  {m['title']}")

    # ── Mark reviewed ───────────────────────────────────────────
    if d["memories"]:
        first_review_id = d["memories"][0]["id"]
        print(f"\n=== MARKING REVIEWED: {first_review_id[:8]} ===")
        r = client.post(f"{BASE}/review/{first_review_id}")
        print(f"  {r.json()}")

    # ── Chapters ────────────────────────────────────────────────
    print("\n=== CHAPTERS ===")
    r = client.get(f"{BASE}/chapters", params={"user_id": "default-user"})
    for ch in r.json()["chapters"]:
        print(f"  {ch['chapter']:15}  {ch['count']} pages  avg_imp={ch['avg_importance']:.3f}")

    # ── Entity search ───────────────────────────────────────────
    print("\n=== ENTITY SEARCH: 'Priya' ===")
    r = client.post(f"{BASE}/search/entity", json={
        "user_id": "default-user",
        "entity": "Priya",
    })
    for m in r.json()["memories"]:
        print(f"  {m['title']}")

    # ── Entity search: Stripe ───────────────────────────────────
    print("\n=== ENTITY SEARCH: 'Stripe' ===")
    r = client.post(f"{BASE}/search/entity", json={
        "user_id": "default-user",
        "entity": "Stripe",
    })
    for m in r.json()["memories"]:
        print(f"  {m['title']}")

    # ── Stats ───────────────────────────────────────────────────
    print("\n=== STATS ===")
    r = client.get(f"{BASE}/stats", params={"user_id": "default-user"})
    print(json.dumps(r.json(), indent=2))

    # ── Link two memories ───────────────────────────────────────
    if len(stored_ids) >= 2:
        print(f"\n=== LINKING: {stored_ids[0][:8]} -> {stored_ids[1][:8]} ===")
        r = client.post(f"{BASE}/link", json={
            "source_id": stored_ids[0],
            "target_id": stored_ids[1],
            "link_type": "related",
            "strength": 0.7,
        })
        print(f"  {r.json()}")

        print(f"\n=== LINKS FOR {stored_ids[0][:8]} ===")
        r = client.get(f"{BASE}/links/{stored_ids[0]}")
        print(json.dumps(r.json(), indent=2))

    # ── Pin/unpin test ──────────────────────────────────────────
    if stored_ids:
        print(f"\n=== PIN/UNPIN: {stored_ids[-1][:8]} ===")
        r = client.post(f"{BASE}/pin/{stored_ids[-1]}", params={"pin": True})
        print(f"  Pin: {r.json()}")
        r = client.post(f"{BASE}/pin/{stored_ids[-1]}", params={"pin": False})
        print(f"  Unpin: {r.json()}")

    print("\n=== ALL TESTS PASSED ===")
    client.close()


if __name__ == "__main__":
    main()
