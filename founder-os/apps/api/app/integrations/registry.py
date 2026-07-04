"""Process-wide adapter registry (ADR-010).

Adapters are registered once at startup (app.main lifespan) and looked up by
name — callers never import adapter modules ad-hoc.
"""
from __future__ import annotations

from app.integrations.base import IntegrationAdapter

_REGISTRY: dict[str, IntegrationAdapter] = {}


def register(adapter: IntegrationAdapter) -> IntegrationAdapter:
    if not adapter.name:
        raise ValueError("adapter.name must be a non-empty string")
    if adapter.name in _REGISTRY:
        raise ValueError(f"integration adapter already registered: {adapter.name!r}")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> IntegrationAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"no integration adapter named {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def all_adapters() -> dict[str, IntegrationAdapter]:
    return dict(_REGISTRY)


def _reset_for_tests() -> None:
    _REGISTRY.clear()
