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
        "Delegate a task to a specialist agent. Use this when a request "
        "requires domain expertise. Available agents: planner, content, "
        "research, ops, product, support. Pass a clear, specific task "
        "description — don't just forward the user's message verbatim."
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
