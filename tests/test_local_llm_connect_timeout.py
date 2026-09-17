"""A node that has left the network must cost seconds to discover, not minutes.

The deploy host's pool listed thirteen addresses; twelve of them were no longer on the
tailnet. A machine that has gone does not refuse the connection — the SYN is swallowed — so
the client sits through the kernel's whole retry ladder. Measured from the deploy host
2026-09-17 against three of those addresses: 133.3s, 135.2s and 135.2s before the connection
gave up. Each. And `_quarantine` releases a benched node after QUARANTINE_SECONDS, so the pool
walks back into every dead address every five minutes for the length of the run.

Nothing in the run reports this. The grading stage simply takes hours, the CSV comes out
complete, and the cause looks like "the model is slow" — which is what it was reported as.

The fix is to stop sharing one budget between two different questions. Reaching the server is
allowed to take `local_llm_timeout_seconds`, because a real grading call does take minutes;
the TCP handshake is not, because a healthy node on this tailnet completes it in about a
second.
"""
from __future__ import annotations

import httpx
import pytest

from backend.config import settings
from backend.providers import llm_local


@pytest.fixture
def _openai(monkeypatch):
    """Capture the kwargs the provider hands to `openai.OpenAI`, without a network."""
    captured: list[dict] = []

    class _Fake:
        def __init__(self, **kw):
            captured.append(kw)
            self.chat = self
            self.completions = self

    import openai
    monkeypatch.setattr(openai, "OpenAI", _Fake)
    return captured


def test_connect_budget_is_separate_from_the_answer_budget(_openai):
    llm_local.LocalLLM("http://a:8080/v1", "m")
    timeout = _openai[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout), "a bare float gives connect the read budget"
    assert timeout.connect == settings.local_llm_connect_timeout_seconds
    assert timeout.read == settings.local_llm_timeout_seconds


def test_the_connect_budget_is_short_enough_to_matter():
    """The whole point is that a dead node is cheap. 133s was the measured cost of not doing
    this; anything near that reproduces the defect, so the default is pinned well below it."""
    assert settings.local_llm_connect_timeout_seconds <= 15.0


def test_an_explicit_timeout_still_only_governs_the_answer(_openai):
    llm_local.LocalLLM("http://a:8080/v1", "m", timeout=42.0)
    timeout = _openai[0]["timeout"]
    assert timeout.read == 42.0
    assert timeout.connect == settings.local_llm_connect_timeout_seconds


def test_every_node_in_a_pool_gets_the_same_budget(_openai):
    llm_local.LocalLLM("http://a:8080/v1,http://b:8080/v1,http://c:8080/v1", "m")
    assert len(_openai) == 3
    assert {t["timeout"].connect for t in _openai} == {
        settings.local_llm_connect_timeout_seconds}


def test_connect_budget_never_collapses_to_zero(monkeypatch, _openai):
    """A misconfigured 0 would refuse every connection rather than speed anything up."""
    monkeypatch.setattr(settings, "local_llm_connect_timeout_seconds", 0.0)
    llm_local.LocalLLM("http://a:8080/v1", "m")
    assert _openai[0]["timeout"].connect >= 0.5
