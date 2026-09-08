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
from typing import Any

from ..config import settings

from .llm_base import LLMProvider


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
        self._reset_rotation()
        self.model_version = model

    def _reset_rotation(self) -> None:
        """(Re)build the rotation over the currently healthy clients."""
        # itertools.cycle is not thread-safe on its own; grading calls it from
        # `mapping_concurrency` threads at once, and an unsynchronised counter hands one node
        # two calls while another sits idle.
        self._healthy = list(self._clients)
        self._cycle = itertools.cycle(self._healthy)

    def _next_client(self):
        with self._lock:
            return next(self._cycle)

    def _quarantine(self, client) -> None:
        """Drop a node that failed. Measured 2026-09-07 on the twelve-node cluster: ten
        answered a grading call in 13-18s, one took 120s and one raised BadRequestError in
        1s. Left in the rotation those two collect a twelfth of the run each, which is how a
        twelve-node pool finished slower than a single healthy node."""
        with self._lock:
            if client in self._healthy and len(self._healthy) > 1:
                self._healthy.remove(client)
                self._cycle = itertools.cycle(self._healthy)

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
