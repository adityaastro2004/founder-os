"""
Founder OS — Background Scheduler
====================================
Runs the Weekly Planner automatically on a cron schedule for ALL
users who have connected their Google Calendar.

Jobs:
  automated_planner_job — For each connected user: gathers their stored
  business context, generates a personalised weekly plan via LLM, and
  pushes events directly to their Google Calendar.

Schedule:
  - Every Monday at 08:00 AM IST (production cadence)
  - 30 seconds after startup in dev mode (for testing)
"""

from __future__ import annotations

import datetime
import logging
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


# ============================================================================
# The main job — runs for every connected user
# ============================================================================

async def automated_planner_job() -> None:
    """
    Background job that iterates over ALL users with connected
    Google Calendar and generates + pushes a personalised weekly plan.
    """
    logger.info("🗓️  Running automated weekly planner for all connected users...")

    from app.user_store import get_users_with_gcal, save_user, store_plan_history

    users = get_users_with_gcal()
    if not users:
        logger.warning(
            "⚠️  No users with Google Calendar connected — skipping. "
            "Users should onboard via POST /api/planner/onboard then "
            "connect via GET /api/planner/connect"
        )
        return

    settings = get_settings()
    total_events = 0
    total_failed = 0

    for user in users:
        logger.info("  📋 Generating plan for %s (%s)...", user.user_id, user.business_name or "unnamed")
        start = time.time()

        try:
            plan = await _generate_plan_for_user(user, settings)
        except Exception as exc:
            logger.error("  ❌ Plan generation failed for %s: %s", user.user_id, exc)
            continue

        duration = time.time() - start
        task_count = sum(len(d.tasks) for d in plan.daily_schedule.values())
        logger.info("    Plan: %d tasks in %.1fs", task_count, duration)

        # Push to Google Calendar
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
            created = result.get("events_created", 0)
            failed = result.get("events_failed", 0)
            total_events += created
            total_failed += failed
            logger.info("    ✅ %d events created, %d failed", created, failed)

            # Update user stats
            user.last_plan_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            user.last_plan_events = created
            user.plan_count += 1
            save_user(user)

            # Store in history (DB-backed)
            _store_plan_history(user.user_id, plan, result, duration,
                                store_fn=store_plan_history)

        except Exception as exc:
            logger.error("    ❌ Calendar push failed for %s: %s", user.user_id, exc)

    logger.info(
        "🗓️  Weekly planner complete — %d user(s), %d events created, %d failed",
        len(users), total_events, total_failed,
    )


# ============================================================================
# Plan generation using stored user context (no mock dependency)
# ============================================================================

async def _generate_plan_for_user(user, settings) -> "WeeklyPlan":
    """Generate a weekly plan using the user's actual business context.

    Single-call JSON generation — asks the LLM to output structured JSON
    directly rather than markdown → parse → JSON.
    """
    import json as _json
    import re as _re
    from datetime import timedelta as _td
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

    system_prompt = f"""\
You are the Planning Agent for Founder OS. Generate a detailed weekly plan as a JSON object.

RULES:
- Create 3-5 actionable tasks per day (Monday–Friday), each with start_time and end_time
- Tasks should fit within {user.preferred_work_hours}
- Use ICE scoring (Impact, Confidence, Ease — each 1-10)
- Owner agents: planner, content, research, ops, product, support
- Each task needs a unique, descriptive title
- Break goals into concrete sub-tasks
- Time slots must not overlap within a day

Dates: {_json.dumps(days_with_dates)}

Return ONLY a JSON object (no markdown, no commentary):
{{
  "top_priorities": [
    {{"rank": 1, "title": "...", "rationale": "...", "ice_score": {{"impact": 8, "confidence": 7, "ease": 6}}, "owner_agent": "planner"}}
  ],
  "daily_schedule": {{
    "monday": {{"day": "monday", "tasks": [{{"title": "...", "description": "...", "owner_agent": "planner", "priority": 1, "est_hours": 2.0, "start_time": "09:00", "end_time": "11:00", "ice_score": {{"impact": 8, "confidence": 7, "ease": 6}}, "tags": ["dev"]}}]}},
    "tuesday": {{ ... }}, "wednesday": {{ ... }}, "thursday": {{ ... }}, "friday": {{ ... }}
  }},
  "success_criteria": ["Measurable outcome 1"]
}}"""

    messages = [LLMMessage(role=Role.USER, content=f"Plan my week\n\nFounder Context:\n{context}")]

    try:
        response = await provider.generate(
            messages,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8192,
        )

        raw = response.content.strip()
        raw = _re.sub(r"^```(?:json)?\s*", "", raw)
        raw = _re.sub(r"\s*```$", "", raw)
        raw = _clean_llm_json(raw)

        data = _json.loads(raw)
        plan = WeeklyPlan.model_validate(data)
        plan.ensure_daily_schedule()
        plan.compute_totals()
        plan.founder_context = {
            "user_id": user.user_id,
            "business_name": user.business_name,
            "goals": user.goals_this_week,
        }
        return plan

    except Exception as exc:
        logger.warning("Direct JSON plan failed (%s), using fallback", exc)
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


