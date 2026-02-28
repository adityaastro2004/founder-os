"""
Founder OS — Redis Event Bus
==============================
Lightweight Redis pub/sub event bus for inter-agent async communication.

Events flow through named channels. Agents and services can:
  - **publish** events (fire-and-forget)
  - **subscribe** to event types with async handlers
  - **wait_for** a specific event (one-shot, with timeout)

Uses the existing Redis connection from ``app.redis``.

Event types:
  agent.started / agent.completed / agent.failed
  task.created / task.completed
  tool.called / tool.result
  delegation.requested / delegation.completed
  workflow.step_completed
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Channel prefix so we don't collide with other Redis usage
_CHANNEL_PREFIX = "fos:events:"


# ============================================================================
# Event data type
# ============================================================================

@dataclass
class Event:
    """A typed event flowing through the bus."""
    type: str                              # e.g. "agent.completed"
    agent: str = ""                        # source agent name
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""               # trace across delegations

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "agent": self.agent,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }, default=str)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Event":
        d = json.loads(raw)
        return cls(
            type=d["type"],
            agent=d.get("agent", ""),
            data=d.get("data", {}),
            event_id=d.get("event_id", ""),
            timestamp=d.get("timestamp", 0),
            correlation_id=d.get("correlation_id", ""),
        )


# Type alias for event handlers
EventHandler = Callable[[Event], Awaitable[None]]


# ============================================================================
# Event Bus
# ============================================================================

class EventBus:
    """
    Redis pub/sub event bus for the Founder OS agent system.

    Usage::

        bus = EventBus(redis_client)
        await bus.start()

        # Subscribe
        async def on_agent_done(event: Event):
            print(f"Agent {event.agent} finished")

        bus.subscribe("agent.completed", on_agent_done)

        # Publish
        await bus.publish(Event(type="agent.completed", agent="planner", data={"result": "ok"}))

        # Cleanup
        await bus.stop()
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._pubsub: aioredis.client.PubSub | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False

    # -- Lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Start listening for events."""
        if self._running:
            return
        self._pubsub = self._redis.pubsub()
        self._running = True
        self._listener_task = asyncio.create_task(self._listen(), name="event-bus-listener")
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the listener and clean up."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            self._pubsub = None
        logger.info("Event bus stopped")

    # -- Publish ----------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        channel = f"{_CHANNEL_PREFIX}{event.type}"
        await self._redis.publish(channel, event.to_json())
        logger.debug("Published event: %s (id=%s)", event.type, event.event_id)

    # -- Subscribe --------------------------------------------------------

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
            # Subscribe to the Redis channel
            if self._pubsub and self._running:
                asyncio.create_task(
                    self._pubsub.subscribe(f"{_CHANNEL_PREFIX}{event_type}")
                )
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler | None = None) -> None:
        """Remove a handler (or all handlers) for an event type."""
        if event_type not in self._handlers:
            return
        if handler is None:
            del self._handlers[event_type]
        else:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    # -- One-shot wait ----------------------------------------------------

    async def wait_for(
        self,
        event_type: str,
        *,
        timeout: float = 30.0,
        predicate: Callable[[Event], bool] | None = None,
    ) -> Event | None:
        """
        Wait for a single event of the given type (with optional filter).
        Returns None on timeout.
        """
        future: asyncio.Future[Event] = asyncio.get_event_loop().create_future()

        async def _waiter(event: Event) -> None:
            if future.done():
                return
            if predicate and not predicate(event):
                return
            future.set_result(event)

        self.subscribe(event_type, _waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(event_type, _waiter)

    # -- Internal listener ------------------------------------------------

    async def _listen(self) -> None:
        """Background task that reads messages from Redis pub/sub."""
        if not self._pubsub:
            return

        # Subscribe to all known event types
        for event_type in list(self._handlers.keys()):
            await self._pubsub.subscribe(f"{_CHANNEL_PREFIX}{event_type}")

        # Also subscribe to a wildcard pattern for late-registered handlers
        await self._pubsub.psubscribe(f"{_CHANNEL_PREFIX}*")

        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                # Extract event type from channel
                channel = message.get("channel", b"").decode() if isinstance(
                    message.get("channel"), bytes
                ) else message.get("channel", "")

                raw_data = message.get("data")
                if not raw_data or isinstance(raw_data, int):
                    continue

                try:
                    event = Event.from_json(raw_data)
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Invalid event on channel %s", channel)
                    continue

                # Dispatch to handlers
                handlers = self._handlers.get(event.type, [])
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception:
                        logger.exception(
                            "Event handler failed for %s", event.type
                        )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Event bus listener error")
                await asyncio.sleep(1.0)

    # -- Utility ----------------------------------------------------------

    @property
    def subscribed_events(self) -> list[str]:
        return list(self._handlers.keys())

    @property
    def is_running(self) -> bool:
        return self._running
