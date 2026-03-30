"""
Founder OS — Built-in Tools
============================
Real tool implementations backed by database, web search, and integrations.

Tools are registered via the @tool decorator. Some are standalone (e.g.
get_current_datetime), others are stubs that get their implementation
injected at runtime by AgentRegistry (e.g. search_knowledge, save_draft,
create_task) so they have access to the DB session and user context.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.tools import tool

logger = logging.getLogger(__name__)


# ============================================================================
# Knowledge & Research
# ============================================================================

@tool(
    name="search_knowledge",
    description=(
        "Search the user's knowledge base for relevant information. "
        "Returns the top matching documents with their content."
    ),
)
async def search_knowledge(query: str, category: str = "", limit: int = 5) -> str:
    """Placeholder — wired to pgvector search in AgentRegistry at runtime."""
    return json.dumps({"results": [], "note": "Knowledge search not yet wired"})


@tool(
    name="web_search",
    description=(
        "Search the web for current information on a topic. "
        "Returns a summary of the top results. Use this for market research, "
        "competitor analysis, current events, pricing data, or any information "
        "that needs to be current."
    ),
)
async def web_search(query: str, num_results: int = 5) -> str:
    """Real web search using DuckDuckGo HTML (no API key needed).

    Falls back to Tavily/SerpAPI if configured.
    This stub is replaced at runtime by the registry if API keys are set.
    The default implementation uses DuckDuckGo for zero-config search.
    """
    try:
        results = await _duckduckgo_search(query, num_results)
        if results:
            return json.dumps({
                "query": query,
                "results": results,
                "source": "duckduckgo",
                "total": len(results),
            })
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)

    return json.dumps({
        "query": query,
        "results": [],
        "note": "Web search unavailable. Configure TAVILY_API_KEY or SERPAPI_KEY in .env for reliable search.",
    })


async def _duckduckgo_search(query: str, num_results: int = 5) -> list[dict]:
    """Search DuckDuckGo via the instant answer API (JSON, no key needed)."""
    import httpx

    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # DuckDuckGo instant answer API
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            data = resp.json()

            # Abstract (main answer)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "snippet": data["Abstract"][:500],
                    "url": data.get("AbstractURL", ""),
                    "source": data.get("AbstractSource", ""),
                })

            # Related topics
            for topic in (data.get("RelatedTopics") or [])[:num_results - len(results)]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "snippet": topic.get("Text", "")[:300],
                        "url": topic.get("FirstURL", ""),
                        "source": "DuckDuckGo",
                    })

            # If no instant answer results, try the HTML search fallback
            if not results:
                resp2 = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "FounderOS/1.0"},
                    follow_redirects=True,
                )
                # Parse basic results from HTML
                import re
                # Extract result snippets from the HTML response
                snippet_matches = re.findall(
                    r'class="result__snippet"[^>]*>(.*?)</a',
                    resp2.text, re.DOTALL,
                )
                url_matches = re.findall(
                    r'class="result__url"[^>]*href="([^"]*)"',
                    resp2.text,
                )
                title_matches = re.findall(
                    r'class="result__a"[^>]*>(.*?)</a>',
                    resp2.text, re.DOTALL,
                )

                for i in range(min(num_results, len(snippet_matches))):
                    # Strip HTML tags
                    snippet = re.sub(r'<[^>]+>', '', snippet_matches[i]).strip()
                    title = re.sub(r'<[^>]+>', '', title_matches[i]).strip() if i < len(title_matches) else ""
                    url = url_matches[i] if i < len(url_matches) else ""
                    if snippet:
                        results.append({
                            "title": title or query,
                            "snippet": snippet[:300],
                            "url": url,
                            "source": "DuckDuckGo",
                        })

    except Exception as exc:
        logger.debug("DuckDuckGo search error: %s", exc)

    return results[:num_results]


# ============================================================================
# Content
# ============================================================================

@tool(
    name="save_draft",
    description=(
        "Save a content draft (blog post, tweet, email, etc.) to the outputs table. "
        "Pass the content, title, and output_type. Returns the saved draft ID."
    ),
)
async def save_draft(title: str, content: str, output_type: str = "blog_post") -> str:
    """Placeholder — wired to DB at runtime by AgentRegistry."""
    return json.dumps({"status": "saved", "title": title, "output_type": output_type,
                        "note": "save_draft not yet wired to DB"})


@tool(
    name="get_writing_style",
    description="Retrieve the user's preferred writing voice and tone guidelines.",
)
async def get_writing_style() -> str:
    """Return the founder's writing voice preferences.
    Wired at runtime to pull from FounderProfile.writing_voice if available.
    """
    from app.agents.mock_data import get_mock_writing_style
    return json.dumps(get_mock_writing_style())


# ============================================================================
# Content Agent — Format Detection & Structured Generation
# ============================================================================

@tool(
    name="detect_content_type",
    description=(
        "Analyse a user message and detect the content type they want. "
        "Returns the format (blog, social, email, general), suggested "
        "output schema, and any extracted parameters (topic, audience, "
        "platform, tone). ALWAYS call this first for content requests."
    ),
)
async def detect_content_type(user_message: str) -> str:
    """Rule-based content type detection to bootstrap the LLM's judgment."""
    import re
    msg = user_message.lower().strip()

    content_type = "general"
    platform = None
    params: dict = {}

    # Social media detection (check FIRST)
    if any(w in msg for w in ("tweet", "twitter", "thread", "x post")):
        content_type = "social"
        platform = "twitter"
    elif any(w in msg for w in ("linkedin", "li post")):
        content_type = "social"
        platform = "linkedin"
    elif any(w in msg for w in ("social media", "social post")):
        content_type = "social"
        platform = "both"
    elif any(w in msg for w in ("blog", "article", "post about", "write about", "long-form", "longform")):
        content_type = "blog"
    elif any(w in msg for w in ("email", "newsletter", "welcome sequence", "drip", "outreach", "cold email")):
        content_type = "email"
        if "welcome" in msg or "onboard" in msg or "sequence" in msg or "drip" in msg:
            params["email_type"] = "welcome_sequence"
        elif "newsletter" in msg:
            params["email_type"] = "newsletter"
        elif "cold" in msg or "outreach" in msg or "sales" in msg:
            params["email_type"] = "sales"
        elif "update" in msg or "announce" in msg or "launch" in msg:
            params["email_type"] = "product_update"
        else:
            params["email_type"] = "newsletter"

    # Extract topic
    topic_match = re.search(r'["\'](.+?)["\']', user_message)
    if topic_match:
        params["topic"] = topic_match.group(1)
    else:
        about_match = re.search(r'(?:about|on|regarding|topic[:\s]+)\s+(.+?)(?:\.|$)', msg)
        if about_match:
            params["topic"] = about_match.group(1).strip()

    # Extract audience
    for_match = re.search(r'(?:for|targeting|aimed at)\s+(.+?)(?:\.|,|$)', msg)
    if for_match:
        params["target_audience"] = for_match.group(1).strip()

    # Tone cues
    tone_keywords = {
        "professional": "professional", "casual": "casual",
        "funny": "humorous", "serious": "serious",
        "technical": "technical", "simple": "simple",
        "inspiring": "inspirational", "urgent": "urgent",
    }
    for kw, tone in tone_keywords.items():
        if kw in msg:
            params["tone"] = tone
            break

    from app.agents.content_prompts import get_output_schema
    schema = get_output_schema(content_type)

    return json.dumps({
        "content_type": content_type,
        "platform": platform,
        "params": params,
        "has_structured_schema": schema is not None,
        "schema_fields": list(schema.get("properties", {}).keys()) if schema else [],
        "original_message": user_message,
    }, default=str)


