"""
Founder OS — Google Calendar Integration
==========================================
Provides OAuth2 authentication and event creation for Google Calendar.

Two export paths:
  1. ICS file download — works with any calendar app, no auth
  2. Google Calendar API — pushes events directly via REST + OAuth2
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Token store — backed by PostgreSQL via user_store
# ============================================================================
# Tokens are persisted in the planner_users table (gcal_access_token,
# gcal_refresh_token, gcal_token_data). These functions provide a
# backward-compatible interface used by _get_valid_token() and routes.
# ============================================================================


def store_tokens(user_id: str, tokens: dict[str, Any]) -> None:
    """Save OAuth tokens for a user (persisted to PostgreSQL)."""
    tokens["stored_at"] = time.time()
    try:
        from app.user_store import get_or_create_user, save_user
        user = get_or_create_user(user_id)
        user.store_gcal_tokens(tokens)
        save_user(user)
        logger.info("Stored GCal tokens for %s in PostgreSQL", user_id)
    except Exception as exc:
        logger.error("Failed to persist tokens for %s: %s", user_id, exc)


def get_tokens(user_id: str) -> dict[str, Any] | None:
    """Retrieve stored OAuth tokens for a user (from PostgreSQL)."""
    try:
        from app.user_store import get_user
        user = get_user(user_id)
        if user and user.gcal_tokens:
            return user.gcal_tokens
    except Exception as exc:
        logger.error("Failed to fetch tokens for %s: %s", user_id, exc)
    return None


def clear_tokens(user_id: str) -> None:
    """Remove stored OAuth tokens for a user."""
    try:
        from app.user_store import get_user, save_user
        user = get_user(user_id)
        if user:
            user.gcal_tokens = {}
            user.gcal_connected = False
            save_user(user)
    except Exception as exc:
        logger.error("Failed to clear tokens for %s: %s", user_id, exc)


# ============================================================================
# OAuth2 Helpers
# ============================================================================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events"


def get_auth_url(
    client_id: str,
    redirect_uri: str,
    state: str = "founder-os",
    force_consent: bool = True,
) -> str:
    """
    Build the Google OAuth2 authorization URL.

    The user visits this URL to grant calendar access.
    Set force_consent=False when re-linking (we already have a refresh_token).
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "state": state,
    }
    # Only force consent on first-time auth — ensures we get a refresh_token.
    # On re-links where we already have a refresh_token, skip the consent screen.
    if force_consent:
        params["prompt"] = "consent"
    url = httpx.URL(GOOGLE_AUTH_URL, params=params)
    return str(url)


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """
    Exchange an authorization code for access + refresh tokens.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()


class CalendarAuthExpired(Exception):
    """Raised when Google Calendar tokens are expired/revoked and re-auth is needed."""


def _clear_gcal_connection(user_id: str) -> None:
    """Mark the user as disconnected from Google Calendar."""
    try:
        from app.user_store import get_user, save_user
        user = get_user(user_id)
        if user:
            user.gcal_connected = False
            user.gcal_tokens = {}
            save_user(user)
            logger.info("Cleared GCal connection for user %s (token revoked/expired)", user_id)
    except Exception as exc:
        logger.error("Failed to clear GCal connection for %s: %s", user_id, exc)


async def _get_valid_token(
    user_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Get a valid access token, refreshing if expired."""
    tokens = get_tokens(user_id)
    if not tokens:
        raise CalendarAuthExpired(
            "Google Calendar not connected. Please reconnect your calendar."
        )

    # Check if token is expired (with 60s buffer)
    stored_at = tokens.get("stored_at", 0)
    expires_in = tokens.get("expires_in", 3600)
    if time.time() > stored_at + expires_in - 60:
        # Refresh
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            _clear_gcal_connection(user_id)
            raise CalendarAuthExpired(
                "Google Calendar session expired. Please reconnect your calendar."
            )

        try:
            new_tokens = await refresh_access_token(
                refresh_token, client_id, client_secret,
            )
        except httpx.HTTPStatusError as exc:
            # 400/401 from Google means refresh token is revoked/expired
            logger.warning(
                "Google token refresh failed for user %s: %s %s",
                user_id, exc.response.status_code, exc.response.text,
            )
            _clear_gcal_connection(user_id)
            raise CalendarAuthExpired(
                "Google Calendar authorization expired. "
                "Please reconnect your calendar to continue."
            ) from exc

        new_tokens["refresh_token"] = refresh_token  # Google doesn't always return it
        store_tokens(user_id, new_tokens)
        return new_tokens["access_token"]

    return tokens["access_token"]


