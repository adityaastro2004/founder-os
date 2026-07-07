"""Write-gate (arch §2.3): hard rejects, borderline classification, bounded judge."""
import asyncio

import pytest

from app.state.write_gate import EntityCandidate, GateDecision, evaluate, judge


def cand(entity_type="note", title="A real title", body="Some substantive body text that matters.",
         frontmatter_keys=(), tags=(), has_headings=False):
    return EntityCandidate(
        entity_type=entity_type, title=title, body=body,
        frontmatter_keys=tuple(frontmatter_keys), tags=tuple(tags),
        has_headings=has_headings,
    )


# ── hard rejects (§2.3 rules 1–4) ───────────────────────────────────────

@pytest.mark.parametrize("title", ["", "  ", "ab"])
def test_rule1_short_title_rejected(title):
    decision, reasons = evaluate(cand(title=title))
    assert decision is GateDecision.REJECT


def test_rule2_short_task_text_rejected():
    decision, _ = evaluate(cand(entity_type="task", title="ok", body=""))
    assert decision is GateDecision.REJECT
    decision, _ = evaluate(cand(entity_type="task", title="ship the page", body=""))
    assert decision is not GateDecision.REJECT


def test_rule3_empty_note_stub_rejected():
    decision, _ = evaluate(cand(title="abc", body="   "))
    assert decision is GateDecision.REJECT


@pytest.mark.parametrize("filler", ["todo", "Untitled", "new note", "misc", "TEMP", "2026-07-06"])
def test_rule4_filler_title_with_tiny_body_rejected(filler):
    decision, _ = evaluate(cand(title=filler, body="short"))
    assert decision is GateDecision.REJECT


def test_rule4_carveout_filler_title_substantive_body_is_borderline():
    body = " ".join(["substantive"] * 40)
    decision, _ = evaluate(cand(title="todo", body=body))
    assert decision is GateDecision.BORDERLINE


# ── borderline (§2.3 a/b/c) ─────────────────────────────────────────────

def test_short_bare_note_is_borderline():
    decision, _ = evaluate(cand(title="Quick thought", body="only a few words here"))
    assert decision is GateDecision.BORDERLINE


def test_short_note_with_tags_or_frontmatter_accepted():
    decision, _ = evaluate(cand(title="Quick thought", body="only a few words here", tags=("idea",)))
    assert decision is GateDecision.ACCEPT
    decision, _ = evaluate(cand(title="Quick thought", body="only a few words here",
                                frontmatter_keys=("project",)))
    assert decision is GateDecision.ACCEPT


def test_bare_url_title_is_borderline():
    decision, _ = evaluate(cand(title="https://example.com/x", body=" ".join(["w"] * 60)))
    assert decision is GateDecision.BORDERLINE


def test_tasks_never_borderline_on_brevity():
    decision, _ = evaluate(cand(entity_type="task", title="pay the invoice", body=""))
    assert decision is GateDecision.ACCEPT


def test_substantive_note_accepted():
    decision, _ = evaluate(cand(body=" ".join(["word"] * 60)))
    assert decision is GateDecision.ACCEPT


# ── judge (bounded, fail-open) ──────────────────────────────────────────

class FakeProvider:
    def __init__(self, content=None, exc=None, delay=0.0):
        self.content, self.exc, self.delay = content, exc, delay
        self.calls = 0

    async def generate(self, *a, **k):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        class R:  # minimal LLMResponse shape
            pass
        r = R()
        r.content = self.content
        return r


async def test_judge_keep_true_and_false():
    keep, _, fail_open = await judge(cand(), FakeProvider('{"keep": true, "reason": "durable"}'), timeout_s=5)
    assert keep is True and fail_open is False
    keep, _, fail_open = await judge(cand(), FakeProvider('{"keep": false, "reason": "trivial"}'), timeout_s=5)
    assert keep is False and fail_open is False


async def test_judge_error_and_garbage_fail_open():
    keep, _, fail_open = await judge(cand(), FakeProvider(exc=RuntimeError("down")), timeout_s=5)
    assert keep is True and fail_open is True
    keep, _, fail_open = await judge(cand(), FakeProvider("not json at all"), timeout_s=5)
    assert keep is True and fail_open is True


async def test_judge_timeout_fails_open():
    keep, _, fail_open = await judge(cand(), FakeProvider('{"keep": false}', delay=1.0), timeout_s=0.05)
    assert keep is True and fail_open is True


async def test_judge_fail_open_is_structured_not_string_sniffed():
    """An LLM reason CONTAINING 'fail-open' must not read as a judge failure."""
    keep, reason, fail_open = await judge(
        cand(), FakeProvider('{"keep": true, "reason": "fail-open mindset note"}'), timeout_s=5,
    )
    assert keep is True and fail_open is False and "fail-open" in reason


# ── S2: filler titles gate ALL types, not just notes ────────────────────

@pytest.mark.parametrize("etype", ["task", "goal", "project", "decision"])
def test_filler_title_rejected_for_all_types(etype):
    decision, _ = evaluate(cand(entity_type=etype, title="todo", body=""))
    assert decision is GateDecision.REJECT
    decision, _ = evaluate(cand(entity_type=etype, title="test", body=""))
    assert decision is GateDecision.REJECT
