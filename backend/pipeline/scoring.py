"""ZONE 3 (optional) — RDTII Raw-Score assignment.

Mapping (Zone 2) decides WHICH indicator a provision satisfies. Scoring decides HOW
RESTRICTIVE that measure is on the methodology's 0 / 0.5 / 1 compliance-cost scale, and
writes the Database's "Raw Score", "Coverage" and "Impact or comments" for the measure.

Like the grader, the scorer judges ONLY the verbatim snippet against the indicator's own
scoring criteria (backend/rdtii/scoring_rubric.py) — it never invents law text. Each
(measure) is one independent LLM call; calls run concurrently and a failure degrades to a
conservative default rather than crashing the run. An offline mock produces deterministic
scores so the whole pipeline still runs with no key.

The per-measure score is the unit the Database stores. The INDICATOR-level score (one per
economy) is the most-restrictive measure — see `aggregate_indicator_scores` — including the
methodology rule that >1 sectoral (0.5) measure in 6.1/6.2 rolls up to 1.
"""
from __future__ import annotations

from collections import defaultdict

from ..config import settings
from ..providers import get_llm_provider
from ..providers.llm_base import LLMProvider
from ..rdtii import coerce_score, get_rubric
from ..schemas import EvidenceMapping

SCORE_SYSTEM = (
    "You are a scoring officer for the UNESCAP RDTII 2.1 framework. A legal MEASURE has "
    "already been matched to ONE indicator; assign its RAW SCORE on the methodology's "
    "compliance-cost scale, judging ONLY the verbatim snippet against the indicator's "
    "scoring criteria.\n\n"
    "The score is a RESTRICTIVENESS / compliance-cost grade, not a 'did we find it' flag:\n"
    "  1   = high compliance cost — a broad, all-sector or personal-data measure.\n"
    "  0.5 = medium — the measure bites only a SPECIFIC sector, specific data, or non-personal data.\n"
    "  0   = low / simplified — no restrictive requirement in the snippet.\n"
    "INVERTED indicators (P7-I1 comprehensive data-protection framework, P7-I2 dedicated "
    "cybersecurity framework): the polarity FLIPS — a desirable HORIZONTAL framework scores 0, "
    "a sectoral-only framework 0.5, and the absence of any framework 1. The RUBRIC states the "
    "exact tiers; OBEY them and pick the score whose criteria the snippet actually meets.\n\n"
    "Also decide COVERAGE: 'Horizontal' if the measure applies across all sectors / to a law of "
    "general application (e.g. a Companies, Tax or Employment Act, or a national data-protection "
    "Act); else a short scope phrase naming the sector or data type it is limited to (e.g. "
    "'Financial sector', 'Health data', 'Telecommunications').\n\n"
    "Write IMPACT as one or two sentences: state the rule and WHY it earns the score (cite the "
    "section). For a score of 0, say what is absent or why it is non-restrictive. <=320 chars.\n\n"
    "Return ONLY this JSON: {raw_score: number (one of 1, 0.5, 0), coverage: str, impact: str}"
)


def _score_prompt(m: EvidenceMapping) -> str:
    rb = get_rubric(m.indicator_id)
    rubric_txt = rb.prompt_block() if rb else f"{m.indicator_id}: score 1/0.5/0 by restrictiveness."
    allowed = "1 or 0" if (rb and rb.binary) else "1, 0.5 or 0"
    cov_hint = m.coverage or ("Sectoral" if m.scope_flag else "Horizontal")
    return (
        f"<RUBRIC>\n{rubric_txt}\n</RUBRIC>\n"
        f"<SCORE_INDICATOR>{m.indicator_id}</SCORE_INDICATOR>\n"
        f"<ALLOWED_SCORES>{allowed}</ALLOWED_SCORES>\n"
        f"<COVERAGE_HINT>{cov_hint}</COVERAGE_HINT>\n"
        f"<LAW>{m.law_name} — {m.article_section}</LAW>\n"
        f"<SNIPPET>{m.verbatim_snippet}</SNIPPET>\n"
        "Assign the raw score strictly from the RUBRIC tiers, set coverage, and justify in "
        "impact. Return the JSON object only."
    )


def _default_impact(m: EvidenceMapping, score: float) -> str:
    rb = get_rubric(m.indicator_id)
    tier = next((t for t in (rb.tiers if rb else ()) if t.score == score), None)
    crit = f" — {tier.criteria}" if tier else ""
    return f"Scored {score} for {m.indicator_id} ({m.article_section}){crit}."[:320]


def score_mappings(
    mappings: list[EvidenceMapping],
    llm: LLMProvider | None = None,
    log=lambda *_: None,
) -> list[EvidenceMapping]:
    """Assign raw_score + impact (+ refine coverage) on each mapping, in place. Returns the
    same list for chaining. Safe to call with an empty list or the mock LLM."""
    if not mappings:
        return mappings
    llm = llm or get_llm_provider()

    def _score(m: EvidenceMapping) -> EvidenceMapping:
        rb = get_rubric(m.indicator_id)
        try:
            out = llm.complete_json(SCORE_SYSTEM, _score_prompt(m))
            score = coerce_score(out.get("raw_score"), rb)
            cov = (out.get("coverage") or "").strip()
            impact = (out.get("impact") or "").strip()
        except Exception as e:  # noqa: BLE001 — a rate-limited call must not crash the run
            log(f"[score] LLM call failed ({type(e).__name__}) for {m.indicator_id}/"
                f"{m.law_name[:28]}; using conservative default")
            score, cov, impact = None, "", ""
        if score is None:
            # conservative fallback: a measure we matched is restrictive unless it's an
            # inverted indicator (where a found horizontal framework is the LOW-cost case).
            score = 0.0 if (rb and rb.inverted) else (1.0 if (m.coverage or "Horizontal") == "Horizontal" else 0.5)
        m.raw_score = score
        if cov:
            m.coverage = cov
        m.impact = (impact or _default_impact(m, score))[:320]
        return m

    workers = max(1, min(settings.mapping_concurrency, len(mappings)))
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_score, mappings))
    else:
        for m in mappings:
            _score(m)

    scored = sum(1 for m in mappings if m.raw_score is not None)
    dist = defaultdict(int)
    for m in mappings:
        dist[m.raw_score] += 1
    log(f"[score] {scored}/{len(mappings)} measures scored — "
        + " ".join(f"{k}:{dist[k]}" for k in sorted(dist, key=lambda x: -(x or 0))))
    return mappings


def aggregate_indicator_scores(mappings: list[EvidenceMapping]) -> dict[str, dict]:
    """Roll per-measure scores up to ONE score per indicator (the unit RDTII reports per
    economy). For ordinary (restrictive) indicators the MOST-RESTRICTIVE measure wins (max),
    with the 6.1/6.2 twist that ≥2 sectoral (0.5) measures roll up to 1 ('more than one
    measure in category 2'). For the INVERTED indicators (P7-I1, P7-I2) the polarity flips:
    the BEST framework found wins (min) — if any dedicated HORIZONTAL framework exists the
    indicator scores 0, even when sectoral instruments also turn up (e.g. SG 7.2 = 0 from the
    Cybersecurity Act 2018 despite a sectoral MAS cyber notice scoring 0.5 on its own). The
    answer key confirms this min behaviour. Indicators with no mapped measure are absent.
    Returns {indicator_id: {score, n_measures, n_half, basis}}."""
    from ..rdtii import get_rubric
    by_ind: dict[str, list[EvidenceMapping]] = defaultdict(list)
    for m in mappings:
        if m.raw_score is not None:
            by_ind[m.indicator_id].append(m)

    out: dict[str, dict] = {}
    for ind, ms in by_ind.items():
        scores = [m.raw_score for m in ms]
        n_half = sum(1 for s in scores if s == 0.5)
        rb = get_rubric(ind)
        if rb and rb.inverted:
            top = min(scores)
            basis = "best (most comprehensive) framework found — inverted indicator"
        else:
            top = max(scores)
            basis = "most-restrictive measure"
            if ind in ("P6-I1", "P6-I2") and top < 1.0 and n_half >= 2:
                top = 1.0
                basis = f"{n_half} sectoral (0.5) measures roll up to 1 per methodology"
        out[ind] = {"score": top, "n_measures": len(ms), "n_half": n_half, "basis": basis}
    return out
