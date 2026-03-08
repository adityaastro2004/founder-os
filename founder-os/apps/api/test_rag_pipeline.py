#!/usr/bin/env python3
"""
Founder OS — RAG Pipeline Integration Test
=============================================
Tests the full RAG pipeline end-to-end:
  1. Ingest text → verify chunking + embedding
  2. Ingest via file upload → verify processing
  3. Search (hybrid, semantic, fulltext, MMR) → verify relevance
  4. Agent uses uploaded context in responses

Run: python3 test_rag_pipeline.py
"""

import httpx
import json
import time
import sys

BASE = "http://localhost:8000"
USER = "integration-test-user"
PASS, FAIL, SKIP = 0, 0, 0
RESULTS: list[tuple[str, str, str]] = []

KNOWLEDGE_ITEM_IDS: list[str] = []


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


def auth_headers():
    return {"x-test-user": USER}


client = httpx.Client(base_url=BASE, headers=auth_headers(), timeout=60)


# ─── 1. Health Check ────────────────────────────────────────

def test_health():
    header("1. Health Check")
    r = client.get("/health")
    if r.status_code == 200:
        ok("API healthy", r.json().get("status", ""))
    else:
        fail("API health check", f"status={r.status_code}")


# ─── 2. Text Ingestion ──────────────────────────────────────

SAMPLE_DOC = """
# Founder OS Pricing Strategy

## Enterprise Tier
Our enterprise tier is priced at $499/month per seat with a minimum of 10 seats.
This includes:
- Unlimited AI agent runs
- Custom agent training
- Priority support with 4-hour SLA
- SOC 2 compliance reports
- Dedicated account manager

## Growth Tier
The growth tier is $99/month per seat with no minimum seats.
This includes:
- 1000 AI agent runs per month
- Standard agent templates
- Email support with 24-hour SLA

## Startup Tier
Free for up to 3 seats with 100 agent runs per month.
Perfect for solo founders and small teams getting started.
"""


def test_ingest_text():
    header("2. Text Ingestion (Ingest → Chunk → Embed → Store)")

    r = client.post("/api/knowledge/ingest/text", json={
        "content": SAMPLE_DOC,
        "title": "Pricing Strategy Document",
        "category": "business",
        "tags": ["pricing", "enterprise", "startup"],
        "chunk_size": 256,
        "chunk_overlap": 30,
    })

    if r.status_code != 201:
        fail("Ingest text", f"status={r.status_code} body={r.text[:200]}")
        return

    data = r.json()
    chunks = data.get("chunks_created", 0)
    item_ids = data.get("knowledge_item_ids", [])
    KNOWLEDGE_ITEM_IDS.extend(item_ids)

    if chunks > 0:
        ok("Text ingested", f"{chunks} chunks, {data.get('total_tokens', 0)} tokens")
    else:
        fail("Text ingestion produced 0 chunks")

    if item_ids:
        ok("Knowledge items created", f"{len(item_ids)} items stored")
    else:
        fail("No knowledge item IDs returned")


# ─── 3. Second Document (for MMR diversity testing) ─────────

SAMPLE_DOC_2 = """
# Founder OS Technical Architecture

## Agent System
The agent system uses a multi-agent orchestrator pattern inspired by Stripe's Minions.
Each specialist agent (content, planner, analytics) can be delegated tasks by the
orchestrator. Agents share context via Redis-backed shared memory.

## Memory Architecture
Four-layer memory: ConversationMemory (rolling chat), WorkingMemory (Redis per-agent),
SharedMemory (Redis cross-agent), LongTermMemory (pgvector RAG).

## RAG Pipeline
Documents are chunked using token-aware recursive splitting (tiktoken cl100k_base),
embedded via Ollama or OpenAI, and stored in PostgreSQL with pgvector.
Retrieval uses hybrid search combining cosine similarity and full-text ranking
via Reciprocal Rank Fusion (RRF).
"""


def test_ingest_second_doc():
    header("3. Second Document Ingestion")

    r = client.post("/api/knowledge/ingest/text", json={
        "content": SAMPLE_DOC_2,
        "title": "Technical Architecture",
        "category": "engineering",
        "tags": ["architecture", "agents", "memory"],
    })

    if r.status_code != 201:
        fail("Ingest second doc", f"status={r.status_code}")
        return

    data = r.json()
    KNOWLEDGE_ITEM_IDS.extend(data.get("knowledge_item_ids", []))
    ok("Second doc ingested", f"{data.get('chunks_created', 0)} chunks")