@tool(
    name="generate_structured_content",
    description=(
        "Generate content and return it as structured JSON matching the "
        "format's output schema. Pass: content_type (blog, social, email), "
        "the generated content as JSON string, and an optional title."
    ),
)
async def generate_structured_content(
    content_type: str,
    content_json: str,
    title: str = "",
) -> str:
    """Validate and store structured content output."""
    import json as _json
    from app.agents.content_prompts import get_output_schema

    try:
        content_data = _json.loads(content_json)
    except _json.JSONDecodeError as e:
        return _json.dumps({
            "status": "error",
            "error": f"Invalid JSON: {e}",
            "hint": "Ensure the content is valid JSON matching the schema.",
        })

    schema = get_output_schema(content_type)
    if not schema:
        return _json.dumps({
            "status": "warning",
            "message": f"No schema for content_type '{content_type}', saving as-is.",
            "content": content_data,
        })

    required = schema.get("required", [])
    missing = [f for f in required if f not in content_data]
    if missing:
        return _json.dumps({
            "status": "incomplete",
            "missing_fields": missing,
            "hint": f"Add these fields: {', '.join(missing)}",
            "partial_content": content_data,
        })

    content_data["_metadata"] = {
        "content_type": content_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title or content_data.get("title", "Untitled"),
        "schema_version": "1.0",
    }

    return _json.dumps({
        "status": "success",
        "content_type": content_type,
        "title": title or content_data.get("title", "Untitled"),
        "content": content_data,
        "fields_present": list(content_data.keys()),
    }, default=str)


