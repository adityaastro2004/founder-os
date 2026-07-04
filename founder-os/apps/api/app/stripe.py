"""
Founder OS — Stripe Integration Service
==========================================
Core billing logic: Checkout sessions, Customer Portal, webhook processing.

All Stripe interactions are centralised here so routes stay thin.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SubscriptionPlan, User

logger = logging.getLogger(__name__)

settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY

# ── Plan ↔ Price ID mapping ─────────────────────────────────

PLAN_PRICE_MAP: dict[str, str] = {
    "starter": settings.STRIPE_STARTER_PRICE_ID,
    "pro": settings.STRIPE_PRO_PRICE_ID,
    "enterprise": settings.STRIPE_ENTERPRISE_PRICE_ID,
}

PRICE_PLAN_MAP: dict[str, str] = {v: k for k, v in PLAN_PRICE_MAP.items() if v}


# ── Checkout ─────────────────────────────────────────────────

async def create_checkout_session(
    user: User,
    plan_name: str,
    success_url: str = "http://localhost:3000/dashboard/billing?success=true",
    cancel_url: str = "http://localhost:3000/dashboard/billing?canceled=true",
) -> str:
    """Create a Stripe Checkout session and return the URL.

    If the user already has a ``stripe_customer_id`` we reuse it so
    Stripe can track their payment history.
    """
    price_id = PLAN_PRICE_MAP.get(plan_name)
    if not price_id:
        raise ValueError(f"Unknown plan '{plan_name}' or price ID not configured")

    checkout_params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "clerk_user_id": user.clerk_user_id,
            "plan": plan_name,
        },
    }

    # Attach existing Stripe customer if we have one
    if user.stripe_customer_id:
        checkout_params["customer"] = user.stripe_customer_id
    else:
        checkout_params["customer_email"] = user.email

    session = stripe.checkout.Session.create(**checkout_params)
    return session.url


# ── Customer Portal ──────────────────────────────────────────

async def create_portal_session(
    user: User,
    return_url: str = "http://localhost:3000/dashboard/billing",
) -> str:
    """Create a Stripe Customer Portal session for self-service management."""
    if not user.stripe_customer_id:
        raise ValueError("User has no Stripe customer ID — they haven't subscribed yet")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    return session.url


# ── Webhook Processing ───────────────────────────────────────

async def handle_webhook_event(event: stripe.Event, db: AsyncSession) -> None:
    """Process a verified Stripe webhook event.

    Dispatches to specific handlers based on event type.
    """
    event_type = event["type"]
    data = event["data"]["object"]

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.payment_succeeded": _handle_payment_succeeded,
        "invoice.payment_failed": _handle_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(data, db)
        logger.info("Processed Stripe event: %s", event_type)
    else:
        logger.debug("Ignored Stripe event: %s", event_type)


async def _handle_checkout_completed(data: dict, db: AsyncSession) -> None:
    """Checkout completed → link Stripe customer, activate subscription."""
    user_id = data.get("client_reference_id")
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")
    plan = data.get("metadata", {}).get("plan", "starter")

    if not user_id:
        logger.warning("checkout.session.completed missing client_reference_id")
        return

    # Look up plan limits
    plan_limits = await _get_plan_limits(plan, db)

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            stripe_customer_id=customer_id,
            subscription_tier=plan,
            subscription_status="active",
            monthly_task_limit=plan_limits.get("monthly_task_limit", 500),
            monthly_tasks_used=0,
        )
    )
    await db.commit()
    logger.info("Activated %s plan for user %s", plan, user_id)


async def _handle_subscription_updated(data: dict, db: AsyncSession) -> None:
    """Subscription updated → sync tier and status."""
    customer_id = data.get("customer")
    status = data.get("status")  # active, past_due, canceled, etc.
    price_id = _extract_price_id(data)

    if not customer_id:
        return

    plan = PRICE_PLAN_MAP.get(price_id, "free") if price_id else None
    update_values: dict = {"subscription_status": status}
    if plan:
        update_values["subscription_tier"] = plan
        plan_limits = await _get_plan_limits(plan, db)
        update_values["monthly_task_limit"] = plan_limits.get("monthly_task_limit", 100)

    await db.execute(
        update(User)
        .where(User.stripe_customer_id == customer_id)
        .values(**update_values)
    )
    await db.commit()


async def _handle_subscription_deleted(data: dict, db: AsyncSession) -> None:
    """Subscription canceled → downgrade to free."""
    customer_id = data.get("customer")
    if not customer_id:
        return

    await db.execute(
        update(User)
        .where(User.stripe_customer_id == customer_id)
        .values(
            subscription_tier="free",
            subscription_status="canceled",
            monthly_task_limit=50,
        )
    )
    await db.commit()
    logger.info("Downgraded customer %s to free", customer_id)


async def _handle_payment_succeeded(data: dict, db: AsyncSession) -> None:
    """Payment succeeded → reset monthly usage counters."""
    customer_id = data.get("customer")
    if not customer_id:
        return

    await db.execute(
        update(User)
        .where(User.stripe_customer_id == customer_id)
        .values(
            monthly_tasks_used=0,
            last_reset_at=datetime.now(timezone.utc),
            subscription_status="active",
        )
    )
    await db.commit()


async def _handle_payment_failed(data: dict, db: AsyncSession) -> None:
    """Payment failed → mark as past_due."""
    customer_id = data.get("customer")
    if not customer_id:
        return

    await db.execute(
        update(User)
        .where(User.stripe_customer_id == customer_id)
        .values(subscription_status="past_due")
    )
    await db.commit()
    logger.warning("Payment failed for customer %s", customer_id)


# ── Helpers ──────────────────────────────────────────────────

def _extract_price_id(subscription_data: dict) -> Optional[str]:
    """Pull the first price ID from a subscription object."""
    items = subscription_data.get("items", {}).get("data", [])
    if items:
        return items[0].get("price", {}).get("id")
    return None


async def _get_plan_limits(plan_name: str, db: AsyncSession) -> dict:
    """Look up plan limits from the subscription_plans table."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)
    )
    plan = result.scalar_one_or_none()
    if plan:
        return {
            "monthly_task_limit": plan.monthly_task_limit or 100,
            "agent_limit": plan.agent_limit,
            "workflow_limit": plan.workflow_limit,
            "knowledge_items_limit": plan.knowledge_items_limit,
        }
    return {"monthly_task_limit": 100}