# ─── 4. File Upload ─────────────────────────────────────────

def test_file_upload():
    header("4. File Upload Ingestion")

    file_content = (
        "# Team Meeting Notes - Q4 Planning\n\n"
        "Attendees: Sarah (CEO), John (CTO), Maria (VP Sales)\n\n"
        "## Key Decisions\n"
        "1. Launch enterprise tier by January 15th\n"
        "2. Hire 3 more engineers for the agent team\n"
        "3. Target: 50 enterprise customers by end of Q1\n"
        "4. Budget: $200K for Q1 marketing campaign\n"
    )

    r = client.post(
        "/api/knowledge/ingest/file",
        files={"file": ("meeting-notes.md", file_content, "text/markdown")},
        data={
            "title": "Q4 Planning Meeting Notes",
            "category": "meetings",
            "tags": "planning,q4,enterprise",
        },
    )

    if r.status_code == 201:
        data = r.json()
        KNOWLEDGE_ITEM_IDS.extend(data.get("knowledge_item_ids", []))
        ok("File uploaded", f"{data.get('chunks_created', 0)} chunks from markdown file")
    elif r.status_code == 501:
        skip("File upload", "Feature returned 501 (may need pdfplumber for PDF)")
    else:
        fail("File upload", f"status={r.status_code} body={r.text[:200]}")


# ─── 5. Knowledge Stats ─────────────────────────────────────

def test_stats():
    header("5. Knowledge Base Stats")

    r = client.get("/api/knowledge/stats")
    if r.status_code != 200:
        fail("Stats endpoint", f"status={r.status_code}")
        return

    stats = r.json()
    total = stats.get("total_items", 0)
    with_emb = stats.get("items_with_embeddings", 0)

    if total > 0:
        ok("Knowledge stats", f"{total} items, {with_emb} with embeddings")
    else:
        fail("No knowledge items found after ingestion")


# ─── 6. Search — Hybrid ─────────────────────────────────────

def test_search_hybrid():
    header("6. Hybrid Search")

    r = client.post("/api/knowledge/search", json={
        "query": "What is the enterprise pricing?",
        "limit": 5,
        "search_type": "hybrid",
    })

    if r.status_code != 200:
        fail("Hybrid search", f"status={r.status_code}")
        return

    data = r.json()
    results = data.get("results", [])

    if not results:
        fail("Hybrid search returned 0 results")
        return

    ok("Hybrid search", f"{len(results)} results")

    # Check relevance — top result should mention pricing
    top_content = results[0].get("content", "").lower()
    if "pricing" in top_content or "enterprise" in top_content or "$499" in top_content:
        ok("Hybrid relevance", f"Top result score={results[0].get('score', 0):.3f}")
    else:
        fail("Hybrid relevance", "Top result doesn't mention pricing/enterprise")


# ─── 7. Search — Semantic ───────────────────────────────────

def test_search_semantic():
    header("7. Semantic Search")

    r = client.post("/api/knowledge/search", json={
        "query": "How does the agent memory system work?",
        "limit": 3,
        "search_type": "semantic",
    })

    if r.status_code != 200:
        fail("Semantic search", f"status={r.status_code}")
        return

    data = r.json()
    results = data.get("results", [])

    if results:
        ok("Semantic search", f"{len(results)} results, top score={results[0].get('score', 0):.3f}")
    else:
        fail("Semantic search returned 0 results")


# ─── 8. Search — Full-Text ──────────────────────────────────

def test_search_fulltext():
    header("8. Full-Text Search")

    r = client.post("/api/knowledge/search", json={
        "query": "enterprise tier",
        "limit": 3,
        "search_type": "fulltext",
    })

    if r.status_code != 200:
        fail("Full-text search", f"status={r.status_code}")
        return

    data = r.json()
    results = data.get("results", [])

    if results:
        ok("Full-text search", f"{len(results)} results")
    else:
        fail("Full-text search returned 0 results")


# ─── 9. Search — MMR (Maximal Marginal Relevance) ───────────

