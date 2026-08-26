"""OpenRouter LLM provider — access to many models (incl. free ones) via one
OpenAI-compatible endpoint. Great for the no-vendor-lock-in requirement.

Key is supplied at runtime (env/.env/secrets/dashboard) — never hardcoded here.
"""
from __future__ import annotations

import random
import time
from typing import Any

from ..config import settings
from .. import metering
from .llm_base import LLMProvider

BASE_URL = "https://openrouter.ai/api/v1"


def _is_auth_error(e: Exception) -> bool:
    """A 401/403 from OpenRouter — the key is invalid/revoked/out-of-credit (same for every
    model, so there's no point failing over the whole pool)."""
    code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    return code in (401, 403) or type(e).__name__ in ("AuthenticationError", "PermissionDeniedError")


def _is_key_quota_exhausted(e: Exception) -> bool:
    """A 403 that is really a LIMIT, not a dead key: 'Key limit exceeded (daily limit)'.

    Measured on a shared hackathon key 2026-08-25: the paid pool answers 403 with this body
    while free models on the SAME key answer 200 — the limit binds credits, not the key. So it
    must not raise the 'your API key is invalid' panic below: the honest response is to stop
    burning candidates (every paid model will say the same until the window resets) and let
    the caller decide.
    """
    body = str(getattr(e, "body", None) or e)[:500].lower()
    return ("key limit" in body or "daily limit" in body
            or "credit limit" in body or "monthly limit" in body)


def _is_rate_limited(e: Exception) -> bool:
    """A 429 from OpenRouter or the upstream provider.

    Kept separate from every other failure because the right response is the opposite one. A
    model returning 400, timing out, or emitting unparseable output has a problem another model
    would not have — failing over is correct. A model returning 429 has no problem at all: we
    are asking too fast, and failing over quietly answers the call with an engine we did not
    declare.
    """
    code = (getattr(e, "status_code", None)
            or getattr(getattr(e, "response", None), "status_code", None))
    return code == 429 or type(e).__name__ == "RateLimitError" or "429" in str(e)[:200]


class OpenRouterLLM(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "deepseek/deepseek-v4-flash"):
        from openai import OpenAI

        if not api_key:
            raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY")
        self._client = OpenAI(
            base_url=BASE_URL,
            api_key=api_key,
            max_retries=0,   # we classify and back off ourselves (see _is_rate_limited);
                             # the SDK's blind retry would stall a 16-way burst
            timeout=30.0,
            default_headers={  # optional attribution headers OpenRouter recommends
                "HTTP-Referer": "https://github.com/ftulabs/law-v2.0",
                "X-Title": "VeriTrade",
            },
        )
        self._chosen = model
        self.model_version = model

    def _ask(self, model: str, sys_msg: str, user: str) -> dict[str, Any]:
        """One model, one answer. Raises on any transport failure so the caller classifies it.

        Reasoning models (deepseek-v4-flash) spend the max_tokens budget on their thinking
        BEFORE the JSON answer, and the thinking length varies per call — a response can come
        back truncated (finish_reason=length) with empty or half-written JSON. One retry with
        4x the budget covers the long-thinking tail; a still-broken response is returned so the
        caller can COUNT it as a failed call rather than silently misread it as "not relevant".
        """
        parsed: dict[str, Any] = {}
        for cap in (settings.openrouter_max_tokens, settings.openrouter_max_tokens * 4):
            t0 = time.monotonic()
            resp = self._client.chat.completions.create(
                model=model, temperature=0, max_tokens=cap,
                messages=[{"role": "system", "content": sys_msg},
                          {"role": "user", "content": user}],
            )
            self.model_version = model      # record the model that actually answered
            choice = resp.choices[0]
            # Metered here rather than at the call site: this is the only place that sees the
            # token counts, and a retry at 4x the budget is a second billable call that a
            # caller-side counter would miss entirely.
            usage = getattr(resp, "usage", None)
            metering.record_llm(model, getattr(usage, "prompt_tokens", 0) or 0,
                                getattr(usage, "completion_tokens", 0) or 0,
                                time.monotonic() - t0)
            parsed = self._parse_json(choice.message.content or "{}")
            if parsed and not parsed.get("_parse_error"):
                return parsed
            if getattr(choice, "finish_reason", None) != "length":
                break       # unparseable but NOT truncated → a bigger budget will not help
        return parsed

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # Not every model honours response_format=json_object, so we instruct strongly
        # and rely on the robust parser in LLMProvider._parse_json.
        sys_msg = system + "\nReturn ONLY a valid JSON object, no prose, no code fences."
        last_err: Exception | None = None
        for model in self._candidates():
            try:
                # A rate limit is not a model failure, and treating it as one was a real defect:
                # the old code fell straight over to a DIFFERENT model on 429, so a run against
                # a busy model completed normally while most answers came from somewhere else.
                # Criterion C5b is marked by watching the DECLARED engine do the work, and the
                # bake-off measured mistral-small-3.2-24b returning 429 on 44 of 58 calls at
                # eight-way concurrency — the pipeline runs sixteen. Wait it out first; fail
                # over only for failures another model could actually fix.
                for attempt in range(max(1, settings.openrouter_rate_limit_retries)):
                    try:
                        return self._ask(model, sys_msg, user)
                    except Exception as exc:            # noqa: BLE001 — classified right here
                        if not _is_rate_limited(exc):
                            raise
                        if attempt == settings.openrouter_rate_limit_retries - 1:
                            raise
                        # Jittered, so sixteen workers do not all retry on the same tick and
                        # rebuild the burst that caused the 429 in the first place.
                        time.sleep(min(2 ** attempt,
                                       max(1, settings.openrouter_backoff_cap))
                                   * (1.0 + random.random()))
            except Exception as e:  # noqa: BLE001 — this model is out; try the next one
                last_err = e
                # An AUTH failure (401/403) is the same for every model — the key itself is
                # invalid/revoked/out-of-credit. Don't churn the whole pool per call; fail fast
                # with a message that names the real cause (not "rate limits").
                if _is_auth_error(e):
                    if _is_key_quota_exhausted(e):
                        break       # every remaining candidate is paid and will say the same
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
