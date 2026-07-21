"""FounderProfileCreate bounds — unbounded form ints used to overflow
Postgres INTEGER and surface as 500s (and as "[object Object]" 422s in the
old web error rendering)."""

import pytest
from pydantic import ValidationError

from app.api.onboarding_routes import FounderProfileCreate

BASE = {
    "business_name": "Acme",
    "business_type": "saas",
    "industry": "software",
    "business_stage": "mvp",
    "primary_goal": "growth",
}


def test_valid_payload_accepts_defaults():
    profile = FounderProfileCreate(**BASE)
    assert profile.team_size == 1
    assert profile.current_users == 0


def test_valid_payload_accepts_reasonable_metrics():
    profile = FounderProfileCreate(
        **BASE, team_size=12, current_mrr=25_000.5, current_users=4_300
    )
    assert profile.team_size == 12


@pytest.mark.parametrize(
    "field,value",
    [
        ("team_size", 10**24),
        ("team_size", 0),
        ("current_users", 3_000_000_000),  # > INT32 max
        ("current_users", -1),
        ("monthly_traffic", 10**12),
        ("current_mrr", 10**13),
        ("current_mrr", -5),
    ],
)
def test_out_of_range_numbers_rejected(field, value):
    with pytest.raises(ValidationError):
        FounderProfileCreate(**{**BASE, field: value})


def test_none_team_size_rejected():
    # JSON.stringify(Infinity) -> null: the exact payload huge form input produced
    with pytest.raises(ValidationError):
        FounderProfileCreate(**{**BASE, "team_size": None})
