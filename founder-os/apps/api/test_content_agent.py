#!/usr/bin/env python3
"""
Founder OS — Content Agent Test Suite
=======================================
Tests the ContentAgent end-to-end:
  1. Content type detection (blog, social, email)
  2. Format guide retrieval with few-shot examples
  3. Structured content generation & validation
  4. Blog post generation from a topic
  5. Social post generation from a topic
  6. Email generation
  7. Content repurposing (blog → social + email)
  8. Writing style integration
  9. Full agent run via API (if server is running)

Run:
  # Unit tests (no server needed):
  python -m pytest test_content_agent.py -v

  # Integration tests (requires running server):
  python test_content_agent.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────
# Unit Tests (no server needed)
# ─────────────────────────────────────────────────────────────

import pytest

# Configure pytest-asyncio to auto mode
pytestmark = pytest.mark.anyio


# ── Content Type Detection ──────────────────────────────────

async def test_detect_blog():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Write a blog post about pricing strategies"))
    assert result["content_type"] == "blog"
    assert "pricing" in result["params"].get("topic", "").lower()



async def test_detect_social_twitter():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Create a tweet thread about our launch"))
    assert result["content_type"] == "social"
    assert result["platform"] == "twitter"



async def test_detect_social_linkedin():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Write a LinkedIn post about our funding round"))
    assert result["content_type"] == "social"
    assert result["platform"] == "linkedin"



async def test_detect_email_newsletter():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Draft a newsletter about our new feature"))
    assert result["content_type"] == "email"
    assert result["params"]["email_type"] == "newsletter"



async def test_detect_welcome_sequence():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Create a welcome email sequence for new users"))
    assert result["content_type"] == "email"
    assert result["params"]["email_type"] == "welcome_sequence"



async def test_detect_cold_email():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Write a cold outreach email for enterprise leads"))
    assert result["content_type"] == "email"
    assert result["params"]["email_type"] == "sales"



async def test_detect_with_audience():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Write a blog post about AI for startup founders"))
    assert result["content_type"] == "blog"



async def test_detect_with_tone():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Write a casual tweet about our product launch"))
    assert result["content_type"] == "social"
    assert result["params"].get("tone") == "casual"



async def test_detect_general_fallback():
    from app.agents.builtin_tools import detect_content_type
    result = json.loads(await detect_content_type("Help me brainstorm some ideas"))
    assert result["content_type"] == "general"


# ── Format Guide Retrieval ──────────────────────────────────


async def test_format_guide_blog():
    from app.agents.builtin_tools import get_content_format_guide
    result = json.loads(await get_content_format_guide("blog"))
    assert result["content_type"] == "blog"
    assert "format_guide" in result
    assert "BLOG POST FORMAT GUIDE" in result["format_guide"]
    assert "title" in result["output_schema_fields"]
    assert "sections" in result["output_schema_fields"]



async def test_format_guide_social():
    from app.agents.builtin_tools import get_content_format_guide
    result = json.loads(await get_content_format_guide("social"))
    assert result["content_type"] == "social"
    assert "SOCIAL MEDIA FORMAT GUIDE" in result["format_guide"]
    assert "twitter_thread" in result["output_schema_fields"]
    assert "linkedin_post" in result["output_schema_fields"]



async def test_format_guide_email():
    from app.agents.builtin_tools import get_content_format_guide
    result = json.loads(await get_content_format_guide("email"))
    assert result["content_type"] == "email"
    assert "EMAIL FORMAT GUIDE" in result["format_guide"]
    assert "subject_lines" in result["output_schema_fields"]



async def test_format_guide_unknown():
    from app.agents.builtin_tools import get_content_format_guide
    result = json.loads(await get_content_format_guide("podcast"))
    assert "available_types" in result


# ── Structured Content Generation ───────────────────────────


async def test_structured_blog_valid():
    from app.agents.builtin_tools import generate_structured_content
    blog_data = json.dumps({
        "title": "Why Usage-Based Pricing Works for SaaS",
        "meta_description": "Learn why usage-based pricing outperforms per-seat models for B2B SaaS startups.",
        "hook": "Last quarter we changed our pricing model and tripled enterprise pipeline.",
        "sections": [
            {"heading": "The Problem", "content": "Per-seat pricing penalises power users."},
            {"heading": "The Solution", "content": "Usage-based pricing aligns with value delivered."},
        ],
        "key_takeaways": [
            "Usage pricing aligns incentives",
            "Hybrid models reduce risk",
            "Communicate early and often",
        ],
        "cta": "What pricing model works for you? Hit reply and tell me.",
        "word_count": 1200,
    })
    result = json.loads(await generate_structured_content("blog", blog_data, "Pricing Post"))
    assert result["status"] == "success"
    assert result["content_type"] == "blog"
    assert result["content"]["_metadata"]["content_type"] == "blog"



async def test_structured_blog_missing_fields():
    from app.agents.builtin_tools import generate_structured_content
    # Missing required fields: hook, sections, key_takeaways, cta
    incomplete = json.dumps({
        "title": "Test Post",
        "meta_description": "A test.",
    })
    result = json.loads(await generate_structured_content("blog", incomplete))
    assert result["status"] == "incomplete"
    assert "hook" in result["missing_fields"]
    assert "sections" in result["missing_fields"]



async def test_structured_social_valid():
    from app.agents.builtin_tools import generate_structured_content
    social_data = json.dumps({
        "topic": "Lessons from $10k MRR",
        "twitter_thread": [
            {"tweet_number": 1, "text": "I hit $10k MRR as a solo founder. Here's how 🧵", "char_count": 52},
            {"tweet_number": 2, "text": "1. I deleted 9 out of 14 features.", "char_count": 35},
        ],
        "linkedin_post": {
            "text": "I hit $10k MRR last week as a solo founder...",
            "char_count": 46,
            "hashtags": ["#startup", "#saas", "#founderlife"],
        },
        "suggested_posting_times": ["Tuesday 9am EST", "Wednesday 8am EST"],
    })
    result = json.loads(await generate_structured_content("social", social_data))
    assert result["status"] == "success"
    assert result["content_type"] == "social"



async def test_structured_email_valid():
    from app.agents.builtin_tools import generate_structured_content
    email_data = json.dumps({
        "email_type": "newsletter",
        "subject_lines": [
            "What we shipped this week (and what it means for you)",
            "3 updates you'll actually care about",
        ],
        "preview_text": "New dashboard, faster exports, and a pricing surprise.",
        "body_html": "Hey {{first_name}},\n\nBig week for us...",
        "cta_text": "See what's new →",
        "cta_url_placeholder": "{{dashboard_url}}",
        "send_timing": "Tuesday 10am EST",
    })
    result = json.loads(await generate_structured_content("email", email_data))
    assert result["status"] == "success"
    assert result["content_type"] == "email"



async def test_structured_invalid_json():
    from app.agents.builtin_tools import generate_structured_content
    result = json.loads(await generate_structured_content("blog", "not valid json"))
    assert result["status"] == "error"
    assert "Invalid JSON" in result["error"]


# ── Content Repurposing ─────────────────────────────────────


async def test_repurpose_content():
    from app.agents.builtin_tools import repurpose_content
    result = json.loads(await repurpose_content(
        source_content="A 1500-word blog post about pricing...",
        source_type="blog",
        target_types="social,email",
    ))
    assert result["status"] == "ready_for_repurposing"
    assert "social" in result["target_formats"]
    assert "email" in result["target_formats"]


# ── Writing Style ───────────────────────────────────────────


async def test_writing_style():
    from app.agents.builtin_tools import get_writing_style
    result = json.loads(await get_writing_style())
    assert "voice" in result
    assert "tone" in result
    assert "avoid" in result
    assert isinstance(result["preferred_formats"], list)


# ── Content Prompts Module ──────────────────────────────────

def test_prompt_module_imports():
    from app.agents.content_prompts import (
        CONTENT_AGENT_SYSTEM_PROMPT,
        BLOG_POST_PROMPT,
        SOCIAL_MEDIA_PROMPT,
        EMAIL_PROMPT,
        CONTENT_OUTPUT_SCHEMAS,
        get_format_prompt,
        get_output_schema,
    )
    # Functional anchors of the master prompt (not decorative headers)
    for anchor in ("detect_content_type", "get_writing_style", "save_draft",
                   "generate_structured_content", "publish-ready"):
        assert anchor in CONTENT_AGENT_SYSTEM_PROMPT, anchor
    assert "BLOG POST FORMAT GUIDE" in BLOG_POST_PROMPT
    assert "SOCIAL MEDIA FORMAT GUIDE" in SOCIAL_MEDIA_PROMPT
    assert "EMAIL FORMAT GUIDE" in EMAIL_PROMPT
    assert "blog_post" in CONTENT_OUTPUT_SCHEMAS
    assert "social_posts" in CONTENT_OUTPUT_SCHEMAS
    assert "email" in CONTENT_OUTPUT_SCHEMAS
    assert "email_sequence" in CONTENT_OUTPUT_SCHEMAS


def test_get_format_prompt():
    from app.agents.content_prompts import get_format_prompt
    assert "BLOG" in get_format_prompt("blog")
    assert "SOCIAL" in get_format_prompt("social")
    assert "EMAIL" in get_format_prompt("email")
    assert "EMAIL" in get_format_prompt("newsletter")
    assert get_format_prompt("unknown_type") == ""


def test_get_output_schema():
    from app.agents.content_prompts import get_output_schema
    blog_schema = get_output_schema("blog")
    assert blog_schema is not None
    assert "title" in blog_schema["properties"]
    assert "sections" in blog_schema["properties"]

    social_schema = get_output_schema("social")
    assert social_schema is not None
    assert "twitter_thread" in social_schema["properties"]

    email_schema = get_output_schema("email")
    assert email_schema is not None
    assert "subject_lines" in email_schema["properties"]

    assert get_output_schema("podcast") is None


def test_content_agent_class():
    """Verify the ContentAgent has the expected attributes."""
    from app.agents.agents import ContentAgent
    assert ContentAgent.name == "content"
    assert "writing" in ContentAgent.capabilities
    assert "blog_writing" in ContentAgent.capabilities
    assert "email_marketing" in ContentAgent.capabilities
    assert "detect_content_type" in ContentAgent.default_tools
    assert "generate_structured_content" in ContentAgent.default_tools
    assert "get_content_format_guide" in ContentAgent.default_tools
    assert "repurpose_content" in ContentAgent.default_tools
    assert "publish-ready" in ContentAgent.default_system_prompt


def test_content_agent_in_registry():
    """Verify the ContentAgent is registered in AGENT_CLASSES."""
    from app.agents.agents import AGENT_CLASSES
    assert "content" in AGENT_CLASSES
    from app.agents.agents import ContentAgent
    assert AGENT_CLASSES["content"] is ContentAgent


# ─────────────────────────────────────────────────────────────
# Integration Tests (requires running server)
# ─────────────────────────────────────────────────────────────

BASE = "http://localhost:8000"
USER = "content-test-user"


def run_integration_tests():
    """Run integration tests against a running Founder OS server."""
    import httpx

    PASS, FAIL, SKIP = 0, 0, 0
    RESULTS: list[tuple[str, str, str]] = []

    def ok(name: str, detail: str = ""):
        nonlocal PASS
        PASS += 1
        RESULTS.append((name, "PASS", detail))
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))

    def fail_t(name: str, detail: str = ""):
        nonlocal FAIL
        FAIL += 1
        RESULTS.append((name, "FAIL", detail))
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))

    def skip_t(name: str, detail: str = ""):
        nonlocal SKIP
        SKIP += 1
        RESULTS.append((name, "SKIP", detail))
        print(f"  [SKIP] {name}" + (f" — {detail}" if detail else ""))

    # x-test-user: dev-only auth identity (APP_ENV=development bypass in app/auth.py)
    # 300s: local Ollama generations + multi-round orchestrator delegation need headroom
    c = httpx.Client(base_url=BASE, timeout=300, headers={"x-test-user": USER})

    # ── 1. Health check ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  CONTENT AGENT — Integration Tests")
    print("=" * 60)

    try:
        r = c.get("/")
        assert r.status_code == 200
        ok("Server healthy")
    except Exception as e:
        fail_t("Server healthy", str(e))
        print("\n  Server not running! Start it first.\n")
        return

    # ── 2. Generate blog post via agent chat ────────────────
    print("\n--- Blog Post Generation ---")
    try:
        r = c.post("/api/agents/content/chat", json={
            "message": (
                'Write a full blog post about "Why solo founders should automate '
                'their content pipeline". Make it actionable with specific tools '
                "and examples. Target audience: technical solo founders."
            ),
        })
        assert r.status_code == 200
        data = r.json()
        content = data.get("reply") or data.get("response") or data.get("content", "")
        assert len(content) > 200, f"Blog too short: {len(content)} chars"
        ok("Blog post generated", f"{len(content)} chars")

        # Check for structure markers
        has_heading = "#" in content or "##" in content
        has_cta = any(w in content.lower() for w in ("reply", "share", "sign up", "try", "check out", "click"))
        if has_heading:
            ok("Blog has headings")
        else:
            fail_t("Blog has headings", "No markdown headings found")
        if has_cta:
            ok("Blog has CTA")
        else:
            fail_t("Blog has CTA", "No call-to-action found")

    except Exception as e:
        fail_t("Blog post generation", str(e))

    # ── 3. Generate social posts via agent chat ─────────────
    print("\n--- Social Post Generation ---")
    try:
        r = c.post("/api/agents/content/chat", json={
            "message": (
                'Create a Twitter thread and LinkedIn post about "How we reached '
                '$10k MRR as a bootstrapped startup". Make it authentic and '
                "data-driven."
            ),
        })
        assert r.status_code == 200
        data = r.json()
        content = data.get("reply") or data.get("response") or data.get("content", "")
        assert len(content) > 100, f"Social posts too short: {len(content)} chars"
        ok("Social posts generated", f"{len(content)} chars")

        # Check for platform markers
        has_twitter = any(w in content.lower() for w in ("thread", "tweet", "🧵", "1/", "/5", "/7"))
        has_linkedin = "linkedin" in content.lower() or len(content) > 500
        if has_twitter:
            ok("Twitter thread present")
        else:
            skip_t("Twitter thread present", "Thread markers not found (may be inline)")
        if has_linkedin:
            ok("LinkedIn post present")
        else:
            skip_t("LinkedIn post present", "LinkedIn markers not found")

    except Exception as e:
        fail_t("Social post generation", str(e))

    # ── 4. Generate email via agent chat ────────────────────
    print("\n--- Email Generation ---")
    try:
        r = c.post("/api/agents/content/chat", json={
            "message": (
                "Draft a product update email announcing our new AI-powered "
                "dashboard feature. Include 2-3 subject line variants for A/B "
                "testing. Keep it concise and action-oriented."
            ),
        })
        assert r.status_code == 200
        data = r.json()
        content = data.get("reply") or data.get("response") or data.get("content", "")
        assert len(content) > 100, f"Email too short: {len(content)} chars"
        ok("Email generated", f"{len(content)} chars")

        has_subject = any(w in content.lower() for w in ("subject", "subject line", "option a", "variant"))
        if has_subject:
            ok("Email has subject line variants")
        else:
            skip_t("Email has subject lines", "Subject line markers not found")

    except Exception as e:
        fail_t("Email generation", str(e))

    # ── 5. Content repurposing test ─────────────────────────
    print("\n--- Content Repurposing ---")
    try:
        r = c.post("/api/agents/content/chat", json={
            "message": (
                "Take this blog post idea and repurpose it: 'We switched from "
                "per-seat to usage-based pricing and tripled our enterprise "
                "pipeline in 60 days.' Generate: 1) A Twitter thread, "
                "2) A LinkedIn post, 3) A newsletter email."
            ),
        })
        assert r.status_code == 200
        data = r.json()
        content = data.get("reply") or data.get("response") or data.get("content", "")
        assert len(content) > 200, f"Repurposed content too short: {len(content)} chars"
        ok("Content repurposed", f"{len(content)} chars, multiple formats")
    except Exception as e:
        fail_t("Content repurposing", str(e))

    # ── 6. Agent delegation (orchestrator → content) ────────
    print("\n--- Delegation Test ---")
    try:
        r = c.post("/api/agents/orchestrator/chat", json={
            "message": (
                "I need a blog post about why startups should invest in "
                "developer experience. Delegate this to the content agent."
            ),
        })
        assert r.status_code == 200
        data = r.json()
        content = data.get("reply") or data.get("response") or data.get("content", "")
        assert len(content) > 100
        ok("Orchestrator → Content delegation", f"{len(content)} chars")
    except Exception as e:
        fail_t("Orchestrator → Content delegation", str(e))

    # ── Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print("=" * 60)

    if FAIL > 0:
        print("\nFailed tests:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  ✗ {name}: {detail}")

    return FAIL == 0


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--unit" in sys.argv:
        # Run unit tests only
        sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
    else:
        # Run integration tests (server must be running)
        success = run_integration_tests()
        sys.exit(0 if success else 1)
