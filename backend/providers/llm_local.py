"""Self-hosted / local LLM provider (OpenAI-compatible endpoint).

Works with any server that speaks the OpenAI Chat Completions API — Ollama, vLLM,
LM Studio, llama.cpp server, LocalAI, text-generation-webui. Point `base_url` at the
server's `/v1` and pick a model it serves; the mapper is unchanged.

base_url / model / api_key come from env/.env/secrets/dashboard — never hardcoded.
Ollama (the common case) ignores the key, so it may be left empty.

`base_url` may name SEVERAL nodes, comma-separated, when a cluster serves one model from
interchangeable replicas. Calls are handed out round-robin. Grading is the only thing that
spends real time here — one economy on one pillar is hundreds of calls — and the nodes hold
no per-request state, so there is nothing to schedule beyond taking the next one.
"""
from __future__ import annotations

import itertools
import threading
import time
from typing import Any

from ..config import settings

from .llm_base import LLMProvider

#: How long a failed node sits out before it is offered work again. See `_quarantine`.
QUARANTINE_SECONDS = 300.0


def parse_base_urls(raw: str | None) -> list[str]:
    """Split a comma-separated endpoint list, dropping blanks left by a trailing comma."""
    return [u.strip().rstrip("/") for u in (raw or "").split(",") if u.strip()]


def _timeout(read_seconds: float):
    """Separate the handshake budget from the answer budget.

    A grading call legitimately takes minutes, so the read timeout has to be generous. The
    CONNECT timeout must not inherit that: a node that has left the tailnet never answers the
    SYN, so a single connect budget of 600s is a node that costs ten minutes to discover is
    gone. Falls back to the plain float if httpx is somehow unavailable, which only restores
    the previous behaviour rather than failing the provider.
    """
    try:
        import httpx                                            # noqa: PLC0415
    except ImportError:                                         # pragma: no cover
        return read_seconds
    connect = max(0.5, float(settings.local_llm_connect_timeout_seconds))
    return httpx.Timeout(read_seconds, connect=connect)


def _probe_slots(base_url: str) -> int | None:
    """`total_slots` from a llama.cpp server, or None if it is not one / is not there.

    `/props` sits beside the OpenAI surface rather than inside it, so `/v1` is stripped. Kept
    deliberately cheap: this runs once per process and must never be what delays a run, so a
    node that does not answer promptly is simply one that did not say.
    """
    import urllib.error                                            # noqa: PLC0415
    import urllib.request                                          # noqa: PLC0415

    root = base_url.rstrip("/")
    root = root[: -len("/v1")] if root.endswith("/v1") else root
    try:
        with urllib.request.urlopen(root + "/props", timeout=6) as resp:
            import json                                            # noqa: PLC0415
            slots = json.load(resp).get("total_slots")
    except Exception:                                              # noqa: BLE001
        return None
    return int(slots) if isinstance(slots, int) and slots > 0 else None


