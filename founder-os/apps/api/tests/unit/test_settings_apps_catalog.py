"""The settings apps catalog must not duplicate State Engine sources.

Notion and Obsidian connect through /api/state/sources (the dashboard's
Company State Sources section). Listing them in SUPPORTED_APPS as well
rendered a second card on the same page — stuck on "Coming soon" before
connecting (connect_url None) and a status-only "Connected" card after
(the state flow upserts an integrations row) — contradicting the real
source status shown just above it.
"""
from typing import get_args

from app.api.settings_routes import SUPPORTED_APPS
from app.api.state_routes import SourceCreateRequest


def test_state_source_types_absent_from_apps_catalog():
    state_source_types = set(
        get_args(SourceCreateRequest.model_fields["type"].annotation)
    )
    assert state_source_types, "SourceCreateRequest.type Literal no longer resolves"

    catalog_keys = {app["key"] for app in SUPPORTED_APPS}
    overlap = state_source_types & catalog_keys
    assert not overlap, (
        f"{sorted(overlap)} connect via /api/state/sources; remove them from "
        "SUPPORTED_APPS so the apps grid doesn't show a second, contradictory "
        "status for the same connection."
    )


def test_catalog_entries_are_connectable_or_honestly_coming_soon():
    # Every catalog entry either has a real connect path or is shown as
    # "coming soon" by the dashboard; a None connect_url must therefore be
    # intentional, not a leftover for something that ships elsewhere.
    for app in SUPPORTED_APPS:
        assert app["key"], "catalog entry missing key"
        assert app["connect_url"] is None or app["connect_url"].startswith("/api/"), (
            f"{app['key']}: connect_url must be None (coming soon) or an API path"
        )
