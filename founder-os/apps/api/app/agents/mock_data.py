"""
Founder OS — Mock Data Sources
================================
Realistic mock data for development and testing.

Provides factory functions that return sample business metrics,
founder profiles, task lists, and writing styles. An in-memory
store (`_manual_context`) can be overwritten at runtime via the
`/api/test/weekly-context` endpoint so founders can inject their
own real data for testing.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any


# ============================================================================
# In-memory manual context store (overridden via API)
# ============================================================================

_manual_context: dict[str, Any] = {}


def set_manual_context(data: dict[str, Any]) -> None:
    """Replace the manual context store with new data."""
    global _manual_context
    _manual_context = data


def get_manual_context() -> dict[str, Any]:
    """Return the current manual context (empty dict if none set)."""
    return _manual_context


def clear_manual_context() -> None:
    """Reset the manual context store."""
    global _manual_context
    _manual_context = {}


# ============================================================================
# Mock Business Metrics
# ============================================================================

def get_mock_metrics(metric_type: str = "", days: int = 30) -> dict[str, Any]:
    """
    Return realistic SaaS business metrics.

    If manual context has been submitted, use those values as the
    baseline. Otherwise, use sensible defaults.
    """
    ctx = _manual_context
    base_mrr = ctx.get("mrr", 8500)
    mrr_growth = ctx.get("mrr_growth_pct", 12)
    base_users = ctx.get("active_users", 215)
    base_traffic = ctx.get("monthly_traffic", 4200)

    now = datetime.now(timezone.utc)

    # Build daily data points
    daily_data = []
    for i in range(min(days, 30), 0, -1):
        date = now - timedelta(days=i)
        jitter = random.uniform(-0.02, 0.02)
        daily_mrr = round(base_mrr * (1 + jitter), 2)
        daily_users = base_users + random.randint(-5, 8)
        daily_traffic = base_traffic // 30 + random.randint(-20, 30)
        daily_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "mrr": daily_mrr,
            "active_users": max(1, daily_users),
            "page_views": max(0, daily_traffic),
            "signups": random.randint(2, 12),
            "churn": random.randint(0, 3),
            "support_tickets": random.randint(1, 8),
            "conversion_rate_pct": round(random.uniform(2.5, 5.5), 1),
        })

    # Summary
    summary = {
        "period": f"last_{days}_days",
        "current_mrr": base_mrr,
        "mrr_growth_pct": mrr_growth,
        "total_active_users": base_users,
        "avg_daily_signups": round(sum(d["signups"] for d in daily_data) / len(daily_data), 1),
        "avg_daily_churn": round(sum(d["churn"] for d in daily_data) / len(daily_data), 1),
        "total_support_tickets": sum(d["support_tickets"] for d in daily_data),
        "avg_conversion_rate_pct": round(
            sum(d["conversion_rate_pct"] for d in daily_data) / len(daily_data), 1
        ),
        "anomalies": [],
    }

    # Flag anomalies
    high_churn_days = [d for d in daily_data if d["churn"] >= 3]
    if high_churn_days:
        summary["anomalies"].append(
            f"Elevated churn on {len(high_churn_days)} day(s)"
        )

    if metric_type:
        # Filter to a specific metric if requested
        filtered = [{
            "date": d["date"],
            metric_type: d.get(metric_type, "N/A"),
        } for d in daily_data]
        return {"metric_type": metric_type, "summary": summary, "data": filtered}

    return {"summary": summary, "data": daily_data}


# ============================================================================
# Mock Founder Profile
# ============================================================================

def get_mock_founder_profile() -> dict[str, Any]:
    """Return the founder's profile — uses manual context if available."""
    ctx = _manual_context
    return {
        "business_name": ctx.get("business_name", "FounderCo"),
        "business_type": ctx.get("business_type", "B2B SaaS"),
        "business_stage": ctx.get("business_stage", "seed"),
        "industry": ctx.get("industry", "Developer Tools"),
        "target_audience": ctx.get("target_audience", "Solo developers and small teams"),
        "primary_goal": ctx.get("primary_goal", "Reach $10k MRR"),
        "current_mrr": ctx.get("mrr", 8500),
        "current_users": ctx.get("active_users", 215),
        "team_size": ctx.get("team_size", 1),
        "goals_this_week": ctx.get("goals_this_week", [
            "Ship the new onboarding flow",
            "Write 2 blog posts",
            "Close 3 sales calls",
        ]),
        "blockers": ctx.get("blockers", []),
        "completed_last_week": ctx.get("completed_last_week", [
            "Launched pricing page",
            "Fixed authentication bug",
            "Sent weekly newsletter",
        ]),
    }


