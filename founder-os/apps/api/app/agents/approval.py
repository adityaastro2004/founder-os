"""
Founder OS — Human-in-the-Loop Approval System
=================================================
Every tool call flows through the ApprovalGate before execution.

Design principles:
  1. ALL actions require approval by default
  2. Users can "always allow" low/medium risk tools to skip the gate
  3. HIGH-RISK actions (PR push, social media, payments, deployments)
     ALWAYS require explicit approval with NO bypass option
  4. Approvals are per-user, stored in Redis for persistence
  5. Pending approvals expire after a configurable TTL

Risk levels:
  LOW      — read-only, no side effects (search, list, get)
  MEDIUM   — writes that are reversible (create task, save draft)
  HIGH     — irreversible or externally-visible (push PR, post tweet,
             send email, deploy, make payment)

Architecture:
  ┌───────────────────────────────────────────────────────────┐
  │               Execution Engine / ToolRegistry              │
  │                                                            │
  │  tool call requested                                       │
  │        │                                                   │
  │        ▼                                                   │
  │  ┌──────────────┐        ┌──────────────────────┐         │
  │  │ ApprovalGate │──check──▶ UserPreferences      │         │
  │  │              │        │ (Redis per-user)      │         │
  │  │              │        └──────────────────────┘         │
  │  │              │                                          │
  │  │  LOW/MED +   │──auto-approve──▶ execute tool            │
  │  │  always_allow│                                          │
  │  │              │                                          │
  │  │  HIGH or     │                                          │
  │  │  not allowed │──create PendingApproval──▶ Redis queue   │
  │  │              │                           │              │
  │  └──────────────┘                           │              │
  │                                              │              │
  │  User approves via API ──────────────────────┘              │
  │  → tool executes → result returned                         │
  └───────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


# ============================================================================
# Risk Levels
# ============================================================================

class RiskLevel(str, Enum):
    LOW = "low"           # read-only, no side effects
    MEDIUM = "medium"     # writes, but reversible / internal
    HIGH = "high"         # irreversible or externally-visible


# ============================================================================
# Tool → Risk Classification
# ============================================================================

# Tools that are ALWAYS high-risk — no "always allow" bypass
HIGH_RISK_TOOLS: set[str] = {
    # Git / Code
    "push_pr",
    "create_pull_request",
    "merge_pull_request",
    "push_to_branch",
    "merge_branch",
    "delete_branch",

    # Social Media
    "post_to_social_media",
    "publish_content",
    "tweet",
    "post_twitter",
    "post_linkedin",
    "post_facebook",
    "post_instagram",
    "schedule_social_post",

    # Communications
    "send_email",
    "send_slack_message",
    "send_notification",

    # Financial
    "make_payment",
    "transfer_funds",
    "create_invoice",
    "execute_transaction",
    "refund_payment",

    # Deployment / Infrastructure
    "deploy",
    "deploy_to_production",
    "deploy_to_staging",
    "run_migration",
    "delete_database",
    "drop_table",

    # Data
    "delete_data",
    "bulk_delete",
    "export_user_data",
}

# Default risk levels for known built-in tools
TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # LOW — read-only
    "search_knowledge": RiskLevel.LOW,
    "web_search": RiskLevel.LOW,
    "get_business_metrics": RiskLevel.LOW,
    "list_tasks": RiskLevel.LOW,
    "get_integrations": RiskLevel.LOW,
    "get_writing_style": RiskLevel.LOW,
    "get_current_datetime": RiskLevel.LOW,

    # MEDIUM — internal writes
    "create_task": RiskLevel.MEDIUM,
    "update_task_status": RiskLevel.MEDIUM,
    "save_draft": RiskLevel.MEDIUM,
    "delegate_task": RiskLevel.MEDIUM,

    # LOW — internal state only
    "store_working_memory": RiskLevel.LOW,
}


def classify_tool_risk(tool_name: str) -> RiskLevel:
    """
    Determine the risk level of a tool.

    Priority:
      1. If in HIGH_RISK_TOOLS → HIGH (always)
      2. If in TOOL_RISK_MAP → use mapped level
      3. Unknown tools (e.g. from MCP servers) → MEDIUM by default
    """
    if tool_name in HIGH_RISK_TOOLS:
        return RiskLevel.HIGH
    return TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)


# ============================================================================
# Pending Approval
# ============================================================================

@dataclass
class PendingApproval:
    """An action awaiting user approval."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    risk_level: str = ""
    agent_name: str = ""
    session_id: str = ""
    description: str = ""        # human-readable explanation
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0      # 0 = use default TTL
    status: str = "pending"      # pending | approved | rejected | expired
    resolution_note: str = ""    # optional note from user on approve/reject

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "description": self.description,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "resolution_note": self.resolution_note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingApproval":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ApprovalDecision:
    """The result of an approval check."""
    approved: bool
    reason: str
    pending_approval: PendingApproval | None = None  # set when approval is needed
    auto_approved: bool = False                       # true if always-allow kicked in


