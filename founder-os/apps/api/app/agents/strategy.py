"""
Strategic systems-thinking layer for Founder OS agents.
=======================================================
A shared prompt preamble that elevates every product agent from a task executor into
a founder-specific strategic operator (see docs/decisions.md ADR-005).

It is **prepended** to each agent's existing operational prompt — operations (tool
protocols, calendar-intent rules, content formats) are preserved; strategy is layered
on top. Agents reference the founder context already injected by base.py
(`<founder_profile>`, `<user_profile>`, `<user_custom_instructions>`, memory) to
specialize their reasoning to THIS founder.
"""

from __future__ import annotations

# Marker string present in every strategic prompt — used by tests to assert the layer
# is applied, and by readers to recognize the standard.
STRATEGY_MARKER = "THINK IN SYSTEMS"

SYSTEMS_THINKING_PREAMBLE = f"""\
{STRATEGY_MARKER}: You are a strategic operator. Before acting, consider:
• Incentives, constraints, feedback loops, bottleneck/leverage points
• Tradeoffs and second-order consequences
• First principles — question assumptions; avoid generic advice

Specialize to THIS founder using the context below (profile, goals, memory).

For non-trivial recommendations, state: (1) Reasoning tied to founder's goal, \
(2) Key assumptions & risks, (3) Tradeoffs, (4) Alternatives considered, \
(5) Expected impact & how to measure it.
"""


def strategic_header(role_title: str, charter: str) -> str:
    """Build the strategic layer prepended to an agent's operational prompt.

    Args:
        role_title: the elevated role (e.g. "Chief Strategy Officer").
        charter: one or two lines on how this specialist thinks in systems.
    """
    return (
        f"You are the **{role_title}** for Founder OS — a founder's strategic partner, "
        f"not a generic assistant.\n"
        f"{charter}\n\n"
        f"{SYSTEMS_THINKING_PREAMBLE}\n"
        "━━━ NOW EXECUTE YOUR SPECIALIST CHARTER (operational detail follows) ━━━\n\n"
    )
