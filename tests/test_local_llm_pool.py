"""A run must be able to spend its grading calls across every node that serves the model.

The self-hosted cluster runs one model on twelve nodes, and `LocalLLM` took a single
`base_url`, so a run used one of them and left eleven idle. Measured 2026-09-07: one node
answers a warm grading call in ~19s, so Singapore's ~380 pillar-6 calls take two hours on one
node and about ten minutes spread across twelve.

Round-robin is the whole mechanism — the nodes are interchangeable replicas of the same
model, so there is nothing to schedule and no state to keep. What matters is that the
rotation is thread-safe (grading runs `mapping_concurrency` calls at once) and that a
single-URL configuration behaves exactly as it did before.
"""
import pytest

from backend.config import settings
from backend.providers.llm_local import LocalLLM, parse_base_urls


# ─────────────────── parsing the configured list ───────────────────
def test_a_single_url_parses_to_one_entry():
    assert parse_base_urls("http://a:8080/v1") == ["http://a:8080/v1"]


def test_a_comma_separated_list_parses_to_many():
    assert parse_base_urls("http://a:8080/v1,http://b:8080/v1") == [
        "http://a:8080/v1", "http://b:8080/v1"]


def test_whitespace_and_empty_entries_are_ignored():
    """A trailing comma or a line-wrapped .env entry must not create a blank client."""
    assert parse_base_urls(" http://a:8080/v1 , , http://b:8080/v1 ,") == [
        "http://a:8080/v1", "http://b:8080/v1"]


def test_an_empty_setting_parses_to_nothing():
    assert parse_base_urls("") == []
    assert parse_base_urls(None) == []


# ─────────────────── the pool itself ───────────────────
def test_one_url_makes_one_client():
    llm = LocalLLM("http://127.0.0.1:9/v1", "m", "k")
    assert len(llm._clients) == 1


def test_many_urls_make_a_client_each():
    llm = LocalLLM("http://127.0.0.1:9/v1,http://127.0.0.2:9/v1,http://127.0.0.3:9/v1", "m", "k")
    assert len(llm._clients) == 3


def test_calls_rotate_through_every_node_before_repeating():
    llm = LocalLLM("http://127.0.0.1:9/v1,http://127.0.0.2:9/v1,http://127.0.0.3:9/v1", "m", "k")
    picked = [llm._next_client() for _ in range(6)]
    assert picked[:3] == llm._clients          # one full cycle, in order
    assert picked[3:] == llm._clients          # then it starts again


def test_a_single_node_always_returns_that_node():
    llm = LocalLLM("http://127.0.0.1:9/v1", "m", "k")
    assert {id(llm._next_client()) for _ in range(5)} == {id(llm._clients[0])}


def test_rotation_is_thread_safe():
    """Grading runs `mapping_concurrency` calls at once; an unsynchronised counter hands the
    same node to two threads and leaves another idle, which is the bug this exists to avoid."""
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor

    llm = LocalLLM(",".join(f"http://127.0.0.{i}:9/v1" for i in range(1, 5)), "m", "k")
    with ThreadPoolExecutor(max_workers=16) as ex:
        got = list(ex.map(lambda _: id(llm._next_client()), range(400)))
    counts = Counter(got)
    assert len(counts) == 4
    assert set(counts.values()) == {100}       # exactly even, no node starved or doubled


def test_an_empty_base_url_still_raises_with_guidance():
    with pytest.raises(ValueError, match="LOCAL_LLM_BASE_URL"):
        LocalLLM("", "m", "k")


def test_every_node_gets_the_configured_timeout():
    llm = LocalLLM("http://127.0.0.1:9/v1,http://127.0.0.2:9/v1", "m", "k")
    # `.read` because the handshake has had its own, much shorter budget since
    # 2026-09-17; a vanished node used to cost the full read timeout to discover.
    assert all(c.timeout.read == settings.local_llm_timeout_seconds for c in llm._clients)


# ─────────────────── a sick node must not throttle the whole run ───────────────────
class _FakeClient:
    """Stands in for an OpenAI client: answers, or raises whatever it was given."""

    def __init__(self, tag, error=None):
        self.tag, self.error, self.calls = tag, error, 0
        outer = self

        class _Msg:
            content = '{"ok": true}'

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        class _Completions:
            def create(self, **kw):
                outer.calls += 1
                if outer.error:
                    raise outer.error
                return _Resp()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()
        self.timeout = 600.0


def _pool(*clients):
    llm = LocalLLM(",".join(f"http://127.0.0.{i}:9/v1" for i in range(1, len(clients) + 1)),
                   "m", "k")
    llm._clients = list(clients)
    llm._reset_rotation()
    return llm


def test_a_call_that_fails_on_one_node_succeeds_on_the_next():
    """Measured 2026-09-07: one node of twelve answered BadRequestError in 1s and another
    took 120s. A call must not die because the rotation happened to land on one of them."""
    bad, good = _FakeClient("bad", RuntimeError("boom")), _FakeClient("good")
    llm = _pool(bad, good)
    assert llm.complete_json("s", "u") == {"ok": True}
    assert bad.calls == 1 and good.calls == 1


def test_a_failing_node_is_dropped_from_the_rotation():
    """Otherwise every subsequent call still pays a slot on the sick node — which is how a
    twelve-node pool took longer than a single healthy node."""
    bad, good = _FakeClient("bad", RuntimeError("boom")), _FakeClient("good")
    llm = _pool(bad, good)
    for _ in range(4):
        llm.complete_json("s", "u")
    assert bad.calls == 1          # tried once, then quarantined
    assert good.calls == 4


def test_the_error_propagates_when_every_node_is_sick():
    a, b = _FakeClient("a", RuntimeError("boom")), _FakeClient("b", RuntimeError("boom"))
    llm = _pool(a, b)
    with pytest.raises(RuntimeError, match="boom"):
        llm.complete_json("s", "u")


def test_a_healthy_pool_still_spreads_evenly():
    a, b, c = _FakeClient("a"), _FakeClient("b"), _FakeClient("c")
    llm = _pool(a, b, c)
    for _ in range(9):
        llm.complete_json("s", "u")
    assert (a.calls, b.calls, c.calls) == (3, 3, 3)
