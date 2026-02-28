"""
Founder OS — Test Routes (development only)
=============================================
Simple endpoints for testing the LLM + agent pipeline
without requiring Clerk authentication.

These routes are only registered when APP_ENV == "development".
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.llm import LLMMessage, Role, create_llm_provider
from app.config import get_settings

router = APIRouter(prefix="/api/test", tags=["test"])


# ── Request / Response ────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    system_prompt: str = Field(
        "You are a helpful AI startup advisor. Keep answers concise.",
        max_length=5000,
    )
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)


class ChatResponse(BaseModel):
    reply: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float


class ProviderInfoResponse(BaseModel):
    provider: str
    model: str
    healthy: bool


# ── Routes ────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def test_chat(body: ChatRequest):
    """
    Send a message to the configured LLM and get a response.
    No auth required — for development testing only.
    """
    settings = get_settings()

    # Build provider from current config
    provider = _create_provider(settings)

    messages = [LLMMessage(role=Role.USER, content=body.message)]

    start = time.time()
    try:
        response = await provider.generate(
            messages,
            system=body.system_prompt,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")
    finally:
        if hasattr(provider, "close"):
            await provider.close()

    duration = time.time() - start

    return ChatResponse(
        reply=response.content,
        model=response.model or body.model or settings.GEMINI_MODEL,
        provider=provider.provider_name,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        duration_seconds=round(duration, 3),
    )


@router.get("/provider", response_model=ProviderInfoResponse)
async def test_provider_info():
    """Check which LLM provider is configured and whether it's healthy."""
    settings = get_settings()
    provider = _create_provider(settings)

    try:
        healthy = await provider.health_check()
    except Exception:
        healthy = False
    finally:
        if hasattr(provider, "close"):
            await provider.close()

    model = _get_model(settings)
    return ProviderInfoResponse(
        provider=settings.LLM_PROVIDER,
        model=model,
        healthy=healthy,
    )


# ── Helpers ───────────────────────────────────────────────────

def _create_provider(settings):
    """Build an LLM provider instance from the current settings."""
    return create_llm_provider(
        provider=settings.LLM_PROVIDER,
        api_key=_get_api_key(settings),
        base_url=_get_base_url(settings),
        model=_get_model(settings),
    )


