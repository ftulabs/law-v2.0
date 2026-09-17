"""A self-hosted grader's request timeout must be configurable.

`llm_local` hardcoded 120s. A shared 4B server answering a 4,200-token grading prompt takes
longer than that under concurrency, and every call over the line comes back as
`APITimeoutError` — 78 of 90 rows in the 2026-09-06 P7-I3 replay, which is not a measurement.
The ceiling belongs in config, where a slow lab box can be given room.

It governs the ANSWER only. Since 2026-09-17 the handshake has its own, much shorter
budget — see `tests/test_local_llm_connect_timeout.py` — so these read `.read` rather than
comparing the whole `httpx.Timeout` to a float.
"""
from backend.config import settings
from backend.providers.llm_local import LocalLLM


def test_timeout_has_a_configurable_default():
    assert settings.local_llm_timeout_seconds >= 120


def test_provider_uses_the_configured_timeout():
    llm = LocalLLM("http://127.0.0.1:9/v1", "m", "k")
    assert llm._clients[0].timeout.read == settings.local_llm_timeout_seconds


def test_an_explicit_timeout_overrides_the_setting():
    llm = LocalLLM("http://127.0.0.1:9/v1", "m", "k", timeout=45.0)
    assert llm._clients[0].timeout.read == 45.0
