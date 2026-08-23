"""Standard output that cannot kill a run.

A pillar-6 run for Mongolia died here:

    print(f"[discovery] {src.get('name', '?')} failed on {q!r}: ")
    UnicodeEncodeError: 'charmap' codec can't encode characters in position 71-75

That line lives inside the `except` block written so that one dead query is not fatal. The
query was Mongolian, Python's stdout on Windows defaults to the console's ANSI code page
(cp1252 here), and the handler reporting the failure raised a second exception that nothing
caught — so the recovery path became the fatal path, and the whole run ended on a message
whose only job was to be read later.

Two rules follow, and both are enforced here rather than at each of the forty-odd `print`
calls in the backend:

  * stdout and stderr speak UTF-8. Every economy after Round 1 writes in a script cp1252 has
    no code points for, so this is not a nicety.
  * a byte that still cannot be encoded is replaced, never raised. Logging is observation; if
    observing changes whether the program completes, it is not observation.

`errors="replace"` is deliberate over `errors="ignore"`: a `?` in a log line is visible, and a
silently shortened one is not.
"""
from __future__ import annotations

import sys


def enable_utf8_stdio() -> None:
    """Make `print` safe for non-Latin text. Idempotent; never raises.

    Called from the entry points (`main.py`, `backend/cli.py`, `frontend/app.py`) rather than
    at import of a library module — reconfiguring the process's streams is the application's
    decision, not a side effect a library should impose on whoever imports it.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # Streamlit and some test harnesses replace the stream with an object that has no
            # `reconfigure`. Nothing to do: `safe_log` below still holds the second rule.
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass                      # a detached or already-closed stream is not worth a crash


def safe_log(message: str) -> None:
    """Print a line, whatever is in it and whatever the stream can encode.

    The fallback re-encodes through the stream's OWN encoding with replacement, so a Mongolian
    title on a cp1252 console degrades to question marks instead of taking the run with it.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(message.encode(encoding, "replace").decode(encoding, "replace"))
    except Exception:                 # noqa: BLE001 — a broken pipe must not end the run either
        pass
