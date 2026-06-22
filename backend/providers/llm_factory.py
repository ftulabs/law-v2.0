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
        # Zone-3 scoring requests carry a <SCORE_INDICATOR> tag; dispatch to the
        # deterministic mock scorer so the offline pipeline still produces raw scores.
        if "<SCORE_INDICATOR>" in user:
            return _mock_score(user)
        # The mapper packs a compact, parseable block into `user`. We read it back
        # rather than free-text parse, keeping the mock deterministic.
        snippet = _between(user, "<SNIPPET>", "</SNIPPET>").lower()
        terms = _split_terms(_between(user, "<QUERY_TERMS>", "</QUERY_TERMS>"))
        indicator_scope = _between(user, "<INDICATOR_SCOPE>", "</INDICATOR_SCOPE>").strip().lower() or "national"
        ind_block = _between(user, "<TARGET_INDICATOR>", "</TARGET_INDICATOR>")
        ind_id = ind_block.split("—")[0].strip() or "the indicator"
        ind_title = ind_block.split("—", 1)[1].strip().lower() if "—" in ind_block else "the indicator"
        law_block = _between(user, "<LAW>", "</LAW>")
        article = law_block.split("—", 1)[1].strip() if "—" in law_block else "This provision"

        # ── disambiguation: score the TARGET against every sibling, pick the best ──
        def overlap(term_list: list[str]) -> tuple[float, int]:
            # token-based: a phrase counts when most of its CONTENT words appear,
            # robust to punctuation / word-order ("collect, use or disclose" matches
            # the term "collect use or disclose"). Returns (score, strong_hits) where
            # a strong hit is a phrase whose content words are essentially all present.
            score, strong = 0.0, 0
            for t in term_list:
                ws = _content_words(t)
                if not ws:
                    continue
                frac = sum(1 for w in ws if w in snippet) / len(ws)
                if frac >= 0.7:
                    score += 1 + 0.5 * len(ws)
                    strong += 1
                elif frac >= 0.4:
                    score += frac
            return score, strong

        target_score, target_strong = overlap(terms)
        sib_scores = {sid: overlap(st)[0] for sid, st in _parse_siblings(user).items()}
        best_id, best_score = ind_id, target_score
        for sid, sc in sib_scores.items():
            if sc > best_score:                       # strict '>' → target wins ties
                best_id, best_score = sid, sc

        binding = any(b in snippet for b in BINDING_MARKERS)
        # require at least one STRONG phrase hit — kills mappings built only on weak,
        # incidental word overlap (e.g. a security clause drifting onto a rights indicator)
        target_wins = target_strong >= 1 and target_score >= best_score

        if target_wins:
            legal_match = min(1.0, 0.45 + 0.16 * target_score + (0.12 if binding else 0.0))
        else:
            legal_match = min(0.45, 0.20 + 0.08 * target_score)

        # scope alignment — sectoral instrument vs a national indicator → penalty + flag.
        # Check the law TITLE too (e.g. "MAS Notice … Banks") so it fires even when an
        # individual paragraph omits the marker words.
        scope_text = snippet + " " + law_block.lower()
        sectoral = any(m in scope_text for m in SECTORAL_MARKERS)
        scope_flag = None
        if indicator_scope == "national" and sectoral:
            scope_alignment = 0.35
            scope_flag = "SECTORAL_NOT_NATIONAL"
        else:
            scope_alignment = 0.95 if not sectoral else 0.8

        # Pillar-6 gate: the Pillar-6 (data-localisation) indicators only fit a provision
        # that concerns cross-border movement OR a localisation requirement (store/process/
        # host data in-country). Stops a generic domestic clause being mislabelled as a
        # localisation rule. Covers transfer (6.1/6.4), storage (6.2) and infrastructure (6.3).
        pillar6 = ind_id.upper().startswith("P6")
        localisation_ctx = any(k in snippet for k in (
            "transfer", "cross-border", "cross border", "outside", "overseas", "to a country",
            "place outside", "another country", "foreign", "stored", "store", "storage",
            "located in", "within the territory", "in the country", "locally", "local server",
            "data centre", "data center", "infrastructure", "server"))
        gate_ok = (not pillar6) or localisation_ctx
        if not gate_ok:
            legal_match = min(legal_match, 0.3)

        # Mirror the real-LLM schema (operative_rule / satisfies_target / better_sibling /
        # relevant) so the offline grader exercises the SAME contract the prompt asks for.
        satisfies_target = target_wins and gate_ok and legal_match >= 0.5 and scope_alignment >= 0.5
        better_sibling = best_id if (best_id and best_id != ind_id and not satisfies_target) else None
        relevant = satisfies_target and not better_sibling
        rationale = _rationale(article, ind_id, ind_title, snippet, binding, sectoral,
                               indicator_scope, relevant, best_id)
        return {
            "operative_rule": f"This {article} {_verb(snippet)} {ind_title.lower()}.",
            "satisfies_target": satisfies_target,
            "better_sibling": better_sibling,
            "relevant": relevant,
            "best_fit_indicator": best_id,   # kept for back-compat / debugging
            "legal_match": round(legal_match, 3),
            "scope_alignment": round(scope_alignment, 3),
            "scope_flag": scope_flag,
            "rationale": rationale,
        }


def _verb(snippet: str) -> str:
    if "shall not" in snippet or "may not" in snippet or "must not" in snippet:
        return "prohibits"
    if "shall" in snippet or "must" in snippet or "required to" in snippet:
        return "requires"
    if "may " in snippet or "permit" in snippet or "is allowed" in snippet:
        return "permits"
    return "establishes obligations on"


