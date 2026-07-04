"""
Founder OS — Workflow engine package (n8n-backed).

The shared contract layer for the n8n-backed auto-workflow system (ADR-008):
the canonical IR (`ir.py`), user-scoped persistence helpers (`service.py`), and
(built in later tracks) the compiler, n8n client, callback auth, and runner.

n8n is invisible execution + visualization infrastructure; the IR in
`workflows.steps` (JSONB) is the single contract the Orchestrator emits and the
compiler reads. Risk is classified server-side by tool name via
`app.agents.approval.classify_tool_risk` — never declared in the IR.
"""
