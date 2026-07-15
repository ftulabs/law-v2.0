"""OpenRouter LLM provider — access to many models (incl. free ones) via one
OpenAI-compatible endpoint. Great for the no-vendor-lock-in requirement.

Key is supplied at runtime (env/.env/secrets/dashboard) — never hardcoded here.
"""
from __future__ import annotations

from typing import Any

from ..config import settings
from .llm_base import LLMProvider

BASE_URL = "https://openrouter.ai/api/v1"


def _is_auth_error(e: Exception) -> bool:
    """A 401/403 from OpenRouter — the key is invalid/revoked/out-of-credit (same for every
    model, so there's no point failing over the whole pool)."""
    code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    return code in (401, 403) or type(e).__name__ in ("AuthenticationError", "PermissionDeniedError")


class OpenRouterLLM(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "deepseek/deepseek-v4-flash"):
        from openai import OpenAI

        if not api_key:
            raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY")
        self._client = OpenAI(
            base_url=BASE_URL,
            api_key=api_key,
            max_retries=0,   # our own model-fallover handles 429 — avoid SDK backoff stalls
            timeout=30.0,
            default_headers={  # optional attribution headers OpenRouter recommends
                "HTTP-Referer": "https://github.com/ftulabs/law-v2.0",
                "X-Title": "VeriTrade",
            },
        )
        self._chosen = model
        self.model_version = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # Not every model honours response_format=json_object, so we instruct strongly
        # and rely on the robust parser in LLMProvider._parse_json.
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        last_err: Exception | None = None
        for model in self._candidates():
            try:
                # Reasoning models (deepseek-v4-flash) spend the max_tokens budget on their
                # thinking BEFORE the JSON answer, and the thinking length varies per call —
                # a response can come back truncated (finish_reason=length) with empty or
                # half-written JSON. One retry with 4× the budget covers the long-thinking
                # tail; a still-broken response falls through so the caller can COUNT it as
                # a failed call instead of silently misreading it as "not relevant".
                parsed: dict[str, Any] = {}
                for cap in (settings.openrouter_max_tokens, settings.openrouter_max_tokens * 4):
                    resp = self._client.chat.completions.create(
                        model=model, temperature=0, max_tokens=cap,
                        messages=[{"role": "system", "content": sys_msg},
                                  {"role": "user", "content": user}],
                    )
                    self.model_version = model  # record the model that actually answered
                    choice = resp.choices[0]
                    parsed = self._parse_json(choice.message.content or "{}")
                    if parsed and not parsed.get("_parse_error"):
                        return parsed
                    if getattr(choice, "finish_reason", None) != "length":
                        break   # unparseable but NOT truncated → a bigger budget won't help
                return parsed
            except Exception as e:  # noqa: BLE001 — a paid model can transiently 429 under burst; fall over
                last_err = e
                # An AUTH failure (401/403) is the same for every model — the key itself is
                # invalid/revoked/out-of-credit. Don't churn the whole pool per call; fail fast
                # with a message that names the real cause (not "rate limits").
                if _is_auth_error(e):
                    raise RuntimeError(
                        "OpenRouter rejected the API key (HTTP 401/403 — 'User not found' means "
                        "the key is invalid, revoked, or the account was removed). Set a valid "
                        "OPENROUTER_API_KEY (openrouter.ai/keys), or switch LLM_PROVIDER."
                    ) from e
                continue
        raise RuntimeError(f"All OpenRouter models failed (last: {last_err})")

    def _candidates(self) -> list[str]:
        """Chosen model first, then the paid failover pool (no `:free` models)."""
        try:
            from .registry import OPENROUTER_PAID_MODELS as paid
        except Exception:
            paid = []
        ordered, seen = [], set()
        for m in [self._chosen, *paid]:
            if m and m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered
