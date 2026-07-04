"""Approval gate contract (Phase 0 audit F2 + security review S1/S3).

Pins the 3-tier semantics from standards/security.md + app/agents/approval.py
across the FULL matrix of risk level × stored preference:
  - HIGH risk        → ALWAYS a pending approval, no bypass (any preference)
  - explicit "ask"   → pending approval (the founder asked to be asked — F2)
  - unset preference → default policy: LOW/MEDIUM auto-approve
  - always_allow / always_deny → honored for LOW/MEDIUM
  - unrecognized or empty stored values → fail safe toward asking (S1)
  - unknown tools default to MEDIUM, never LOW
"""
import pytest

from app.agents.approval import (
    ApprovalDecision,
    ApprovalGate,
    RiskLevel,
    classify_tool_risk,
)

LOW_TOOL = "search_knowledge"
MEDIUM_TOOL = "create_task"
HIGH_TOOL = "send_email"


class FakeRedis:
    """Only what ApprovalPreferences.get_preference touches: hget."""

    def __init__(self, prefs: dict[str, bytes] | None = None):
        self._prefs = prefs or {}

    async def hget(self, key: str, field: str):
        return self._prefs.get(field)


def make_gate(prefs: dict[str, bytes] | None = None) -> tuple[ApprovalGate, list[dict]]:
    """Gate with fake redis prefs and a recording _create_pending stub."""
    gate = ApprovalGate(FakeRedis(prefs))
    created: list[dict] = []

    async def fake_create_pending(**kwargs) -> ApprovalDecision:
        created.append(kwargs)
        return ApprovalDecision(approved=False, reason=kwargs.get("reason", "pending"))

    gate._create_pending = fake_create_pending
    return gate, created


# ── classify_tool_risk ──────────────────────────────────────────────────

def test_high_risk_tools_always_high():
    assert classify_tool_risk("tweet") is RiskLevel.HIGH
    assert classify_tool_risk("send_email") is RiskLevel.HIGH
    assert classify_tool_risk("deploy_to_production") is RiskLevel.HIGH


def test_known_tools_use_map():
    assert classify_tool_risk(LOW_TOOL) is RiskLevel.LOW
    assert classify_tool_risk("gcal_create_event") is RiskLevel.MEDIUM


def test_unknown_tools_default_medium_not_low():
    assert classify_tool_risk("some_future_mcp_tool") is RiskLevel.MEDIUM


# ── check(): full matrix — risk level × stored preference ───────────────
# Outcomes: "auto" (approved, auto), "deny" (rejected, no pending),
#           "pending" (gated via _create_pending).

MATRIX = [
    # HIGH: always pending, whatever the preference says. Note: always_deny on
    # HIGH also yields pending (never executes without a human either way) —
    # pinned deliberately; see Phase 0 security report observation.
    (HIGH_TOOL, None, "pending"),
    (HIGH_TOOL, b"ask", "pending"),
    (HIGH_TOOL, b"always_allow", "pending"),
    (HIGH_TOOL, b"always_deny", "pending"),
    # MEDIUM
    (MEDIUM_TOOL, None, "auto"),
    (MEDIUM_TOOL, b"ask", "pending"),          # F2 regression
    (MEDIUM_TOOL, b"always_allow", "auto"),
    (MEDIUM_TOOL, b"always_deny", "deny"),
    # LOW
    (LOW_TOOL, None, "auto"),
    (LOW_TOOL, b"ask", "pending"),
    (LOW_TOOL, b"always_allow", "auto"),
    (LOW_TOOL, b"always_deny", "deny"),
]


@pytest.mark.parametrize("tool,stored,expected", MATRIX)
async def test_check_matrix(tool, stored, expected):
    prefs = {tool: stored} if stored is not None else {}
    gate, created = make_gate(prefs)

    decision = await gate.check("u1", tool, {"arg": "x"})

    if expected == "auto":
        assert decision.approved is True
        assert decision.auto_approved is True
        assert created == []
    elif expected == "deny":
        assert decision.approved is False
        assert created == []
    else:  # pending
        assert decision.approved is False
        assert len(created) == 1
        if tool == HIGH_TOOL:
            assert created[0]["risk_level"] is RiskLevel.HIGH


# ── fail-safe edges (S1 + unrecognized values) ──────────────────────────

@pytest.mark.parametrize("stored", [b"", b"banana"])
async def test_bad_stored_values_gate_never_auto_approve(stored):
    """Empty or garbage pref values mean corruption/tampering → always gate."""
    gate, created = make_gate({MEDIUM_TOOL: stored})
    decision = await gate.check("u1", MEDIUM_TOOL, {"arg": "x"})
    assert decision.approved is False
    assert len(created) == 1


# ── named F2 regression (kept explicit for readability) ─────────────────

async def test_explicit_ask_preference_creates_pending():
    """F2: a founder who sets 'ask' for a tool MUST be asked — not auto-approved."""
    gate, created = make_gate({MEDIUM_TOOL: b"ask"})
    decision = await gate.check("u1", MEDIUM_TOOL, {"title": "t"})
    assert decision.approved is False, "explicit 'ask' was silently auto-approved"
    assert len(created) == 1