@tool(
    name="get_content_format_guide",
    description=(
        "Retrieve the detailed format guide and few-shot examples for a "
        "specific content type (blog, social, email)."
    ),
)
async def get_content_format_guide(content_type: str) -> str:
    """Return the format-specific prompt and examples."""
    from app.agents.content_prompts import get_format_prompt, get_output_schema

    prompt = get_format_prompt(content_type)
    schema = get_output_schema(content_type)

    if not prompt:
        return json.dumps({
            "content_type": content_type,
            "guide": "No specific guide for this type. Use general writing best practices.",
            "available_types": ["blog", "social", "email", "newsletter", "twitter", "linkedin"],
        })

    return json.dumps({
        "content_type": content_type,
        "format_guide": prompt,
        "output_schema_fields": list(schema.get("properties", {}).keys()) if schema else [],
        "required_fields": schema.get("required", []) if schema else [],
    }, default=str)


@tool(
    name="repurpose_content",
    description=(
        "Take existing content and repurpose it into other formats. "
        "Pass the source content and the target format(s)."
    ),
)
async def repurpose_content(
    source_content: str,
    source_type: str = "blog",
    target_types: str = "social,email",
) -> str:
    """Flag the content for repurposing."""
    targets = [t.strip() for t in target_types.split(",")]
    return json.dumps({
        "status": "ready_for_repurposing",
        "source_type": source_type,
        "source_length": len(source_content),
        "target_formats": targets,
        "instructions": (
            "Generate content for each target format. For each, use the "
            "format-specific structure and few-shot examples. Extract the "
            "key insight from the source and adapt it for each platform. "
            "Use generate_structured_content to save each piece."
        ),
    }, default=str)


# ============================================================================
# Analytics & Metrics
# ============================================================================

@tool(
    name="get_business_metrics",
    description=(
        "Retrieve the user's business metrics (MRR, users, traffic, etc.) "
        "for a given time range. Returns real data from business_metrics table "
        "if available, otherwise mock data for development."
    ),
)
async def get_business_metrics(metric_type: str = "", days: int = 30) -> str:
    """Return metrics — wired to real DB at runtime, falls back to mock."""
    from app.agents.mock_data import get_mock_metrics
    return json.dumps(get_mock_metrics(metric_type=metric_type, days=days))


@tool(
    name="get_integrations",
    description="List the user's connected integrations and their sync status.",
)
async def get_integrations() -> str:
    """Placeholder — wired to DB at runtime by AgentRegistry."""
    from app.agents.mock_data import get_mock_integrations
    return json.dumps(get_mock_integrations())


# ============================================================================
# Planning & Tasks
# ============================================================================

@tool(
    name="create_task",
    description=(
        "Create a new task in the system. Specify: title, description, "
        "priority (1-10), and optionally an agent to assign it to. "
        "The task is persisted to the database."
    ),
)
async def create_task(
    title: str,
    description: str = "",
    priority: int = 5,
    agent_name: str = "",
) -> str:
    """Placeholder — wired to DB at runtime by AgentRegistry."""
    return json.dumps({
        "status": "created",
        "title": title,
        "priority": priority,
        "agent_name": agent_name,
        "note": "create_task not yet wired to DB",
    })


@tool(
    name="list_tasks",
    description="List tasks for the user, optionally filtered by status or agent.",
)
async def list_tasks(status: str = "", agent_name: str = "", limit: int = 10) -> str:
    """Placeholder — wired to DB at runtime by AgentRegistry."""
    from app.agents.mock_data import get_mock_tasks
    return json.dumps(get_mock_tasks(status=status, agent_name=agent_name, limit=limit))


@tool(
    name="update_task_status",
    description="Update the status of a task (pending, in_progress, completed, failed).",
)
async def update_task_status(task_id: str, status: str) -> str:
    """Placeholder — wired to DB at runtime by AgentRegistry."""
    return json.dumps({"task_id": task_id, "new_status": status,
                        "note": "update_task_status not yet wired to DB"})


# ============================================================================
# Utility
# ============================================================================

