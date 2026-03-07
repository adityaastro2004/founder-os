"""
Founder OS — Built-in Tools
============================
Starter tools available to agents. Each is a thin async function
registered via the @tool decorator. They'll grow over time; this
file provides the initial toolkit that the core agents rely on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.agents.tools import tool


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
    # This gets monkey-patched with a real implementation by the registry
    # when it has access to the DB session and user_id.
    return json.dumps({"results": [], "note": "Knowledge search not yet wired"})


@tool(
    name="web_search",
    description=(
        "Search the web for current information on a topic. "
        "Returns a summary of the top results."
    ),
)
async def web_search(query: str, num_results: int = 5) -> str:
    """Placeholder — will integrate with Tavily / SerpAPI / Brave."""
    return json.dumps({
        "query": query,
        "results": [],
        "note": "Web search integration not yet configured",
    })


# ============================================================================
# Content
# ============================================================================

@tool(
    name="save_draft",
    description=(
        "Save a content draft (blog post, tweet, email, etc.) to the outputs table. "
        "Pass the content, title, and output_type."
    ),
)
async def save_draft(title: str, content: str, output_type: str = "blog_post") -> str:
    """Placeholder — wired to DB at runtime."""
    return json.dumps({"status": "saved", "title": title, "output_type": output_type})


@tool(
    name="get_writing_style",
    description="Retrieve the user's preferred writing voice and tone guidelines.",
)
async def get_writing_style() -> str:
    """Return the founder's writing voice preferences (mock data)."""
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

    # Blog detection
    if any(w in msg for w in ("blog", "article", "post about", "write about", "long-form", "longform")):
        content_type = "blog"
    # Social media detection
    elif any(w in msg for w in ("tweet", "twitter", "thread", "x post")):
        content_type = "social"
        platform = "twitter"
    elif any(w in msg for w in ("linkedin", "li post")):
        content_type = "social"
        platform = "linkedin"
    elif any(w in msg for w in ("social", "social media", "social post")):
        content_type = "social"
        platform = "both"
    # Email detection
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

    # Extract topic (quoted text or after "about")
    topic_match = re.search(r'["\'](.+?)["\']', user_message)
    if topic_match:
        params["topic"] = topic_match.group(1)
    else:
        about_match = re.search(r'(?:about|on|regarding|topic[:\s]+)\s+(.+?)(?:\.|$)', msg)
        if about_match:
            params["topic"] = about_match.group(1).strip()

    # Extract audience cues
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

    # Get the output schema name
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
        "format's output schema. This tool wraps the generated content "
        "into a structured format that downstream systems (CMS, social "
        "schedulers, email tools) can consume. Pass: content_type (blog, "
        "social, email), the generated content as JSON string, and an "
        "optional title. The tool validates the structure and saves it."
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

    # Parse the content JSON
    try:
        content_data = _json.loads(content_json)
    except _json.JSONDecodeError as e:
        return _json.dumps({
            "status": "error",
            "error": f"Invalid JSON: {e}",
            "hint": "Ensure the content is valid JSON matching the schema.",
        })

    # Get expected schema
    schema = get_output_schema(content_type)
    if not schema:
        return _json.dumps({
            "status": "warning",
            "message": f"No schema for content_type '{content_type}', saving as-is.",
            "content": content_data,
        })

    # Validate required fields
    required = schema.get("required", [])
    missing = [f for f in required if f not in content_data]

    if missing:
        return _json.dumps({
            "status": "incomplete",
            "missing_fields": missing,
            "hint": f"Add these fields: {', '.join(missing)}",
            "partial_content": content_data,
        })

    # Enrich with metadata
    from datetime import datetime, timezone
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
        "specific content type (blog, social, email). Returns platform-specific "
        "structure, guidelines, and quality examples. Call this after "
        "detect_content_type to get format-specific writing instructions."
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
        "Take existing content (e.g., a blog post) and repurpose it into "
        "other formats (social posts, email, etc.). Pass the source content "
        "and the target format(s). Returns structured content for each target."
    ),
)
async def repurpose_content(
    source_content: str,
    source_type: str = "blog",
    target_types: str = "social,email",
) -> str:
    """Flag the content for repurposing — the LLM does the actual transformation."""
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
        "for a given time range."
    ),
)
async def get_business_metrics(metric_type: str = "", days: int = 30) -> str:
    """Return realistic mock metrics (or manual-input data if set)."""
    from app.agents.mock_data import get_mock_metrics
    return json.dumps(get_mock_metrics(metric_type=metric_type, days=days))


@tool(
    name="get_integrations",
    description="List the user's connected integrations and their sync status.",
)
async def get_integrations() -> str:
    """Return mock integration status list."""
    from app.agents.mock_data import get_mock_integrations
    return json.dumps(get_mock_integrations())


# ============================================================================
# Planning & Tasks
# ============================================================================

