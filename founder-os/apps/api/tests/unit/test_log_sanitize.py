"""sl() must neutralize CR/LF so user input cannot forge log lines."""
from app.log_sanitize import sl


def test_newlines_become_visible_escapes():
    forged = "user-1\n2026-07-07 ERROR fake admin grant\r\nanother"
    out = sl(forged)
    assert "\n" not in out and "\r" not in out
    assert "\\n" in out and "\\r" in out


def test_non_strings_coerced():
    assert sl(42) == "42"
    assert sl(None) == "None"
    exc = ValueError("boom\nline2")
    assert "\n" not in sl(exc)