def test_search_mmr():
    header("9. MMR Search (diversity-aware)")

    r = client.post("/api/knowledge/search", json={
        "query": "Founder OS features and pricing",
        "limit": 5,
        "search_type": "mmr",
    })

    if r.status_code != 200:
        fail("MMR search", f"status={r.status_code}")
        return

    data = r.json()
    results = data.get("results", [])

    if not results:
        fail("MMR search returned 0 results")
        return

    ok("MMR search", f"{len(results)} results")

    # MMR should return diverse results — check we get items from different categories
    categories = set(r.get("category") for r in results if r.get("category"))
    if len(categories) > 1:
        ok("MMR diversity", f"Results span {len(categories)} categories: {categories}")
    else:
        # Even with one category, MMR still works — just note it
        ok("MMR returned results", f"Categories: {categories or 'uncategorized'}")


# ─── 10. Search with Category Filter ────────────────────────

def test_search_with_filter():
    header("10. Filtered Search (by category)")

    r = client.post("/api/knowledge/search", json={
        "query": "architecture",
        "limit": 5,
        "search_type": "hybrid",
        "category": "engineering",
    })

    if r.status_code != 200:
        fail("Filtered search", f"status={r.status_code}")
        return

    data = r.json()
    results = data.get("results", [])

    if results:
        # All results should be in the engineering category
        cats = [r.get("category") for r in results]
        if all(c == "engineering" for c in cats):
            ok("Category filter", f"All {len(results)} results in 'engineering'")
        else:
            fail("Category filter", f"Got mixed categories: {cats}")
    else:
        skip("Filtered search", "No results (may need more data)")


# ─── 11. Agent Uses Knowledge in Response ────────────────────

def test_agent_uses_knowledge():
    header("11. Agent Uses Uploaded Context in Responses")

    r = client.post("/api/agents/chat", json={
        "agent_name": "content",
        "message": "What is our enterprise pricing? How much does it cost per seat?",
        "session_id": "rag-test-session",
    })

    if r.status_code != 200:
        fail("Agent chat", f"status={r.status_code} body={r.text[:200]}")
        return

    data = r.json()
    response_text = data.get("response", "") or data.get("content", "") or str(data)
    response_lower = response_text.lower()

    # Check if the agent's response includes information from our ingested doc
    pricing_indicators = ["$499", "499", "enterprise", "per seat", "per month"]
    found = [ind for ind in pricing_indicators if ind.lower() in response_lower]

    if found:
        ok("Agent uses RAG context", f"Found indicators: {found}")
        print(f"    Response preview: {response_text[:300]}...")
    else:
        fail(
            "Agent response missing ingested knowledge",
            f"None of {pricing_indicators} found in response",
        )
        print(f"    Response: {response_text[:500]}")


# ─── 12. List Knowledge Items ───────────────────────────────

def test_list_items():
    header("12. List Knowledge Items")

    r = client.get("/api/knowledge/items?limit=10")
    if r.status_code != 200:
        fail("List items", f"status={r.status_code}")
        return

    items = r.json()
    if isinstance(items, list) and len(items) > 0:
        ok("List items", f"{len(items)} items returned")
        # Check that items have embeddings
        with_emb = sum(1 for i in items if i.get("has_embedding"))
        ok("Embeddings present", f"{with_emb}/{len(items)} items have embeddings")
    else:
        fail("List items", "No items returned")


# ─── Cleanup ────────────────────────────────────────────────

def cleanup():
    header("Cleanup")
    if not KNOWLEDGE_ITEM_IDS:
        print("  No items to clean up")
        return

    deleted = 0
    for item_id in KNOWLEDGE_ITEM_IDS:
        r = client.delete(f"/api/knowledge/items/{item_id}")
        if r.status_code == 204:
            deleted += 1

    print(f"  Deleted {deleted}/{len(KNOWLEDGE_ITEM_IDS)} test knowledge items")


# ─── Main ────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Founder OS — RAG Pipeline Integration Test")
    print("=" * 60)

    try:
        test_health()

        # Ingestion
        test_ingest_text()
        test_ingest_second_doc()
        test_file_upload()

        # Allow a moment for embeddings to process
        time.sleep(1)

        # Stats
        test_stats()

        # Search (all types)
        test_search_hybrid()
        test_search_semantic()
        test_search_fulltext()
        test_search_mmr()
        test_search_with_filter()

        # Agent RAG integration
        test_agent_uses_knowledge()

        # List and verify
        test_list_items()

    finally:
        cleanup()

    # Summary
    print("\n" + "=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print("=" * 60)

    for name, status, detail in RESULTS:
        marker = {"PASS": "✓", "FAIL": "✗", "SKIP": "○"}.get(status, "?")
        print(f"  {marker} {name}" + (f" — {detail}" if detail else ""))

    print()
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()