@tool(
    name="get_current_datetime",
    description="Get the current date and time in UTC.",
)
async def get_current_datetime() -> str:
    now = datetime.now(timezone.utc)
    return json.dumps({
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "day_of_week": now.strftime("%A"),
        "time": now.strftime("%H:%M UTC"),
    })


@tool(
    name="store_working_memory",
    description=(
        "Store a key-value pair in working memory (persists for this session). "
        "Use this to remember intermediate results, plans, or state."
    ),
)
async def store_working_memory(key: str, value: str) -> str:
    """Placeholder — the registry wires this to WorkingMemory at runtime."""
    return json.dumps({"stored": key})


# ============================================================================
# User Context & Intelligence
# ============================================================================

@tool(
    name="get_user_profile",
    description=(
        "Retrieve the user's full profile: business info, primary goals, "
        "blockers, team size, MRR, preferred work hours, and calendar status. "
        "ALWAYS call this before making recommendations or planning."
    ),
)
async def get_user_profile() -> str:
    """Placeholder — wired to user_store at runtime by the registry."""
    return json.dumps({"note": "get_user_profile not yet wired", "profile": {}})


@tool(
    name="check_calendar_conflicts",
    description=(
        "Check the user's Google Calendar for conflicts/overlaps with a "
        "proposed time range. Returns conflicting events if any exist. "
        "ALWAYS call this before creating or moving events."
    ),
)
async def check_calendar_conflicts(
    start_datetime: str,
    end_datetime: str,
) -> str:
    """Placeholder — wired at runtime with real gcal_list_events."""
    return json.dumps({"conflicts": [], "note": "check_calendar_conflicts not yet wired"})


@tool(
    name="ask_user_clarification",
    description=(
        "When you don't have enough information to proceed, use this tool "
        "to formulate a clear question back to the user. Include what you "
        "already know and what's specifically missing."
    ),
)
async def ask_user_clarification(
    question: str,
    what_i_know: str = "",
    options: str = "",
) -> str:
    """Return a structured clarification request."""
    return json.dumps({
        "type": "clarification_needed",
        "question": question,
        "context": what_i_know,
        "options": options,
    })


# ============================================================================
# Calendar Intent Detection & Validation
# ============================================================================

_AGENT_TAGS = ("PLANNER", "OPS", "CONTENT", "RESEARCH", "PRODUCT", "SUPPORT")

@tool(
    name="detect_calendar_intent",
    description=(
        "Analyse a user message and detect the calendar intent. "
        "Returns intent type, extracted fields, and missing fields. "
        "ALWAYS call this first for any calendar-related user message."
    ),
)
async def detect_calendar_intent(user_message: str) -> str:
    """Deterministic rule-based parser for calendar intents."""
    import re
    msg = user_message.lower().strip()

    intent = "query"
    if any(w in msg for w in ("delete", "remove", "cancel", "clear", "drop")):
        intent = "delete"
    elif any(w in msg for w in ("create", "add", "schedule", "book", "set up", "setup", "block")):
        intent = "create"
    elif any(w in msg for w in ("update", "change", "modify", "edit", "move", "reschedule", "postpone", "shift")):
        intent = "update" if "reschedule" not in msg else "reschedule"
    elif any(w in msg for w in ("list", "show", "what", "tell me", "do i have", "any events")):
        intent = "list"

    extracted: dict = {}
    missing: list[str] = []

    date_keywords = {
        "today": "today", "tonight": "today",
        "tomorrow": "tomorrow", "tmrw": "tomorrow",
        "day after": "day_after_tomorrow",
        "this week": "this_week", "next week": "next_week",
        "monday": "monday", "tuesday": "tuesday", "wednesday": "wednesday",
        "thursday": "thursday", "friday": "friday", "saturday": "saturday", "sunday": "sunday",
    }
    for kw, val in date_keywords.items():
        if kw in msg:
            extracted["date_ref"] = val
            break

    date_match = re.search(r'\d{4}-\d{2}-\d{2}', msg)
    if date_match:
        extracted["date"] = date_match.group()

    time_match = re.search(r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)', msg)
    if time_match:
        extracted["time"] = time_match.group()

    dur_match = re.search(r'(\d+\.?\d*)\s*(hour|hr|min|minute)', msg)
    if dur_match:
        extracted["duration"] = dur_match.group()

    if intent == "delete":
        if any(w in msg for w in ("all", "every", "everything")):
            extracted["scope"] = "all"
        elif any(w in msg for w in ("ai", "generated", "founder os", "agent")):
            extracted["scope"] = "ai_generated_only"
        else:
            extracted["scope"] = "matching"
        for tag in _AGENT_TAGS:
            if tag.lower() in msg:
                extracted["agent_filter"] = tag
                break

    if intent == "create":
        if "date_ref" not in extracted and "date" not in extracted:
            missing.append("date")
        if "time" not in extracted:
            missing.append("start_time")
        if "duration" not in extracted:
            missing.append("duration")
        title_match = re.search(r'["\'](.+?)["\']', user_message)
        if title_match:
            extracted["title"] = title_match.group(1)
        else:
            missing.append("title")
    elif intent in ("update", "reschedule"):
        if "date_ref" not in extracted and "date" not in extracted:
            missing.append("target_date_or_event")
        missing.append("event_identifier")
    elif intent == "delete":
        if "date_ref" not in extracted and "date" not in extracted:
            missing.append("date_range")

    return json.dumps({
        "intent": intent,
        "extracted": extracted,
        "missing_fields": missing,
        "needs_clarification": len(missing) > 0 and intent in ("create", "update", "reschedule"),
        "original_message": user_message,
    }, default=str)


