"""
Founder OS — Planner Routes (Production)
==========================================
User-facing endpoints for the autonomous weekly planner.

Flow for end users:
  1. POST /api/planner/onboard   — Provide business context (one-time)
  2. GET  /api/planner/connect   — Connect Google Calendar (one-time)
  3. Done! The scheduler generates plans + pushes to GCal every Monday.

Optional:
  - POST /api/planner/update     — Update context with natural language
  - POST /api/planner/generate   — Force an immediate plan generation
  - GET  /api/planner/status     — Check connection, last plan, etc.
  - GET  /api/planner/history    — View past plan summaries
"""

from __future__ import annotations

import time
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.user_store import (
    UserProfile,
    get_user,
    get_or_create_user,
    save_user,
    update_user_context,
    store_plan_history,
    get_plan_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planner", tags=["planner"])


# Plan history is now DB-backed via user_store.store_plan_history / get_plan_history


# ============================================================================
# Request / Response Models
# ============================================================================

class OnboardRequest(BaseModel):
    """One-time onboarding — tell us about your business."""
    user_id: str = Field("default-user", description="Unique user identifier")
    name: str = Field("", description="Your name")
    business_name: str = Field(..., min_length=1, description="Company/product name")
    business_type: str = Field("B2B SaaS", description="B2B SaaS, D2C, marketplace, agency, etc.")
    industry: str = Field("", description="e.g. Developer Tools, FinTech, HealthTech")
    business_stage: str = Field("mvp", description="idea, mvp, seed, series-a, profitable")
    target_audience: str = Field("", description="Who you serve")
    team_size: int = Field(1, ge=1)
    current_mrr: float = Field(0.0, ge=0)
    current_users: int = Field(0, ge=0)
    primary_goal: str = Field("", description="Your #1 goal right now")
    goals_this_week: list[str] = Field(default_factory=list, description="Top goals for this week")
    timezone: str = Field("Asia/Kolkata", description="Your timezone")
    preferred_work_hours: str = Field("09:00-18:00", description="e.g. 09:00-18:00")
    custom_instructions: str = Field("", description="Any preferences for planning")


class UpdateContextRequest(BaseModel):
    """Update your context — plain text or structured fields."""
    user_id: str = Field("default-user")
    message: str = Field(
        "",
        description="Natural language update, e.g. 'We just hit $15k MRR, focused on hiring this week'",
    )
    # Optional structured overrides (merged if provided)
    goals_this_week: list[str] | None = None
    completed_last_week: list[str] | None = None
    blockers: list[str] | None = None
    current_mrr: float | None = None
    current_users: int | None = None
    primary_goal: str | None = None
    custom_instructions: str | None = None


class GenerateRequest(BaseModel):
    """Force an immediate plan generation."""
    user_id: str = Field("default-user")
    message: str = Field(
        "Plan my week",
        description="Optional extra context or focus areas for this week",
    )


# ============================================================================
# 1. ONBOARD — set up business context (one-time)
# ============================================================================

@router.post("/onboard")
async def onboard(body: OnboardRequest):
    """
    Set up your business profile. Call this once — your data is remembered
    and used automatically every Monday when the planner runs.

    After onboarding, connect Google Calendar via GET /api/planner/connect.
    """
    user = get_or_create_user(body.user_id)

    # Merge all fields
    for field_name in body.model_fields:
        value = getattr(body, field_name)
        if value is not None and field_name != "user_id":
            setattr(user, field_name, value)

    save_user(user)

    return {
        "status": "onboarded",
        "user_id": user.user_id,
        "business_name": user.business_name,
        "gcal_connected": user.gcal_connected,
        "next_step": (
            "Connect Google Calendar: GET /api/planner/connect?user_id=" + user.user_id
            if not user.gcal_connected
            else "You're all set! The planner will run every Monday at 8 AM."
        ),
        "message": (
            f"Welcome to Founder OS, {user.name or 'founder'}! "
            f"Your profile for {user.business_name} is saved. "
            + ("Connect Google Calendar next." if not user.gcal_connected
               else "Your calendar is connected — plans will be generated automatically.")
        ),
    }


# ============================================================================
# 2. CONNECT — Google Calendar OAuth (one-time)
# ============================================================================

@router.get("/connect")
async def connect_gcal(user_id: str = Query("default-user")):
    """
    Start Google Calendar connection. Opens OAuth consent screen.
    After granting access, your calendar is linked permanently.
    """
    from app.integrations.calendar_integration import get_auth_url

    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not configured. Set GOOGLE_CLIENT_ID in .env.",
        )

    # Ensure user exists
    get_or_create_user(user_id)

    # Use user_id as state so we know who to link on callback
    auth_url = get_auth_url(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        state=user_id,
    )
    return {
        "auth_url": auth_url,
        "message": "Open this URL in your browser to connect Google Calendar.",
        "user_id": user_id,
    }


