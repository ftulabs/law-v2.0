"""A benched node has to come back, and the pool has to stay a pool.

`_quarantine` had no release. `_healthy` only ever shrank, `_reset_rotation` ran once in
`__init__`, and in a server process the provider outlives every run — the deployed container had
been up two days. One dropped connection removed a node until the container was rebuilt, and the
pool ratcheted down across unrelated runs until `len(self._healthy) > 1` was the only thing
stopping it reaching zero.

Why that is expensive rather than merely untidy, measured 2026-09-12 against the thirteen-node
cluster with the real grading prompt:

    concurrency  1   wall 215.8s   throughput 0.3 calls/min
    concurrency 13   wall 278.1s   throughput 2.6 calls/min
    concurrency 26   wall 153.9s   throughput 9.4 calls/min

A collapsed pool does not just lose redundancy, it loses the concurrency the throughput comes
from. The difference between thirteen nodes and one is the difference between minutes and hours.
"""
from __future__ import annotations

import pytest

from backend.providers import llm_local


class _Client:
    """Stands in for an `openai.OpenAI` — only what the provider actually touches."""

    def __init__(self, name: str, fail: bool = False):
        self.name, self.fail, self.calls = name, fail, 0
        self.chat = self                      # provider calls client.chat.completions.create
        self.completions = self

    def create(self, **_kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return _Resp('{"ok": true}')


class _Resp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class _Clock:
    """A clock the test moves. `time.monotonic()` must be controlled BEFORE the node is
    benched, not after: the bench timestamp is taken from the same function, so patching it
    afterwards records a bench time in the future and the cooldown never expires."""

    def __init__(self):
        self.now = 10_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(llm_local.time, "monotonic", c)
    return c


def _provider(monkeypatch, clients):
    """A `LocalLLM` over stub clients, without constructing real OpenAI objects."""
    monkeypatch.setattr(llm_local, "OpenAI", None, raising=False)
    obj = llm_local.LocalLLM.__new__(llm_local.LocalLLM)
    import threading
    obj._clients = list(clients)
    obj._lock = threading.Lock()
    obj._benched = {}
    obj._reset_rotation()
    obj.model_version = "stub"
    return obj


def test_a_failed_node_leaves_the_rotation(monkeypatch):
    good, bad = _Client("good"), _Client("bad", fail=True)
    p = _provider(monkeypatch, [bad, good])
    assert p.complete_json("s", "u") == {"ok": True}
    assert len(p._healthy) == 1 and p._healthy[0] is good


def test_and_comes_back_when_the_cooldown_expires(monkeypatch, clock):
    """The half that did not exist. Without it the pool only ever shrinks."""
    good, bad = _Client("good"), _Client("bad", fail=True)
    p = _provider(monkeypatch, [bad, good])
    p.complete_json("s", "u")
    assert len(p._healthy) == 1

    clock.advance(llm_local.QUARANTINE_SECONDS + 1)
    p._next_client()                                   # releases on the way past
    assert len(p._healthy) == 2, "the benched node never returned"
    assert not p._benched


def test_it_does_not_come_back_early(monkeypatch, clock):
    """A cooldown that releases immediately is the same as no benching at all: a dead node
    would then collect its share of every wave, which is the 2026-09-07 measurement that put
    `_quarantine` there in the first place."""
    good, bad = _Client("good"), _Client("bad", fail=True)
    p = _provider(monkeypatch, [bad, good])
    p.complete_json("s", "u")
    clock.advance(llm_local.QUARANTINE_SECONDS - 1)
    p._next_client()
    assert len(p._healthy) == 1


def test_the_pool_never_empties_however_many_nodes_fail(monkeypatch):
    """`len(self._healthy) > 1` is load-bearing: `complete_json` iterates over `_healthy`, and
    an empty rotation makes `next(self._cycle)` raise StopIteration inside a lock."""
    bad = [_Client(f"bad{i}", fail=True) for i in range(4)]
    p = _provider(monkeypatch, bad)
    with pytest.raises(RuntimeError):
        p.complete_json("s", "u")
    assert len(p._healthy) >= 1


def test_a_healthy_pool_is_used_round_robin(monkeypatch):
    """The reason the pool exists. Two calls must not land on the same node while another
    sits idle — that is what makes concurrency buy throughput."""
    nodes = [_Client(f"n{i}") for i in range(4)]
    p = _provider(monkeypatch, nodes)
    for _ in range(8):
        p.complete_json("s", "u")
    assert [n.calls for n in nodes] == [2, 2, 2, 2]


def test_resetting_the_rotation_also_clears_the_bench(monkeypatch):
    """Otherwise a released node would be in `_healthy` and still in `_benched`, and the next
    expiry would append it a second time."""
    good, bad = _Client("good"), _Client("bad", fail=True)
    p = _provider(monkeypatch, [bad, good])
    p.complete_json("s", "u")
    assert p._benched
    p._reset_rotation()
    assert not p._benched and len(p._healthy) == 2


def test_a_cluster_gets_concurrency_proportional_to_its_nodes(monkeypatch):
    """16 threads across thirteen nodes leaves most of them idle. Measured 2026-09-12 with the
    real grading prompt: 13 threads -> 2.6 calls/min, 39 threads -> 12.3 calls/min at the same
    7.7% failure rate."""
    from backend.config import settings
    p = _provider(monkeypatch, [_Client(f"n{i}") for i in range(13)])
    assert p.suggested_concurrency() == 13 * settings.local_llm_calls_per_node == 39


def test_a_single_node_never_gets_less_than_the_shared_default(monkeypatch):
    """An Ollama on a laptop must not end up MORE serialised than a cloud endpoint would be."""
    from backend.config import settings
    p = _provider(monkeypatch, [_Client("only")])
    assert p.suggested_concurrency() == settings.mapping_concurrency


def test_a_provider_with_no_opinion_still_gets_the_setting():
    """Everything that is not a self-hosted pool keeps behaving exactly as it did."""
    from backend.config import settings
    from backend.providers.llm_base import LLMProvider

    class _Plain(LLMProvider):
        def complete_json(self, system, user):
            return {}

    assert _Plain().suggested_concurrency() == settings.mapping_concurrency