def _rationale(article, ind_id, ind_title, snippet, binding, sectoral, scope, relevant, best_id) -> str:
    """Template format: 'This [article] [verb] [what]. Maps to [indicator] because [logic].'"""
    verb = _verb(snippet)
    if not relevant:
        if best_id and best_id != ind_id:
            return (f"This {article} relates to {ind_title} but indicator {best_id} fits its operative "
                    f"rule better; not mapped to {ind_id}.")[:300]
        return (f"This {article} relates to {ind_title} but does not satisfy {ind_id}: "
                f"no operative rule of the required scope in the snippet.")[:300]
    because = ("it uses binding obligation language matching the indicator's legal test"
               if binding else "its wording matches the indicator's legal test")
    if sectoral and scope == "national":
        because = ("the text is sector-specific (flagged SECTORAL_NOT_NATIONAL) and cannot stand "
                   "as national-scope evidence without review")
    return f"This {article} {verb} {ind_title}. Maps to {ind_id} because {because}."[:300]


_STOP = {"of", "the", "a", "to", "or", "and", "for", "in", "on", "that", "is", "as",
         "an", "by", "it", "his", "her", "any", "with", "be", "are", "this"}


def _content_words(phrase: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", phrase.lower()) if w not in _STOP and len(w) > 2]


def _split_terms(block: str) -> list[str]:
    return [t.strip().lower() for t in block.split("|") if t.strip()]


def _parse_siblings(user: str) -> dict[str, list[str]]:
    """Parse the <SIBLINGS> block: 'ID :: title — desc :: t1 | t2 | t3' per line."""
    out: dict[str, list[str]] = {}
    for line in _between(user, "<SIBLINGS>", "</SIBLINGS>").splitlines():
        parts = line.split("::")
        if len(parts) >= 3:
            out[parts[0].strip()] = _split_terms(parts[2])
    return out


def _between(text: str, a: str, b: str) -> str:
    m = re.search(re.escape(a) + r"(.*?)" + re.escape(b), text, re.DOTALL)
    return m.group(1).strip() if m else ""


# explicit duration (P7-I3 needs a SPECIFIED minimum period to score 1)
_DURATION_RE = re.compile(
    r"\b\d+\s*(?:year|years|month|months|day|days|week|weeks)\b"
    r"|\b(?:one|two|three|four|five|six|seven|ten|twelve)\s+(?:year|years|month|months|days?)\b",
    re.IGNORECASE,
)


def _mock_score(user: str) -> dict[str, Any]:
    """Deterministic offline scorer for Zone 3 — coarse but rule-aligned. A real LLM does the
    nuanced reading (specific-data vs all-sector, court-order carve-outs); the mock keeps the
    pipeline runnable with no key and follows the rubric's polarity + binary tiers."""
    from ..rdtii.scoring_rubric import get_rubric

    ind_id = _between(user, "<SCORE_INDICATOR>", "</SCORE_INDICATOR>").strip()
    hint = _between(user, "<COVERAGE_HINT>", "</COVERAGE_HINT>").strip() or "Horizontal"
    law_block = _between(user, "<LAW>", "</LAW>")
    article = law_block.split("—", 1)[1].strip() if "—" in law_block else "This provision"
    snippet = _between(user, "<SNIPPET>", "</SNIPPET>")
    rb = get_rubric(ind_id)

    scope_text = (snippet + " " + law_block).lower()
    sectoral = (hint.lower() != "horizontal") or any(m in scope_text for m in SECTORAL_MARKERS)
    coverage = hint if hint.lower() == "horizontal" or sectoral is False else hint
    if sectoral and hint.lower() == "horizontal":
        coverage = "Sectoral"

    if rb and rb.inverted:
        # P7-I1 / P7-I2: a found framework is the LOW-cost case → horizontal 0, sectoral 0.5
        score = 0.5 if sectoral else 0.0
        why = ("a sectoral-only framework (scores 0.5)" if sectoral
               else "a comprehensive horizontal framework (scores 0)")
    elif ind_id == "P7-I3":
        has_duration = bool(_DURATION_RE.search(snippet))
        score = 1.0 if has_duration else 0.0
        why = ("a specified minimum retention period is stated (scores 1)" if has_duration
               else "no specific minimum duration is stated in the snippet (scores 0)")
    elif rb and rb.binary:
        # P6-I3 infrastructure, P7-I5 government access: presence of the matched rule → 1
        score = 1.0
        why = "the matched requirement is present (binary indicator: 1)"
    else:
        # tiered 6.1 / 6.2 / 6.4 / 7.4 — all-sector/horizontal → 1, sector-limited → 0.5
        score = 0.5 if sectoral else 1.0
        why = ("the measure is limited to a specific sector/data (scores 0.5)" if sectoral
               else "the measure applies horizontally / to all sectors (scores 1)")

    impact = f"{article}: {why}, mapped to {ind_id}."[:320]
    return {"raw_score": score, "coverage": coverage, "impact": impact}


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
    if name == "openrouter":
        from .llm_openrouter import OpenRouterLLM
        return OpenRouterLLM(api_key or settings.openrouter_api_key, model or settings.openrouter_model)
    if name == "gemini":
        from .llm_gemini import GeminiLLM
        return GeminiLLM(api_key or settings.gemini_api_key, model or settings.gemini_model)
    if name == "local":
        from .llm_local import LocalLLM
        # base_url is env/.env/dashboard-driven (settings); key optional (Ollama ignores it)
        return LocalLLM(settings.local_llm_base_url, model or settings.local_llm_model,
                        api_key or settings.local_llm_api_key)
    raise ValueError(f"Unknown LLM_PROVIDER: {name}")