# ============================================================================
# Mock Tasks
# ============================================================================

_MOCK_TASKS = [
    {"id": "t-001", "title": "Ship new onboarding flow", "status": "in_progress",
     "priority": 1, "agent": "product", "est_hours": 6},
    {"id": "t-002", "title": "Write blog post: Why founders need an OS", "status": "pending",
     "priority": 3, "agent": "content", "est_hours": 2},
    {"id": "t-003", "title": "Analyse competitor pricing pages", "status": "completed",
     "priority": 4, "agent": "research", "est_hours": 1.5},
    {"id": "t-004", "title": "Set up Stripe webhook for churn alerts", "status": "completed",
     "priority": 2, "agent": "ops", "est_hours": 1},
    {"id": "t-005", "title": "Draft welcome email sequence", "status": "pending",
     "priority": 5, "agent": "content", "est_hours": 2},
    {"id": "t-006", "title": "Prepare sales call deck", "status": "in_progress",
     "priority": 2, "agent": "content", "est_hours": 1.5},
    {"id": "t-007", "title": "Review support ticket trends", "status": "completed",
     "priority": 6, "agent": "ops", "est_hours": 0.5},
    {"id": "t-008", "title": "Write changelog for v0.4 release", "status": "pending",
     "priority": 4, "agent": "product", "est_hours": 1},
]


def get_mock_tasks(
    status: str = "",
    agent_name: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return mock tasks, optionally filtered by status or agent."""
    tasks = list(_MOCK_TASKS)

    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if agent_name:
        tasks = [t for t in tasks if t["agent"] == agent_name]

    tasks = tasks[:limit]

    completed = sum(1 for t in _MOCK_TASKS if t["status"] == "completed")
    total = len(_MOCK_TASKS)

    return {
        "tasks": tasks,
        "total": len(tasks),
        "completion_rate_pct": round(completed / total * 100, 1) if total else 0,
    }


# ============================================================================
# Mock Writing Style
# ============================================================================

def get_mock_writing_style() -> dict[str, Any]:
    """Return the founder's writing voice preferences."""
    return {
        "voice": "Conversational but knowledgeable. Like explaining something "
                 "complex to a smart friend over coffee.",
        "tone": "Confident, approachable, slightly informal",
        "avoid": [
            "Corporate jargon",
            "Passive voice",
            "Clickbait headlines",
        ],
        "preferred_formats": [
            "Short paragraphs (2-3 sentences)",
            "Bullet points for lists",
            "Bold key takeaways",
        ],
        "examples": [
            "We shipped the new dashboard last week. Here's what we learned.",
            "Three things I wish I knew before building my first SaaS.",
        ],
    }


# ============================================================================
# Mock Integrations
# ============================================================================

def get_mock_integrations() -> dict[str, Any]:
    """Return a list of connected (mock) integrations."""
    return {
        "integrations": [
            {
                "name": "Stripe",
                "type": "payment",
                "status": "connected",
                "last_sync": "2026-02-28T09:00:00Z",
                "sync_status": "ok",
            },
            {
                "name": "Notion",
                "type": "project_management",
                "status": "connected",
                "last_sync": "2026-02-28T08:30:00Z",
                "sync_status": "ok",
            },
            {
                "name": "Google Analytics",
                "type": "analytics",
                "status": "connected",
                "last_sync": "2026-02-28T07:00:00Z",
                "sync_status": "ok",
            },
            {
                "name": "Slack",
                "type": "communication",
                "status": "disconnected",
                "last_sync": None,
                "sync_status": "needs_reauth",
            },
        ]
    }
