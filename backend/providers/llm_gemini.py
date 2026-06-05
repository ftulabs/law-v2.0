"""Google Gemini LLM provider (via the OpenAI-compatible endpoint).

Gemini exposes an OpenAI-compatible API at
  https://generativelanguage.googleapis.com/v1beta/openai/
so we reuse the OpenAI SDK with that base_url and the key as a Bearer token. The key is
read from env/.env/secrets (GEMINI_API_KEY) — never hardcoded or committed.
"""
from __future__ import annotations

from typing import Any

from .llm_base import LLMProvider

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiLLM(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from openai import OpenAI

        if not api_key:
            raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")
        self._client = OpenAI(base_url=BASE_URL, api_key=api_key, max_retries=1, timeout=60.0)
        self.model_version = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # Gemini follows the JSON instruction well; ask firmly and lean on the robust
        # parser (some responses wrap JSON in code fences).
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        resp = self._client.chat.completions.create(
            model=self.model_version,
            temperature=0,
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": user}],
        )
        return self._parse_json(resp.choices[0].message.content or "{}")
