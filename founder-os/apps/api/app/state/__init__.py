"""Company State Engine (ADR-009, slice 1).

Canonical, non-decaying company state: typed entities + relations + provenance,
fed by IntegrationAdapter ObservedEvents through the reconciler (write-gate +
dedup-on-ingest). Architecture:
docs/superpowers/specs/2026-07-04-phase1-state-engine-architecture.md
"""
