"""
Founder OS — Settings Routes
==============================
Endpoints for founder profile (including primary goal) and connected apps.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.log_sanitize import sl
from app.models import FounderProfile, Integration, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Schemas ──────────────────────────────────────────────

class FounderProfileOut(BaseModel):
    id: str
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    business_stage: Optional[str] = None
    industry: Optional[str] = None
    target_audience: Optional[str] = None
    primary_goal: Optional[str] = None
    primary_goal_description: Optional[str] = None
    team_size: int = 1
    team_roles: Optional[list] = None
    current_mrr: Optional[float] = None
    current_users: Optional[int] = None
    monthly_traffic: Optional[int] = None
    preferred_communication: Optional[str] = None
    writing_voice: Optional[str] = None
    working_hours: Optional[dict] = None


class FounderProfileUpdate(BaseModel):
    business_name: Optional[str] = Field(None, max_length=255)
    business_type: Optional[str] = Field(None, max_length=100)
    business_stage: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    target_audience: Optional[str] = None
    primary_goal: Optional[str] = Field(None, max_length=100)
    primary_goal_description: Optional[str] = None
    team_size: Optional[int] = Field(None, ge=1)
    team_roles: Optional[list[str]] = None
    current_mrr: Optional[float] = None
    current_users: Optional[int] = None
    monthly_traffic: Optional[int] = None
    preferred_communication: Optional[str] = Field(None, max_length=50)
    writing_voice: Optional[str] = None
    working_hours: Optional[dict] = None


class ConnectedAppOut(BaseModel):
    id: str
    integration_type: str
    display_name: Optional[str] = None
    is_active: bool = False
    last_sync_at: Optional[str] = None
    sync_status: Optional[str] = None
    sync_error: Optional[str] = None
    scopes: Optional[list[str]] = None
    created_at: str


# ── Helpers ──────────────────────────────────────────────

async def _get_user(clerk_user: ClerkUser, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.clerk_user_id == clerk_user.user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Complete onboarding first.")
    return user


# ── Founder Profile ─────────────────────────────────────

@router.get("/profile", response_model=FounderProfileOut)
async def get_founder_profile(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get the founder's business profile including primary goal."""
    user = await _get_user(clerk_user, db)
    result = await db.execute(
        select(FounderProfile).where(FounderProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")

    return FounderProfileOut(
        id=str(profile.id),
        business_name=profile.business_name,
        business_type=profile.business_type,
        business_stage=profile.business_stage,
        industry=profile.industry,
        target_audience=profile.target_audience,
        primary_goal=profile.primary_goal,
        primary_goal_description=profile.primary_goal_description,
        team_size=profile.team_size,
        team_roles=profile.team_roles,
        current_mrr=float(profile.current_mrr) if profile.current_mrr else None,
        current_users=profile.current_users,
        monthly_traffic=profile.monthly_traffic,
        preferred_communication=profile.preferred_communication,
        writing_voice=profile.writing_voice,
        working_hours=profile.working_hours,
    )


@router.patch("/profile", response_model=FounderProfileOut)
async def update_founder_profile(
    payload: FounderProfileUpdate,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update the founder's business profile. Only provided fields are updated."""
    user = await _get_user(clerk_user, db)
    result = await db.execute(
        select(FounderProfile).where(FounderProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(profile, field_name, value)

    await db.commit()
    await db.refresh(profile)

    return FounderProfileOut(
        id=str(profile.id),
        business_name=profile.business_name,
        business_type=profile.business_type,
        business_stage=profile.business_stage,
        industry=profile.industry,
        target_audience=profile.target_audience,
        primary_goal=profile.primary_goal,
        primary_goal_description=profile.primary_goal_description,
        team_size=profile.team_size,
        team_roles=profile.team_roles,
        current_mrr=float(profile.current_mrr) if profile.current_mrr else None,
        current_users=profile.current_users,
        monthly_traffic=profile.monthly_traffic,
        preferred_communication=profile.preferred_communication,
        writing_voice=profile.writing_voice,
        working_hours=profile.working_hours,
    )


# ── Connected Apps ───────────────────────────────────────

# Registry of all supported apps (for display even if not connected).
# Notion and Obsidian are deliberately absent: they connect through the State
# Engine source flow (/api/state/sources, SourceCreateRequest types) — listing
# them here too would show a second, contradictory status for the same
# connection. The apps page derives their cards client-side from that endpoint
# (STATE_APPS in apps/web .../dashboard/apps/page.tsx).
SUPPORTED_APPS = [
    {
        "key": "google_calendar",
        "display_name": "Google Calendar",
        "description": "Sync weekly plans and tasks to your calendar",
        "category": "Productivity",
        "icon": "calendar",
        "connect_url": "/api/planner/connect",
    },
    {
        "key": "slack",
        "display_name": "Slack",
        "description": "Get notifications and interact with agents via Slack",
        "category": "Communication",
        "icon": "message-square",
        "connect_url": None,
    },
    {
        "key": "github",
        "display_name": "GitHub",
        "description": "Track repos, PRs, and development progress",
        "category": "Development",
        "icon": "code",
        "connect_url": None,
    },
    {
        "key": "stripe",
        "display_name": "Stripe",
        "description": "Monitor revenue, subscriptions, and billing",
        "category": "Finance",
        "icon": "credit-card",
        "connect_url": None,
    },
    {
        "key": "linear",
        "display_name": "Linear",
        "description": "Project management and issue tracking",
        "category": "Development",
        "icon": "layout-list",
        "connect_url": None,
    },
    {
        "key": "gmail",
        "display_name": "Gmail",
        "description": "Email management and smart inbox features",
        "category": "Communication",
        "icon": "mail",
        "connect_url": None,
    },
    {
        "key": "analytics",
        "display_name": "Google Analytics",
        "description": "Website traffic and conversion tracking",
        "category": "Analytics",
        "icon": "bar-chart-2",
        "connect_url": None,
    },
    {
        "key": "twitter",
        "display_name": "X (Twitter)",
        "description": "Social media posting and engagement tracking",
        "category": "Social",
        "icon": "share-2",
        "connect_url": None,
    },
    {
        "key": "hubspot",
        "display_name": "HubSpot",
        "description": "CRM, contacts, and sales pipeline",
        "category": "Sales",
        "icon": "users",
        "connect_url": None,
    },
]


# Credential-shaped substrings that must never survive into a detail field.
# Provider error text routinely embeds the failing request URL (…?access_token=…)
# or an echoed Authorization header.
_SECRET_PATTERNS = [
    # key=value / "key": "value", with or without a separator (space too).
    re.compile(r"(access_token|refresh_token|client_secret|api[_-]?key|id_token"
               r"|token|password)"
               r"\s*(=|:)?\s*\"?[A-Za-z0-9._\-/+]{8,}\"?", re.IGNORECASE),
    re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._\-/+=]+", re.IGNORECASE),
    re.compile(r"\bey[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
    re.compile(r"\bya29\.[A-Za-z0-9._\-]+"),            # Google access
    re.compile(r"\b1//[A-Za-z0-9._\-]+"),               # Google refresh
    re.compile(r"\bAIza[A-Za-z0-9._\-]{10,}"),          # Google API key
    re.compile(r"\b(ntn|secret)_[A-Za-z0-9]{8,}"),      # Notion
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{8,}"),      # Slack
    re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{8,}"),  # GitHub
    re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}"),             # Stripe
    re.compile(r"\bpat-[a-z0-9]{2,}-[A-Za-z0-9-]{8,}"),                  # HubSpot
]


def redact_secrets(text: str) -> str:
    """Strip credential-shaped substrings from text bound for the client."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


class AppDetailField(BaseModel):
    """One human-readable row in the connection detail panel.

    Deliberately a flat label/value pair rather than a free-form dict: every
    field shown to the user is constructed explicitly below, so a new column on
    planner_users or integrations can never reach the client by accident. No
    credential ever becomes an AppDetailField (see standards/security.md).
    """

    label: str
    value: str
    # "default" | "success" | "warning" | "danger" — drives the value's colour.
    tone: str = "default"


class AppStatusOut(BaseModel):
    key: str
    display_name: str
    description: str
    category: str
    icon: str
    status: str  # "connected" | "disconnected" | "error" | "coming_soon"
    is_active: bool = False
    last_sync_at: Optional[str] = None
    sync_status: Optional[str] = None
    connect_url: Optional[str] = None
    # Populated only for connected apps; drives the detail drawer.
    details: list[AppDetailField] = []
    # Present only when the app supports being disconnected from the UI.
    # The method ships with the URL so the client never has to infer a verb
    # from the path — credentials live in different stores with different routes.
    disconnect_url: Optional[str] = None
    disconnect_method: Optional[str] = None


def _gcal_details(planner_user) -> list[AppDetailField]:
    """Build the Google Calendar detail rows from the planner_users row.

    Only non-secret, user-meaningful facts. We cannot show the connected Google
    account's email: the OAuth scope is calendar.events only (no userinfo.email),
    so Google never tells us which account it is — the calendar id is the closest
    identifying fact we legitimately hold.
    """
    fields = [
        AppDetailField(label="Calendar", value=planner_user.calendar_id or "primary"),
        AppDetailField(label="Access", value="Calendar events (read & write)"),
        AppDetailField(label="Time zone", value=planner_user.timezone or "—"),
    ]

    # Token health drives whether the user should be nudged to reconnect.
    if planner_user.has_valid_gcal_tokens():
        fields.append(
            AppDetailField(label="Authorization", value="Valid", tone="success")
        )
    else:
        fields.append(
            AppDetailField(
                label="Authorization",
                value="Expired — reconnect to keep syncing",
                tone="warning",
            )
        )

    fields.append(
        AppDetailField(label="Plans pushed", value=str(planner_user.plan_count or 0))
    )
    if planner_user.last_plan_at:
        fields.append(
            AppDetailField(
                label="Last plan",
                value=f"{planner_user.last_plan_at} · "
                      f"{planner_user.last_plan_events or 0} events",
            )
        )
    return fields


@router.get("/apps", response_model=list[AppStatusOut])
async def list_connected_apps(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all supported apps with their connection status."""
    user = await _get_user(clerk_user, db)

    # Fetch user's connected integrations
    result = await db.execute(
        select(Integration).where(Integration.user_id == user.id)
    )
    integrations = {i.integration_type: i for i in result.scalars().all()}

    # Also check planner GCal connection (stored differently — in planner_users)
    gcal_connected = False
    planner_user = None
    try:
        # Fresh read: this endpoint decides whether the UI shows "Connected",
        # so a stale cache would offer a disconnect for an already-gone grant.
        from app.user_store import get_user_fresh as get_planner_user
        planner_user = get_planner_user(clerk_user.user_id)
        if planner_user and planner_user.gcal_connected:
            gcal_connected = True
    except Exception:
        pass

    apps = []
    for app_def in SUPPORTED_APPS:
        integration = integrations.get(app_def["key"])

        if app_def["key"] == "google_calendar":
            # Special handling — GCal is connected via planner
            if gcal_connected:
                status = "connected"
                is_active = True
            else:
                status = "disconnected"
                is_active = False
            apps.append(AppStatusOut(
                key=app_def["key"],
                display_name=app_def["display_name"],
                description=app_def["description"],
                category=app_def["category"],
                icon=app_def["icon"],
                status=status,
                is_active=is_active,
                connect_url=app_def["connect_url"],
                details=_gcal_details(planner_user) if gcal_connected else [],
                disconnect_url="/api/planner/disconnect" if gcal_connected else None,
                disconnect_method="POST" if gcal_connected else None,
            ))
        elif integration:
            details = [
                AppDetailField(
                    label="Account",
                    value=integration.display_name or app_def["display_name"],
                ),
                AppDetailField(
                    label="Status",
                    value="Active" if integration.is_active else "Needs attention",
                    tone="success" if integration.is_active else "danger",
                ),
            ]
            if integration.scopes:
                details.append(
                    AppDetailField(label="Access", value=", ".join(integration.scopes))
                )
            if integration.sync_status:
                details.append(
                    AppDetailField(label="Last sync", value=integration.sync_status)
                )
            if integration.sync_error:
                # Provider error text is NOT published. It routinely embeds the
                # failing request URL (…?access_token=…) or an echoed
                # Authorization header, and a token-shape denylist is a
                # mitigation, not a guarantee — every provider has its own
                # format and the next one added is the one that slips through.
                # The raw text stays in the logs, where operators can read it.
                logger.warning(
                    "integration %s sync_error for user %s: %s",
                    sl(app_def["key"]), sl(str(user.id)),
                    sl(redact_secrets(integration.sync_error)),
                )
                details.append(
                    AppDetailField(
                        label="Error",
                        value="Last sync failed. Reconnect, or contact support "
                              "if it keeps failing.",
                        tone="danger",
                    )
                )
            details.append(
                AppDetailField(
                    label="Connected since",
                    value=integration.created_at.strftime("%d %b %Y")
                    if integration.created_at else "—",
                )
            )
            apps.append(AppStatusOut(
                key=app_def["key"],
                display_name=app_def["display_name"],
                description=app_def["description"],
                category=app_def["category"],
                icon=app_def["icon"],
                status="connected" if integration.is_active else "error",
                is_active=integration.is_active,
                last_sync_at=integration.last_sync_at.isoformat() if integration.last_sync_at else None,
                sync_status=integration.sync_status,
                connect_url=app_def["connect_url"],
                details=details,
                disconnect_url=f"/api/settings/apps/{app_def['key']}",
                disconnect_method="DELETE",
            ))
        else:
            apps.append(AppStatusOut(
                key=app_def["key"],
                display_name=app_def["display_name"],
                description=app_def["description"],
                category=app_def["category"],
                icon=app_def["icon"],
                status="coming_soon" if not app_def["connect_url"] else "disconnected",
                is_active=False,
                connect_url=app_def["connect_url"],
            ))

    return apps


@router.delete("/apps/{key}", status_code=200)
async def disconnect_app(
    key: str,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect an integrations-table app, deleting its stored credentials.

    Google Calendar is NOT handled here — its tokens live on planner_users and
    need a Google-side revoke, so it has its own route
    (POST /api/planner/disconnect).
    """
    if key == "google_calendar":
        raise HTTPException(
            status_code=400,
            detail="Disconnect Google Calendar via POST /api/planner/disconnect.",
        )
    if key not in {a["key"] for a in SUPPORTED_APPS}:
        raise HTTPException(status_code=404, detail=f"Unknown app: {key}")

    user = await _get_user(clerk_user, db)

    # Scoped to this user's row — a key alone must never reach another tenant's
    # integration (see standards/security.md, crawler IDOR precedent).
    integration = (await db.execute(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.integration_type == key,
        )
    )).scalar_one_or_none()

    if integration is None:
        raise HTTPException(status_code=404, detail=f"{key} is not connected.")

    # Delete rather than deactivate: leaving access/refresh tokens at rest for an
    # app the user explicitly disconnected is exactly what they asked us not to do.
    await db.delete(integration)
    await db.commit()

    logger.info("Disconnected integration %s for user %s", key, user.id)
    return {"status": "disconnected", "key": key}