# ============================================================================
# Google Calendar Event Creation
# ============================================================================

async def push_plan_to_gcal(
    plan: Any,  # WeeklyPlan
    user_id: str,
    client_id: str,
    client_secret: str,
    calendar_id: str = "primary",
    timezone_str: str = "Asia/Kolkata",
) -> dict[str, Any]:
    """
    Push all tasks from a WeeklyPlan to Google Calendar.

    Returns a summary with created event IDs.
    """
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    day_offsets = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }

    created_events = []
    errors = []

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        for day_name, schedule in plan.daily_schedule.items():
            day_key = day_name.lower()
            # Support both day names ("monday") and date strings ("2026-03-24")
            if day_key in day_offsets:
                task_date = plan.week_of + timedelta(days=day_offsets[day_key])
            else:
                # Try parsing as a date string
                try:
                    from datetime import date as _date_cls
                    task_date = _date_cls.fromisoformat(day_key)
                except (ValueError, TypeError):
                    task_date = plan.week_of  # fallback

            for task in schedule.tasks:
                event_body = _build_gcal_event(
                    task=task,
                    task_date=task_date,
                    timezone_str=timezone_str,
                )

                try:
                    resp = await client.post(
                        f"/calendars/{calendar_id}/events",
                        json=event_body,
                    )
                    resp.raise_for_status()
                    event_data = resp.json()
                    created_events.append({
                        "task_id": task.id,
                        "task_title": task.title,
                        "event_id": event_data.get("id"),
                        "html_link": event_data.get("htmlLink"),
                        "day": day_name,
                    })
                    logger.info(
                        "Created GCal event: %s → %s",
                        task.title,
                        event_data.get("id"),
                    )
                except Exception as exc:
                    errors.append({
                        "task_id": task.id,
                        "task_title": task.title,
                        "error": str(exc),
                    })
                    logger.error(
                        "Failed to create GCal event for '%s': %s",
                        task.title, exc,
                    )

    return {
        "status": "completed",
        "calendar_id": calendar_id,
        "events_created": len(created_events),
        "events_failed": len(errors),
        "events": created_events,
        "errors": errors,
    }


# ============================================================================
# Individual Event Helpers (for prompt-driven calendar updates)
# ============================================================================

async def create_single_event(
    user_id: str,
    client_id: str,
    client_secret: str,
    summary: str,
    start_datetime: str,
    end_datetime: str,
    timezone_str: str = "Asia/Kolkata",
    calendar_id: str = "primary",
    description: str = "",
    color_id: str = "5",
) -> dict[str, Any]:
    """
    Create a single event on Google Calendar.

    Args:
        summary: Event title
        start_datetime: ISO format, e.g. "2026-03-06T14:00:00"
        end_datetime: ISO format, e.g. "2026-03-06T15:00:00"
    """
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_datetime, "timeZone": timezone_str},
        "end": {"dateTime": end_datetime, "timeZone": timezone_str},
    }
    if description:
        event_body["description"] = description + "\n\n— Created by Founder OS"
    if color_id:
        event_body["colorId"] = color_id

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.post(
            f"/calendars/{calendar_id}/events",
            json=event_body,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("Created GCal event: %s → %s", summary, data.get("id"))
        return {
            "event_id": data.get("id"),
            "summary": summary,
            "html_link": data.get("htmlLink"),
            "start": start_datetime,
            "end": end_datetime,
        }


async def create_all_day_event(
    user_id: str,
    client_id: str,
    client_secret: str,
    summary: str,
    event_date: str,
    timezone_str: str = "Asia/Kolkata",
    calendar_id: str = "primary",
    description: str = "",
) -> dict[str, Any]:
    """Create an all-day event. event_date is ISO date like '2026-03-06'."""
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    next_day = (date.fromisoformat(event_date) + timedelta(days=1)).isoformat()
    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"date": event_date},
        "end": {"date": next_day},
    }
    if description:
        event_body["description"] = description + "\n\n— Created by Founder OS"

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.post(
            f"/calendars/{calendar_id}/events",
            json=event_body,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "event_id": data.get("id"),
            "summary": summary,
            "html_link": data.get("htmlLink"),
            "date": event_date,
            "all_day": True,
        }


