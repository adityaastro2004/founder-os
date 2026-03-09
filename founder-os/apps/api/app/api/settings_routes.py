"""
Founder OS — Settings Routes
==============================
Endpoints for founder profile (including primary goal) and connected apps.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
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

# Registry of all supported apps (for display even if not connected)
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
        "key": "notion",
        "display_name": "Notion",
        "description": "Sync tasks, knowledge, and meeting notes",
        "category": "Productivity",
        "icon": "file-text",
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
    try:
        from app.user_store import get_user as get_planner_user
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
            ))
        elif integration:
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
