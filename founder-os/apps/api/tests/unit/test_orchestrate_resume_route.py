"""Unit tests for the /orchestrate/resume route wiring + validation (Task 10).

In-process (no running server/DB): asserts the route is registered and that the
ResumeRequest contract rejects bad input. The resume *mechanics* (checkpointed
pause → resume without re-running specialists) are covered by the durability
tests in tests/unit/test_graph_durability.py.
"""

import pytest
from pydantic import ValidationError

from app.api.agent_routes import ResumeRequest, router


def test_resume_route_registered():
    paths = {(r.path, tuple(sorted(r.methods))) for r in router.routes if hasattr(r, "methods")}
    assert ("/api/agents/orchestrate/resume", ("POST",)) in paths


def test_resume_request_requires_nonempty_session_id():
    with pytest.raises(ValidationError):
        ResumeRequest(session_id="", answer="approved")


def test_resume_request_requires_answer():
    with pytest.raises(ValidationError):
        ResumeRequest(session_id="s1")  # type: ignore[call-arg]


def test_resume_request_valid():
    req = ResumeRequest(session_id="s1", answer="approved")
    assert req.session_id == "s1"
    assert req.answer == "approved"
