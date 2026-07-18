"""
Founder OS — Billing Routes
==============================
Stripe-powered subscription management: plans, checkout, portal, webhooks.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.posthog_client import get_posthog
from app.models import SubscriptionPlan, User
from app.stripe import (
    create_checkout_session,
    create_portal_session,
    handle_webhook_event,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ── Schemas ──────────────────────────────────────────────

class PlanOut(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    price_monthly_usd: Optional[float] = None
    price_yearly_usd: Optional[float] = None
    monthly_task_limit: Optional[int] = None
    agent_limit: Optional[int] = None
    workflow_limit: Optional[int] = None
    knowledge_items_limit: Optional[int] = None
    team_members_limit: Optional[int] = None
    features: Optional[list] = None
    is_current: bool = False


class BillingStatusOut(BaseModel):
    subscription_tier: str
    subscription_status: str
    monthly_task_limit: int
    monthly_tasks_used: int
    trial_ends_at: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    has_payment_method: bool = False


class CheckoutIn(BaseModel):
    plan: str = Field(..., pattern="^(starter|pro|enterprise)$")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutOut(BaseModel):
    checkout_url: str


class PortalOut(BaseModel):
    portal_url: str


# ── Helpers ──────────────────────────────────────────────

async def _get_user(clerk_user: ClerkUser, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.clerk_user_id == clerk_user.user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Complete onboarding first.")
    return user


# ── Routes ───────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    user: Optional[ClerkUser] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all available subscription plans."""
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active == True)
        .order_by(SubscriptionPlan.price_monthly_usd.asc().nulls_first())
    )
    plans = result.scalars().all()

    # Determine current plan if user is authenticated
    current_tier = None
    if user:
        db_user = await _get_user(user, db)
        current_tier = db_user.subscription_tier

    return [
        PlanOut(
            name=p.name,
            display_name=p.display_name,
            description=p.description,
            price_monthly_usd=float(p.price_monthly_usd) if p.price_monthly_usd else None,
            price_yearly_usd=float(p.price_yearly_usd) if p.price_yearly_usd else None,
            monthly_task_limit=p.monthly_task_limit,
            agent_limit=p.agent_limit,
            workflow_limit=p.workflow_limit,
            knowledge_items_limit=p.knowledge_items_limit,
            team_members_limit=p.team_members_limit,
            features=p.features,
            is_current=(p.name == current_tier),
        )
        for p in plans
    ]


@router.get("/status", response_model=BillingStatusOut)
async def get_billing_status(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's billing status and usage."""
    user = await _get_user(clerk_user, db)

    return BillingStatusOut(
        subscription_tier=user.subscription_tier or "free",
        subscription_status=user.subscription_status or "trial",
        monthly_task_limit=user.monthly_task_limit or 50,
        monthly_tasks_used=user.monthly_tasks_used or 0,
        trial_ends_at=user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        stripe_customer_id=user.stripe_customer_id,
        has_payment_method=bool(user.stripe_customer_id),
    )


@router.post("/checkout", response_model=CheckoutOut)
async def create_checkout(
    body: CheckoutIn,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session and return the redirect URL."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY in .env.",
        )

    user = await _get_user(clerk_user, db)

    try:
        url = await create_checkout_session(
            user=user,
            plan_name=body.plan,
            success_url=body.success_url or "http://localhost:3000/dashboard/billing?success=true",
            cancel_url=body.cancel_url or "http://localhost:3000/dashboard/billing?canceled=true",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except stripe.StripeError as exc:
        logger.error("Stripe checkout error: %s", exc)
        raise HTTPException(status_code=502, detail="Stripe error — please try again.")

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=clerk_user.user_id,
            event="checkout_initiated",
            properties={"plan": body.plan},
        )

    return CheckoutOut(checkout_url=url)


@router.post("/portal", response_model=PortalOut)
async def create_portal(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Customer Portal session for subscription management."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY in .env.",
        )

    user = await _get_user(clerk_user, db)

    try:
        url = await create_portal_session(user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except stripe.StripeError as exc:
        logger.error("Stripe portal error: %s", exc)
        raise HTTPException(status_code=502, detail="Stripe error — please try again.")

    return PortalOut(portal_url=url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive and verify Stripe webhook events.

    This endpoint does NOT require auth — it's called by Stripe's servers.
    Authentication is via the webhook signature.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="STRIPE_WEBHOOK_SECRET not configured.",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    await handle_webhook_event(event, db)

    ph = get_posthog()
    if ph is not None:
        event_type = event["type"]
        data = event["data"]["object"]
        if event_type in (
            "checkout.session.completed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            clerk_user_id = data.get("metadata", {}).get("clerk_user_id") or data.get("customer", "unknown")
            ph.capture(
                distinct_id=clerk_user_id,
                event="subscription_changed",
                properties={
                    "stripe_event_type": event_type,
                    "subscription_status": data.get("status"),
                    "plan": data.get("metadata", {}).get("plan"),
                },
            )

    return {"status": "ok"}
