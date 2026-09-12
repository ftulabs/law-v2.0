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
        self._clients = [
            OpenAI(
                base_url=u,
                api_key=api_key or "not-needed",  # Ollama ignores it; the SDK requires non-empty
                max_retries=1,
                timeout=timeout if timeout is not None else settings.local_llm_timeout_seconds,
            )
            for u in urls
        ]
        self._lock = threading.Lock()
        self._benched: dict[int, tuple[Any, float]] = {}   # id(client) -> (client, benched at)
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
        """
        from ..config import settings                              # noqa: PLC0415
        per_node = max(1, int(settings.local_llm_calls_per_node))
        return max(int(settings.mapping_concurrency), per_node * len(self._clients))

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