class LocalLLM(LLMProvider):
    name = "local"

    def __init__(self, base_url: str, model: str, api_key: str = "",
                 timeout: float | None = None):
        from openai import OpenAI

        urls = parse_base_urls(base_url)
        if not urls:
            raise ValueError(
                "LLM_PROVIDER=local requires LOCAL_LLM_BASE_URL "
                "(e.g. http://gpu-lab:11434/v1 for Ollama, or a comma-separated list "
                "of nodes serving the same model)"
            )
        read_timeout = (timeout if timeout is not None
                        else settings.local_llm_timeout_seconds)
        self._clients = [
            OpenAI(
                base_url=u,
                api_key=api_key or "not-needed",  # Ollama ignores it; the SDK requires non-empty
                max_retries=1,
                timeout=_timeout(read_timeout),
            )
            for u in urls
        ]
        self._url_of = {id(c): u for c, u in zip(self._clients, urls)}
        self._lock = threading.Lock()
        self._benched: dict[int, tuple[Any, float]] = {}   # id(client) -> (client, benched at)
        self._slots: dict[str, int | None] | None = None   # url -> total_slots, probed once
        self._reset_rotation()
        self.model_version = model

    def _reset_rotation(self) -> None:
        """(Re)build the rotation over the currently healthy clients."""
        # itertools.cycle is not thread-safe on its own; grading calls it from
        # `mapping_concurrency` threads at once, and an unsynchronised counter hands one node
        # two calls while another sits idle.
        self._healthy = list(self._clients)
        self._benched.clear()
        self._cycle = itertools.cycle(self._healthy)

    def _next_client(self):
        with self._lock:
            self._release_expired()
            return next(self._cycle)

    def _quarantine(self, client) -> None:
        """Bench a node that failed — for a while, not for ever.

        Why bench it at all: measured 2026-09-07 on the twelve-node cluster, ten answered a
        grading call in 13-18s, one took 120s and one raised BadRequestError in 1s. Left in the
        rotation those two collect a twelfth of the run each, which is how a twelve-node pool
        finished slower than a single healthy node.

        Why RELEASE it again, added 2026-09-12: until now there was no release. `_healthy` only
        ever shrank, `_reset_rotation` ran once in `__init__`, and the provider outlives every
        run in a long-lived server process — the deployed container had been up two days. So a
        node that dropped ONE connection was gone until the container was rebuilt, and the pool
        ratcheted downwards across unrelated runs until the `len(self._healthy) > 1` guard was
        all that stopped it reaching zero. A pool of one serialises everything: measured the
        same day, a single grading call takes 216s on one node while twenty-six concurrent ones
        finish in 154s, so the difference between a full pool and a collapsed one is the
        difference between minutes and hours.

        The cooldown has to be long enough that a genuinely dead node is not retried on every
        call, and short enough that a blip heals inside one run. A grading call on this cluster
        takes ~100-220s, so five minutes is roughly one to three calls' worth of rest.
        """
        with self._lock:
            if client in self._healthy and len(self._healthy) > 1:
                self._healthy.remove(client)
                self._benched[id(client)] = (client, time.monotonic())
                self._cycle = itertools.cycle(self._healthy)

    def _release_expired(self) -> None:
        """Return benched nodes whose cooldown has passed. Caller holds `self._lock`."""
        if not self._benched:
            return
        now = time.monotonic()
        due = [k for k, (_c, t) in self._benched.items()
               if now - t >= QUARANTINE_SECONDS]
        for k in due:
            client, _t = self._benched.pop(k)
            if client not in self._healthy:
                self._healthy.append(client)
        if due:
            self._cycle = itertools.cycle(self._healthy)

    def suggested_concurrency(self) -> int:
        """`local_llm_calls_per_node` x the number of nodes — measured, not assumed.

        Measured 2026-09-12 against the thirteen-node Qwen3.5-4B cluster, sending the REAL
        grading prompt (10,102-char system + provision, ~2,900 tokens) and counting completed
        calls per minute:

            threads  per node   throughput    failed    median latency
                  1       0.1    0.3/min        0 %          216 s
                 13       1.0    2.6/min      7.7 %          189 s
                 26       2.0    9.4/min      7.7 %          104 s
                 39       3.0   12.3/min      7.7 %           98 s
                 52       4.0   16.7/min       23 %           94 s
                 78       6.0   19.4/min       18 %           74 s
                104       8.0   24.0/min       23 %           94 s

        Two things in that table decide the number. Throughput keeps climbing past 39 — this is
        not a plateau — but the FAILURE RATE stops being flat: 7.7 % at every level up to 39,
        then 18-23 % from 52. The kind of failure changes with it. Up to 39 the only error is
        URLError at a steady ~1 in 13, which is a constant per-call rate and not load; from 52
        the server starts returning HTTPError, which is the cluster saying it has had enough.

        A failed grading call is not free here. `mapping` counts it, skips that provision, and
        `_quarantine` benches the node that raised — so buying 40 % more throughput at three
        times the failure rate buys lost evidence and a shrinking pool. 39 is the last point
        where the cluster is being worked hard and still answering reliably.

        Bounded below by `settings.mapping_concurrency` so a single-node Ollama on a laptop
        does not end up with LESS concurrency than the shared default.

        SUPERSEDED where the server answers for itself, 2026-09-17. The table above counts
        NODES, which was the right unit for thirteen interchangeable boxes but says nothing
        about how many requests any one of them will run at once. llama.cpp publishes that as
        `total_slots` on `/props`, and a server started without `--parallel` reports 1: it
        queues everything else, so threads past the first buy nothing at all. Measured from the
        deploy host against the two surviving servers, eight real grading calls each:

            node              1 thread   2 threads   4 threads   8 threads
            Qwen3.5-4B          28.5s       31.0s       30.9s       29.0s   per call
            Qwen3.6-35B-A3B     15.0s       15.7s       17.5s       15.6s   per call

        Flat, both of them, because both report `total_slots = 1`. Sixteen threads at a
        one-slot server is not concurrency, it is a queue with a longer name. Asking the server
        makes the number honest, and makes it FOLLOW: raise `--parallel` on the server and the
        run picks the capacity up by itself, with nothing to re-tune here.
        """
        from ..config import settings                              # noqa: PLC0415
        per_node = max(1, int(settings.local_llm_calls_per_node))
        fallback = max(int(settings.mapping_concurrency), per_node * len(self._clients))

        slots = self.pool_slots()
        if not slots or any(s is None for s in slots.values()):
            # Ollama, vLLM and LocalAI do not publish `/props`; an unreachable node does not
            # either. Either way we have not been told, so nothing is assumed.
            return fallback
        # One queued request per slot, so a slot is never idle across the HTTP round trip.
        # Never below 2: a pool that drops to one thread cannot overlap anything at all.
        return max(2, sum(s + 1 for s in slots.values()))

    def pool_slots(self) -> dict[str, int | None]:
        """Per node, how many requests it says it runs at once — None when it does not say.

        Probed once per process and cached: the answer changes only when someone restarts the
        server, and `mapping` asks for it on every run.
        """
        with self._lock:
            if self._slots is not None:
                return self._slots
        probed = {u: _probe_slots(u) for u in self._url_of.values()}
        with self._lock:
            self._slots = probed
        return probed

    def pool_report(self) -> str:
        """One line naming what the pool actually is, for the run log.

        The pool had no voice: twelve of the thirteen addresses on the deploy host had left the
        tailnet and the only symptom was that grading took hours. A run should be able to say
        how many nodes answered and how much parallelism they offer, because "slow" and "gone"
        look identical from the outside.
        """
        slots = self.pool_slots()
        live = {u: s for u, s in slots.items() if s is not None}
        total = sum(live.values()) if live else 0
        parts = [f"{len(live)}/{len(slots)} node(s) answered"]
        if live:
            parts.append(f"{total} parallel slot(s)")
        dead = [u for u, s in slots.items() if s is None]
        if dead and live:
            parts.append(f"unreachable or not llama.cpp: {', '.join(dead)}")
        return f"[llm] pool {self.model_version}: " + "; ".join(parts)

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # Many local models don't honour response_format=json_object, so we instruct
        # firmly and rely on the robust parser in LLMProvider._parse_json.
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        last: Exception | None = None
        for _ in range(max(1, len(self._healthy))):
            client = self._next_client()
            try:
                resp = client.chat.completions.create(
                    model=self.model_version,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user},
                    ],
                )
            except Exception as exc:                              # noqa: BLE001
                last = exc
                self._quarantine(client)
                continue
            return self._parse_json(resp.choices[0].message.content or "{}")
        raise last if last else RuntimeError("no local LLM node answered")
