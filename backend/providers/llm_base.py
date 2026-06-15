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
        # Reasoning models (Qwen3, DeepSeek-R1, gpt-oss, …) emit a <think>…</think> chain of
        # thought BEFORE the answer — and the thinking itself often contains draft JSON. Drop
        # it first, else the greedy object-grab below splices thinking into the result.
        if "</think>" in raw:
            raw = raw.rsplit("</think>", 1)[-1].strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # strip ```json fences if present
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        # Try the whole string, then each balanced {...} object — LAST first, since the final
        # object is the model's answer when prose/drafts precede it.
        for cand in [raw, *reversed(LLMProvider._json_objects(raw))]:
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        return {"_parse_error": True, "_raw": raw[:2000]}

    @staticmethod
    def _json_objects(s: str) -> list[str]:
        """Every top-level balanced {...} span (brace-matched, string-aware)."""
        out: list[str] = []
        depth = start = 0
        instr = esc = False
        start = -1
        for i, ch in enumerate(s):
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
                continue
            if ch == '"':
                instr = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    out.append(s[start:i + 1])
        return out