@tool(
    name="create_task",
    description=(
        "Create a new task in the system. Specify: title, description, "
        "priority (1-10), and optionally an agent to assign it to."
    ),
)
async def create_task(
    title: str,
    description: str = "",
    priority: int = 5,
    agent_name: str = "",
) -> str:
    """Placeholder — wired to DB at runtime."""
    return json.dumps({
        "status": "created",
        "title": title,
        "priority": priority,
        "agent_name": agent_name,
    })


@tool(
    name="list_tasks",
    description="List tasks for the user, optionally filtered by status or agent.",
)
async def list_tasks(status: str = "", agent_name: str = "", limit: int = 10) -> str:
    """Return mock tasks with completion stats."""
    from app.agents.mock_data import get_mock_tasks
    return json.dumps(get_mock_tasks(status=status, agent_name=agent_name, limit=limit))


@tool(
    name="update_task_status",
    description="Update the status of a task (pending, in_progress, completed, failed).",
)
async def update_task_status(task_id: str, status: str) -> str:
    """Placeholder — will update tasks table."""
    return json.dumps({"task_id": task_id, "new_status": status})


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
    """Placeholder — the BaseAgent wires this to WorkingMemory at runtime."""
    return json.dumps({"stored": key})


# ============================================================================
# User Context & Intelligence
# ============================================================================

@tool(
    name="get_user_profile",
    description=(
        "Retrieve the user's full profile: business info, primary goals, "
        "blockers, team size, MRR, preferred work hours, and calendar status. "
        "ALWAYS call this before making recommendations or planning — "
        "you need to know the founder's context and current priorities."
    ),
)
async def get_user_profile() -> str:
    """Placeholder — wired to user_store at runtime by the registry."""
    return json.dumps({
        "note": "get_user_profile not yet wired",
        "profile": {},
    })


@tool(
    name="check_calendar_conflicts",
    description=(
        "Check the user's Google Calendar for conflicts/overlaps with a "
        "proposed time range. Returns conflicting events if any exist. "
        "ALWAYS call this before creating or moving events to avoid "
        "double-booking. Pass start and end as ISO datetimes."
    ),
)
async def check_calendar_conflicts(
    start_datetime: str,
    end_datetime: str,
) -> str:
    """Placeholder — wired at runtime with real gcal_list_events."""
    return json.dumps({
        "conflicts": [],
        "note": "check_calendar_conflicts not yet wired",
    })


@tool(
    name="ask_user_clarification",
    description=(
        "When you don't have enough information to proceed, or the user's "
        "request is ambiguous/conflicting, use this tool to formulate a "
        "clear question back to the user. This signals that you need more "
        "input before acting. Include what you already know and what's "
        "specifically missing."
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
        "Returns the intent type (create, delete, update, list, reschedule, query), "
        "any fields that were extracted (date, time, duration, title, attendees), "
        "and a list of MISSING fields that must be collected before acting. "
        "ALWAYS call this first for any calendar-related user message."
    ),
)
async def detect_calendar_intent(user_message: str) -> str:
    """Parse user message to detect calendar intent and missing fields.

    This is implemented as a deterministic rule-based parser so it works
    even when the LLM is rate-limited.  The LLM should still use its own
    judgment but this tool gives it a structured starting point.
    """
    import re
    msg = user_message.lower().strip()

    # --- Intent classification ---
    intent = "query"  # default
    if any(w in msg for w in ("delete", "remove", "cancel", "clear", "drop")):
        intent = "delete"
    elif any(w in msg for w in ("create", "add", "schedule", "book", "set up", "setup", "block")):
        intent = "create"
    elif any(w in msg for w in ("update", "change", "modify", "edit", "move", "reschedule", "postpone", "shift")):
        intent = "update" if "reschedule" not in msg else "reschedule"
    elif any(w in msg for w in ("list", "show", "what", "tell me", "do i have", "any events")):
        intent = "list"

    # --- Field extraction ---
    extracted: dict = {}
    missing: list[str] = []

    # Date keywords
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

    # Explicit date  (YYYY-MM-DD or DD/MM etc.)
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', msg)
    if date_match:
        extracted["date"] = date_match.group()

    # Time extraction
    time_match = re.search(r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)', msg)
    if time_match:
        extracted["time"] = time_match.group()

    # Duration
    dur_match = re.search(r'(\d+\.?\d*)\s*(hour|hr|min|minute)', msg)
    if dur_match:
        extracted["duration"] = dur_match.group()

    # Scope for deletes
    if intent == "delete":
        if any(w in msg for w in ("all", "every", "everything")):
            extracted["scope"] = "all"
        elif any(w in msg for w in ("ai", "generated", "founder os", "agent")):
            extracted["scope"] = "ai_generated_only"
        else:
            extracted["scope"] = "matching"

        # Check for agent-tag filter  e.g. "delete planner events"
        for tag in _AGENT_TAGS:
            if tag.lower() in msg:
                extracted["agent_filter"] = tag
                break

    # --- Missing field detection per intent ---
    if intent == "create":
        if "date_ref" not in extracted and "date" not in extracted:
            missing.append("date")
        if "time" not in extracted:
            missing.append("start_time")
        if "duration" not in extracted:
            missing.append("duration")
        # Title extraction (rough — take quoted text or last noun phrase)
        title_match = re.search(r'["\'](.+?)["\']', user_message)
        if title_match:
            extracted["title"] = title_match.group(1)
        else:
            missing.append("title")

    elif intent == "update" or intent == "reschedule":
        if "date_ref" not in extracted and "date" not in extracted:
            missing.append("target_date_or_event")
        # Need to know which event
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
        "Validate that all required fields for creating / updating a calendar event "
        "are present and correct. Pass the collected fields as JSON. Returns a list "
        "of validation errors (empty means valid). Call BEFORE gcal_create_event."
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
        errors.append("end_datetime is required when start_datetime is provided (or provide a duration)")
    if start_datetime and end_datetime:
        try:
            from datetime import datetime as _dt
            s = _dt.fromisoformat(start_datetime.replace("Z", "+00:00"))
            e = _dt.fromisoformat(end_datetime.replace("Z", "+00:00"))
            if e <= s:
                errors.append("end_datetime must be after start_datetime")
            if (e - s).total_seconds() > 24 * 3600:
                errors.append("event duration exceeds 24 hours — is this intentional?")
        except ValueError as exc:
            errors.append(f"datetime parse error: {exc}")
    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
    })


# ============================================================================
# Orchestrator — Agent delegation (Stripe Minions pattern)
# ============================================================================

@tool(
    name="delegate_task",
    description=(
        "Delegate a task to a specialist agent. This is your PRIMARY tool for "
        "getting work done. Available agents: planner, content, research, ops, "
        "product, support.\n\n"
        "IMPORTANT RULES:\n"
        "1. ALWAYS rewrite the task as a clear, specific instruction — never "
        "   just forward the user's raw message.\n"
        "2. Include relevant context: user's primary goal, timezone, business "
        "   stage, and any prior delegation results that this agent needs.\n"
        "3. For calendar operations → delegate to 'planner' with timezone.\n"
        "4. For multi-step work → delegate sequentially, passing output of "
        "   step N as context to step N+1.\n\n"
        "The agent will execute the task and return its full response."
    ),
)
async def delegate_task(
    agent_name: str,
    task: str,
    context: str = "",
) -> str:
    """
    Placeholder — wired to OrchestratorAgent.execute_delegation() at runtime.

    The AgentRegistry injects a real implementation that creates the target
    specialist agent, runs it, and returns its response.
    """
    return json.dumps({
        "error": "delegate_task not wired — must be called via orchestrator",
    })


# ============================================================================
# Orchestrator — Memory & Context Tools
# ============================================================================

@tool(
    name="recall_last_orchestration",
    description=(
        "Recall what happened in the most recent orchestration for this user. "
        "Returns: the user's last request, which agents were used, what was "
        "discussed, and what actions were taken. Use this at the START of "
        "every orchestration to maintain conversation continuity. If the "
        "user says 'also' or 'and' or refers to something prior, this gives "
        "you the context."
    ),
)
async def recall_last_orchestration() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({
        "last_orchestration": None,
        "note": "No prior orchestration found (first interaction).",
    })


@tool(
    name="list_available_agents",
    description=(
        "List all currently available specialist agents with their capabilities. "
        "Use this when you need to understand what agents are available, or "
        "when you want to explain to the user what the system can do. "
        "Returns each agent's name, capabilities, and what they're best at."
    ),
)
async def list_available_agents() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({
        "agents": [
            {
                "name": "planner",
                "best_for": "Planning, scheduling, calendar, tasks, prioritisation",
                "has_calendar": True,
            },
            {
                "name": "content",
                "best_for": "Writing, blog posts, emails, social media, copy",
                "has_calendar": False,
            },
            {
                "name": "research",
                "best_for": "Market research, competitor analysis, data analysis",
                "has_calendar": False,
            },
            {
                "name": "ops",
                "best_for": "Operations, metrics, integrations, system health",
                "has_calendar": True,
            },
            {
                "name": "product",
                "best_for": "PRDs, features, roadmap, user stories",
                "has_calendar": False,
            },
            {
                "name": "support",
                "best_for": "Customer emails, FAQs, support playbooks",
                "has_calendar": False,
            },
        ],
    })


@tool(
    name="check_delegation_health",
    description=(
        "Check the health status of the delegation system. Returns whether "
        "agents are available and the router is functioning. Use this if a "
        "delegation fails to diagnose the issue."
    ),
)
async def check_delegation_health() -> str:
    """Placeholder — wired at runtime by the registry."""
    return json.dumps({
        "status": "healthy",
        "agents_available": 6,
        "router_connected": True,
        "note": "All systems operational.",
    })
