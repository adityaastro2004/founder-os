"""LangGraph-based durable orchestrator.

Replaces the orchestrator's in-memory control loop with a checkpointed
`StateGraph` (see docs/superpowers/specs/2026-07-27-langgraph-orchestrator-design.md
and docs/superpowers/plans/2026-07-27-langgraph-orchestrator.md).

Only three primitives come from LangGraph — `StateGraph`, `AsyncPostgresSaver`,
and `interrupt`. Every node calls existing Founder OS code (specialist agents,
tools, memory, event bus, and the 3-tier provider fallback), so nothing below a
node is rewritten.
"""
