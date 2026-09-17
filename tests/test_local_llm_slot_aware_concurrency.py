"""Threads should equal the parallelism the servers actually have, not the node count.

`suggested_concurrency` counted NODES times a measured calls-per-node figure. That was the
right unit for thirteen interchangeable boxes, and it says nothing about how many requests any
one box will run at once. A llama.cpp server started without `--parallel` reports
`total_slots: 1` and queues everything else, so every thread past the first waits its turn.

Measured from the deploy host, eight real grading calls against each surviving server:

    node              1 thread   2 threads   4 threads   8 threads
    Qwen3.5-4B          28.5s       31.0s       30.9s       29.0s   per call
    Qwen3.6-35B-A3B     15.0s       15.7s       17.5s       15.6s   per call

Flat. Both report one slot. Sixteen threads at a one-slot server is a queue, not concurrency.

Asking the server does two things: it stops the configured number being a fiction, and it
makes the number FOLLOW — raise `--parallel` on the server and the next run uses the capacity
with nothing to re-tune here.
"""
from __future__ import annotations

import pytest

from backend.config import settings
from backend.providers import llm_local


@pytest.fixture
def _openai(monkeypatch):
    class _Fake:
        def __init__(self, **kw):
            self.chat = self
            self.completions = self

    import openai
    monkeypatch.setattr(openai, "OpenAI", _Fake)


def _with_slots(monkeypatch, answers: dict[str, int | None]):
    monkeypatch.setattr(llm_local, "_probe_slots", lambda url: answers.get(url))


def test_one_slot_server_does_not_get_sixteen_threads(_openai, monkeypatch):
    _with_slots(monkeypatch, {"http://a:8081/v1": 1})
    llm = llm_local.LocalLLM("http://a:8081/v1", "m")
    assert llm.suggested_concurrency() == 2, "one slot plus one queued, not the 16 default"


def test_raising_parallel_on_the_server_raises_the_thread_count(_openai, monkeypatch):
    _with_slots(monkeypatch, {"http://a:8081/v1": 8})
    llm = llm_local.LocalLLM("http://a:8081/v1", "m")
    assert llm.suggested_concurrency() == 9


def test_slots_are_summed_across_a_pool(_openai, monkeypatch):
    _with_slots(monkeypatch, {"http://a:8081/v1": 4, "http://b:8081/v1": 2})
    llm = llm_local.LocalLLM("http://a:8081/v1,http://b:8081/v1", "m")
    assert llm.suggested_concurrency() == (4 + 1) + (2 + 1)


def test_a_server_that_does_not_publish_slots_keeps_the_old_behaviour(_openai, monkeypatch):
    """Ollama, vLLM and LocalAI have no `/props`. Not being told is not the same as being
    told one, and guessing one would throttle a server that can take far more."""
    _with_slots(monkeypatch, {"http://a:11434/v1": None})
    llm = llm_local.LocalLLM("http://a:11434/v1", "m")
    per_node = max(1, int(settings.local_llm_calls_per_node))
    assert llm.suggested_concurrency() == max(int(settings.mapping_concurrency), per_node)


def test_one_silent_node_in_a_pool_falls_back_rather_than_undercounting(_openai, monkeypatch):
    """Summing only the nodes that answered would size the run to part of the cluster."""
    _with_slots(monkeypatch, {"http://a:8081/v1": 4, "http://b:11434/v1": None})
    llm = llm_local.LocalLLM("http://a:8081/v1,http://b:11434/v1", "m")
    per_node = max(1, int(settings.local_llm_calls_per_node))
    assert llm.suggested_concurrency() == max(int(settings.mapping_concurrency), per_node * 2)


def test_slots_are_probed_once_not_once_per_call(_openai, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm_local, "_probe_slots", lambda url: calls.append(url) or 2)
    llm = llm_local.LocalLLM("http://a:8081/v1", "m")
    llm.suggested_concurrency()
    llm.suggested_concurrency()
    llm.pool_report()
    assert calls == ["http://a:8081/v1"]


def test_pool_report_names_how_many_answered_and_what_they_offer(_openai, monkeypatch):
    _with_slots(monkeypatch, {"http://a:8081/v1": 1, "http://dead:8080/v1": None})
    llm = llm_local.LocalLLM("http://a:8081/v1,http://dead:8080/v1", "m")
    line = llm.pool_report()
    assert "1/2 node(s) answered" in line
    assert "1 parallel slot(s)" in line
    assert "http://dead:8080/v1" in line, "a vanished node must be named, not merely counted"


def test_pool_report_survives_every_node_being_gone(_openai, monkeypatch):
    """The whole-pool-dead case is exactly when the line has to be readable."""
    _with_slots(monkeypatch, {"http://a:8080/v1": None})
    llm = llm_local.LocalLLM("http://a:8080/v1", "m")
    assert "0/1 node(s) answered" in llm.pool_report()


def test_probe_reads_props_beside_the_openai_surface(monkeypatch):
    """`/props` is not under `/v1`; probing `…/v1/props` silently returns None for ever."""
    seen: list[str] = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"total_slots": 3}'

    def _fake_urlopen(url, timeout=None):
        seen.append(url)
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    assert llm_local._probe_slots("http://a:8081/v1") == 3
    assert seen == ["http://a:8081/props"]