async def delete_event(
    user_id: str,
    client_id: str,
    client_secret: str,
    event_id: str,
    calendar_id: str = "primary",
) -> bool:
    """Delete a calendar event by ID."""
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.delete(
            f"/calendars/{calendar_id}/events/{event_id}",
        )
        return resp.status_code in (200, 204)


async def update_event(
    user_id: str,
    client_id: str,
    client_secret: str,
    event_id: str,
    updates: dict[str, Any],
    timezone_str: str = "Asia/Kolkata",
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Patch a Google Calendar event.

    ``updates`` can contain: summary, description, start_datetime, end_datetime,
    start_date, end_date (for all-day), color_id.
    """
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    body: dict[str, Any] = {}
    if "summary" in updates:
        body["summary"] = updates["summary"]
    if "description" in updates:
        body["description"] = updates["description"]
    if "start_datetime" in updates:
        body["start"] = {
            "dateTime": updates["start_datetime"],
            "timeZone": timezone_str,
        }
    if "end_datetime" in updates:
        body["end"] = {
            "dateTime": updates["end_datetime"],
            "timeZone": timezone_str,
        }
    if "start_date" in updates:
        body["start"] = {"date": updates["start_date"]}
    if "end_date" in updates:
        body["end"] = {"date": updates["end_date"]}
    if "color_id" in updates:
        body["colorId"] = updates["color_id"]

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.patch(
            f"/calendars/{calendar_id}/events/{event_id}",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("Updated GCal event %s: %s", event_id, list(body.keys()))
        start = data.get("start", {})
        return {
            "event_id": data.get("id"),
            "summary": data.get("summary"),
            "html_link": data.get("htmlLink"),
            "start": start.get("dateTime") or start.get("date"),
            "end": (data.get("end", {}).get("dateTime")
                    or data.get("end", {}).get("date")),
            "updated": True,
        }


async def get_event(
    user_id: str,
    client_id: str,
    client_secret: str,
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Get a single calendar event by ID."""
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.get(
            f"/calendars/{calendar_id}/events/{event_id}",
        )
        resp.raise_for_status()
        data = resp.json()
        start = data.get("start", {})
        return {
            "event_id": data.get("id"),
            "summary": data.get("summary"),
            "description": data.get("description"),
            "html_link": data.get("htmlLink"),
            "start": start.get("dateTime") or start.get("date"),
            "end": (data.get("end", {}).get("dateTime")
                    or data.get("end", {}).get("date")),
            "status": data.get("status"),
        }


async def list_upcoming_events(
    user_id: str,
    client_id: str,
    client_secret: str,
    calendar_id: str = "primary",
    max_results: int = 20,
    time_min: str | None = None,
) -> list[dict[str, Any]]:
    """List upcoming events from Google Calendar."""
    access_token = await _get_valid_token(user_id, client_id, client_secret)

    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()
    else:
        # Google Calendar API requires RFC3339 with timezone suffix.
        # If the caller passed a bare datetime (no tz), append 'Z' (UTC).
        if "Z" not in time_min and "+" not in time_min and "-" not in time_min[10:]:
            time_min = time_min + "Z"

    params = {
        "maxResults": str(max_results),
        "orderBy": "startTime",
        "singleEvents": "true",
        "timeMin": time_min,
    }

    async with httpx.AsyncClient(
        base_url=GOOGLE_CALENDAR_API,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    ) as client:
        resp = await client.get(
            f"/calendars/{calendar_id}/events",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        events = []
        for item in data.get("items", []):
            start = item.get("start", {})
            description = item.get("description", "") or ""
            creator = item.get("creator", {})
            # Detect events created by Founder OS
            ai_generated = (
                "Founder OS" in description
                or "Generated by Founder OS" in description
                or "Created by Founder OS" in description
                or any(
                    item.get("summary", "").startswith(f"[{tag}]")
                    for tag in ("PLANNER", "OPS", "CONTENT", "RESEARCH", "PRODUCT", "SUPPORT")
                )
            )
            events.append({
                "event_id": item.get("id"),
                "summary": item.get("summary", "(no title)"),
                "description": description[:300],
                "start": start.get("dateTime") or start.get("date"),
                "end": (item.get("end", {}).get("dateTime")
                        or item.get("end", {}).get("date")),
                "html_link": item.get("htmlLink"),
                "ai_generated": ai_generated,
                "creator_email": creator.get("email", ""),
            })
        return events


def _build_gcal_event(
    task: Any,  # PlanTask
    task_date: date,
    timezone_str: str = "Asia/Kolkata",
) -> dict[str, Any]:
    """Build a Google Calendar event body from a PlanTask."""
    # Description
    desc_parts = []
    if task.description:
        desc_parts.append(task.description)
    desc_parts.append(f"🤖 Agent: {task.owner_agent}")
    desc_parts.append(f"🎯 Priority: {task.priority}/10")
    desc_parts.append(f"⏱️ Estimated: {task.est_hours}h")
    if task.ice_score:
        desc_parts.append(
            f"🧊 ICE: I={task.ice_score.impact} "
            f"C={task.ice_score.confidence} "
            f"E={task.ice_score.ease} "
            f"→ {task.ice_score.total}"
        )
    if task.tags:
        desc_parts.append(f"🏷️ Tags: {', '.join(task.tags)}")
    desc_parts.append("\n— Generated by Founder OS Weekly Planner")

    # Color mapping (Google Calendar color IDs)
    agent_colors = {
        "planner": "5",    # banana (yellow)
        "content": "3",    # grape (purple)
        "research": "9",   # blueberry (blue)
        "support": "2",    # sage (green)
    }

    event: dict[str, Any] = {
        "summary": f"[{task.owner_agent.upper()}] {task.title}",
        "description": "\n".join(desc_parts),
        "colorId": agent_colors.get(task.owner_agent, "0"),
    }

    if task.start_time and task.end_time:
        event["start"] = {
            "dateTime": f"{task_date.isoformat()}T{task.start_time}:00",
            "timeZone": timezone_str,
        }
        event["end"] = {
            "dateTime": f"{task_date.isoformat()}T{task.end_time}:00",
            "timeZone": timezone_str,
        }
    elif task.start_time:
        # Use est_hours for duration
        from datetime import time as dt_time
        start_dt = datetime.combine(
            task_date, dt_time.fromisoformat(task.start_time),
        )
        end_dt = start_dt + timedelta(hours=task.est_hours)
        event["start"] = {
            "dateTime": f"{task_date.isoformat()}T{task.start_time}:00",
            "timeZone": timezone_str,
        }
        event["end"] = {
            "dateTime": end_dt.strftime(f"{task_date.isoformat()}T%H:%M:00"),
            "timeZone": timezone_str,
        }
    else:
        # All-day event
        event["start"] = {"date": task_date.isoformat()}
        next_day = task_date + timedelta(days=1)
        event["end"] = {"date": next_day.isoformat()}

    return event