# ============================================================================
# User Approval Preferences (Redis-backed)
# ============================================================================

class ApprovalPreferences:
    """
    Per-user approval preferences stored in Redis.

    Each user has a hash of tool_name → preference:
      - "always_allow"  — auto-approve this tool
      - "always_deny"   — auto-reject this tool
      - "ask"           — always ask (default)

    HIGH-RISK tools cannot be set to "always_allow".
    """

    KEY_PREFIX = "approval:prefs"
    PENDING_PREFIX = "approval:pending"
    PENDING_LIST_PREFIX = "approval:user_pending"
    DEFAULT_PENDING_TTL = 3600  # 1 hour

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    # -- Preferences -----------------------------------------------------

    def _prefs_key(self, user_id: str) -> str:
        return f"{self.KEY_PREFIX}:{user_id}"

    async def get_preference(self, user_id: str, tool_name: str) -> str:
        """Get the user's preference for a specific tool. Default: 'ask'."""
        val = await self._redis.hget(self._prefs_key(user_id), tool_name)
        return val.decode() if val else "ask"

    async def get_all_preferences(self, user_id: str) -> dict[str, str]:
        """Get all tool preferences for a user."""
        raw = await self._redis.hgetall(self._prefs_key(user_id))
        return {k.decode(): v.decode() for k, v in raw.items()} if raw else {}

    async def set_preference(
        self,
        user_id: str,
        tool_name: str,
        preference: str,
    ) -> bool:
        """
        Set a tool preference. Returns False if the operation is disallowed.

        HIGH-RISK tools cannot be set to "always_allow".
        """
        if preference not in ("always_allow", "always_deny", "ask"):
            raise ValueError(f"Invalid preference: {preference}")

        if preference == "always_allow" and tool_name in HIGH_RISK_TOOLS:
            logger.warning(
                "Blocked attempt to always-allow high-risk tool '%s' for user '%s'",
                tool_name, user_id,
            )
            return False

        await self._redis.hset(self._prefs_key(user_id), tool_name, preference)
        return True

    async def clear_preference(self, user_id: str, tool_name: str) -> None:
        """Remove a specific tool preference (reverts to 'ask')."""
        await self._redis.hdel(self._prefs_key(user_id), tool_name)

    async def clear_all_preferences(self, user_id: str) -> None:
        """Remove all preferences for a user."""
        await self._redis.delete(self._prefs_key(user_id))

    # -- Pending approvals -----------------------------------------------

    def _pending_key(self, approval_id: str) -> str:
        return f"{self.PENDING_PREFIX}:{approval_id}"

    def _user_pending_key(self, user_id: str) -> str:
        return f"{self.PENDING_LIST_PREFIX}:{user_id}"

    async def store_pending(
        self,
        approval: PendingApproval,
        ttl: int | None = None,
    ) -> None:
        """Store a pending approval in Redis."""
        ttl = ttl or self.DEFAULT_PENDING_TTL
        approval.expires_at = time.time() + ttl

        key = self._pending_key(approval.id)
        await self._redis.set(key, json.dumps(approval.to_dict()), ex=ttl)

        # Also add to user's pending list (sorted set by creation time)
        await self._redis.zadd(
            self._user_pending_key(approval.user_id),
            {approval.id: approval.created_at},
        )

    async def get_pending(self, approval_id: str) -> PendingApproval | None:
        """Retrieve a pending approval by ID."""
        raw = await self._redis.get(self._pending_key(approval_id))
        if not raw:
            return None
        data = json.loads(raw)
        return PendingApproval.from_dict(data)

    async def list_pending(self, user_id: str) -> list[PendingApproval]:
        """List all pending approvals for a user (most recent first)."""
        ids = await self._redis.zrevrange(
            self._user_pending_key(user_id), 0, -1,
        )
        results: list[PendingApproval] = []
        for aid in ids:
            approval = await self.get_pending(aid.decode() if isinstance(aid, bytes) else aid)
            if approval and approval.status == "pending":
                results.append(approval)
        return results

    async def resolve(
        self,
        approval_id: str,
        status: str,
        note: str = "",
    ) -> PendingApproval | None:
        """
        Resolve a pending approval (approve or reject).

        Returns the updated approval, or None if not found / expired.
        """
        approval = await self.get_pending(approval_id)
        if not approval:
            return None

        approval.status = status
        approval.resolution_note = note

        # Update in Redis (keep for audit, short TTL)
        key = self._pending_key(approval_id)
        await self._redis.set(key, json.dumps(approval.to_dict()), ex=300)

        # Remove from pending list
        await self._redis.zrem(
            self._user_pending_key(approval.user_id),
            approval_id,
        )

        logger.info(
            "Approval '%s' for tool '%s' → %s (user: %s)",
            approval_id, approval.tool_name, status, approval.user_id,
        )
        return approval


# ============================================================================
# Approval Gate — the main entry point for tool execution approval
# ============================================================================

