"""Shared PostHog client instance.

Initialized in app.main lifespan; imported by route modules so they can
capture events without a circular-import through main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from posthog import Posthog

_client: "Posthog | None" = None


def get_posthog() -> "Posthog | None":
    """Return the shared PostHog client, or None when analytics is disabled."""
    return _client


def _set_posthog(client: "Posthog | None") -> None:
    """Called once by the lifespan handler on startup."""
    global _client
    _client = client
