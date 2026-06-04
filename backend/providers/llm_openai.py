"""OpenAI LLM provider (optional import)."""
from __future__ import annotations

from typing import Any

from .llm_base import LLMProvider


class OpenAILLM(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import OpenAI

        if not api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self.model_version = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self.model_version,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return self._parse_json(resp.choices[0].message.content or "{}")
