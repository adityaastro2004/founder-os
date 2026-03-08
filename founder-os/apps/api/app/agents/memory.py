"""
Founder OS — Agent Memory System (v2)
=======================================
Four-layer memory architecture:

1. **ConversationMemory** — In-process message history for the current run.
   Keeps the rolling chat window that gets sent to the LLM.

2. **WorkingMemory** — Redis-backed scratch-pad for active task context.
   Persists across requests within a session. Auto-expires.

3. **LongTermMemory** — PostgreSQL + pgvector. Retrieves relevant knowledge
   items via cosine similarity on embeddings for RAG injection.

4. **SharedMemory** — Redis-backed cross-agent scratch-pad.
   Allows agents to share intermediate results with each other.
   Scoped to (user_id, session_id) — any agent can read/write.

``AgentMemory`` composes all four and exposes a single
``build_context(query)`` method that the BaseAgent calls before each LLM turn.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# 1. Conversation Memory (in-process)
# ============================================================================

@dataclass
class Message:
    role: str          # "user" | "assistant" | "tool"
    content: str
    name: str | None = None          # tool name when role == "tool"
    tool_use_id: str | None = None   # for tool_result pairing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationMemory:
    """Rolling message window for a single agent run / session."""

    def __init__(self, max_messages: int = 50) -> None:
        self._messages: list[Message] = []
        self._max = max_messages

    # -- mutate -----------------------------------------------------------

    def add(self, role: str, content: str, **kwargs: Any) -> None:
        self._messages.append(Message(role=role, content=content, **kwargs))
        # Trim oldest (but never the system prompt at index 0 if present)
        while len(self._messages) > self._max:
            self._messages.pop(1 if self._messages[0].role == "system" else 0)

    def add_user(self, content: str) -> None:
        self.add("user", content)

    def add_assistant(self, content: str) -> None:
        self.add("assistant", content)

    def add_tool_result(self, tool_use_id: str, content: str, name: str = "") -> None:
        self.add("user", content, name=name, tool_use_id=tool_use_id)

    # -- read -------------------------------------------------------------

    def to_anthropic_messages(self) -> list[dict[str, Any]]:
        """Format for the Anthropic messages API (excludes system prompt)."""
        msgs: list[dict[str, Any]] = []
        for m in self._messages:
            if m.role == "user" and m.tool_use_id:
                # Tool result
                msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_use_id,
                        "content": m.content,
                    }],
                })
            else:
                msgs.append({"role": m.role, "content": m.content})
        return msgs

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)


# ============================================================================
# 2. Working Memory (Redis)
# ============================================================================

class WorkingMemory:
    """
    Redis-backed scratch-pad scoped to (user_id, agent_name, session_id).

    Stores structured data (current plan, intermediate results) with TTL.
    """

    TTL_SECONDS = 3600 * 24  # 24 hours — survive a full workday

    def __init__(
        self,
        redis: aioredis.Redis,
        user_id: uuid.UUID,
        agent_name: str,
        session_id: str | None = None,
    ) -> None:
        self._redis = redis
        sid = session_id or "default"
        self._prefix = f"agent:wm:{user_id}:{agent_name}:{sid}"

    def _key(self, field: str) -> str:
        return f"{self._prefix}:{field}"

    async def set(self, field: str, value: Any, ttl: int | None = None) -> None:
        raw = json.dumps(value, default=str) if not isinstance(value, str) else value
        await self._redis.set(self._key(field), raw, ex=ttl or self.TTL_SECONDS)

    async def get(self, field: str) -> Any | None:
        raw = await self._redis.get(self._key(field))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def delete(self, field: str) -> None:
        await self._redis.delete(self._key(field))

    async def get_all(self) -> dict[str, Any]:
        """Return all working memory fields for this scope."""
        keys: list[str] = []
        async for key in self._redis.scan_iter(match=f"{self._prefix}:*"):
            keys.append(key)
        if not keys:
            return {}
        values = await self._redis.mget(keys)
        result: dict[str, Any] = {}
        for k, v in zip(keys, values):
            short_key = k.replace(f"{self._prefix}:", "", 1)
            if v is not None:
                try:
                    result[short_key] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[short_key] = v
        return result

    async def clear(self) -> None:
        keys: list[str] = []
        async for key in self._redis.scan_iter(match=f"{self._prefix}:*"):
            keys.append(key)
        if keys:
            await self._redis.delete(*keys)

    async def to_context_string(self) -> str:
        """Serialise working memory into a string suitable for the LLM."""
        data = await self.get_all()
        if not data:
            return ""
        parts = ["<working_memory>"]
        for k, v in data.items():
            formatted = json.dumps(v, indent=2, default=str) if not isinstance(v, str) else v
            parts.append(f"[{k}]\n{formatted}")
        parts.append("</working_memory>")
        return "\n".join(parts)


# ============================================================================
# 2b. Shared Memory (Redis — cross-agent)
# ============================================================================

class SharedMemory:
    """
    Redis-backed shared scratch-pad scoped to (user_id, session_id).
    Any agent can read/write — used for passing context between agents
    during multi-agent workflows (A2A delegation results, plans, etc.).
    """

    TTL_SECONDS = 3600 * 48  # 48 hours — persist across sessions

    def __init__(
        self,
        redis: aioredis.Redis,
        user_id: uuid.UUID,
        session_id: str | None = None,
    ) -> None:
        self._redis = redis
        sid = session_id or "default"
        self._prefix = f"agent:shared:{user_id}:{sid}"

    def _key(self, field: str) -> str:
        return f"{self._prefix}:{field}"

    async def set(self, field: str, value: Any, ttl: int | None = None) -> None:
        raw = json.dumps(value, default=str) if not isinstance(value, str) else value
        await self._redis.set(self._key(field), raw, ex=ttl or self.TTL_SECONDS)

    async def get(self, field: str) -> Any | None:
        raw = await self._redis.get(self._key(field))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def get_all(self) -> dict[str, Any]:
        keys: list[str] = []
        async for key in self._redis.scan_iter(match=f"{self._prefix}:*"):
            keys.append(key)
        if not keys:
            return {}
        values = await self._redis.mget(keys)
        result: dict[str, Any] = {}
        for k, v in zip(keys, values):
            short_key = k.replace(f"{self._prefix}:", "", 1)
            if v is not None:
                try:
                    result[short_key] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[short_key] = v
        return result

    async def delete(self, field: str) -> None:
        await self._redis.delete(self._key(field))

    async def to_context_string(self) -> str:
        data = await self.get_all()
        if not data:
            return ""
        parts = ["<shared_memory>"]
        for k, v in data.items():
            formatted = json.dumps(v, indent=2, default=str) if not isinstance(v, str) else v
            parts.append(f"[{k}]\n{formatted}")
        parts.append("</shared_memory>")
        return "\n".join(parts)


# ============================================================================
# 3. Long-Term Memory (PostgreSQL + pgvector)
# ============================================================================

@dataclass
class RetrievedKnowledge:
    id: uuid.UUID
    title: str | None
    content: str
    category: str | None
    similarity: float


class LongTermMemory:
    """
    Retrieves relevant knowledge items for the user via cosine similarity.

    Assumes ``knowledge_items.embedding`` is a pgvector ``vector(1536)`` column
    and that rows have been pre-embedded (embedding pipeline is separate).
    """

    def __init__(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        self._db = db
        self._user_id = user_id

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.70,
        category: str | None = None,
    ) -> list[RetrievedKnowledge]:
        """Retrieve top-k knowledge items by embedding similarity."""
        # pgvector cosine distance: 1 - (a <=> b) gives similarity
        cat_filter = "AND ki.category = :cat" if category else ""
        sql = text(f"""
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.category,
                1 - (ki.embedding <=> :emb::vector) AS similarity
            FROM knowledge_items ki
            WHERE ki.user_id = :uid
              AND ki.is_active = true
              AND ki.embedding IS NOT NULL
              {cat_filter}
            ORDER BY ki.embedding <=> :emb::vector
            LIMIT :lim
        """)

        params: dict[str, Any] = {
            "uid": self._user_id,
            "emb": str(query_embedding),
            "lim": limit,
        }
        if category:
            params["cat"] = category

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            RetrievedKnowledge(
                id=r.id,
                title=r.title,
                content=r.content,
                category=r.category,
                similarity=r.similarity,
            )
            for r in rows
            if r.similarity >= min_similarity
        ]

    async def to_context_string(
        self,
        query_embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.70,
    ) -> str:
        """Retrieve and format knowledge items for LLM context."""
        items = await self.search(query_embedding, limit, min_similarity)
        if not items:
            return ""
        parts = ["<knowledge_context>"]
        for item in items:
            parts.append(
                f"--- {item.title or 'Untitled'} (similarity: {item.similarity:.2f}) ---\n"
                f"{item.content}\n"
            )
        parts.append("</knowledge_context>")
        return "\n".join(parts)


# ============================================================================
# Composed Memory — single interface for BaseAgent
# ============================================================================

class AgentMemory:
    """
    Unified memory interface that composes:
    - conversation (in-process)
    - working (Redis — per-agent)
    - shared (Redis — cross-agent)
    - long_term (PostgreSQL + pgvector)
    - retriever (optional — full ContextRetriever with hybrid/MMR search)
    """

    def __init__(
        self,
        conversation: ConversationMemory,
        working: WorkingMemory,
        long_term: LongTermMemory,
        shared: SharedMemory | None = None,
        retriever: Any | None = None,
    ) -> None:
        self.conversation = conversation
        self.working = working
        self.long_term = long_term
        self.shared = shared
        self.retriever = retriever  # ContextRetriever when available

    async def build_context(
        self,
        query: str | None = None,
        query_embedding: list[float] | None = None,
        rag_limit: int = 5,
    ) -> str:
        """
        Assemble all memory layers into a context block
        that gets prepended to the system prompt.

        When a ContextRetriever is available, uses hybrid/MMR search
        instead of basic cosine similarity for better retrieval quality.
        """
        parts: list[str] = []

        # Working memory (active task state)
        wm = await self.working.to_context_string()
        if wm:
            parts.append(wm)

        # Shared memory (cross-agent context)
        if self.shared:
            sm = await self.shared.to_context_string()
            if sm:
                parts.append(sm)

        # Long-term RAG — prefer ContextRetriever (hybrid/MMR) over basic cosine
        if self.retriever and query:
            try:
                ctx = await self.retriever.get_context(
                    query,
                    limit=rag_limit,
                    search_type="mmr",
                )
                if ctx:
                    parts.append(ctx)
            except Exception:
                logger.warning("ContextRetriever failed, falling back to LongTermMemory", exc_info=True)
                if query_embedding:
                    ltm = await self.long_term.to_context_string(query_embedding, limit=rag_limit)
                    if ltm:
                        parts.append(ltm)
        elif query_embedding:
            ltm = await self.long_term.to_context_string(query_embedding, limit=rag_limit)
            if ltm:
                parts.append(ltm)

        return "\n\n".join(parts)

    async def save_to_working(self, key: str, value: Any) -> None:
        await self.working.set(key, value)

    async def save_to_shared(self, key: str, value: Any) -> None:
        """Save to the cross-agent shared memory."""
        if self.shared:
            await self.shared.set(key, value)

    async def get_from_shared(self, key: str) -> Any | None:
        """Read from cross-agent shared memory."""
        if self.shared:
            return await self.shared.get(key)
        return None

    async def clear_working(self) -> None:
        await self.working.clear()
