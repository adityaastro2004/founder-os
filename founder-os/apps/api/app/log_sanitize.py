"""Log-line sanitizer (CodeQL py/log-injection remediation, 2026-07-07).

Any request-derived value (Clerk user ids, titles, model names, exception
text from user-triggered flows) interpolated into a log line goes through
``sl()`` so embedded CR/LF cannot forge additional log records.
"""
from __future__ import annotations


def sl(value: object) -> str:
    """Return a single-line string safe for log interpolation."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")
