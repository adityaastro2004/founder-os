#!/usr/bin/env python3
"""
Founder OS — Planner Onboarding Bridge Tests
=============================================
Regression tests for the onboarding → planner profile bridge.

Bug: the dashboard onboarding wizard saves a FounderProfile via
POST /api/onboarding/profile, but the planner only read its own
planner_users row that nothing in the UI ever created — so every
founder saw a dead-end "Setup Required / Call POST /api/planner/onboard"
card on the Planner page. GET /api/planner/status now provisions the
planner profile from the founder's onboarding answers.

Run:
  python -m pytest test_planner_onboarding_bridge.py -v
"""

from __future__ import annotations

from decimal import Decimal

from app.api.planner_routes import _planner_profile_from_founder
from app.models import FounderProfile


def _founder(**overrides) -> FounderProfile:
    """A FounderProfile as the onboarding wizard would create it."""
    fields = {
        "business_name": "Acme Inc.",
        "business_type": "saas",
        "business_stage": "growth",
        "industry": "technology",
        "target_audience": "SaaS founders with $1K-$50K MRR",
        "primary_goal": "grow_revenue",
        "current_mrr": Decimal("1500.00"),
        "current_users": 42,
        "team_size": 3,
        "working_hours": {"start": "08:30", "end": "17:00"},
    }
    fields.update(overrides)
    return FounderProfile(**fields)


def test_maps_all_onboarding_fields_to_planner_profile():
    profile = _planner_profile_from_founder(_founder(), "user_clerk123", name="Aditya")

    assert profile.user_id == "user_clerk123"
    assert profile.name == "Aditya"
    assert profile.business_name == "Acme Inc."
    assert profile.business_type == "saas"
    assert profile.business_stage == "growth"
    assert profile.industry == "technology"
    assert profile.target_audience == "SaaS founders with $1K-$50K MRR"
    assert profile.primary_goal == "grow_revenue"
    assert profile.current_mrr == 1500.0
    assert profile.current_users == 42
    assert profile.team_size == 3
    assert profile.preferred_work_hours == "08:30-17:00"
    # Google Calendar still needs its own connect step
    assert profile.gcal_connected is False


def test_handles_missing_optional_fields_with_safe_defaults():
    founder = _founder(
        target_audience=None,
        primary_goal=None,
        current_mrr=None,
        current_users=None,
        team_size=None,
        working_hours=None,
    )

    profile = _planner_profile_from_founder(founder, "user_clerk123")

    assert profile.name == ""
    assert profile.target_audience == ""
    assert profile.primary_goal == ""
    assert profile.current_mrr == 0.0
    assert profile.current_users == 0
    assert profile.team_size == 1
    assert profile.preferred_work_hours == "09:00-18:00"


def test_handles_partial_working_hours():
    founder = _founder(working_hours={"start": "10:00"})

    profile = _planner_profile_from_founder(founder, "user_clerk123")

    assert profile.preferred_work_hours == "10:00-18:00"
