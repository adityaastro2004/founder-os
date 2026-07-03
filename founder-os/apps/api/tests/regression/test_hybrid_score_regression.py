"""F3 regression (Phase 0 audit §5): hybrid search scores must be non-zero.

Root cause: in hybrid_search's RRF SQL, Postgres inferred :sem_w/:ft_w as bigint
from the `/(:rrf_k + rank)` context, truncating 0.7 → 0 → integer division → every
hybrid_score was exactly 0 and ranking degenerated to ties. Pinned here end-to-end.
"""
import uuid

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = "http://localhost:8000"


def test_hybrid_search_returns_positive_scores():
    user = f"f3-regression-{uuid.uuid4().hex[:8]}"
    c = httpx.Client(base_url=BASE, timeout=120, headers={"x-test-user": user})

    ingest = c.post("/api/knowledge/ingest/text", json={
        "content": (
            "Our enterprise pricing is $499 per seat per month. The startup tier "
            "costs $49. Enterprise includes SSO, audit logs, and priority support."
        ),
        "title": "Pricing (F3 regression)",
        "category": "business",
        "tags": ["pricing"],
    })
    assert ingest.status_code in (200, 201), ingest.text[:300]

    try:
        r = c.post("/api/knowledge/search", json={
            "query": "enterprise pricing",
            "search_type": "hybrid",
            "limit": 5,
        })
        assert r.status_code == 200, r.text[:300]
        results = r.json()["results"]
        assert results, "hybrid search returned no results for seeded content"
        top = results[0]
        assert top["score"] > 0, (
            f"hybrid score must be positive (RRF floor is ~0.7/(60+3*limit)); "
            f"got {top['score']!r} — integer-division regression is back"
        )
    finally:
        for item_id in ingest.json().get("knowledge_item_ids", []):
            c.delete(f"/api/knowledge/items/{item_id}")
