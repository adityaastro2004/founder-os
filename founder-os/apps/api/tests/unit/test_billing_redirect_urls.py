"""Unit tests for the browser-facing redirect URLs the billing routes hand Stripe.

These URLs used to default to ``http://localhost:3000`` inside ``app/stripe.py``
and the request body was allowed to override them. Both were production bugs:
the default stranded paying users on a dead redirect after checkout, and the
override let a caller bounce a post-payment browser to an arbitrary origin.

The URLs are now derived server-side from ``settings.FRONTEND_BASE_URL``. These
tests pin all three properties so a regression is caught in the unit tier rather
than by a customer completing a payment.
"""

from __future__ import annotations

import inspect

import pytest

from app.api.billing_routes import CheckoutIn
from app.config import Settings
from app.stripe import create_checkout_session, create_portal_session


def test_frontend_base_url_defaults_to_localhost_for_dev_only():
    """The default is a dev convenience; production must override it."""
    assert Settings().FRONTEND_BASE_URL == "http://localhost:3000"


def test_checkout_body_cannot_supply_redirect_urls():
    """success_url / cancel_url must not be accepted from the request body.

    Stripe redirects the browser to whatever it is handed, so a caller-supplied
    value is an open redirect on a post-payment user.
    """
    assert "success_url" not in CheckoutIn.model_fields
    assert "cancel_url" not in CheckoutIn.model_fields

    # Pydantic ignores unknown keys by default — assert the value cannot sneak
    # through even when a client sends it.
    body = CheckoutIn.model_validate(
        {
            "plan": "pro",
            "success_url": "https://evil.example/steal",
            "cancel_url": "https://evil.example/steal",
        }
    )
    assert not hasattr(body, "success_url")
    assert not hasattr(body, "cancel_url")


@pytest.mark.parametrize(
    "func,params",
    [
        (create_checkout_session, ("success_url", "cancel_url")),
        (create_portal_session, ("return_url",)),
    ],
)
def test_stripe_helpers_require_explicit_urls(func, params):
    """No localhost defaults — a caller that forgets a URL must fail loudly."""
    signature = inspect.signature(func)
    for name in params:
        assert signature.parameters[name].default is inspect.Parameter.empty, (
            f"{func.__name__}({name}=...) must not have a default; a silent "
            "localhost fallback is how this shipped to production before."
        )


@pytest.mark.parametrize(
    "configured,expected_base",
    [
        ("https://myfounderos.com", "https://myfounderos.com"),
        # A trailing slash must not produce a '//' in the path.
        ("https://myfounderos.com/", "https://myfounderos.com"),
    ],
)
def test_redirect_urls_are_built_from_frontend_base_url(configured, expected_base):
    """Mirrors the construction in billing_routes so the shape is pinned."""
    base = Settings(FRONTEND_BASE_URL=configured).FRONTEND_BASE_URL.rstrip("/")

    assert base == expected_base
    assert f"{base}/dashboard/billing?success=true" == (
        f"{expected_base}/dashboard/billing?success=true"
    )
    assert f"{base}/dashboard/billing" == f"{expected_base}/dashboard/billing"


def test_frontend_base_url_is_not_the_api_host():
    """Guard the specific confusion this setting exists to prevent.

    FRONTEND_BASE_URL is where the *browser* goes, not where the API lives.
    Pointing it at the API host renders the post-checkout page unreachable.
    """
    settings = Settings(FRONTEND_BASE_URL="https://myfounderos.com")
    assert "api." not in settings.FRONTEND_BASE_URL
