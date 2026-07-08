"""Integration adapter framework (ADR-010).

Every external tool (Google Calendar, Obsidian, Notion, Paperclip, ...) plugs
into Founder OS through exactly one IntegrationAdapter. Adapters carry NO
business logic — they translate between the external tool and Founder OS
types. Reconciliation into canonical company state is the State Engine's job
(ADR-009, Phase 1); adapter output is provenance-tagged "observed" for it.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Capability(enum.Flag):
    OBSERVE = enum.auto()  # pull external events/state into Founder OS
    SYNC = enum.auto()     # push canonical state out to the tool
    HEALTH = enum.auto()   # report connectivity/config status


@dataclass
class HealthStatus:
    ok: bool
    detail: str = ""


@dataclass
class ObservedEvent:
    """One event/state snapshot pulled from an external tool."""

    source: str            # adapter name, e.g. "google_calendar"
    kind: str              # adapter-defined event kind, e.g. "event.upcoming"
    external_id: str       # stable id in the source system (dedup key)
    payload: dict[str, Any]
    observed_at: datetime
    provenance: str = "observed"  # ADR-009 feed 1; adapters never emit other feeds


@dataclass
class SyncResult:
    ok: bool
    pushed: int = 0
    errors: list[str] = field(default_factory=list)
    # D5 (Phase 2 arch §7): outbound adapters return cursor-ish state (e.g. the
    # Notion managed-page ledger) here; the SERVICE persists it — adapters never
    # touch state tables (ADR-010).
    data: dict[str, Any] = field(default_factory=dict)


class IntegrationAdapter(ABC):
    """Base class for all tool integrations. Multi-tenant: per-call user_id."""

    name: str = ""
    capabilities: Capability = Capability.HEALTH

    @abstractmethod
    async def configure(self, settings: dict[str, Any]) -> None:
        """Receive credentials/config. Secrets come from env/DB, never literals."""

    @abstractmethod
    async def health(self) -> HealthStatus:
        """Cheap connectivity/config check; must not mutate anything."""

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        raise NotImplementedError(f"{self.name} does not support OBSERVE")

    async def sync(self, user_id: str, changes: list[dict[str, Any]]) -> SyncResult:
        raise NotImplementedError(f"{self.name} does not support SYNC")