class ApprovalGate:
    """
    Checks whether a tool call can proceed.

    Call ``check()`` before executing any tool. It returns an
    ``ApprovalDecision`` indicating:
      - approved=True, auto_approved=True  → execute immediately (always-allow)
      - approved=True, auto_approved=False → user explicitly approved
      - approved=False, pending_approval   → need to wait for user decision
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._prefs = ApprovalPreferences(redis)
        self._redis = redis

    @property
    def preferences(self) -> ApprovalPreferences:
        return self._prefs

    async def check(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        agent_name: str = "",
        session_id: str = "",
    ) -> ApprovalDecision:
        """
        Determine whether a tool call should proceed, wait, or be blocked.

        Logic:
          1. Classify the tool's risk level
          2. For HIGH-risk: ALWAYS create a pending approval (no bypass)
          3. For LOW/MEDIUM: check user preferences
             - "always_allow" → auto-approve
             - "always_deny"  → reject immediately
             - "ask" (default) → create pending approval
        """
        risk = classify_tool_risk(tool_name)

        # HIGH risk — always require explicit approval, never auto-approve
        if risk == RiskLevel.HIGH:
            return await self._create_pending(
                user_id=user_id,
                tool_name=tool_name,
                arguments=arguments,
                risk_level=risk,
                agent_name=agent_name,
                session_id=session_id,
                reason="High-risk action — explicit approval required (no bypass)",
            )

        # LOW / MEDIUM — check user preferences
        pref = await self._prefs.get_preference(user_id, tool_name)

        if pref == "always_allow":
            return ApprovalDecision(
                approved=True,
                reason=f"Auto-approved (user set 'always allow' for '{tool_name}')",
                auto_approved=True,
            )

        if pref == "always_deny":
            return ApprovalDecision(
                approved=False,
                reason=f"Auto-rejected (user set 'always deny' for '{tool_name}')",
            )

        # Default: "ask" — create pending approval
        return await self._create_pending(
            user_id=user_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk,
            agent_name=agent_name,
            session_id=session_id,
            reason=f"Approval required for '{tool_name}' ({risk.value} risk)",
        )

    async def _create_pending(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
        agent_name: str,
        session_id: str,
        reason: str,
    ) -> ApprovalDecision:
        """Create a pending approval and return a decision to wait."""
        description = self._describe_action(tool_name, arguments, agent_name)

        approval = PendingApproval(
            user_id=user_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level.value,
            agent_name=agent_name,
            session_id=session_id,
            description=description,
        )

        await self._prefs.store_pending(approval)

        return ApprovalDecision(
            approved=False,
            reason=reason,
            pending_approval=approval,
        )

    async def approve(self, approval_id: str, note: str = "") -> PendingApproval | None:
        """Approve a pending action."""
        return await self._prefs.resolve(approval_id, "approved", note)

    async def reject(self, approval_id: str, note: str = "") -> PendingApproval | None:
        """Reject a pending action."""
        return await self._prefs.resolve(approval_id, "rejected", note)

    async def list_pending(self, user_id: str) -> list[PendingApproval]:
        """List all pending approvals for a user."""
        return await self._prefs.list_pending(user_id)

    # -- Description generation ------------------------------------------

    @staticmethod
    def _describe_action(
        tool_name: str,
        arguments: dict[str, Any],
        agent_name: str,
    ) -> str:
        """Generate a human-readable description of what the tool will do."""
        agent_prefix = f"[{agent_name}] " if agent_name else ""

        # Custom descriptions for known tools
        descriptions: dict[str, str] = {
            "create_task": f"Create task: \"{arguments.get('title', '?')}\"",
            "update_task_status": (
                f"Update task {arguments.get('task_id', '?')} → "
                f"{arguments.get('status', '?')}"
            ),
            "save_draft": (
                f"Save {arguments.get('output_type', 'draft')}: "
                f"\"{arguments.get('title', '?')}\""
            ),
            "delegate_task": (
                f"Delegate to {arguments.get('agent_name', '?')}: "
                f"\"{arguments.get('task', '?')[:80]}\""
            ),
            "send_email": (
                f"Send email to {arguments.get('to', '?')}: "
                f"\"{arguments.get('subject', '?')}\""
            ),
            "post_to_social_media": (
                f"Post to {arguments.get('platform', '?')}: "
                f"\"{str(arguments.get('content', '?'))[:80]}…\""
            ),
            "push_pr": (
                f"Push PR to {arguments.get('repo', '?')}: "
                f"\"{arguments.get('title', '?')}\""
            ),
            "deploy": f"Deploy to {arguments.get('environment', '?')}",
            "make_payment": (
                f"Payment of {arguments.get('amount', '?')} "
                f"{arguments.get('currency', 'USD')} "
                f"to {arguments.get('recipient', '?')}"
            ),
        }

        desc = descriptions.get(tool_name)
        if desc:
            return f"{agent_prefix}{desc}"

        # Generic fallback
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(arguments.items())[:3])
        return f"{agent_prefix}{tool_name}({args_str})"
