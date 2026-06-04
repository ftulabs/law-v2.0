"""Anthropic Claude LLM provider (optional import)."""
from __future__ import annotations

from typing import Any

from .llm_base import LLMProvider


class AnthropicLLM(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-4-8"):
        import anthropic

        if not api_key:
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model_version = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        msg = self._client.messages.create(
            model=self.model_version,
            max_tokens=1500,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return self._parse_json(text)
