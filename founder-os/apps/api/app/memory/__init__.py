"""
Founder OS — Temporal Memory System
======================================
Page-indexed, temporally-aware long-term memory for startup founders.

Replaces pure vector similarity search with a composite scoring system:
  - Semantic similarity (embedding cosine distance)
  - Temporal relevance (exponential decay)
  - Importance scoring
  - Access frequency
  - Review scheduling (spaced repetition)

Modules:
  - manager.py   — MemoryManager (main interface)
  - temporal.py  — Temporal scoring functions
"""
