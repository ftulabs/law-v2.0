"""A log line must never end a run.

A Mongolia pillar-6 run died in the dashboard with

    UnicodeEncodeError: 'charmap' codec can't encode characters in position 71-75
    File "backend/pipeline/discovery.py", line 1251, in discover_live
        print(f"[discovery] {src.get('name', '?')} failed on {q!r}: "

That `print` is inside the `except` block written so that one dead query is not fatal. The
query was Mongolian; Windows gives a process the console's ANSI code page (cp1252 here); the
handler reporting the failure raised a second exception nobody caught. The recovery path
became the fatal path.

It surfaced in the browser and not in a terminal because `main.py` and `batch_run.py` had
reconfigured stdout since Round 1 and `frontend/app.py` never had — so every CLI run was
immune and every dashboard run was not.
"""
import io
import sys

import pytest

from backend.console import enable_utf8_stdio, safe_log

#: The exact strings that killed the run, plus one per remaining Round-2 script.
NON_LATIN = [
    "хүний хувийн мэдээлэл",          # mn — the query in the traceback
    "中华人民共和国个人信息保护法",        # zh
    "Российской Федерации",           # ru
    "ข้อมูลส่วนบุคคล",                     # th
]


class _Cp1252Stream(io.TextIOBase):
    """A stream that behaves like a Windows console: cp1252, and it raises."""

    encoding = "cp1252"

    def __init__(self):
        self.written = []

    def write(self, s):
        s.encode("cp1252")            # raises UnicodeEncodeError, exactly as the console does
        self.written.append(s)
        return len(s)


@pytest.mark.parametrize("text", NON_LATIN)
def test_the_stream_this_test_uses_really_does_raise(text):
    """Guard the guard: if the fake stream stopped raising, every test below would pass for
    the wrong reason."""
    with pytest.raises(UnicodeEncodeError):
        _Cp1252Stream().write(text)


@pytest.mark.parametrize("text", NON_LATIN)
def test_safe_log_never_raises_on_a_cp1252_stream(text, monkeypatch):
    monkeypatch.setattr(sys, "stdout", _Cp1252Stream())
    safe_log(f"[discovery] portal failed on {text!r}: TimeoutError")   # must not raise


def test_safe_log_still_says_something(monkeypatch):
    """Degrading to question marks is the point; degrading to silence is not."""
    stream = _Cp1252Stream()
    monkeypatch.setattr(sys, "stdout", stream)
    safe_log("[discovery] failed on 'хүний'")
    assert stream.written and "discovery" in "".join(stream.written)


def test_safe_log_survives_a_stream_that_is_simply_broken(monkeypatch):
    class _Dead(io.TextIOBase):
        def write(self, s):
            raise OSError("broken pipe")

    monkeypatch.setattr(sys, "stdout", _Dead())
    safe_log("anything")              # must not raise


def test_enable_utf8_stdio_tolerates_a_stream_without_reconfigure(monkeypatch):
    """Streamlit and pytest both replace the stream with an object that has no `reconfigure`;
    that must be a no-op, not an AttributeError at import time."""
    monkeypatch.setattr(sys, "stdout", _Cp1252Stream())
    monkeypatch.setattr(sys, "stderr", _Cp1252Stream())
    enable_utf8_stdio()


def test_discovery_has_no_bare_print_left():
    """The lane that crashed. Its messages now go to the run's `log`, which reaches the Run
    screen instead of a terminal nobody is watching."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "backend" / "pipeline" / "discovery.py"
           ).read_text(encoding="utf-8")
    assert "print(" not in src
    assert "log=print" not in src


def test_every_entry_point_enables_utf8_stdio():
    """Including the dashboard. Its absence there is the entire reason this bug reached a user
    while every CLI run looked fine."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in ("main.py", "batch_run.py", "backend/cli.py", "frontend/app.py"):
        assert "enable_utf8_stdio()" in (root / rel).read_text(encoding="utf-8"), rel
