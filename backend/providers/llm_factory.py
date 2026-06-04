"""LLM provider factory + a deterministic, *grounded* mock.

The mock is not random: it scores a (provision, indicator) pair using transparent
lexical signals derived from the indicator's `query_terms` and `legal_test`, and
detects sectoral language to flag scope confusion. This lets the whole mapping +
confidence + routing flow run offline and behave like a conservative grader —
ideal for a reproducible demo. Set LLM_PROVIDER=anthropic|openai for real reasoning.
"""
from __future__ import annotations

import re
from typing import Any

from ..config import settings
from .llm_base import LLMProvider

# words that signal a *sectoral* (not national) instrument
SECTORAL_MARKERS = [
    "monetary authority", "mas notice", "financial institution", "licensed bank",
    "insurer", "capital markets", "telecommunications licensee", "healthcare provider",
    "prudential", "for banks", "financial sector",
]
BINDING_MARKERS = ["shall", "must", "is required to", "may not", "shall not", "required to"]


class MockLLM(LLMProvider):
    name = "mock"
    model_version = "mock-grounded-grader-0.1"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # The mapper packs a compact, parseable block into `user`. We read it back
        # rather than free-text parse, keeping the mock deterministic.
        snippet_raw = _between(user, "<SNIPPET>", "</SNIPPET>")
        snippet = snippet_raw.lower()
        legal_test = _between(user, "<LEGAL_TEST>", "</LEGAL_TEST>").lower()
        terms = [t.strip().lower() for t in _between(user, "<QUERY_TERMS>", "</QUERY_TERMS>").split("|") if t.strip()]
        indicator_scope = _between(user, "<INDICATOR_SCOPE>", "</INDICATOR_SCOPE>").strip().lower() or "national"
        ind_block = _between(user, "<INDICATOR>", "</INDICATOR>")
        ind_id = ind_block.split("—")[0].strip() or "the indicator"
        ind_title = ind_block.split("—", 1)[1].strip().lower() if "—" in ind_block else "the indicator"
        law_block = _between(user, "<LAW>", "</LAW>")
        article = law_block.split("—", 1)[1].strip() if "—" in law_block else "This provision"

        # signal 1: term overlap (semantic+lexical relevance)
        hits = [t for t in terms if t and t in snippet]
        term_score = min(1.0, len(hits) / max(2, len(terms) * 0.5)) if terms else 0.0

        # signal 2: binding language (legal, not merely topical)
        binding = any(b in snippet for b in BINDING_MARKERS)
        legal_match = round(min(1.0, 0.35 + 0.5 * term_score + (0.15 if binding else 0.0)), 3)

        # signal 3: scope alignment — sectoral text against a national indicator → penalty + flag.
        # Check the law TITLE too: a sectoral instrument's name (e.g. "MAS Notice … Banks")
        # signals scope even when an individual paragraph omits the marker words.
        scope_text = snippet + " " + law_block.lower()
        sectoral = any(m in scope_text for m in SECTORAL_MARKERS)
        scope_flag = None
        if indicator_scope == "national" and sectoral:
            scope_alignment = 0.35
            scope_flag = "SECTORAL_NOT_NATIONAL"
        else:
            scope_alignment = 0.95 if not sectoral else 0.8

        relevant = legal_match >= 0.5 and scope_alignment >= 0.5

        rationale = _rationale(article, ind_id, ind_title, snippet, binding, sectoral, indicator_scope, relevant)
        return {
            "relevant": relevant,
            "legal_match": legal_match,
            "scope_alignment": round(scope_alignment, 3),
            "scope_flag": scope_flag,
            "rationale": rationale,
            "matched_terms": hits,
        }


def _verb(snippet: str) -> str:
    if "shall not" in snippet or "may not" in snippet or "must not" in snippet:
        return "prohibits"
    if "shall" in snippet or "must" in snippet or "required to" in snippet:
        return "requires"
    if "may " in snippet or "permit" in snippet or "is allowed" in snippet:
        return "permits"
    return "establishes obligations on"


def _rationale(article, ind_id, ind_title, snippet, binding, sectoral, scope, relevant) -> str:
    """Template format: 'This [article] [verb] [what]. Maps to [indicator] because [logic].'"""
    verb = _verb(snippet)
    if not relevant:
        return (f"This {article} relates to {ind_title} but does not satisfy {ind_id}: "
                f"no binding rule of the required scope found in the snippet.")[:300]
    because = ("it uses binding obligation language matching the indicator's legal test"
               if binding else "its wording matches the indicator's legal test")
    if sectoral and scope == "national":
        because = ("the text is sector-specific (flagged SECTORAL_NOT_NATIONAL) and cannot stand "
                   "as national-scope evidence without review")
    return f"This {article} {verb} {ind_title}. Maps to {ind_id} because {because}."[:300]


def _between(text: str, a: str, b: str) -> str:
    m = re.search(re.escape(a) + r"(.*?)" + re.escape(b), text, re.DOTALL)
    return m.group(1).strip() if m else ""


def get_llm_provider(name: str | None = None, model: str | None = None,
                     api_key: str | None = None) -> LLMProvider:
    """`model` and `api_key` override the env defaults at runtime — this is what
    lets the dashboard switch LLM/model/key without editing `.env`."""
    name = (name or settings.llm_provider or "mock").lower()
    if name == "mock":
        return MockLLM()
    if name == "anthropic":
        from .llm_anthropic import AnthropicLLM
        return AnthropicLLM(api_key or settings.anthropic_api_key, model or settings.anthropic_model)
    if name == "openai":
        from .llm_openai import OpenAILLM
        return OpenAILLM(api_key or settings.openai_api_key, model or settings.openai_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {name}")
