"""Write-gate (arch §2.3): nothing persists unless novel/specific/durable.

PURE heuristics — no IO in evaluate(). The LLM judge fires only on BORDERLINE,
is provider-neutral, and fails OPEN (hygiene must never wedge a sync or lose
founder data; the future Curator prunes low-confidence rows).
"""
from __future__ import annotations

import asyncio
import enum
import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FILLER_TITLES = {
    "todo", "to do", "untitled", "new note", "notes", "misc", "temp", "test",
    "scratch", "asdf", "inbox",
}
_DAILY_NOTE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BARE_URL_RE = re.compile(r"^https?://\S+$")
_BARE_FILENAME_RE = re.compile(r"^[\w-]+\.[A-Za-z0-9]{1,5}$")

# Confidence assigned when the judge cannot run (timeout/error/budget) — the
# item is kept but marked prunable (arch §2.3 "fail-open at 0.5").
FAIL_OPEN_CONFIDENCE = 0.5

JUDGE_SYSTEM_PROMPT = (
    "You are a strict gatekeeper for a founder's canonical company-state store. "
    "Decide if the candidate item is worth keeping: it must be specific (not "
    "generic filler) and durable (matters beyond today). Reply with STRICT JSON "
    'only: {"keep": true|false, "reason": "<short>"}'
)


class GateDecision(enum.Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    BORDERLINE = "borderline"


@dataclass(frozen=True)
class EntityCandidate:
    entity_type: str
    title: str
    body: str = ""
    frontmatter_keys: tuple = ()
    tags: tuple = ()
    has_headings: bool = False


def evaluate(c: EntityCandidate) -> tuple[GateDecision, list[str]]:
    """Hard rejects 1–4 then borderline flags a/b/c (arch §2.3). Rule 5: exact
    duplicates are not a gate concern — handled upstream by the observation hash."""
    title = c.title.strip()
    body = c.body.strip()

    # 1. minimal title
    if len(title) < 3:
        return GateDecision.REJECT, ["title < 3 chars"]
    # 2. task text length (tasks have no body — the title IS the text)
    if c.entity_type == "task" and len(title) < 3:
        return GateDecision.REJECT, ["task text < 3 chars"]
    # tasks/decisions/goals/projects are durable by nature — never brevity-gated
    if c.entity_type != "note":
        return GateDecision.ACCEPT, ["non-note types accepted after hard checks"]
    # 3. empty stubs
    if len(title) + len(body) < 10:
        return GateDecision.REJECT, ["empty stub (<10 chars total)"]
    # 4. filler titles
    is_filler = title.casefold() in FILLER_TITLES or _DAILY_NOTE_RE.match(title)
    if is_filler:
        if len(body) < 40:
            return GateDecision.REJECT, ["filler title + tiny body"]
        return GateDecision.BORDERLINE, ["filler title, substantive body"]

    reasons: list[str] = []
    word_count = len(body.split())
    if word_count < 25 and not c.frontmatter_keys and not c.tags and not c.has_headings:
        reasons.append("short bare note (<25 words, no structure)")
    if _BARE_URL_RE.match(title) or _BARE_FILENAME_RE.match(title):
        reasons.append("title is a bare URL/filename")
    if reasons:
        return GateDecision.BORDERLINE, reasons
    return GateDecision.ACCEPT, ["passed all heuristics"]


async def judge(c: EntityCandidate, provider, timeout_s: float) -> tuple[bool, str]:
    """One bounded LLM call on a BORDERLINE candidate. Fail-open on any error.

    Budget enforcement (max calls per sync) lives in the reconciler, which also
    applies FAIL_OPEN_CONFIDENCE when the budget is exhausted.
    """
    from app.agents.llm import LLMMessage, Role

    user_msg = (
        f"type: {c.entity_type}\ntitle: {c.title}\nbody (truncated):\n{c.body[:800]}"
    )
    try:
        response = await asyncio.wait_for(
            provider.generate(
                [LLMMessage(role=Role.USER, content=user_msg)],
                system=JUDGE_SYSTEM_PROMPT,
                temperature=0,
                max_tokens=200,
            ),
            timeout=timeout_s,
        )
        raw = (response.content or "").strip()
        start, end = raw.find("{"), raw.rfind("}")
        verdict = json.loads(raw[start:end + 1])
        return bool(verdict["keep"]), str(verdict.get("reason", ""))[:200]
    except Exception as exc:  # timeout, provider error, bad JSON — never wedge a sync
        logger.warning("write-gate judge fail-open (%s): %s", type(exc).__name__, exc)
        return True, f"fail-open: judge unavailable ({type(exc).__name__})"
