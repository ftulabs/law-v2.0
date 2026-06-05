"""Self-hosted / local LLM provider (OpenAI-compatible endpoint).

Works with any server that speaks the OpenAI Chat Completions API — Ollama, vLLM,
LM Studio, llama.cpp server, LocalAI, text-generation-webui. Point `base_url` at the
server's `/v1` and pick a model it serves; the mapper is unchanged.

base_url / model / api_key come from env/.env/secrets/dashboard — never hardcoded.
Ollama (the common case) ignores the key, so it may be left empty.
"""
from __future__ import annotations

from typing import Any

from .llm_base import LLMProvider


class LocalLLM(LLMProvider):
    name = "local"

    def __init__(self, base_url: str, model: str, api_key: str = ""):
        from openai import OpenAI

        if not base_url:
            raise ValueError(
                "LLM_PROVIDER=local requires LOCAL_LLM_BASE_URL "
                "(e.g. http://gpu-lab:11434/v1 for Ollama)"
            )
        self._client = OpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key or "not-needed",   # Ollama ignores it; the SDK requires non-empty
            max_retries=1,
            timeout=120.0,                      # shared-lab GPUs can be slow to first token
        )
        self.model_version = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # Many local models don't honour response_format=json_object, so we instruct
        # firmly and rely on the robust parser in LLMProvider._parse_json.
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        resp = self._client.chat.completions.create(
            model=self.model_version,
            temperature=0,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user},
            ],
        )
        return self._parse_json(resp.choices[0].message.content or "{}")
