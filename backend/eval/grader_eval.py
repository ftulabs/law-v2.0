"""Grader + confidence-weight experiment (the only stage that spends LLM budget).

Retrieval quality is measurable offline; grader quality is not. This builds a labelled pair
set from the judges' Database and runs the SHIPPED grading prompt over it, so three things
can be measured rather than assumed:

  1. grader recall   — does it accept the provision the panel actually cited?
  2. grader FPR      — how often does it accept a provision from a law the panel did NOT cite
                       for that indicator, when that provision is a known sibling-indicator
                       answer (the P6-I1/P6-I4 and P7-I1/P7-I2 confusions)?
  3. confidence      — with the four signals recorded per pair, weights can be FITTED to
                       separate correct from incorrect instead of being hand-chosen.

Negatives are constructed, not sampled at random: a provision the panel cited for indicator X
is used as a negative for a SIBLING indicator Y only when the panel did not also cite it for
Y. That is the discrimination that actually fails in production, and a random negative
(a fisheries provision vs a data indicator) measures nothing.

Every call is metered against a hard USD budget and the run stops when it would exceed it.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import ROOT
from ..rdtii import get_indicator, get_indicators, siblings
from ..schemas import Provision

# OpenRouter list price, USD per million tokens (verified against the live /models feed).
PRICING = {
    "deepseek/deepseek-v4-flash": (0.064, 0.129),
    "google/gemini-2.5-flash": (0.300, 2.500),
    "openai/gpt-4o-mini": (0.150, 0.600),
}
OUT_DIR = ROOT / "logs"


@dataclass
class Pair:
    economy: str
    indicator_id: str
    provision_id: str
    law_name: str
    article_section: str
    text: str
    label: int                 # 1 = the panel cited this provision for this indicator
    kind: str                  # positive | sibling_negative | random_negative
    source_indicator: str = ""  # for sibling negatives: the indicator it IS the answer to


@dataclass
class Graded:
    pair: Pair
    satisfied: bool = False
    legal_match: float = 0.0
    grounding: float = 0.0
    scope_alignment: float = 0.0
    retrieval_score: float = 0.0
    rationale: str = ""
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ─────────────────────────── pair construction ───────────────────────────
def build_pairs(economies=("SG", "AU", "MY"), sibling_per_indicator: int = 2,
                random_per_indicator: int = 1, seed: int = 20260801) -> list[Pair]:
    import random

    from .harness import (load_provisions, section_matches, targets_by_indicator,
                          version_law_map)
    rnd = random.Random(seed)
    pairs: list[Pair] = []
    for econ in economies:
        provs = load_provisions(econ)
        v2l = version_law_map(econ)
        targets = targets_by_indicator(econ)
        by_indicator_positive: dict[str, list[Provision]] = {}
        for ind_id, t in targets.items():
            hits = []
            for p in provs:
                lid = v2l.get(p.doc_id)
                if lid in t["law_ids"] and t["sections"].get(lid) \
                        and section_matches(p.article_section, t["sections"][lid]):
                    hits.append(p)
            by_indicator_positive[ind_id] = hits
            for p in hits:
                pairs.append(Pair(econ, ind_id, p.provision_id, p.law_name, p.article_section,
                                  p.verbatim_snippet, 1, "positive"))
        # sibling negatives: a confirmed answer for X, offered to a sibling Y it is NOT an
        # answer to. This is the exact discrimination the legal_test is supposed to make.
        for ind_id, hits in by_indicator_positive.items():
            for sib in siblings(ind_id):
                if sib.indicator_id in targets and any(
                        p.provision_id in {h.provision_id for h in hits}
                        for p in by_indicator_positive.get(sib.indicator_id, [])):
                    continue          # co-cited for both → not a negative
                for p in hits[:sibling_per_indicator]:
                    pairs.append(Pair(econ, sib.indicator_id, p.provision_id, p.law_name,
                                      p.article_section, p.verbatim_snippet, 0,
                                      "sibling_negative", source_indicator=ind_id))
        # random negatives: sanity floor — an unrelated provision must be rejected
        pool = [p for p in provs if len(p.verbatim_snippet) > 400]
        for ind in get_indicators(None):
            for p in rnd.sample(pool, min(random_per_indicator, len(pool))):
                pairs.append(Pair(econ, ind.indicator_id, p.provision_id, p.law_name,
                                  p.article_section, p.verbatim_snippet, 0, "random_negative"))
    return pairs


# ─────────────────────────── grading ───────────────────────────
def _cost(model: str, prompt_t: int, completion_t: int) -> float:
    pin, pout = PRICING.get(model, (0.2, 0.8))
    return prompt_t / 1e6 * pin + completion_t / 1e6 * pout


def grade_pairs(pairs: list[Pair], budget_usd: float = 5.0, concurrency: int = 8,
                log=print) -> tuple[list[Graded], dict]:
    """Run the SHIPPED prompt over every pair, stopping before `budget_usd` is exceeded."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from ..config import settings
    from ..pipeline import confidence as conf
    from ..pipeline.mapping import SYSTEM, _user_prompt
    from ..providers import get_llm_provider

    llm = get_llm_provider()
    model = getattr(llm, "model_version", "") or settings.openrouter_model
    spent = {"usd": 0.0, "calls": 0, "prompt": 0, "completion": 0}
    results: list[Graded] = []
    stop = {"flag": False}

    def _one(pair: Pair) -> Graded:
        g = Graded(pair=pair)
        if stop["flag"]:
            g.error = "budget"
            return g
        ind = get_indicator(pair.indicator_id)
        prov = Provision(provision_id=pair.provision_id, doc_id="eval",
                         economy=pair.economy, law_name=pair.law_name,
                         article_section=pair.article_section,
                         verbatim_snippet=pair.text, source_url="")
        try:
            out = llm.complete_json(SYSTEM, _user_prompt(ind, prov))
        except Exception as e:  # noqa: BLE001
            g.error = f"{type(e).__name__}: {e}"[:160]
            return g
        g.satisfied = bool(out.get("satisfied") or out.get("relevant"))
        try:
            g.legal_match = float(out.get("legal_match") or 0.0)
        except (TypeError, ValueError):
            g.legal_match = 0.0
        g.rationale = str(out.get("rationale") or "")[:400]
        snippet = str(out.get("snippet") or out.get("verbatim_snippet") or "")
        g.grounding = conf.snippet_grounding(snippet or pair.text[:200], pair.text)
        g.scope_alignment = 1.0 if (ind.scope or "national") == "national" else 0.5
        # token accounting, when the provider surfaced it
        usage = getattr(llm, "last_usage", None) or {}
        g.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        g.completion_tokens = int(usage.get("completion_tokens") or 0)
        return g

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_one, p): p for p in pairs}
        for i, fut in enumerate(as_completed(futs), 1):
            g = fut.result()
            results.append(g)
            spent["calls"] += 1
            spent["prompt"] += g.prompt_tokens
            spent["completion"] += g.completion_tokens
            # fall back to a conservative estimate when the provider hides usage
            est = _cost(model, g.prompt_tokens or 2000, g.completion_tokens or 3000)
            spent["usd"] += est
            if spent["usd"] >= budget_usd * 0.95:
                stop["flag"] = True
            if i % 25 == 0:
                log(f"[grader-eval] {i}/{len(pairs)} calls, ~${spent['usd']:.2f}, "
                    f"{time.perf_counter()-t0:.0f}s")
    spent["model"] = model
    return results, spent