def _get_api_key(settings) -> str:
    mapping = {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai_compatible": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


def _get_base_url(settings) -> str:
    mapping = {
        "ollama": settings.OLLAMA_BASE_URL,
        "openai_compatible": settings.OPENAI_BASE_URL,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


def _get_model(settings) -> str:
    mapping = {
        "ollama": settings.OLLAMA_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "openai_compatible": settings.OPENAI_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


# ── Weekly Context (manual data input) ────────────────────────

class WeeklyContextRequest(BaseModel):
    """Manual input for the founder's weekly context."""
    business_name: str | None = None
    business_type: str | None = None
    industry: str | None = None
    mrr: float | None = None
    mrr_growth_pct: float | None = None
    active_users: int | None = None
    monthly_traffic: int | None = None
    team_size: int | None = None
    primary_goal: str | None = None
    goals_this_week: list[str] | None = None
    blockers: list[str] | None = None
    completed_last_week: list[str] | None = None


@router.post("/weekly-context")
async def set_weekly_context(body: WeeklyContextRequest):
    """
    Submit your business context for the Weekly Planner.

    This data overrides the default mock values so subsequent
    planner calls use YOUR real numbers and goals.
    """
    from app.agents.mock_data import set_manual_context

    # Only include fields that were actually sent (not None)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    set_manual_context(data)

    return {
        "status": "saved",
        "fields_set": list(data.keys()),
        "message": (
            "Context saved. Your data will be used by the PlannerAgent's "
            "tools (get_business_metrics, list_tasks, etc.) until you clear it."
        ),
    }


@router.get("/weekly-context")
async def get_weekly_context():
    """Retrieve the current manual context (returns defaults if none set)."""
    from app.agents.mock_data import get_manual_context, get_mock_founder_profile

    manual = get_manual_context()
    profile = get_mock_founder_profile()

    return {
        "manual_overrides": manual,
        "effective_profile": profile,
        "has_manual_data": bool(manual),
    }


@router.delete("/weekly-context")
async def clear_weekly_context():
    """Reset manual context — tools will revert to default mock data."""
    from app.agents.mock_data import clear_manual_context

    clear_manual_context()
    return {"status": "cleared", "message": "Reverted to default mock data."}


# ── Structured Plan Generation ───────────────────────────────

# In-memory store for the most recent plan
_latest_plan: dict[str, Any] = {}


class PlanRequest(BaseModel):
    """Request body for generating a structured weekly plan."""
    message: str = Field(
        "Plan my week",
        min_length=1,
        max_length=10000,
        description="Your planning request — include goals, context, etc.",
    )
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)


@router.post("/plan")
async def generate_structured_plan(body: PlanRequest):
    """
    Generate a structured weekly plan.

    1. Sends your message to the LLM with the PlannerAgent's prompt
    2. Parses the markdown response into a structured WeeklyPlan JSON
    3. Returns tasks, priorities, timeline, delegations, risks

    The plan is stored in memory for ICS download and Google Calendar push.
    """
    from app.agents.agents import PlannerAgent
    from app.agents.planner_models import parse_plan_to_model, WeeklyPlan, Priority, DaySchedule, PlanTask, ICEScore
    from app.agents.mock_data import get_mock_founder_profile
    import datetime

    global _latest_plan

    # ── MOCK BYPASS FOR RATE LIMITS ──
    if body.message.strip().lower() == "mock_plan":
        mock_plan_obj = WeeklyPlan(
            week_of=datetime.date.today().isoformat(),
            top_priorities=[
                Priority(rank=1, title="Test Google Calendar Auth", rationale="To verify the OAuth flow.", ice_score=ICEScore(impact=10, confidence=10, ease=10), owner_agent="planner")
            ],
            daily_schedule={
                "monday": DaySchedule(
                    day="monday",
                    tasks=[
                        PlanTask(
                            id="pt-mock-1",
                            title="Mock Task for Calendar Sync",
                            description="This event was generated without hitting the LLM to avoid rate limits.",
                            owner_agent="planner",
                            priority=1,
                            est_hours=1.0,
                            start_time="10:00",
                            end_time="11:00",
                            status="pending",
                            ice_score=ICEScore(impact=5, confidence=5, ease=5),
                            tags=["test"]
                        )
                    ]
                )
            },
            delegations=[],
            risks=[],
            success_criteria=["Event synced successfully to GCAL."]
        )
        mock_plan_obj.compute_totals()
        
        plan_dict = mock_plan_obj.model_dump(mode="json")
        _latest_plan = plan_dict
        return {
            "plan": plan_dict,
            "raw_markdown": "MOCK_PLAN_USED",
            "duration_seconds": 0.0,
            "model": "mock-bypass",
        }

    settings = get_settings()
    provider = _create_provider(settings)

    # Build a rich prompt with founder context
    profile = get_mock_founder_profile()
    context_block = (
        f"\n\n<founder_context>\n"
        f"Business: {profile['business_name']} ({profile['industry']})\n"
        f"Stage: {profile['business_stage']} | Team: {profile['team_size']}\n"
        f"MRR: ${profile['current_mrr']:,.0f} | Users: {profile['current_users']}\n"
        f"Goals this week: {', '.join(profile['goals_this_week'])}\n"
        f"Completed last week: {', '.join(profile['completed_last_week'])}\n"
    )
    if profile.get("blockers"):
        context_block += f"Blockers: {', '.join(profile['blockers'])}\n"
    context_block += "</founder_context>"

    full_message = body.message + context_block

    # Step 1: Generate markdown plan with the PlannerAgent's system prompt
    from app.agents.llm import LLMMessage, Role

    messages = [LLMMessage(role=Role.USER, content=full_message)]

    start = time.time()
    try:
        response = await provider.generate(
            messages,
            system=PlannerAgent.default_system_prompt,
            model=body.model,
            temperature=body.temperature,
            max_tokens=4096,
        )
        markdown_plan = response.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM plan generation failed: {exc}")

    # Step 2: Parse markdown into structured WeeklyPlan
    try:
        plan = await parse_plan_to_model(
            markdown_plan=markdown_plan,
            llm_provider=provider,
            model=body.model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Plan parsing failed: {exc}",
        )
    finally:
        if hasattr(provider, "close"):
            await provider.close()

    duration = time.time() - start

    # Store for ICS / GCal export
    plan_dict = plan.model_dump(mode="json")
    _latest_plan = plan_dict

    return {
        "plan": plan_dict,
        "raw_markdown": markdown_plan,
        "duration_seconds": round(duration, 3),
        "model": response.model or settings.GEMINI_MODEL,
    }


@router.get("/plan/ical")
async def download_plan_ical():
    """
    Download the most recent structured plan as an .ics file.

    Works with any calendar app (Apple Calendar, Outlook, Google Calendar).
    No authentication required.
    """
    from app.agents.planner_models import WeeklyPlan, plan_to_ical
    from fastapi.responses import Response

    if not _latest_plan:
        raise HTTPException(
            status_code=404,
            detail="No plan generated yet. Call POST /api/test/plan first.",
        )

    plan = WeeklyPlan.model_validate(_latest_plan)
    ical_data = plan_to_ical(plan)

    return Response(
        content=ical_data,
        media_type="text/calendar",
        headers={
            "Content-Disposition": (
                f"attachment; filename=founder-os-week-{plan.week_of.isoformat()}.ics"
            ),
        },
    )


# ── Google Calendar OAuth + Push ──────────────────────────────

@router.get("/plan/gcal/auth")
async def gcal_auth():
    """
    Start the Google Calendar OAuth2 flow.

    Returns the URL the user should visit to grant calendar access.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.
    """
    from app.integrations.calendar_integration import get_auth_url

    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                "GOOGLE_CLIENT_ID not set in .env. "
                "Get credentials at https://console.cloud.google.com/apis/credentials"
            ),
        )

    auth_url = get_auth_url(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    return {"auth_url": auth_url, "message": "Visit this URL to grant calendar access."}


@router.get("/plan/gcal/callback")
async def gcal_callback(code: str, state: str = "founder-os"):
    """
    OAuth2 callback from Google.

    Exchanges the authorization code for access + refresh tokens.
    """
    from app.integrations.calendar_integration import (
        exchange_code_for_tokens,
        store_tokens,
    )

    settings = get_settings()

    try:
        tokens = await exchange_code_for_tokens(
            code=code,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    # Store tokens (using "dev-user" as the user ID for testing)
    store_tokens("dev-user", tokens)

    return {
        "status": "authenticated",
        "message": "Google Calendar access granted. You can now push plans.",
        "scopes": tokens.get("scope", ""),
    }


@router.post("/plan/gcal/push")
async def push_plan_to_google_calendar(
    calendar_id: str = "primary",
    timezone: str = "Asia/Kolkata",
):
    """
    Push the most recent structured plan to Google Calendar.

    Requires completing the OAuth flow first (GET /plan/gcal/auth).
    Each task becomes a color-coded calendar event.
    """
    from app.agents.planner_models import WeeklyPlan
    from app.integrations.calendar_integration import push_plan_to_gcal, get_tokens

    if not _latest_plan:
        raise HTTPException(
            status_code=404,
            detail="No plan generated yet. Call POST /api/test/plan first.",
        )

    tokens = get_tokens("dev-user")
    if not tokens:
        raise HTTPException(
            status_code=401,
            detail=(
                "Not authenticated with Google Calendar. "
                "Visit GET /api/test/plan/gcal/auth first."
            ),
        )

    settings = get_settings()
    plan = WeeklyPlan.model_validate(_latest_plan)

    result = await push_plan_to_gcal(
        plan=plan,
        user_id="dev-user",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        calendar_id=calendar_id,
        timezone_str=timezone,
    )

    return result