@router.get("/connect/callback")
async def connect_callback(code: str, state: str = "default-user"):
    """
    OAuth2 callback — automatically called by Google after user grants access.
    Links the calendar to the user's profile.
    """
    from app.integrations.calendar_integration import exchange_code_for_tokens

    settings = get_settings()
    user_id = state  # state param carries the user_id

    try:
        tokens = await exchange_code_for_tokens(
            code=code,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    # Link tokens to user profile
    user = get_or_create_user(user_id)
    user.store_gcal_tokens(tokens)
    save_user(user)

    # Also store in the legacy calendar_integration token store
    from app.integrations.calendar_integration import store_tokens
    store_tokens(user_id, tokens)

    return {
        "status": "connected",
        "user_id": user_id,
        "message": (
            f"Google Calendar connected for {user.business_name or user_id}! "
            "Your weekly plan will be generated and pushed automatically every Monday at 8 AM. "
            "You don't need to do anything else."
        ),
        "gcal_connected": True,
    }


# Also handle the legacy callback path so Google's registered redirect still works
from fastapi import Request
from fastapi.responses import RedirectResponse


@router.get("/connect/legacy-callback")
async def legacy_callback_redirect(code: str, state: str = "default-user"):
    """Redirect from old callback path — not typically called directly."""
    return await connect_callback(code=code, state=state)


# ============================================================================
# 3. UPDATE CONTEXT — natural language or structured
# ============================================================================

@router.post("/update")
async def update_context(body: UpdateContextRequest):
    """
    Update your business context. You can send:
    - Natural language: "We hit $15k MRR, hired 2 engineers, focusing on enterprise this week"
    - Structured fields: goals_this_week, blockers, mrr, etc.
    - Both! The LLM extracts structured data from your text *and* your fields are merged.

    The updated context will be used in the next plan generation.
    """
    user = get_or_create_user(body.user_id)
    settings = get_settings()
    changes: dict[str, Any] = {}

    # Apply structured overrides first
    for field_name in ["goals_this_week", "completed_last_week", "blockers",
                       "current_mrr", "current_users", "primary_goal",
                       "custom_instructions"]:
        value = getattr(body, field_name)
        if value is not None:
            changes[field_name] = value

    # If natural language message provided, use LLM to extract structured data
    if body.message.strip():
        try:
            extracted = await _extract_context_from_text(body.message, user, settings)
            # LLM-extracted fields only override if not already set by structured input
            for k, v in extracted.items():
                if k not in changes and v:
                    changes[k] = v
        except Exception as exc:
            logger.warning("LLM context extraction failed, using text as custom_instructions: %s", exc)
            if "custom_instructions" not in changes:
                changes["custom_instructions"] = body.message

    if changes:
        user = update_user_context(body.user_id, changes)

    return {
        "status": "updated",
        "user_id": user.user_id,
        "fields_updated": list(changes.keys()),
        "effective_context": {
            "business_name": user.business_name,
            "primary_goal": user.primary_goal,
            "goals_this_week": user.goals_this_week,
            "blockers": user.blockers,
            "current_mrr": user.current_mrr,
            "current_users": user.current_users,
            "custom_instructions": user.custom_instructions,
        },
        "message": "Context updated. This will be reflected in your next weekly plan.",
    }


# ============================================================================
# 4. GENERATE — force immediate plan (optional)
# ============================================================================

@router.post("/generate")
async def generate_now(body: GenerateRequest):
    """
    Generate and push a weekly plan immediately (don't wait for Monday).
    Uses your stored business context + any extra context in the message.
    Pushes directly to your connected Google Calendar.
    """
    user = get_user(body.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User '{body.user_id}' not found. Call POST /api/planner/onboard first.",
        )

    if not user.gcal_connected:
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not connected. GET /api/planner/connect first.",
        )

    settings = get_settings()

    # Generate plan
    start = time.time()
    try:
        plan = await _generate_plan_for_user(user, settings, extra_message=body.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plan generation failed: {exc}")
    duration = time.time() - start

    # Push to calendar
    from app.integrations.calendar_integration import push_plan_to_gcal
    try:
        result = await push_plan_to_gcal(
            plan=plan,
            user_id=user.user_id,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            calendar_id=user.calendar_id,
            timezone_str=user.timezone,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar push failed: {exc}")

    # Update user stats
    from datetime import datetime, timezone as tz
    user.last_plan_at = datetime.now(tz.utc).isoformat()
    user.last_plan_events = result.get("events_created", 0)
    user.plan_count += 1
    save_user(user)

    # Store in history (DB-backed)
    task_count = sum(len(d.tasks) for d in plan.daily_schedule.values())
    _store_plan_summary(user.user_id, plan, result, duration)

    # Also store plan outcomes as a memory for long-term recall
    try:
        from app.memory.manager import get_memory_manager
        mgr = get_memory_manager()
        top_titles = [p.title for p in plan.top_priorities[:5]]
        memory_content = (
            f"Generated weekly plan for {user.business_name}. "
            f"Tasks: {task_count}, Events created: {result.get('events_created', 0)}. "
            f"Top priorities: {'; '.join(top_titles)}"
        )
        await mgr.async_store(
            user_id=user.user_id,
            title=f"Weekly Plan — {plan.week_of.isoformat()}",
            content=memory_content,
            page_type="milestone",
            chapter="planning",
            importance=0.6,
            tags=["weekly-plan", "auto-generated"],
            source="planner",
            review_in_days=7,
            auto_embed=False,
        )
    except Exception as mem_exc:
        logger.warning("Memory store for plan failed (non-fatal): %s", mem_exc)

    return {
        "status": "completed",
        "user_id": user.user_id,
        "plan_id": plan.id,
        "tasks_generated": task_count,
        "events_created": result.get("events_created", 0),
        "events_failed": result.get("events_failed", 0),
        "duration_seconds": round(duration, 1),
        "message": (
            f"Your weekly plan is live on Google Calendar! "
            f"{result.get('events_created', 0)} events created across the week."
        ),
        "events": result.get("events", []),
    }


# ============================================================================
# 5. STATUS — check everything
# ============================================================================

@router.get("/status")
async def get_status(user_id: str = Query("default-user")):
    """
    Check your planner status — connection, last plan, upcoming schedule.
    """
    user = get_user(user_id)
    if not user:
        return {
            "status": "not_onboarded",
            "message": "No profile found. Call POST /api/planner/onboard to get started.",
        }

    return {
        "status": "active" if user.gcal_connected else "pending_gcal",
        "user_id": user.user_id,
        "business_name": user.business_name,
        "gcal_connected": user.gcal_connected,
        "timezone": user.timezone,
        "goals_this_week": user.goals_this_week,
        "primary_goal": user.primary_goal,
        "last_plan_at": user.last_plan_at,
        "last_plan_events": user.last_plan_events,
        "total_plans_generated": user.plan_count,
        "message": (
            "Planner is active and will run every Monday at 8 AM."
            if user.gcal_connected
            else "Connect Google Calendar to activate automatic planning."
        ),
    }


# ============================================================================
# 6. HISTORY — past plans
# ============================================================================

@router.get("/history")
async def get_history(user_id: str = Query("default-user"), limit: int = 10):
    """View your past plan summaries (from database)."""
    plans = get_plan_history(user_id, limit=limit)
    return {
        "user_id": user_id,
        "total_plans": len(plans),
        "plans": plans,
    }


# ============================================================================
# Internal helpers
# ============================================================================

async def _extract_context_from_text(
    text: str,
    user: UserProfile,
    settings,
) -> dict[str, Any]:
    """Use LLM to extract structured business context from natural language."""
    from app.agents.llm import LLMMessage, Role, create_llm_provider

    provider = create_llm_provider(
        provider=settings.LLM_PROVIDER,
        api_key=_get_api_key(settings),
        base_url=_get_base_url(settings),
        model=_get_model(settings),
    )

    system = """\
You are a data extraction assistant. Given a founder's natural language update \
about their business, extract structured fields. Return ONLY valid JSON with \
these optional fields (omit any not mentioned):

{
  "primary_goal": "string",
  "goals_this_week": ["string"],
  "completed_last_week": ["string"],
  "blockers": ["string"],
  "current_mrr": number,
  "current_users": number,
  "business_stage": "string",
  "team_size": number,
  "custom_instructions": "string (any planning preferences mentioned)"
}

Return ONLY the JSON object, nothing else."""

    user_msg = (
        f"Current context: {user.business_name} ({user.industry}), "
        f"Stage: {user.business_stage}, MRR: ${user.current_mrr:,.0f}\n\n"
        f"Founder's update:\n{text}"
    )

    try:
        response = await provider.generate(
            [LLMMessage(role=Role.USER, content=user_msg)],
            system=system,
            temperature=0.1,
            max_tokens=1024,
        )
        import json, re
        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Context extraction failed: %s", exc)
        return {}
    finally:
        if hasattr(provider, "close"):
            await provider.close()


async def _generate_plan_for_user(
    user: UserProfile,
    settings,
    extra_message: str = "",
) -> "WeeklyPlan":
    """Generate a weekly plan using the user's stored context.

    Uses a single LLM call that outputs JSON directly matching the WeeklyPlan
    schema, which is far more reliable than generate-markdown → parse-to-JSON.
    """
    import json as _json
    import re as _re
    from datetime import date as _date, timedelta as _td
    from app.agents.llm import LLMMessage, Role, create_llm_provider
    from app.agents.planner_models import WeeklyPlan, _next_monday, _clean_llm_json

    provider = create_llm_provider(
        provider=settings.LLM_PROVIDER,
        api_key=_get_api_key(settings),
        base_url=_get_base_url(settings),
        model=_get_model(settings),
    )

    next_mon = _next_monday()
    days_with_dates = {
        day: (next_mon + _td(days=i)).isoformat()
        for i, day in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday"])
    }

    # Build context
    goals = user.goals_this_week or ["Not specified"]
    context = (
        f"Business: {user.business_name} ({user.industry})\n"
        f"Type: {user.business_type} | Stage: {user.business_stage}\n"
        f"Team size: {user.team_size} | MRR: ${user.current_mrr:,.0f} | Users: {user.current_users}\n"
        f"Primary goal: {user.primary_goal}\n"
        f"Goals this week: {', '.join(goals)}\n"
        f"Work hours: {user.preferred_work_hours} ({user.timezone})\n"
    )
    if user.custom_instructions:
        context += f"Preferences: {user.custom_instructions}\n"
    if user.completed_last_week:
        context += f"Completed last week: {', '.join(user.completed_last_week)}\n"
    if user.blockers:
        context += f"Blockers: {', '.join(user.blockers)}\n"

    # Inject relevant memories from temporal knowledge graph
    try:
        from app.memory.manager import get_memory_manager
        mgr = get_memory_manager()
        # Get memories due for review + recent high-importance ones
        review_hits = await mgr.async_get_due_reviews(user.user_id, limit=5)
        recall_hits = await mgr.async_recall(
            user.user_id,
            query=extra_message or user.primary_goal,
            limit=10,
            min_importance=0.3,
            auto_embed_query=False,  # skip embedding for speed
        )
        all_memories = review_hits + [h for h in recall_hits if h.id not in {r.id for r in review_hits}]
        if all_memories:
            memory_context = mgr.format_for_llm(all_memories[:10], max_chars=3000)
            context += f"\nRelevant memories from your business history:\n{memory_context}\n"
    except Exception as mem_exc:
        logger.debug("Memory recall for plan generation skipped: %s", mem_exc)

    system_prompt = f"""\
You are the Planning Agent for Founder OS. Generate a detailed weekly plan as a JSON object.

RULES:
- Create 3-5 actionable tasks per day (Monday–Friday), each with start_time and end_time
- Tasks should fit within the founder's work hours ({user.preferred_work_hours})
- Use ICE scoring (Impact, Confidence, Ease — each 1-10) to prioritize
- Owner agents: planner, content, research, ops, product, support
- Each task needs a unique, descriptive title (NOT just the goal name)
- Break goals into concrete sub-tasks (e.g., "Set up CI/CD pipeline" not "Deploy backend")
- Time slots must not overlap within a day
- Total estimated hours per day should be 6-8 hours

Dates for the upcoming week: {_json.dumps(days_with_dates)}

Return ONLY a JSON object matching this exact structure (no markdown, no commentary):
{{
  "top_priorities": [
    {{"rank": 1, "title": "...", "rationale": "...", "ice_score": {{"impact": 8, "confidence": 7, "ease": 6}}, "owner_agent": "planner"}}
  ],
  "daily_schedule": {{
    "monday": {{
      "day": "monday",
      "tasks": [
        {{
          "title": "Specific task name",
          "description": "What exactly to do",
          "owner_agent": "planner",
          "priority": 1,
          "est_hours": 2.0,
          "start_time": "09:00",
          "end_time": "11:00",
          "ice_score": {{"impact": 8, "confidence": 7, "ease": 6}},
          "tags": ["development"]
        }}
      ]
    }},
    "tuesday": {{ ... }},
    "wednesday": {{ ... }},
    "thursday": {{ ... }},
    "friday": {{ ... }}
  }},
  "delegations": [],
  "risks": [{{"risk": "...", "mitigation": "...", "severity": "medium"}}],
  "success_criteria": ["Measurable outcome 1", "Measurable outcome 2"]
}}"""

    user_msg = extra_message if extra_message else "Plan my week"
    user_msg += f"\n\nFounder Context:\n{context}"

    messages = [LLMMessage(role=Role.USER, content=user_msg)]

    try:
        response = await provider.generate(
            messages,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8192,
        )

        # Parse JSON response
        raw = response.content.strip()
        raw = _re.sub(r"^```(?:json)?\s*", "", raw)
        raw = _re.sub(r"\s*```$", "", raw)
        raw = _clean_llm_json(raw)

        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as jde:
            # Second chance: ask LLM to fix the JSON
            logger.info("JSON parse error, attempting repair: %s", jde)
            repair_messages = [LLMMessage(
                role=Role.USER,
                content=(
                    f"The following JSON has a syntax error: {jde}.\n"
                    "Fix it and return ONLY valid JSON, nothing else. "
                    "If there are placeholder entries like '...' or '{ ... }', expand them "
                    "into proper complete entries matching the surrounding pattern.\n\n"
                    f"{raw[:8000]}"
                ),
            )]
            repair_resp = await provider.generate(
                repair_messages,
                system="You fix broken JSON. Return ONLY the corrected JSON, no text.",
                temperature=0.0,
                max_tokens=8192,
            )
            fixed = repair_resp.content.strip()
            fixed = _re.sub(r"^```(?:json)?\s*", "", fixed)
            fixed = _re.sub(r"\s*```$", "", fixed)
            fixed = _clean_llm_json(fixed)
            data = _json.loads(fixed)

        plan = WeeklyPlan.model_validate(data)
        plan.ensure_daily_schedule()  # fallback if LLM still missed days
        plan.compute_totals()
        plan.founder_context = {
            "user_id": user.user_id,
            "business_name": user.business_name,
            "goals": user.goals_this_week,
        }
        return plan

    except Exception as exc:
        logger.warning("Direct JSON plan generation failed (%s), using fallback", exc)
        # Fallback: create a plan from raw priorities/goals
        from app.agents.planner_models import Priority
        priorities = [
            Priority(rank=i + 1, title=goal)
            for i, goal in enumerate(goals[:5])
        ]
        plan = WeeklyPlan(top_priorities=priorities)
        plan.ensure_daily_schedule()
        plan.compute_totals()
        plan.founder_context = {
            "user_id": user.user_id,
            "business_name": user.business_name,
            "goals": user.goals_this_week,
        }
        return plan
    finally:
        if hasattr(provider, "close"):
            await provider.close()


def _store_plan_summary(
    user_id: str,
    plan: Any,
    gcal_result: dict,
    duration: float,
) -> None:
    """Store a plan summary in DB via user_store."""
    task_count = sum(len(d.tasks) for d in plan.daily_schedule.values())
    try:
        store_plan_history(
            user_id=user_id,
            plan_id=plan.id,
            week_of=plan.week_of,
            task_count=task_count,
            events_created=gcal_result.get("events_created", 0),
            events_failed=gcal_result.get("events_failed", 0),
            duration_seconds=round(duration, 1),
            top_priorities=[p.title for p in plan.top_priorities],
            plan_data=plan.model_dump() if hasattr(plan, 'model_dump') else {},
            gcal_events=gcal_result.get("events", []),
        )
    except Exception as exc:
        logger.error("Failed to store plan history: %s", exc)


def _get_api_key(settings) -> str:
    return {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai_compatible": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }.get(settings.LLM_PROVIDER, "")


def _get_base_url(settings) -> str:
    return {
        "ollama": settings.OLLAMA_BASE_URL,
        "openai_compatible": settings.OPENAI_BASE_URL,
    }.get(settings.LLM_PROVIDER, "")


def _get_model(settings) -> str:
    return {
        "ollama": settings.OLLAMA_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "openai_compatible": settings.OPENAI_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }.get(settings.LLM_PROVIDER, "")
