"""Notion integration (ADR-010 adapter; State Engine source #2, arch 2026-07-07).

client.py — HTTP transport ONLY (pacing, retries, pagination, jailed write
sinks). mapper.py — PURE Notion-JSON → ObservedEvents + md→blocks (no IO).
adapter.py — the ADR-010 seam composing both.
"""
