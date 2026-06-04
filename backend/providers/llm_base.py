"""LLM provider interface used by the mapping engine.

We deliberately keep the surface tiny: a single `complete_json` that takes a
system + user prompt and returns parsed JSON. The mapper is provider-agnostic;
swapping Anthropic↔OpenAI↔mock requires no mapper changes.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    name: str = "base"
    model_version: str = "unknown"

    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Return a JSON object. Implementations must be robust to fenced output."""
        raise NotImplementedError

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        # strip ```json fences if present
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            m = re.search(r"(\{.*\})", raw, re.DOTALL)
            if m:
                raw = m.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_parse_error": True, "_raw": raw[:2000]}
