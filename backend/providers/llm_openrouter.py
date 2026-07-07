"""OpenRouter LLM provider — access to many models (incl. free ones) via one
OpenAI-compatible endpoint. Great for the no-vendor-lock-in requirement.

Key is supplied at runtime (env/.env/secrets/dashboard) — never hardcoded here.
"""
from __future__ import annotations

from typing import Any

from .llm_base import LLMProvider

BASE_URL = "https://openrouter.ai/api/v1"


def _is_auth_error(e: Exception) -> bool:
    """A 401/403 from OpenRouter — the key is invalid/revoked/out-of-credit (same for every
    model, so there's no point failing over the whole pool)."""
    code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    return code in (401, 403) or type(e).__name__ in ("AuthenticationError", "PermissionDeniedError")


class OpenRouterLLM(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.3-70b-instruct:free"):
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
        # Not all free models honour response_format=json_object, so we instruct
        # strongly and rely on the robust parser in LLMProvider._parse_json.
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        last_err: Exception | None = None
        for model in self._candidates():
            try:
                resp = self._client.chat.completions.create(
                    model=model, temperature=0,
                    messages=[{"role": "system", "content": sys_msg},
                              {"role": "user", "content": user}],
                )
                self.model_version = model  # record the model that actually answered
                return self._parse_json(resp.choices[0].message.content or "{}")
            except Exception as e:  # noqa: BLE001 — free models are often rate-limited; fall over
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
        """Chosen model first, then reliable PAID models, then the free pool. A `:free` model
        that 429s therefore fails over to a PAID model (leveraging a funded key) instead of
        dead-ending on the shared free tier — the cause of near-empty large runs."""
        try:
            from .registry import OPENROUTER_FREE_MODELS as free, OPENROUTER_PAID_MODELS as paid
        except Exception:
            free, paid = [], []
        ordered, seen = [], set()
        for m in [self._chosen, *paid, *free]:
            if m and m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered
