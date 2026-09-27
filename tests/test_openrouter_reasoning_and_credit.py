"""OpenRouter: the reasoning switch reaches the request, and an empty ACCOUNT stops the run.

2026-09-26: deepseek-v4-flash with reasoning off scored 28/28 on the real-row bench at $0.19
per 1,000 calls; with it on, 19/28 at up to 198 s a call. And a 402 "Insufficient credits"
used to walk the whole failover pool on every call and be reported as a rate limit."""
from types import SimpleNamespace

import pytest

from backend.config import settings
from backend.providers import llm_openrouter as orr
from backend.providers.llm_base import LLMTerminalError


class _Completions:
    def __init__(self, exc=None):
        self.kwargs, self.exc = [], exc

    def create(self, **kw):
        self.kwargs.append(kw)
        if self.exc:
            raise self.exc
        msg = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))


def _llm(completions):
    llm = orr.OpenRouterLLM("sk-test", "deepseek/deepseek-v4-flash")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    llm._candidates = lambda: ["deepseek/deepseek-v4-flash", "other/model"]
    return llm


@pytest.mark.parametrize("mode,expected", [("off", {"enabled": False}), ("low", {"effort": "low"}),
                                            ("", None)])
def test_reasoning_setting_reaches_the_request(monkeypatch, mode, expected):
    monkeypatch.setattr(settings, "openrouter_reasoning", mode)
    monkeypatch.setattr(settings, "openrouter_provider_order", "")
    c = _Completions()
    assert _llm(c).complete_json("s", "u") == {"ok": True}
    assert c.kwargs[0].get("extra_body", {}).get("reasoning") == expected


def test_out_of_credit_is_terminal_and_does_not_walk_the_pool(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_provider_order", "")
    err = Exception("Error code: 402 - Insufficient credits. Add more using …")
    err.status_code = 402
    c = _Completions(exc=err)
    with pytest.raises(LLMTerminalError) as ei:
        _llm(c).complete_json("s", "u")
    assert ei.value.kind == "quota"
    assert len(c.kwargs) == 1            # the failover model was never asked


def test_a_model_that_cannot_switch_reasoning_off_is_asked_again_without_it(monkeypatch):
    # google/gemini-3.7-flash, 2026-09-27: 400 "Reasoning is mandatory for this endpoint and
    # cannot be disabled" — engine B failed every call while OPENROUTER_REASONING was "off".
    monkeypatch.setattr(settings, "openrouter_reasoning", "off")
    monkeypatch.setattr(settings, "openrouter_provider_order", "")
    monkeypatch.setattr(orr, "_REASONING_MANDATORY", set())

    class _Mandatory(_Completions):
        def create(self, **kw):
            if "reasoning" in (kw.get("extra_body") or {}):
                self.kwargs.append(kw)
                raise Exception("Error code: 400 - Reasoning is mandatory for this endpoint "
                                "and cannot be disabled.")
            return super().create(**kw)

    c = _Mandatory()
    llm = _llm(c)
    assert llm.complete_json("s", "u") == {"ok": True}
    assert llm.complete_json("s", "u") == {"ok": True}
    # one refused call, then every call goes without the switch
    assert [("reasoning" in (k.get("extra_body") or {})) for k in c.kwargs] == [True, False, False]
