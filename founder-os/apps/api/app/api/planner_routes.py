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

import base64
import hashlib
import hmac
import json
import secrets
import time
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_auth, ClerkUser
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


def _oauth_state_secret() -> str:
    settings = get_settings()
    secret = settings.OAUTH_STATE_SECRET or settings.GOOGLE_CLIENT_SECRET
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="OAuth state secret is not configured.",
        )
    return secret


def _encode_oauth_state(user_id: str, ttl_seconds: int = 600) -> str:
    payload = {
        "u": user_id,
        "exp": int(time.time()) + ttl_seconds,
        "n": secrets.token_urlsafe(8),
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_raw).decode("ascii").rstrip("=")
    signature = hmac.new(
        _oauth_state_secret().encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def _decode_oauth_state(state: str) -> str:
    try:
        payload_b64, signature = state.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    expected = hmac.new(
        _oauth_state_secret().encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature.")

    try:
        payload_raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed OAuth state payload.")

    exp = int(payload.get("exp", 0))
    user_id = str(payload.get("u", ""))
    if not user_id or exp < int(time.time()):
        raise HTTPException(status_code=400, detail="OAuth state is missing or expired.")

    return user_id


# Plan history is now DB-backed via user_store.store_plan_history / get_plan_history


# ============================================================================
# MCP Helper — all calendar operations go through this
# ============================================================================

def _get_mcp_calendar(user: UserProfile) -> "MCPGoogleCalendarProvider":
    """
    Create an MCP calendar provider for the given user.
    This routes all calendar operations through the MCP ToolProvider interface,
    ensuring consistent tool execution, logging, and error handling.
    """
    from app.agents.mcp_tools import MCPGoogleCalendarProvider
    settings = get_settings()
    return MCPGoogleCalendarProvider(
        user_id=user.user_id,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        timezone_str=user.timezone or "Asia/Kolkata",
        calendar_id=user.calendar_id or "primary",
    )


async def _mcp_call(user: UserProfile, tool_name: str, arguments: dict) -> Any:
    """
    Execute a Google Calendar MCP tool call.
    Returns the parsed result dict or raises an exception on error.
    """
    import json as _json
    provider = _get_mcp_calendar(user)
    result = await provider.call_tool(tool_name, arguments)
    if result.is_error:
        raise RuntimeError(f"MCP {tool_name} failed: {result.content}")
    return _json.loads(result.content)


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


class PromptRequest(BaseModel):
    """
    The unified prompt endpoint — one call does everything.

    Send any natural language prompt and the system will:
    1. Pull your business context + long-term memory
    2. Decide what to do (add events, replan week, update metrics, etc.)
    3. Push changes to your Google Calendar
    4. Store the interaction as a memory for future context
    """
    user_id: str = Field("default-user")
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description=(
            "Anything you want — 'Board meeting Friday at 2 PM', "
            "'Reschedule marketing to Thursday', 'Plan my week focused on fundraising', "
            "'We just hit $100k MRR, update everything'"
        ),
    )


# ============================================================================
# 1. ONBOARD — set up business context (one-time)
# ============================================================================

@router.post("/onboard")
async def onboard(body: OnboardRequest, clerk: ClerkUser = Depends(require_auth)):
    """
    Set up your business profile. Call this once — your data is remembered
    and used automatically every Monday when the planner runs.

    After onboarding, connect Google Calendar via GET /api/planner/connect.
    """
    user = get_or_create_user(clerk.user_id)

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
async def connect_gcal(clerk: ClerkUser = Depends(require_auth)):
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
    user = get_or_create_user(clerk.user_id)

    # If user already has valid tokens and is connected, skip the OAuth dance
    if user.gcal_connected and user.has_valid_gcal_tokens():
        return {
            "status": "already_connected",
            "user_id": clerk.user_id,
            "gcal_connected": True,
            "message": (
                f"Google Calendar is already connected for {user.business_name or clerk.user_id}. "
                "No need to re-authenticate — your tokens are saved permanently."
            ),
        }

    # Force consent screen to get a fresh refresh token
    auth_url = get_auth_url(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        state=_encode_oauth_state(clerk.user_id),
        force_consent=True,
    )
    return {
        "auth_url": auth_url,
        "message": "Open this URL in your browser to connect Google Calendar.",
        "user_id": clerk.user_id,
    }


@router.get("/connect/callback")
async def connect_callback(code: str, state: str):
    """
    OAuth2 callback — automatically called by Google after user grants access.
    Links the calendar to the user's profile.
    """
    from app.integrations.calendar_integration import exchange_code_for_tokens

    settings = get_settings()
    user_id = _decode_oauth_state(state)

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

    # Return an HTML page that shows success and auto-closes the popup
    from fastapi.responses import HTMLResponse
    display_name = user.business_name or user_id
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Calendar Connected</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; background: #f8fafc; color: #1e293b;
    }}
    .card {{
      text-align: center; padding: 3rem 2rem; max-width: 400px;
      background: white; border-radius: 1rem;
      box-shadow: 0 1px 3px rgba(0,0,0,.1);
    }}
    .icon {{
      width: 64px; height: 64px; margin: 0 auto 1.5rem;
      background: #ecfdf5; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
    }}
    .icon svg {{ width: 32px; height: 32px; color: #10b981; }}
    h1 {{ font-size: 1.25rem; font-weight: 700; margin-bottom: .5rem; }}
    p {{ font-size: .875rem; color: #64748b; line-height: 1.5; }}
    .countdown {{ margin-top: 1.5rem; font-size: .75rem; color: #94a3b8; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
      </svg>
    </div>
    <h1>Calendar Connected!</h1>
    <p>Google Calendar is now linked for <strong>{display_name}</strong>.
       Your weekly plan will be generated automatically every Monday at 8 AM.</p>
    <p class="countdown">This window will close automatically...</p>
  </div>
  <script>
    // Close the popup after a short delay so user can see the success message
    setTimeout(function() {{ window.close(); }}, 2000);
    // Fallback: if window.close() is blocked, show a manual close hint
    setTimeout(function() {{
      document.querySelector('.countdown').textContent = 'You can close this window now.';
    }}, 3000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


# Also handle the legacy callback path so Google's registered redirect still works
from fastapi import Request
from fastapi.responses import RedirectResponse


@router.get("/connect/legacy-callback")
async def legacy_callback_redirect(code: str, state: str):
    """Redirect from old callback path — not typically called directly."""
    return await connect_callback(code=code, state=state)


# ============================================================================
# 3. UPDATE CONTEXT — natural language or structured
# ============================================================================

@router.post("/update")
async def update_context(body: UpdateContextRequest, clerk: ClerkUser = Depends(require_auth)):
    """
    Update your business context. You can send:
    - Natural language: "We hit $15k MRR, hired 2 engineers, focusing on enterprise this week"
    - Structured fields: goals_this_week, blockers, mrr, etc.
    - Both! The LLM extracts structured data from your text *and* your fields are merged.

    The updated context will be used in the next plan generation.
    """
    user = get_or_create_user(clerk.user_id)
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
        user = update_user_context(clerk.user_id, changes)

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
async def generate_now(body: GenerateRequest, clerk: ClerkUser = Depends(require_auth)):
    """
    Generate and push a weekly plan immediately (don't wait for Monday).
    Uses your stored business context + any extra context in the message.
    Pushes directly to your connected Google Calendar.
    """
    user = get_user(clerk.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User '{clerk.user_id}' not found. Call POST /api/planner/onboard first.",
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

    # Push to calendar (via MCP)
    try:
        result = await _mcp_call(user, "gcal_push_weekly_plan", {
            "plan_json": plan.model_dump_json(),
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar push failed: {exc}")

    # Update user stats (wrapped so a DB glitch doesn't cause a raw 500)
    task_count = sum(len(d.tasks) for d in plan.daily_schedule.values())
    try:
        from datetime import datetime, timezone as tz
        user.last_plan_at = datetime.now(tz.utc).isoformat()
        user.last_plan_events = result.get("events_created", 0)
        user.plan_count += 1
        save_user(user)
    except Exception as exc:
        logger.error("Failed to update user stats after plan generation: %s", exc)

    # Store in history (DB-backed)
    try:
        _store_plan_summary(user.user_id, plan, result, duration)
    except Exception as exc:
        logger.error("Failed to store plan history: %s", exc)

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
async def get_status(clerk: ClerkUser = Depends(require_auth)):
    """
    Check your planner status — connection, last plan, upcoming schedule.
    """
    user = get_user(clerk.user_id)
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
async def get_history(clerk: ClerkUser = Depends(require_auth), limit: int = 10):
    """View your past plan summaries (from database)."""
    plans = get_plan_history(clerk.user_id, limit=limit)
    return {
        "user_id": clerk.user_id,
        "total_plans": len(plans),
        "plans": plans,
    }


# ============================================================================
# 7. PROMPT — The single smart endpoint (prompt → memory → calendar)
# ============================================================================

@router.post("/prompt")
async def handle_prompt(body: PromptRequest, clerk: ClerkUser = Depends(require_auth)):
    """
    **The main endpoint.** Send any natural language prompt and the system will:

    1. Load your business context + calendar tokens (stored from one-time OAuth)
    2. Pull relevant long-term memories (past meetings, milestones, metrics)
    3. Use the LLM to understand your intent and extract:
       - Calendar events to create (meetings, tasks, blocks)
       - Context updates (MRR changes, new goals, blockers)
       - Whether a full weekly replan is needed
    4. Push all events to Google Calendar (using stored tokens — no re-auth)
    5. Store this interaction as a new memory for future reference

    Examples:
    - "Board meeting with investors Friday at 2 PM, prep deck Thursday morning"
    - "We hit $100k MRR! Update my metrics and replan the week for fundraising"
    - "Cancel marketing review, move product sync to Wednesday 3 PM"
    - "Remind me to follow up with Acme Corp next Tuesday at 10 AM"
    - "Plan my week — focus on hiring and closing the Series A"
    """
    user = get_user(clerk.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=(
                f"User '{clerk.user_id}' not found. "
                "Call POST /api/planner/onboard first."
            ),
        )

    if not user.gcal_connected or not user.has_valid_gcal_tokens():
        raise HTTPException(
            status_code=400,
            detail=(
                "Google Calendar not connected. "
                "One-time setup: GET /api/planner/connect?user_id=" + clerk.user_id
            ),
        )

    settings = get_settings()
    start_time = time.time()

    # ── Step 1: Pull relevant memories ──────────────────────────
    memory_context = ""
    try:
        from app.memory.manager import get_memory_manager
        mgr = get_memory_manager()

        # Get memories relevant to the prompt + any due for review
        recall_hits = await mgr.async_recall(
            clerk.user_id,
            query=body.message,
            limit=10,
            min_importance=0.2,
            auto_embed_query=False,
        )
        review_hits = await mgr.async_get_due_reviews(clerk.user_id, limit=5)

        all_memories = recall_hits + [
            h for h in review_hits if h.id not in {r.id for r in recall_hits}
        ]
        if all_memories:
            memory_context = mgr.format_for_llm(all_memories[:10], max_chars=3000)
    except Exception as mem_exc:
        logger.debug("Memory recall for prompt skipped: %s", mem_exc)

    # ── Step 2: Get upcoming calendar events for context ────────
    existing_events_summary = ""
    try:
        upcoming = await _mcp_call(user, "gcal_list_events", {"max_results": 15})
        if upcoming:
            event_lines = []
            for ev in upcoming:
                event_lines.append(f"  - {ev['summary']} @ {ev['start']}")
            existing_events_summary = (
                "Current upcoming events on your calendar:\n"
                + "\n".join(event_lines)
            )
    except Exception as cal_exc:
        logger.debug("Listing upcoming events failed (non-fatal): %s", cal_exc)

    # ── Step 3: LLM — understand intent + generate actions ──────
    import json as _json
    import re as _re
    from datetime import date as _date, timedelta as _td
    from app.agents.llm import LLMMessage, Role, create_llm_provider

    provider = create_llm_provider(
        provider=settings.LLM_PROVIDER,
        api_key=_get_api_key(settings),
        base_url=_get_base_url(settings),
        model=_get_model(settings),
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL or "gpt-4o-mini",
        openai_base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
    )

    today = _date.today()
    # Build day→date mapping for the current + next week
    days_map = {}
    for offset in range(14):
        d = today + _td(days=offset)
        day_name = d.strftime("%A").lower()
        key = f"{day_name}_{d.isoformat()}"
        days_map[day_name] = d.isoformat()
        days_map[d.isoformat()] = d.isoformat()

    context_block = (
        f"Business: {user.business_name} ({user.industry})\n"
        f"Type: {user.business_type} | Stage: {user.business_stage}\n"
        f"Team: {user.team_size} | MRR: ${user.current_mrr:,.0f} | Users: {user.current_users}\n"
        f"Primary goal: {user.primary_goal}\n"
        f"Goals this week: {', '.join(user.goals_this_week) if user.goals_this_week else 'None set'}\n"
        f"Work hours: {user.preferred_work_hours} ({user.timezone})\n"
        f"Today is: {today.strftime('%A, %B %d, %Y')}\n"
    )
    if user.blockers:
        context_block += f"Blockers: {', '.join(user.blockers)}\n"
    if memory_context:
        context_block += f"\nRelevant memories from business history:\n{memory_context}\n"
    if existing_events_summary:
        context_block += f"\n{existing_events_summary}\n"

    # Build day→date mapping for LLM
    day_date_map = {}
    for offset in range(14):
        d = today + _td(days=offset)
        day_name = d.strftime("%A").lower()
        if day_name not in day_date_map:
            day_date_map[day_name] = d.isoformat()
        day_date_map[f"next_{day_name}"] = (today + _td(days=7 + (offset % 7))).isoformat() if offset < 7 else d.isoformat()
    day_date_json = _json.dumps(day_date_map, indent=2)

    system_prompt = f"""\
You are the AI assistant for Founder OS. The founder sends you natural language prompts \
about their schedule, business, and goals. You must respond with a structured JSON action plan.

TODAY: {today.isoformat()} ({today.strftime('%A')})
TIMEZONE: {user.timezone}
WORK HOURS: {user.preferred_work_hours}

Day-to-date mapping (use these exact dates):
{day_date_json}

Return ONLY a JSON object with this structure (omit sections not needed):
{{
  "intent": "add_events | delete_events | update_events | update_context | full_replan | clarification | mixed",
  "reply": "Brief human-friendly confirmation message",
  "needs_clarification": false,
  "clarification_question": "Only if needs_clarification is true — what you need to know",
  "events_to_create": [
    {{
      "summary": "Event title",
      "date": "YYYY-MM-DD",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "description": "Optional details",
      "all_day": false
    }}
  ],
  "events_to_delete": {{
    "scope": "all_ai | by_keyword | by_date_range | specific_ids",
    "keyword": "Optional keyword to match in event titles",
    "date_range_start": "YYYY-MM-DDTHH:MM:SS (start of range to delete)",
    "date_range_end": "YYYY-MM-DDTHH:MM:SS (end of range to delete)",
    "event_ids": ["Optional list of specific event IDs to delete"],
    "delete_all_in_range": false
  }},
  "events_to_update": [
    {{
      "event_id": "Google Calendar event ID (from the existing events list)",
      "new_summary": "Optional new title",
      "new_start": "YYYY-MM-DDTHH:MM:SS (optional)",
      "new_end": "YYYY-MM-DDTHH:MM:SS (optional)",
      "new_description": "Optional new description"
    }}
  ],
  "context_updates": {{
    "current_mrr": 100000,
    "primary_goal": "Close Series A",
    "goals_this_week": ["Goal 1", "Goal 2"],
    "blockers": ["Blocker"],
    "completed_last_week": ["Done task"]
  }},
  "needs_full_replan": false,
  "replan_focus": "Optional focus area if needs_full_replan is true"
}}

RULES:
- Always compute real dates from day names using today={today.isoformat()} ({today.strftime('%A')})
- "Friday" means the NEXT upcoming Friday from today
- "this week" means from today through the upcoming Sunday
- Time slots should be within work hours ({user.preferred_work_hours}) unless specified
- Default meeting duration is 1 hour unless stated otherwise
- If the founder mentions metrics (MRR, users, revenue), include context_updates
- Set needs_full_replan=true only if they ask to "plan my week" or similar

DELETE RULES:
- When asked to delete/remove/cancel/clear events, set intent to "delete_events"
- For "delete all events this week": set scope="all_ai", provide date_range_start (today) and date_range_end (end of week), and set delete_all_in_range=true
- For "delete all events": same but wider range
- For deleting specific events by name: set scope="by_keyword" and provide the keyword
- For deleting events the user can see in the list above: use scope="specific_ids" with event IDs from the existing events list
- ALWAYS include date_range_start and date_range_end for bulk deletes
- If the user's delete request is ambiguous (e.g. which events?), set needs_clarification=true and ask

CLARIFICATION RULES:
- If the user's request is ambiguous, missing critical info (date, time, which event), set needs_clarification=true
- Set intent to "clarification" and provide a clear clarification_question
- Include in reply what you understood and what's missing
- Examples: "Schedule a meeting" (missing: when, with whom, how long), "Delete that event" (which one?)

UPDATE RULES:
- When asked to reschedule/move/change events, use events_to_update with event IDs from the existing events list
- If you can identify the event from the list, include its event_id
- If you can't identify which event, set needs_clarification=true

- Return ONLY valid JSON, no markdown fences, no commentary"""

    user_msg = f"Founder's prompt:\n{body.message}\n\nFounder Context:\n{context_block}"

    import asyncio as _asyncio

    llm_response = None
    last_err = None
    for attempt in range(3):
        try:
            llm_response = await provider.generate(
                [LLMMessage(role=Role.USER, content=user_msg)],
                system=system_prompt,
                temperature=0.3,
                max_tokens=4096,
            )
            break
        except Exception as llm_exc:
            last_err = llm_exc
            if "429" in str(llm_exc) and attempt < 2:
                wait = (attempt + 1) * 15  # 15s, 30s
                logger.info("Gemini 429 — retrying in %ds (attempt %d/3)", wait, attempt + 1)
                await _asyncio.sleep(wait)
            else:
                break

    if hasattr(provider, "close"):
        await provider.close()

    if llm_response is None:
        raise HTTPException(status_code=502, detail=f"LLM failed after retries: {last_err}")

    response = llm_response

    # Parse LLM response
    raw = response.content.strip()
    raw = _re.sub(r"^```(?:json)?\s*", "", raw)
    raw = _re.sub(r"\s*```$", "", raw)

    try:
        actions = _json.loads(raw)
    except _json.JSONDecodeError:
        # Fallback: treat entire prompt as a single event request
        actions = {
            "intent": "mixed",
            "reply": "I'll process your request.",
            "events_to_create": [],
            "context_updates": {},
            "needs_full_replan": False,
        }

    # ── Step 4: Execute actions ──────────────────────────────────
    results: dict[str, Any] = {
        "status": "completed",
        "user_id": clerk.user_id,
        "intent": actions.get("intent", "mixed"),
        "reply": actions.get("reply", "Done."),
    }

    # 4-pre. Handle clarification — don't execute anything, just ask
    if actions.get("needs_clarification"):
        results["status"] = "clarification_needed"
        results["reply"] = actions.get("reply", actions.get("clarification_question", "I need more information."))
        results["clarification_question"] = actions.get("clarification_question", "")
        results["duration_seconds"] = round(time.time() - start_time, 1)
        return results

    # 4a. Apply context updates
    ctx_updates = actions.get("context_updates", {})
    if ctx_updates:
        for key, value in ctx_updates.items():
            if value is not None and hasattr(user, key):
                setattr(user, key, value)
        save_user(user)
        results["context_updated"] = list(ctx_updates.keys())

    # 4b. Create calendar events
    events_to_create = actions.get("events_to_create", [])
    created_events = []
    failed_events = []

    if events_to_create:
        for ev in events_to_create:
            try:
                if ev.get("all_day"):
                    result = await _mcp_call(user, "gcal_create_all_day_event", {
                        "summary": ev["summary"],
                        "event_date": ev["date"],
                        "description": ev.get("description", ""),
                    })
                else:
                    start_dt = f"{ev['date']}T{ev['start_time']}:00"
                    end_dt = f"{ev['date']}T{ev['end_time']}:00"
                    result = await _mcp_call(user, "gcal_create_event", {
                        "summary": ev["summary"],
                        "start_datetime": start_dt,
                        "end_datetime": end_dt,
                        "description": ev.get("description", ""),
                    })
                created_events.append(result)
            except Exception as ev_exc:
                failed_events.append({
                    "summary": ev.get("summary", "Unknown"),
                    "error": str(ev_exc),
                })
                logger.error("Failed to create event '%s': %s", ev.get("summary"), ev_exc)

        results["events_created"] = len(created_events)
        results["events_failed"] = len(failed_events)
        results["events"] = created_events
        if failed_events:
            results["errors"] = failed_events

    # 4c. Delete calendar events (via MCP)
    delete_spec = actions.get("events_to_delete", {})
    if delete_spec and actions.get("intent") in ("delete_events", "mixed"):
        deleted_events: list[dict] = []
        delete_failed: list[dict] = []
        scope = delete_spec.get("scope", "all_ai")

        try:
            if scope == "specific_ids" and delete_spec.get("event_ids"):
                # Delete specific events by ID
                for eid in delete_spec["event_ids"]:
                    try:
                        result = await _mcp_call(user, "gcal_delete_event", {"event_id": eid})
                        if result.get("deleted"):
                            deleted_events.append({"event_id": eid, "deleted": True})
                        else:
                            delete_failed.append({"event_id": eid, "error": "Not found or already deleted"})
                    except Exception as del_exc:
                        delete_failed.append({"event_id": eid, "error": str(del_exc)})

            elif scope in ("all_ai", "by_keyword"):
                # Use gcal_smart_delete via MCP for bulk deletion
                smart_args: dict[str, Any] = {}
                if delete_spec.get("date_range_start"):
                    smart_args["time_min"] = delete_spec["date_range_start"]
                if delete_spec.get("date_range_end"):
                    smart_args["time_max"] = delete_spec["date_range_end"]
                if scope == "by_keyword" and delete_spec.get("keyword"):
                    smart_args["keyword"] = delete_spec["keyword"]

                if delete_spec.get("delete_all_in_range"):
                    # Delete ALL events in range (not just AI-generated)
                    # First list events, then delete each one
                    list_args: dict[str, Any] = {"max_results": 100}
                    if delete_spec.get("date_range_start"):
                        list_args["time_min"] = delete_spec["date_range_start"]
                    all_events_in_range = await _mcp_call(user, "gcal_list_events", list_args)

                    # Filter by date_range_end if provided
                    if delete_spec.get("date_range_end"):
                        from datetime import datetime as _dt_del
                        try:
                            end_dt = _dt_del.fromisoformat(delete_spec["date_range_end"].replace("Z", "+00:00"))
                            filtered_events = []
                            for ev in (all_events_in_range if isinstance(all_events_in_range, list) else []):
                                ev_start = ev.get("start", "")
                                if ev_start:
                                    try:
                                        ev_t = _dt_del.fromisoformat(ev_start.replace("Z", "+00:00"))
                                        if ev_t <= end_dt:
                                            filtered_events.append(ev)
                                    except (ValueError, TypeError):
                                        filtered_events.append(ev)
                                else:
                                    filtered_events.append(ev)
                            all_events_in_range = filtered_events
                        except (ValueError, TypeError):
                            pass

                    # Apply keyword filter if any
                    if scope == "by_keyword" and delete_spec.get("keyword"):
                        kw = delete_spec["keyword"].lower()
                        all_events_in_range = [
                            ev for ev in (all_events_in_range if isinstance(all_events_in_range, list) else [])
                            if kw in ev.get("summary", "").lower()
                        ]

                    # Delete each event
                    for ev in (all_events_in_range if isinstance(all_events_in_range, list) else []):
                        eid = ev.get("event_id") or ev.get("id", "")
                        if not eid:
                            continue
                        try:
                            result = await _mcp_call(user, "gcal_delete_event", {"event_id": eid})
                            deleted_events.append({
                                "event_id": eid,
                                "summary": ev.get("summary", ""),
                                "deleted": True,
                            })
                        except Exception as del_exc:
                            delete_failed.append({
                                "event_id": eid,
                                "summary": ev.get("summary", ""),
                                "error": str(del_exc),
                            })
                else:
                    # AI-only events: use gcal_smart_delete
                    smart_args["dry_run"] = False
                    smart_result = await _mcp_call(user, "gcal_smart_delete", smart_args)
                    deleted_events = smart_result.get("deleted", [])
                    delete_failed = smart_result.get("failed", [])

            elif scope == "by_date_range":
                # List events in range, then delete all
                list_args = {"max_results": 100}
                if delete_spec.get("date_range_start"):
                    list_args["time_min"] = delete_spec["date_range_start"]
                events_in_range = await _mcp_call(user, "gcal_list_events", list_args)

                if delete_spec.get("date_range_end"):
                    from datetime import datetime as _dt_del2
                    try:
                        end_dt = _dt_del2.fromisoformat(delete_spec["date_range_end"].replace("Z", "+00:00"))
                        events_in_range = [
                            ev for ev in (events_in_range if isinstance(events_in_range, list) else [])
                            if ev.get("start", "") and
                            _dt_del2.fromisoformat(ev["start"].replace("Z", "+00:00")) <= end_dt
                        ]
                    except (ValueError, TypeError):
                        pass

                for ev in (events_in_range if isinstance(events_in_range, list) else []):
                    eid = ev.get("event_id") or ev.get("id", "")
                    if not eid:
                        continue
                    try:
                        result = await _mcp_call(user, "gcal_delete_event", {"event_id": eid})
                        deleted_events.append({
                            "event_id": eid,
                            "summary": ev.get("summary", ""),
                            "deleted": True,
                        })
                    except Exception as del_exc:
                        delete_failed.append({
                            "event_id": eid,
                            "summary": ev.get("summary", ""),
                            "error": str(del_exc),
                        })

        except Exception as exc:
            logger.error("Delete operation failed: %s", exc)
            results["delete_error"] = str(exc)

        results["events_deleted"] = len(deleted_events)
        results["delete_failed"] = len(delete_failed)
        results["deleted_events"] = deleted_events
        if delete_failed:
            results["delete_errors"] = delete_failed

    # 4d. Update calendar events (via MCP)
    events_to_update = actions.get("events_to_update", [])
    if events_to_update:
        updated_events: list[dict] = []
        update_failed: list[dict] = []
        for ev_update in events_to_update:
            eid = ev_update.get("event_id", "")
            if not eid:
                update_failed.append({"error": "No event_id provided", "update": ev_update})
                continue
            try:
                update_args: dict[str, Any] = {"event_id": eid}
                if ev_update.get("new_summary"):
                    update_args["summary"] = ev_update["new_summary"]
                if ev_update.get("new_start"):
                    update_args["start_datetime"] = ev_update["new_start"]
                if ev_update.get("new_end"):
                    update_args["end_datetime"] = ev_update["new_end"]
                if ev_update.get("new_description"):
                    update_args["description"] = ev_update["new_description"]
                result = await _mcp_call(user, "gcal_update_event", update_args)
                updated_events.append(result)
            except Exception as upd_exc:
                update_failed.append({"event_id": eid, "error": str(upd_exc)})

        results["events_updated"] = len(updated_events)
        results["update_failed"] = len(update_failed)
        if updated_events:
            results["updated_events"] = updated_events
        if update_failed:
            results["update_errors"] = update_failed

    # 4e. Full weekly replan if requested
    if actions.get("needs_full_replan"):
        try:
            plan = await _generate_plan_for_user(
                user, settings,
                extra_message=actions.get("replan_focus", body.message),
            )

            gcal_result = await _mcp_call(user, "gcal_push_weekly_plan", {
                "plan_json": plan.model_dump_json(),
            })

            from datetime import datetime as _dt, timezone as _tz
            user.last_plan_at = _dt.now(_tz.utc).isoformat()
            user.last_plan_events = gcal_result.get("events_created", 0)
            user.plan_count += 1
            save_user(user)

            duration = time.time() - start_time
            _store_plan_summary(user.user_id, plan, gcal_result, duration)

            results["weekly_plan"] = {
                "plan_id": plan.id,
                "tasks_generated": sum(len(d.tasks) for d in plan.daily_schedule.values()),
                "events_created": gcal_result.get("events_created", 0),
                "events_failed": gcal_result.get("events_failed", 0),
            }
        except Exception as plan_exc:
            logger.error("Full replan failed: %s", plan_exc)
            results["replan_error"] = str(plan_exc)

    # ── Step 5: Store as memory ──────────────────────────────────
    try:
        from app.memory.manager import get_memory_manager
        mgr = get_memory_manager()

        ev_count = len(created_events)
        memory_title = f"Prompt: {body.message[:80]}"
        memory_content = (
            f"User prompt: {body.message}\n"
            f"Actions taken: {actions.get('intent', 'unknown')}\n"
        )
        if ev_count:
            summaries = [e.get("summary", "") for e in created_events]
            memory_content += f"Events created ({ev_count}): {'; '.join(summaries)}\n"
        if ctx_updates:
            memory_content += f"Context updates: {', '.join(ctx_updates.keys())}\n"
        if actions.get("needs_full_replan"):
            memory_content += "Full weekly replan generated.\n"

        await mgr.async_store(
            user_id=clerk.user_id,
            title=memory_title,
            content=memory_content,
            page_type="interaction",
            chapter="planning",
            importance=0.5,
            tags=["prompt", "calendar-update"],
            source="planner-prompt",
            auto_embed=False,
        )
    except Exception as mem_exc:
        logger.debug("Memory store for prompt failed (non-fatal): %s", mem_exc)

    results["duration_seconds"] = round(time.time() - start_time, 1)
    return results


# ============================================================================
# 7b. CHAT — Full agent-based conversational endpoint (MCP-powered)
# ============================================================================

class ChatRequest(BaseModel):
    """
    Chat with the PlannerAgent using the full agentic loop.
    Supports multi-turn conversation, tool calls (via MCP), confirmation,
    deletion, and clarification — everything the PlannerAgent can do.
    """
    user_id: str = Field("default-user")
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Your message to the planner agent",
    )
    session_id: str | None = Field(
        None,
        description="Session ID for conversation continuity",
    )


@router.post("/chat")
async def planner_chat(body: ChatRequest, clerk: ClerkUser = Depends(require_auth)):
    """
    **Conversational planner endpoint** — uses the full PlannerAgent with MCP tools.

    Unlike /prompt (which does a single LLM call for JSON actions), /chat
    runs the full agentic loop:
    - Multi-turn conversation with memory
    - MCP tool calls (gcal_list_events, gcal_delete_event, gcal_smart_delete, etc.)
    - Automatic clarification when information is missing
    - Confirmation before destructive actions
    - Intent detection via detect_calendar_intent tool

    Use this for conversational interactions like:
    - "Delete all events this week"
    - "What's on my calendar tomorrow?"
    - "Schedule a meeting" (will ask for details)
    - "Remove the 2pm meeting on Friday"
    """
    import uuid as _uuid
    from app.agents.registry import AgentRegistry
    from app.config import get_settings
    from app.redis import get_redis

    user = get_user(clerk.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User '{clerk.user_id}' not found. Call POST /api/planner/onboard first.",
        )

    if not user.gcal_connected or not user.has_valid_gcal_tokens():
        raise HTTPException(
            status_code=400,
            detail=(
                "Google Calendar not connected. "
                "One-time setup: GET /api/planner/connect?user_id=" + clerk.user_id
            ),
        )

    settings = get_settings()
    redis = get_redis()
    start_time = time.time()

    # Create a deterministic UUID from the user_id string
    user_uuid = _uuid.uuid5(_uuid.NAMESPACE_URL, f"clerk:{clerk.user_id}")
    session_id = body.session_id or f"planner-chat-{clerk.user_id}"

    try:
        from app.database import async_session as _async_session
        async with _async_session() as db:
            registry = AgentRegistry(db=db, redis=redis, settings=settings)
            agent = await registry.get(
                "planner",
                user_id=user_uuid,
                session_id=session_id,
                planner_user_id=clerk.user_id,
            )

            result = await agent.run(body.message)

            # Extract tool call info
            tool_names = list({
                tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")
            })
            mcp_tools_used = [t for t in tool_names if t.startswith("gcal_")]

            # Detect if any tool returned a calendar_auth_expired error
            reconnect_required = False
            for step in result.steps:
                if step.step_type == "tool_call" and "calendar_auth_expired" in step.result:
                    reconnect_required = True
                    break

            return {
                "status": "completed",
                "user_id": clerk.user_id,
                "reply": result.content,
                "agent": "planner",
                "model": result.model,
                "tokens_used": result.tokens_used,
                "tool_calls_made": len(result.tool_calls_made),
                "tool_names": tool_names,
                "mcp_tools_used": mcp_tools_used,
                "duration_seconds": round(time.time() - start_time, 2),
                "stop_reason": result.stop_reason,
                "cost_usd": round(result.cost_usd, 6),
                "session_id": session_id,
                "pending_approvals": result.pending_approvals,
                "reconnect_required": reconnect_required,
            }

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Planner chat failed")
        raise HTTPException(status_code=502, detail=f"Planner agent error: {exc}")


# ============================================================================
# 8. CALENDAR — view upcoming events
# ============================================================================

@router.get("/calendar")
async def get_upcoming_calendar(
    clerk: ClerkUser = Depends(require_auth),
    max_results: int = Query(20, ge=1, le=100),
):
    """
    View your upcoming Google Calendar events.
    Uses stored tokens — no re-auth needed.
    """
    user = get_user(clerk.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not user.gcal_connected or not user.has_valid_gcal_tokens():
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not connected.",
        )

    try:
        events = await _mcp_call(user, "gcal_list_events", {"max_results": max_results})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar read failed: {exc}")

    return {
        "user_id": clerk.user_id,
        "events_count": len(events),
        "events": events,
    }


# ============================================================================
# 9. CALENDAR CRUD — individual event operations
# ============================================================================

@router.get("/calendar/event/{event_id}")
async def get_calendar_event(
    event_id: str,
    clerk: ClerkUser = Depends(require_auth),
):
    """Get a single calendar event by ID."""
    user = get_user(clerk.user_id)
    if not user or not user.gcal_connected:
        raise HTTPException(status_code=400, detail="Google Calendar not connected.")

    try:
        ev = await _mcp_call(user, "gcal_get_event", {"event_id": event_id})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar read failed: {exc}")

    return {"user_id": clerk.user_id, "event": ev}


@router.post("/calendar/event")
async def create_calendar_event(request: Request, clerk: ClerkUser = Depends(require_auth)):
    """
    Create a single event directly (no LLM).
    Body: { summary, start, end, description?, timezone? }
    """
    body = await request.json()
    user = get_user(clerk.user_id)
    if not user or not user.gcal_connected:
        raise HTTPException(status_code=400, detail="Google Calendar not connected.")

    try:
        ev = await _mcp_call(user, "gcal_create_event", {
            "summary": body["summary"],
            "start_datetime": body["start"],
            "end_datetime": body["end"],
            "description": body.get("description", ""),
        })
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing field: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar create failed: {exc}")

    return {"user_id": clerk.user_id, "created": True, "event": ev}


@router.patch("/calendar/event/{event_id}")
async def update_calendar_event(event_id: str, request: Request, clerk: ClerkUser = Depends(require_auth)):
    """
    Update a calendar event by ID.
    Body: { summary?, start_datetime?, end_datetime?, description?, color_id? }
    """
    body = await request.json()
    user = get_user(clerk.user_id)
    if not user or not user.gcal_connected:
        raise HTTPException(status_code=400, detail="Google Calendar not connected.")

    try:
        ev = await _mcp_call(user, "gcal_update_event", {
            "event_id": event_id,
            **{k: v for k, v in body.items() if k not in ("user_id",)},
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar update failed: {exc}")

    return {"user_id": clerk.user_id, "updated": True, "event": ev}


@router.delete("/calendar/event/{event_id}")
async def delete_calendar_event(
    event_id: str,
    clerk: ClerkUser = Depends(require_auth),
):
    """Delete a calendar event by ID."""
    user = get_user(clerk.user_id)
    if not user or not user.gcal_connected:
        raise HTTPException(status_code=400, detail="Google Calendar not connected.")

    try:
        result = await _mcp_call(user, "gcal_delete_event", {"event_id": event_id})
        ok = result.get("deleted", False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar delete failed: {exc}")

    if not ok:
        raise HTTPException(status_code=404, detail="Event not found or already deleted.")

    return {"user_id": clerk.user_id, "deleted": True, "event_id": event_id}


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
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL or "gpt-4o-mini",
        openai_base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
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
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL or "gpt-4o-mini",
        openai_base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
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


# ============================================================================
# MCP Tools Status Endpoint
# ============================================================================

@router.get("/mcp-tools")
async def get_mcp_tools_status(clerk: ClerkUser = Depends(require_auth)):
    """
    Return the list of MCP tools available for this user.
    Used by the frontend to show MCP connection status and available tools.
    """
    user = get_user(clerk.user_id)
    if not user:
        return {
            "user_id": clerk.user_id,
            "mcp_connected": False,
            "providers": [],
            "tools": [],
            "total_tools": 0,
        }

    providers = []
    tools = []

    # Google Calendar MCP provider
    if user.gcal_connected:
        provider = _get_mcp_calendar(user)
        tool_schemas = await provider.list_tools()
        health = await provider.health_check()
        providers.append({
            "name": provider.provider_name,
            "type": "in-process",
            "status": "connected" if health else "token_expired",
            "tool_count": len(tool_schemas),
        })
        for ts in tool_schemas:
            tools.append({
                "name": ts.name,
                "description": ts.description,
                "provider": provider.provider_name,
            })

    # External MCP servers (from config)
    settings = get_settings()
    external_servers = getattr(settings, "MCP_SERVERS", [])
    for srv in external_servers:
        providers.append({
            "name": srv.get("name", "unknown"),
            "type": srv.get("transport", "unknown"),
            "status": "configured",
            "tool_count": 0,
        })

    return {
        "user_id": clerk.user_id,
        "mcp_connected": len(providers) > 0,
        "providers": providers,
        "tools": tools,
        "total_tools": len(tools),
    }