# ─────────────────────────── metrics + weight fitting ───────────────────────────
def grader_metrics(results: list[Graded]) -> dict:
    ok = [g for g in results if not g.error]
    pos = [g for g in ok if g.pair.label == 1]
    sib = [g for g in ok if g.pair.kind == "sibling_negative"]
    rnd = [g for g in ok if g.pair.kind == "random_negative"]

    def rate(rows):
        return round(sum(g.satisfied for g in rows) / max(len(rows), 1), 3)
    return {
        "graded": len(ok), "errors": len(results) - len(ok),
        "recall_on_cited": rate(pos), "n_positive": len(pos),
        "accept_on_sibling_negative": rate(sib), "n_sibling": len(sib),
        "accept_on_random_negative": rate(rnd), "n_random": len(rnd),
    }


def fit_weights(results: list[Graded], step: float = 0.05) -> dict:
    """Grid-search the four confidence weights for the best separation of cited from
    non-cited pairs, measured by ROC AUC (threshold-free) and by accuracy at the shipped
    auto-accept cut. Weights are constrained to sum to 1 and to stay non-negative, so the
    result stays interpretable and auditable — the point of the four-signal design."""
    ok = [g for g in results if not g.error]
    if not ok or not any(g.pair.label for g in ok):
        return {"error": "no labelled results"}

    def auc(weights):
        s = []
        for g in ok:
            f = (weights[0] * g.retrieval_score + weights[1] * g.legal_match
                 + weights[2] * g.grounding + weights[3] * g.scope_alignment)
            s.append((f, g.pair.label))
        pos = [x for x, y in s if y == 1]
        neg = [x for x, y in s if y == 0]
        if not pos or not neg:
            return 0.0
        wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
        return wins / (len(pos) * len(neg))

    best, best_auc = None, -1.0
    grid = [round(x * step, 3) for x in range(int(1 / step) + 1)]
    for w1 in grid:
        for w2 in grid:
            for w3 in grid:
                w4 = round(1 - w1 - w2 - w3, 3)
                if w4 < 0:
                    continue
                a = auc((w1, w2, w3, w4))
                if a > best_auc:
                    best_auc, best = a, (w1, w2, w3, w4)
    from ..pipeline.confidence import WEIGHTS
    shipped = (WEIGHTS["retrieval_score"], WEIGHTS["legal_match"],
               WEIGHTS["snippet_grounding"], WEIGHTS["scope_alignment"])
    return {
        "best_weights": dict(zip(("retrieval_score", "legal_match", "snippet_grounding",
                                  "scope_alignment"), best)),
        "best_auc": round(best_auc, 4),
        "shipped_weights": dict(zip(("retrieval_score", "legal_match", "snippet_grounding",
                                     "scope_alignment"), shipped)),
        "shipped_auc": round(auc(shipped), 4),
        "n": len(ok),
    }


def save(results: list[Graded], spend: dict, name: str = "grader_eval") -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps({
        "spend": spend,
        "metrics": grader_metrics(results),
        "weights": fit_weights(results),
        "results": [{**asdict(g), "pair": asdict(g.pair)} for g in results],
    }, indent=1, default=str), encoding="utf-8")
    return path
