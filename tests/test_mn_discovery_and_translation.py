"""Regressions for defects that failed SILENTLY.

None of them raised, and none produced a short run or an error row. Each produced a CSV that
looked like a completed analysis and was wrong, which is why they are pinned here rather than
left to the end-to-end run to notice.
"""
from __future__ import annotations

from pathlib import Path

from backend.config import ROOT, Settings


# ─────────────────────────── 1. the .env path ───────────────────────────
def test_env_file_is_absolute_so_the_cwd_cannot_silence_the_key():
    """`env_file=".env"` resolved against the CURRENT WORKING DIRECTORY.

    Launch from anywhere but the repo root — `cd frontend && streamlit run app.py`, a
    scheduler, an IDE run-config — and pydantic-settings found no file at all. It did not
    complain: `llm_provider` fell back to its "mock" default and `openrouter_api_key` to "",
    so the run completed on the lexical mock grader and the only symptom was mappings that
    looked like a rejected API key.
    """
    env_file = Settings.model_config.get("env_file")
    assert env_file is not None
    assert Path(env_file).is_absolute(), (
        "env_file must be absolute; a relative path is read from the cwd and silently "
        "downgrades the run to the mock provider")
    assert Path(env_file) == ROOT / ".env"