@tool(
    name="validate_event_fields",
    description=(
        "Validate that all required fields for creating/updating a calendar "
        "event are present and correct. Call BEFORE gcal_create_event."
    ),
)
async def validate_event_fields(
    title: str = "",
    start_datetime: str = "",
    end_datetime: str = "",
    date_str: str = "",
) -> str:
    """Validate event fields before creating."""
    errors: list[str] = []
    if not title or len(title.strip()) < 2:
        errors.append("title is missing or too short")
    if not start_datetime and not date_str:
        errors.append("start_datetime or date is required")
    if start_datetime and not end_datetime:
        errors.append("end_datetime is required when start_datetime is provided")
    if start_datetime and end_datetime:
        try:
            from datetime import datetime as _dt
            s = _dt.fromisoformat(start_datetime.replace("Z", "+00:00"))
            e = _dt.fromisoformat(end_datetime.replace("Z", "+00:00"))
            if e <= s:
                errors.append("end_datetime must be after start_datetime")
            if (e - s).total_seconds() > 24 * 3600:
                errors.append("event duration exceeds 24 hours")
        except ValueError as exc:
            errors.append(f"datetime parse error: {exc}")
    return json.dumps({"valid": len(errors) == 0, "errors": errors})


# ============================================================================
# Orchestrator — Agent delegation (Stripe Minions pattern)
# ============================================================================

@tool(
    name="delegate_task",
    description=(
        "Delegate a task to a specialist agent. Available agents: planner, "
        "content, research, ops, product, support.\n\n"
        "RULES:\n"
        "1. Rewrite the task as a clear instruction — never forward raw messages.\n"
        "2. Include context: user's goal, timezone, business stage, prior results.\n"
        "3. For calendar operations → delegate to 'planner' with timezone.\n"
        "4. For multi-step work → delegate sequentially, passing prior output."
    ),
)
async def delegate_task(
    agent_name: str,
    task: str,
    context: str = "",
) -> str:
    """Placeholder — wired to OrchestratorAgent.execute_delegation() at runtime."""
    return json.dumps({"error": "delegate_task not wired — must be called via orchestrator"})


# ============================================================================
# Orchestrator — Memory & Context Tools
# ============================================================================

@tool(
    name="recall_last_orchestration",
    description=(
        "Recall the most recent orchestration for this user. Returns: "
        "last request, agents used, what was discussed, actions taken."
    ),
)
async def recall_last_orchestration() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({"last_orchestration": None, "note": "No prior orchestration found."})


@tool(
    name="list_available_agents",
    description="List all currently available specialist agents with their capabilities.",
)
async def list_available_agents() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({
        "agents": [
            {"name": "planner", "best_for": "Planning, scheduling, calendar, tasks", "has_calendar": True},
            {"name": "content", "best_for": "Writing, blog posts, emails, social media", "has_calendar": False},
            {"name": "research", "best_for": "Market research, competitor analysis", "has_calendar": False},
            {"name": "ops", "best_for": "Operations, metrics, integrations", "has_calendar": True},
            {"name": "product", "best_for": "PRDs, features, roadmap, user stories", "has_calendar": False},
            {"name": "support", "best_for": "Customer emails, FAQs, support playbooks", "has_calendar": False},
        ],
    })


@tool(
    name="check_delegation_health",
    description="Check the health status of the delegation system.",
)
async def check_delegation_health() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({"status": "healthy", "agents_available": 6, "router_connected": True})
