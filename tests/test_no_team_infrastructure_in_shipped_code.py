"""Nothing shipped may name, assume, or advertise our own LLM host.

This repository is public and the panel is expected to clone it and run it on their own
machine against their own model. Two different failures follow from forgetting that, and both
have happened here:

  * a DEFAULT that points at our cluster is one a judge cannot reach and cannot diagnose. The
    shipped defaults are a plain local Ollama for exactly this reason.
  * a UI that ASSERTS our cluster is worse than a wrong default, because it is confident. The
    engine card used to read "Self-hosted · flash-next (team V100)", "team key set", "Model:
    Qwen3.8-Flash-Next (team)" — a description of one deployment, presented as a property of
    the software. On anyone else's machine every line of it was false, and the model it named
    had not existed for weeks.

The real endpoints live in `.env`, which is gitignored. These tests keep it that way.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Tailscale CGNAT (100.64.0.0/10) and the lab's private range. An address from either is a
#: machine only we can reach, so neither belongs in a file that ships.
_PRIVATE_HOST = re.compile(r"\b100\.64\.\d{1,3}\.\d{1,3}\b|\b10\.0\.19[01]\.\d{1,3}\b")


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout.split("\n")
    return [ROOT / p for p in out if p.strip()]


def _code_files() -> list[Path]:
    """Shipped code and config. Prose under docs/ records history and is not shipped config."""
    return [p for p in _tracked_files()
            if p.suffix in {".py", ".toml", ".yaml", ".yml", ".env", ".cfg", ".ini"}
            and "docs/" not in p.as_posix()
            and p.name != Path(__file__).name]


def test_no_private_cluster_address_is_committed():
    guilty = []
    for p in _code_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:                                    # pragma: no cover
            continue
        for m in _PRIVATE_HOST.finditer(text):
            line = text[: m.start()].count("\n") + 1
            guilty.append(f"{p.relative_to(ROOT).as_posix()}:{line}  {m.group(0)}")
    assert not guilty, (
        "an address only our own network can reach is committed:\n  " + "\n  ".join(guilty)
        + "\nPut it in .env (gitignored) instead.")


def test_env_is_not_tracked():
    """The one file that legitimately holds the real endpoint and key must stay out of git."""
    tracked = {p.name for p in _tracked_files()}
    assert ".env" not in tracked


def test_shipped_defaults_are_reachable_by_a_stranger():
    from backend.config import Settings

    fresh = Settings.model_construct()
    assert "localhost" in fresh.local_llm_base_url or "127.0.0.1" in fresh.local_llm_base_url
    assert not fresh.local_llm_api_key, "a committed key would live in the public history"
    assert fresh.llm_provider in {"mock", "openrouter"}, (
        "the shipped provider must be one a stranger can actually run")


@pytest.mark.parametrize("claim", ["team V100", "team key", "flash-next", "Tailscale",
                                   "team host", "team cluster"])
def test_the_engine_chooser_asserts_nothing_about_our_deployment(claim):
    """Card copy is read as a statement of fact about the software. It has to be one."""
    text = (ROOT / "frontend" / "enginebench.py").read_text(encoding="utf-8")
    # The docstring recording WHY this rule exists is allowed to quote the old copy.
    body = re.sub(r'"""(?:.|\n)*?"""', "", text)
    assert claim.lower() not in body.lower(), (
        f"{claim!r} is a fact about our deployment, not about the software")


def test_the_self_hosted_card_says_what_to_do_when_nothing_is_configured(monkeypatch):
    """A blank or a lie are the two wrong answers; the card must name the next action."""
    from backend.config import settings
    from frontend import enginebench

    monkeypatch.setattr(settings, "local_llm_base_url", enginebench._UNCONFIGURED_LOCAL)
    spec = enginebench._local_spec()
    values = " ".join(v for _lab, v, _tone in spec["facts"]).lower()
    assert "not set" in values
    assert "base url" in values, "an empty state has to name the action that fills it"
    assert "qwen" not in values and "100.64" not in values


def test_the_self_hosted_card_reports_what_is_actually_configured(monkeypatch):
    from backend.config import settings
    from frontend import enginebench

    monkeypatch.setattr(settings, "local_llm_base_url", "http://gpu-lab.example:9999/v1")
    monkeypatch.setattr(settings, "local_llm_model", "some-model-7b")
    spec = enginebench._local_spec()
    facts = {lab: v for lab, v, _tone in spec["facts"]}
    assert facts["Endpoint"] == "gpu-lab.example:9999", "the host, not the whole URL"
    assert facts["Model"] == "some-model-7b"
    assert facts["Cost"] == "$0 per call"
