"""
Founder OS — MCP Tool Servers (In-Process)
=============================================
In-process MCP tool providers that wrap integrations into the standard
ToolProvider interface. This gives agents access to external services
(Google Calendar, etc.) through the same MCP-compatible interface used
for external tool servers.

Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │                      ToolRegistry                            │
  │  ┌──────────────┐  ┌───────────────────┐  ┌──────────────┐ │
  │  │ LocalTools    │  │ MCPCalendarProv   │  │ MCPStdioClient│ │
  │  │ (@tool deco)  │  │ (in-process MCP)  │  │ (external)   │ │
  │  └──────┬───────┘  └───────┬───────────┘  └──────┬───────┘ │
  │         └──────────────────┼──────────────────────┘         │
  │                      call_tool(name, args)                   │
  └─────────────────────────────────────────────────────────────┘

Why in-process?
  - No subprocess overhead  — zero startup latency
  - Same asyncio loop       — native async/await, no IPC
  - Same JSON-RPC contract  — tools are MCP-compatible
  - Easily swappable        — can be replaced with external MCP
                               servers later (just change config)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agents.llm import ToolSchema
from app.agents.tool_protocol import ToolProvider, ToolResult

logger = logging.getLogger(__name__)


# ============================================================================
# Google Calendar MCP Provider
# ============================================================================

class MCPGoogleCalendarProvider(ToolProvider):
    """
    MCP-compatible tool provider for Google Calendar.

    Wraps the functions in ``calendar_integration.py`` and presents them
    as MCP tools with standard list_tools() / call_tool() contract.

    The provider needs a user_id + Google credentials to call the
    Calendar API. These are injected at construction time (per-request).
    """

    provider_name = "mcp:google-calendar"

    def __init__(
        self,
        user_id: str,
        client_id: str,
        client_secret: str,
        timezone_str: str = "Asia/Kolkata",
        calendar_id: str = "primary",
    ) -> None:
        self._user_id = user_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._timezone = timezone_str
        self._calendar_id = calendar_id

    # ── Tool schemas (MCP tools/list equivalent) ────────────────────

    _TOOL_SCHEMAS = [
        ToolSchema(
            name="gcal_list_events",
            description=(
                "List upcoming events from the user's Google Calendar. "
                "Returns event titles, times, and IDs. "
                "Use this to check existing schedule before creating new events."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default: 20)",
                        "default": 20,
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Optional ISO datetime to start from (default: now)",
                    },
                },
                "required": [],
            },
        ),
        ToolSchema(
            name="gcal_create_event",
            description=(
                "Create a new event on Google Calendar with specific start and end times. "
                "Use ISO datetime format for start and end (e.g. '2026-03-06T14:00:00'). "
                "Returns the created event ID and calendar link."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Start time in ISO format, e.g. '2026-03-06T14:00:00'",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "End time in ISO format, e.g. '2026-03-06T15:00:00'",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description",
                        "default": "",
                    },
                },
                "required": ["summary", "start_datetime", "end_datetime"],
            },
        ),
        ToolSchema(
            name="gcal_create_all_day_event",
            description=(
                "Create an all-day event on Google Calendar. "
                "Use ISO date format (e.g. '2026-03-06')."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "Date in ISO format, e.g. '2026-03-06'",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description",
                        "default": "",
                    },
                },
                "required": ["summary", "event_date"],
            },
        ),
        ToolSchema(
            name="gcal_update_event",
            description=(
                "Update an existing Google Calendar event. "
                "Pass the event_id and any fields to change."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The Google Calendar event ID to update",
                    },
                    "summary": {
                        "type": "string",
                        "description": "New event title",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "New start time (ISO format)",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "New end time (ISO format)",
                    },
                },
                "required": ["event_id"],
            },
        ),
        ToolSchema(
            name="gcal_delete_event",
            description="Delete a Google Calendar event by its event ID.",
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The Google Calendar event ID to delete",
                    },
                },
                "required": ["event_id"],
            },
        ),
        ToolSchema(
            name="gcal_get_event",
            description="Get details of a specific Google Calendar event by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The Google Calendar event ID",
                    },
                },
                "required": ["event_id"],
            },
        ),
        ToolSchema(
            name="gcal_push_weekly_plan",
            description=(
                "Push a full weekly plan to Google Calendar. "
                "Creates calendar events for every task in the plan. "
                "Returns summary of events created/failed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "plan_json": {
                        "description": (
                            "The weekly plan as a JSON string OR object. Must include "
                            "'daily_schedule' mapping day names (monday, tuesday, etc.) "
                            "to objects with a 'tasks' array. Each task needs: "
                            "'title' (string), 'start_time' (HH:MM), 'end_time' (HH:MM), "
                            "and optionally 'description', 'owner_agent', 'priority', 'est_hours'."
                        ),
                    },
                },
                "required": ["plan_json"],
            },
        ),
        ToolSchema(
            name="gcal_smart_delete",
            description=(
                "Smart bulk-delete of calendar events. "
                "By default (ai_only=true) only deletes AI-generated events "
                "(with [PLANNER], [OPS], etc. tags or 'Founder OS' markers). "
                "Set ai_only=false to delete ANY events matching the keyword "
                "and time range. Supports filtering by agent tag, keyword, or "
                "deleting all matched events. Use dry_run=true to preview first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": (
                            "Start of time range in ISO format (default: now). "
                            "Example: '2026-03-06T00:00:00'"
                        ),
                    },
                    "time_max": {
                        "type": "string",
                        "description": (
                            "End of time range in ISO format (default: 7 days from now). "
                            "Example: '2026-03-13T23:59:59'"
                        ),
                    },
                    "agent_filter": {
                        "type": "string",
                        "description": (
                            "Only delete events from a specific agent. "
                            "Values: PLANNER, OPS, CONTENT, RESEARCH, PRODUCT, SUPPORT. "
                            "Leave empty to match ALL Founder OS events."
                        ),
                    },
                    "keyword": {
                        "type": "string",
                        "description": (
                            "Optional keyword to match in event title. "
                            "Only events whose summary contains this keyword "
                            "(case-insensitive) will be deleted."
                        ),
                    },
                    "ai_only": {
                        "type": "boolean",
                        "description": (
                            "If true (default), only delete AI-generated / Founder OS events. "
                            "If false, delete ANY events matching the keyword and time range "
                            "(useful for deleting user-created events by title keyword)."
                        ),
                        "default": True,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": (
                            "If true, list the events that WOULD be deleted "
                            "without actually deleting them. Default: false."
                        ),
                        "default": False,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max events to scan (default: 100)",
                        "default": 100,
                    },
                },
                "required": [],
            },
        ),
    ]

    async def list_tools(self) -> list[ToolSchema]:
        return list(self._TOOL_SCHEMAS)

    # ── Argument coercion (LLMs sometimes stringify types) ──────────

    def _coerce_arguments(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Coerce string booleans/ints to native types based on the tool schema."""
        schema = next((s for s in self._TOOL_SCHEMAS if s.name == tool_name), None)
        if not schema:
            return args
        props = schema.parameters.get("properties", {})
        coerced = dict(args)
        for key, val in coerced.items():
            if key not in props or not isinstance(val, str):
                continue
            expected = props[key].get("type")
            if expected == "boolean":
                coerced[key] = val.lower() in ("true", "1", "yes")
            elif expected == "integer":
                try:
                    coerced[key] = int(val)
                except ValueError:
                    pass
        return coerced

    # ── Tool execution (MCP tools/call equivalent) ──────────────────

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        start = time.monotonic()
        handler = self._HANDLERS.get(name)
        if handler is None:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({
                    "error": f"Unknown calendar tool: {name}",
                    "available": [s.name for s in self._TOOL_SCHEMAS],
                }),
                is_error=True,
            )

        # Coerce arguments to match schema types (LLMs sometimes send
        # "true" instead of true, or "20" instead of 20)
        arguments = self._coerce_arguments(name, arguments)

        try:
            result = await handler(self, **arguments)
            duration = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps(result, default=str),
                is_error=False,
                duration_ms=duration,
                metadata={"provider": self.provider_name, "tool": name},
            )
        except Exception as exc:
            from app.integrations.calendar_integration import CalendarAuthExpired
            duration = (time.monotonic() - start) * 1000
            if isinstance(exc, CalendarAuthExpired):
                logger.warning("Calendar auth expired for user %s", self._user_id)
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=json.dumps({
                        "error": "calendar_auth_expired",
                        "message": str(exc),
                        "action_required": "reconnect_calendar",
                    }),
                    is_error=True,
                    duration_ms=duration,
                )
            logger.exception("MCP calendar tool '%s' failed", name)
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
                duration_ms=duration,
            )

    async def health_check(self) -> bool:
        """Check if we have valid tokens for the user."""
        from app.integrations.calendar_integration import get_tokens
        tokens = get_tokens(self._user_id)
        return tokens is not None

    # ── Handler implementations ─────────────────────────────────────

    async def _list_events(
        self, max_results: int = 20, time_min: str | None = None, **_kw: Any,
    ) -> list[dict[str, Any]]:
        from app.integrations.calendar_integration import list_upcoming_events
        events = await list_upcoming_events(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            calendar_id=self._calendar_id,
            max_results=max_results,
            time_min=time_min,
        )
        # Return compact format to reduce LLM token usage
        return [
            {
                "event_id": e.get("event_id"),
                "summary": e.get("summary"),
                "start": e.get("start"),
                "end": e.get("end"),
                "ai_generated": e.get("ai_generated", False),
            }
            for e in events
        ]

    async def _create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import create_single_event
        return await create_single_event(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            summary=summary,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            timezone_str=self._timezone,
            calendar_id=self._calendar_id,
            description=description,
        )

    async def _create_all_day_event(
        self,
        summary: str,
        event_date: str,
        description: str = "",
        **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import create_all_day_event
        return await create_all_day_event(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            summary=summary,
            event_date=event_date,
            timezone_str=self._timezone,
            calendar_id=self._calendar_id,
            description=description,
        )

    async def _update_event(
        self,
        event_id: str,
        summary: str | None = None,
        description: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import update_event
        updates: dict[str, Any] = {}
        if summary is not None:
            updates["summary"] = summary
        if description is not None:
            updates["description"] = description
        if start_datetime is not None:
            updates["start_datetime"] = start_datetime
        if end_datetime is not None:
            updates["end_datetime"] = end_datetime
        return await update_event(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            event_id=event_id,
            updates=updates,
            timezone_str=self._timezone,
            calendar_id=self._calendar_id,
        )

    async def _delete_event(
        self, event_id: str, **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import delete_event
        deleted = await delete_event(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            event_id=event_id,
            calendar_id=self._calendar_id,
        )
        return {"event_id": event_id, "deleted": deleted}

    async def _get_event(
        self, event_id: str, **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import get_event
        return await get_event(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            event_id=event_id,
            calendar_id=self._calendar_id,
        )

    @staticmethod
    def _normalize_plan_data(data: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize LLM-generated plan data into valid WeeklyPlan shape.

        Handles common LLM quirks:
        - daily_schedule values as bare task lists instead of DaySchedule dicts
        - "task_title" / "task" field instead of "title"
        - Date-string keys ("2026-03-24") instead of day names ("monday")
        """
        ds = data.get("daily_schedule", {})
        if not isinstance(ds, dict):
            return data

        _day_names = {
            0: "monday", 1: "tuesday", 2: "wednesday",
            3: "thursday", 4: "friday", 5: "saturday", 6: "sunday",
        }
        for key, value in list(ds.items()):
            if isinstance(value, list):
                # Bare list of tasks → wrap into DaySchedule shape
                day_name = key
                try:
                    from datetime import date as _date
                    d = _date.fromisoformat(key)
                    day_name = _day_names.get(d.weekday(), key)
                except (ValueError, TypeError):
                    pass
                # Normalize task field names
                tasks = []
                for t in value:
                    if isinstance(t, dict):
                        if "task_title" in t and "title" not in t:
                            t["title"] = t.pop("task_title")
                        elif "task" in t and "title" not in t:
                            t["title"] = t.pop("task")
                    tasks.append(t)
                ds[key] = {"day": day_name, "tasks": tasks}
        return data

    async def _push_weekly_plan(
        self, plan_json: str | dict = "", **_kw: Any,
    ) -> dict[str, Any]:
        from app.integrations.calendar_integration import push_plan_to_gcal
        from app.agents.planner_models import WeeklyPlan

        # Accept both a JSON string and a pre-parsed dict/object
        # (LLMs sometimes pass the object directly instead of a string)
        if isinstance(plan_json, dict):
            data = plan_json
        elif isinstance(plan_json, str) and plan_json.strip():
            data = json.loads(plan_json)
        else:
            return {"status": "error", "events_created": 0,
                    "error": "Empty plan_json provided"}

        data = self._normalize_plan_data(data)

        plan = WeeklyPlan.model_validate(data)
        plan.ensure_daily_schedule()

        return await push_plan_to_gcal(
            plan=plan,
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            calendar_id=self._calendar_id,
            timezone_str=self._timezone,
        )

    # ── Smart Delete — bulk delete AI-generated events ──────────────

    _AI_AGENT_TAGS = ("PLANNER", "OPS", "CONTENT", "RESEARCH", "PRODUCT", "SUPPORT")
    _AI_MARKERS = ("Founder OS", "Generated by Founder OS", "Created by Founder OS")

    @staticmethod
    def _is_ai_event(event: dict[str, Any]) -> bool:
        """Return True if the event was created by Founder OS."""
        summary = event.get("summary", "")
        desc = event.get("description", "") or ""
        # Check summary prefix tags
        for tag in MCPGoogleCalendarProvider._AI_AGENT_TAGS:
            if summary.startswith(f"[{tag}]"):
                return True
        # Check description markers
        for marker in MCPGoogleCalendarProvider._AI_MARKERS:
            if marker in desc:
                return True
        return event.get("ai_generated", False)

    @staticmethod
    def _get_agent_tag(summary: str) -> str | None:
        """Extract agent tag from summary like '[PLANNER] ...' → 'PLANNER'."""
        for tag in MCPGoogleCalendarProvider._AI_AGENT_TAGS:
            if summary.startswith(f"[{tag}]"):
                return tag
        return None

    async def _smart_delete(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        agent_filter: str | None = None,
        keyword: str | None = None,
        ai_only: bool = True,
        dry_run: bool = False,
        max_results: int = 100,
        **_kw: Any,
    ) -> dict[str, Any]:
        """Bulk-delete calendar events (AI-generated or any matching keyword)."""
        from app.integrations.calendar_integration import (
            list_upcoming_events,
            delete_event,
        )

        # 1. Fetch events in range
        all_events = await list_upcoming_events(
            user_id=self._user_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            calendar_id=self._calendar_id,
            max_results=max_results,
            time_min=time_min,
        )

        # 2. Filter: AI-generated only, or ALL events if ai_only=False
        if ai_only:
            matched_events = [e for e in all_events if self._is_ai_event(e)]
        else:
            matched_events = list(all_events)

        # 3. Apply agent filter (e.g. only PLANNER events)
        if agent_filter:
            tag = agent_filter.strip().upper()
            matched_events = [
                e for e in matched_events
                if self._get_agent_tag(e.get("summary", "")) == tag
            ]

        # 4. Apply keyword filter
        if keyword:
            kw_lower = keyword.lower()
            matched_events = [
                e for e in matched_events
                if kw_lower in e.get("summary", "").lower()
                or kw_lower in (e.get("description", "") or "").lower()
            ]

        # 5. Apply time_max filter (list_upcoming_events doesn't take time_max)
        if time_max:
            from datetime import datetime, timezone
            try:
                t_max = datetime.fromisoformat(time_max.replace("Z", "+00:00"))
                filtered = []
                for e in matched_events:
                    start_str = e.get("start", "")
                    if start_str:
                        try:
                            t = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                            if t <= t_max:
                                filtered.append(e)
                        except (ValueError, TypeError):
                            filtered.append(e)  # keep if can't parse
                    else:
                        filtered.append(e)
                matched_events = filtered
            except (ValueError, TypeError):
                pass  # ignore bad time_max, delete all matched

        # 6. Dry run — preview only
        if dry_run:
            return {
                "dry_run": True,
                "total_scanned": len(all_events),
                "events_found": len(matched_events),
                "ai_only_filter": ai_only,
                "events_to_delete": [
                    {
                        "event_id": e.get("event_id"),
                        "summary": e.get("summary"),
                        "start": e.get("start"),
                        "ai_generated": e.get("ai_generated", False),
                        "agent_tag": self._get_agent_tag(e.get("summary", "")),
                    }
                    for e in matched_events
                ],
            }

        # 7. Delete events
        deleted = []
        failed = []
        for event in matched_events:
            eid = event.get("event_id") or ""
            try:
                await delete_event(
                    user_id=self._user_id,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    event_id=eid,
                    calendar_id=self._calendar_id,
                )
                deleted.append({
                    "event_id": eid,
                    "summary": event.get("summary"),
                })
            except Exception as exc:
                failed.append({
                    "event_id": eid,
                    "summary": event.get("summary"),
                    "error": str(exc),
                })

        return {
            "dry_run": False,
            "total_scanned": len(all_events),
            "events_matched": len(matched_events),
            "deleted_count": len(deleted),
            "failed_count": len(failed),
            "deleted": deleted,
            "failed": failed,
        }

    # Handler dispatch table
    _HANDLERS: dict[str, Any] = {
        "gcal_list_events": _list_events,
        "gcal_create_event": _create_event,
        "gcal_create_all_day_event": _create_all_day_event,
        "gcal_update_event": _update_event,
        "gcal_delete_event": _delete_event,
        "gcal_get_event": _get_event,
        "gcal_push_weekly_plan": _push_weekly_plan,
        "gcal_smart_delete": _smart_delete,
    }


# ============================================================================
# MCP Tool Manager — config-driven provider aggregation
# ============================================================================

class MCPToolManager:
    """
    Central manager for all MCP tool providers (in-process + external).

    Reads configuration and creates the appropriate providers.
    The AgentRegistry uses this to inject MCP providers into each agent's
    ToolRegistry alongside the local tools.

    Usage:
        manager = MCPToolManager(settings)
        providers = await manager.get_providers(user_id="default-user")
        for p in providers:
            tool_registry.add_provider(p)
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._external_providers: list[ToolProvider] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Start any configured external MCP servers."""
        if self._initialized:
            return

        # Load external MCP server configs (future: from DB or config file)
        mcp_configs = getattr(self._settings, "MCP_SERVERS", [])
        if mcp_configs:
            from app.agents.mcp_adapter import MCPServerConfig, create_mcp_client
            for cfg_dict in mcp_configs:
                cfg = MCPServerConfig(**cfg_dict)
                client = create_mcp_client(cfg)
                self._external_providers.append(client)
                logger.info("Registered external MCP server: %s (%s)", cfg.name, cfg.transport)

        self._initialized = True
        logger.info(
            "MCPToolManager initialized — %d external servers",
            len(self._external_providers),
        )

    async def get_providers(
        self,
        user_id: str,
        *,
        include_calendar: bool = True,
        include_external: bool = True,
    ) -> list[ToolProvider]:
        """
        Build the list of MCP providers for a given user.

        Args:
            user_id: The user requesting tools (needed for per-user auth tokens)
            include_calendar: Include Google Calendar tools (if connected)
            include_external: Include external MCP server tools
        """
        await self.initialize()
        providers: list[ToolProvider] = []

        # Google Calendar (in-process MCP provider)
        if include_calendar:
            try:
                from app.user_store import get_user
                user = get_user(user_id)
                if user and user.gcal_connected:
                    providers.append(MCPGoogleCalendarProvider(
                        user_id=user_id,
                        client_id=self._settings.GOOGLE_CLIENT_ID,
                        client_secret=self._settings.GOOGLE_CLIENT_SECRET,
                        timezone_str=user.timezone or "Asia/Kolkata",
                        calendar_id=user.calendar_id or "primary",
                    ))
                    logger.debug("Added Google Calendar MCP provider for user %s", user_id)
            except Exception as exc:
                logger.warning("Failed to create calendar MCP provider: %s", exc)

        # External MCP servers (shared across all users)
        if include_external:
            providers.extend(self._external_providers)

        return providers

    async def close(self) -> None:
        """Shut down all external MCP connections."""
        for provider in self._external_providers:
            if hasattr(provider, "close"):
                await provider.close()  # type: ignore[attr-defined]


# ============================================================================
# Convenience: get tool names for agents
# ============================================================================

CALENDAR_TOOL_NAMES = [s.name for s in MCPGoogleCalendarProvider._TOOL_SCHEMAS]
"""Names of all Google Calendar MCP tools — use in agent default_tools."""