# ============================================================================
# Plan history (DB-backed via user_store)
# ============================================================================


def _store_plan_history(user_id: str, plan, gcal_result: dict, duration: float,
                        store_fn=None) -> None:
    """Persist a plan record via user_store.store_plan_history."""
    task_count = sum(len(d.tasks) for d in plan.daily_schedule.values())
    try:
        if store_fn is None:
            from app.user_store import store_plan_history as _store
            store_fn = _store
        store_fn(
            user_id=user_id,
            plan_id=plan.id,
            week_of=plan.week_of,
            task_count=task_count,
            events_created=gcal_result.get("events_created", 0),
            events_failed=gcal_result.get("events_failed", 0),
            duration_seconds=round(duration, 1),
            top_priorities=[p.title for p in plan.top_priorities],
            plan_data={},
            gcal_events=gcal_result.get("events", []),
        )
    except Exception as exc:
        logger.error("Failed to store plan history: %s", exc)


def get_plan_history(user_id: str) -> list[dict]:
    from app.user_store import get_plan_history as _get
    return _get(user_id)


# ============================================================================
# Helpers
# ============================================================================

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
# Scheduler lifecycle
# ============================================================================

def start_scheduler() -> AsyncIOScheduler:
    """
    Initialize and start the background scheduler.

    Jobs:
      1. Weekly planner — every Monday at 8:00 AM IST
      2. Test run — 30 seconds after startup (dev only)
    """
    global _scheduler

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # ── Production: every Monday at 8 AM IST ───────────────────
    # Explicit timezone: a CronTrigger instance built without one resolves to the
    # MACHINE-local zone (not the scheduler's Asia/Kolkata default), which made the
    # weekly plan fire at 8 AM in whatever tz the host happened to be in.
    scheduler.add_job(
        automated_planner_job,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="Asia/Kolkata"),
        id="weekly_planner",
        name="Weekly Planner (Monday 8 AM IST)",
        replace_existing=True,
    )

    # ── Dev: fires 30s after boot for testing (disabled — enable when needed) ──
    # settings = get_settings()
    # if settings.APP_ENV == "development":
    #     from apscheduler.triggers.date import DateTrigger
    #     run_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
    #     scheduler.add_job(
    #         automated_planner_job,
    #         trigger=DateTrigger(run_date=run_at),
    #         id="weekly_planner_test",
    #         name="Weekly Planner (test — 30s after boot)",
    #         replace_existing=True,
    #     )
    #     logger.info("📋 Dev test job scheduled — will fire in 30 seconds")

    scheduler.start()
    _scheduler = scheduler

    logger.info(
        "⏰ Background scheduler started — %d job(s) registered",
        len(scheduler.get_jobs()),
    )
    for job in scheduler.get_jobs():
        logger.info("   • %s (next run: %s)", job.name, job.next_run_time)

    return scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("⏰ Background scheduler stopped")
        _scheduler = None
