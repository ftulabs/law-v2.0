"""Per-target pipeline trace: where exactly does each piece of the judges' evidence die?

Aggregate recall says "we lost 2 of 19" and nothing about WHY, which makes it impossible to
know what to fix. This walks every provision the RDTII panel accepted through the real stages,
in order, and records the FIRST stage that dropped it:

  DISCOVERY   the instrument is not in the catalogue at all
  FETCH       catalogued, but no body could be downloaded/built (state != split)
  EXTRACTION  built, but the cited provision is not in the extracted provisions
              (structure: the splitter never produced that section)
  RETRIEVAL   the provision exists but did not reach the indicator's shortlist
  GRADING     it reached the LLM and the LLM rejected it
  CONFIDENCE  the LLM accepted it but the score routed it out of a submission
  (none)      it survives end to end

Attribution is strictly ordered: a target lost at EXTRACTION is never also counted against
retrieval or the grader. That ordering is the whole point — the previous round's headline
("grader recall 0.29") could not distinguish a strict grader from a target the grader never
saw, and only 41 of 117 graded pairs turned out to be the operative provision at all.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Callable

from ..corpus import store
from ..rdtii import get_indicator, get_indicators

STAGES = ["DISCOVERY", "FETCH", "EXTRACTION", "RETRIEVAL", "GRADING", "CONFIDENCE", "SURVIVED"]


@dataclass
class Target:
    """One piece of panel evidence: an (indicator, law) pair, with the sections they named."""
    economy: str
    indicator_id: str
    coverage: str
    law_label: str                 # the panel's name for the instrument
    sections: list[str] = field(default_factory=list)   # [] = law-level target
    primary_section: str | None = None                  # first named = the operative one
    raw_score: float | None = None
    impact: str = ""

    # trace results
    law_id: str | None = None
    catalogue_title: str | None = None
    collection: str | None = None
    version_id: str | None = None
    version_state: str | None = None
    fmt: str | None = None
    provisions_in_law: int = 0
    matched_provision_id: str | None = None
    matched_section: str | None = None
    shortlist_rank: int | None = None
    shortlist_size: int = 0
    graded: bool | None = None
    legal_match: float | None = None
    rationale: str = ""
    confidence: float | None = None
    review_status: str | None = None
    lost_at: str = ""
    note: str = ""


# ─────────────────────────── build the target list ───────────────────────────
# Instrument classes that live on the statute portal. The brief for this round is to get ACTS
# right end to end; codes of practice, guidance, standards, strategies and licences are being
# tracked separately because their acquisition problem (hidden PDF links behind anchor text)
# is not a retrieval problem.
STATUTE_COLLECTIONS = {"act", "amendment", "subsidiary"}


def is_statute(collection: str | None) -> bool:
    return (collection or "") in STATUTE_COLLECTIONS


def build_targets(economies=("SG", "AU", "MY"), use_reference: bool = True) -> list[Target]:
    from .ground_truth import load_labels
    from .linkage import _norm, link_all
    from .reference import sections_by_law
    links = {e: {lk.label_law: lk for lk in v} for e, v in link_all().items()}
    # curated operative sections, keyed on the normalised law name so the two label sources
    # can disagree on punctuation/年 without losing the override
    ref = {}
    if use_reference:
        for (econ, ind, law), secs in sections_by_law().items():
            ref[(econ, ind, _norm(law))] = secs
    out: list[Target] = []
    for row in load_labels():
        if row.economy not in economies or row.kind != "provision":
            continue
        for law in row.laws:
            lk = links.get(row.economy, {}).get(law)
            secs = ref.get((row.economy, row.indicator_id, _norm(law))) or list(row.sections)
            t = Target(economy=row.economy, indicator_id=row.indicator_id,
                       coverage=row.coverage or "Horizontal", law_label=law,
                       sections=secs,
                       primary_section=(secs[0] if secs else None),
                       raw_score=row.raw_score, impact=row.impact)
            if lk and lk.law_id:
                t.law_id = lk.law_id
                t.catalogue_title = lk.matched_title
            out.append(t)
    return out


# ─────────────────────────── stages 1-3 (offline) ───────────────────────────
def trace_corpus(targets: list[Target]) -> None:
    """DISCOVERY / FETCH / EXTRACTION, from the corpus store alone."""
    from sqlalchemy import select

    from ..corpus.store import corpus_law, corpus_version
    from ..storage.engine import get_engine
    from .harness import section_matches

    laws = {}
    with get_engine().connect() as c:
        for r in c.execute(select(corpus_law.c.law_id, corpus_law.c.collection)):
            laws[r[0]] = r[1]
        versions: dict[str, dict] = {}
        for r in c.execute(select(corpus_version.c.law_id, corpus_version.c.version_id,
                                  corpus_version.c.state, corpus_version.c.fmt,
                                  corpus_version.c.superseded_by, corpus_version.c.updated_at)):
            if r[4] is not None:
                continue                      # superseded
            prev = versions.get(r[0])
            if prev is None or (r[5] or "") > (prev["updated_at"] or ""):
                versions[r[0]] = {"version_id": r[1], "state": r[2], "fmt": r[3],
                                  "updated_at": r[5]}

    by_version: dict[str, list[dict]] = {}
    for econ in {t.economy for t in targets}:
        for p in store.load_provisions(econ):
            by_version.setdefault(p["version_id"], []).append(p)

    for t in targets:
        if not t.law_id:
            t.lost_at = "DISCOVERY"
            t.note = "instrument not located in the catalogue"
            continue
        t.collection = laws.get(t.law_id)
        v = versions.get(t.law_id)
        if not v or v["state"] != "split":
            t.lost_at = "FETCH"
            t.version_state = (v or {}).get("state") or "never built"
            t.note = f"no usable body (state={t.version_state})"
            continue
        t.version_id, t.version_state, t.fmt = v["version_id"], v["state"], v["fmt"]
        provs = by_version.get(t.version_id, [])
        t.provisions_in_law = len(provs)
        if not provs:
            t.lost_at = "EXTRACTION"
            t.note = "built but produced no provisions"
            continue
        if t.sections:
            hits = [p for p in provs if section_matches(p["article_section"], t.sections)]
            if not hits:
                t.lost_at = "EXTRACTION"
                t.note = (f"none of the cited sections {t.sections} appear among "
                          f"{len(provs)} extracted provisions")
                continue
            # prefer a hit on the PRIMARY (operative) section, then the longest text
            prim = [p for p in hits
                    if t.primary_section and section_matches(p["article_section"],
                                                             [t.primary_section])]
            pick = max(prim or hits, key=lambda p: len(p["text"] or ""))
            t.matched_provision_id = pick["provision_id"]
            t.matched_section = pick["article_section"]
        else:
            # law-level target (e.g. "does a comprehensive framework exist"): the law itself is
            # the evidence, so any provision of it can carry the mapping. Take the longest.
            pick = max(provs, key=lambda p: len(p["text"] or ""))
            t.matched_provision_id = pick["provision_id"]
            t.matched_section = pick["article_section"]
            t.note = "law-level target (panel named no section)"


# ─────────────────────────── stage 4: retrieval ───────────────────────────
def trace_retrieval(targets: list[Target], log: Callable = print) -> None:
    """Run the PRODUCTION shortlist per (economy, indicator) and locate each target in it."""
    import math

    from ..config import settings
    from ..pipeline.mapping import _diverse_shortlist
    from .harness import load_provisions, version_law_map

    for econ in sorted({t.economy for t in targets}):
        pending = [t for t in targets if t.economy == econ and not t.lost_at]
        if not pending:
            continue
        provisions = load_provisions(econ)
        v2l = version_law_map(econ)
        k = min(len(provisions), settings.retrieve_max_top_k,
                max(settings.retrieve_top_k,
                    math.ceil(len(provisions) * settings.retrieve_fraction)))
        for ind in get_indicators(None):
            group = [t for t in pending if t.indicator_id == ind.indicator_id]
            if not group:
                continue
            ranked = _diverse_shortlist(ind.indicator_id, provisions, k,
                                        settings.retrieve_per_law_k, log=lambda m: None)
            ids = [r.provision.provision_id for r in ranked]
            law_of = {r.provision.provision_id: v2l.get(r.provision.doc_id) for r in ranked}
            pos = {pid: i + 1 for i, pid in enumerate(ids)}
            for t in group:
                t.shortlist_size = len(ids)
                if t.matched_provision_id in pos:
                    t.shortlist_rank = pos[t.matched_provision_id]
                    continue
                # law-level targets are satisfied by ANY provision of the law reaching the list
                same_law = [i + 1 for i, pid in enumerate(ids) if law_of.get(pid) == t.law_id]
                if not t.sections and same_law:
                    t.shortlist_rank = same_law[0]
                    t.matched_provision_id = ids[same_law[0] - 1]
                    t.matched_section = next(r.provision.article_section for r in ranked
                                             if r.provision.provision_id == t.matched_provision_id)
                    continue
                t.lost_at = "RETRIEVAL"
                t.note = (f"provision exists ({t.matched_section}) but is outside the top-{len(ids)} "
                          f"shortlist" + (f"; {len(same_law)} other provisions of the same law "
                                          f"did reach it (best rank {same_law[0]})" if same_law else
                                          "; no provision of this law reached it"))
        log(f"[trace] {econ}: retrieval stage done (k={k}, {len(provisions)} provisions)")


# ─────────────────────────── stages 5-6: grading + confidence ───────────────────────────
def trace_grading(targets: list[Target], budget_usd: float = 2.0, concurrency: int = 8,
                  log: Callable = print) -> dict:
    """Grade every target that reached the shortlist with the SHIPPED prompt, then apply the
    SHIPPED confidence scoring + routing. Anything rejected here genuinely reached the LLM."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from ..config import settings
    from ..pipeline import confidence as conf
    from ..pipeline.mapping import SYSTEM, _user_prompt
    from ..providers import get_llm_provider
    from ..schemas import Provision
    from .grader_eval import _cost

    live = [t for t in targets if not t.lost_at]
    llm = get_llm_provider()
    model = getattr(llm, "model_version", "") or settings.openrouter_model
    texts = _provision_texts([t.matched_provision_id for t in live])
    spend = {"usd": 0.0, "calls": 0, "model": model}
    stop = {"flag": False}

    def _one(t: Target):
        if stop["flag"]:
            return t, None
        ind = get_indicator(t.indicator_id)
        body = texts.get(t.matched_provision_id, "")
        prov = Provision(provision_id=t.matched_provision_id or "x", doc_id="trace",
                         economy=t.economy, law_name=t.catalogue_title or t.law_label,
                         article_section=t.matched_section or "", verbatim_snippet=body,
                         source_url="")
        try:
            return t, llm.complete_json(SYSTEM, _user_prompt(ind, prov))
        except Exception as e:  # noqa: BLE001
            return t, {"__error__": f"{type(e).__name__}: {e}"[:160]}

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for fut in as_completed([ex.submit(_one, t) for t in live]):
            t, out = fut.result()
            spend["calls"] += 1
            spend["usd"] += _cost(model, 2000, 3000)
            if spend["usd"] >= budget_usd * 0.95:
                stop["flag"] = True
            if not out or "__error__" in (out or {}):
                t.note = (t.note + "; " if t.note else "") + \
                    f"grading call failed ({(out or {}).get('__error__', 'skipped')})"
                t.lost_at = "GRADING"
                t.graded = None
                continue
            t.graded = bool(out.get("satisfied") or out.get("relevant"))
            try:
                t.legal_match = float(out.get("legal_match") or 0.0)
            except (TypeError, ValueError):
                t.legal_match = 0.0
            t.rationale = str(out.get("rationale") or "")[:400]
            if not t.graded:
                t.lost_at = "GRADING"
                continue
            # SHIPPED confidence + routing, with the real signals
            body = texts.get(t.matched_provision_id, "")
            snippet = str(out.get("snippet") or body[:400])
            ind = get_indicator(t.indicator_id)
            grounding = conf.snippet_grounding(snippet, body)
            retrieval_score = max(0.0, 1.0 - (t.shortlist_rank or 1) / max(t.shortlist_size, 1))
            # The topical guard runs on the FULL provision text, exactly as mapping.py does
            # (`topical_grounded(prov.verbatim_snippet, ind.pillar)`). Feeding it the model's
            # quoted snippet instead made five correct record-keeping mappings look
            # quarantined — an artefact of the harness, not behaviour of the pipeline.
            topical_ok = conf.topical_grounded(body, ind.pillar)
            cb = conf.score(retrieval_score=retrieval_score, legal_match=t.legal_match,
                            grounding=grounding, scope_alignment=1.0, scope_flag=None,
                            topical_ok=topical_ok)
            t.confidence = cb.final
            t.review_status = conf.route(cb.final).value
            from ..schemas import SUBMITTABLE_STATUSES
            if t.review_status not in SUBMITTABLE_STATUSES:
                t.lost_at = "CONFIDENCE"
                t.note = (t.note + "; " if t.note else "") + \
                    f"accepted by the grader but routed to {t.review_status} ({cb.final})"
    for t in targets:
        if not t.lost_at:
            t.lost_at = "SURVIVED"
    log(f"[trace] grading: {spend['calls']} calls, ~${spend['usd']:.2f}")
    return spend


def _provision_texts(ids: list[str]) -> dict[str, str]:
    from sqlalchemy import select

    from ..corpus.store import corpus_provision
    from ..storage.engine import get_engine
    ids = [i for i in ids if i]
    out: dict[str, str] = {}
    if not ids:
        return out
    with get_engine().connect() as c:
        for i in range(0, len(ids), 400):
            for r in c.execute(select(corpus_provision.c.provision_id, corpus_provision.c.text)
                               .where(corpus_provision.c.provision_id.in_(ids[i:i + 400]))):
                out[r[0]] = r[1] or ""
    return out


# ─────────────────────────── reporting ───────────────────────────
def summarise(targets: list[Target]) -> dict:
    from collections import Counter
    per_stage = Counter(t.lost_at for t in targets)
    by_econ: dict[str, Counter] = {}
    for t in targets:
        by_econ.setdefault(t.economy, Counter())[t.lost_at] += 1
    # indicator-level: does the indicator end up with ANY surviving evidence?
    ind_ok: dict[str, bool] = {}
    for t in targets:
        key = f"{t.economy}/{t.indicator_id}"
        ind_ok[key] = ind_ok.get(key, False) or (t.lost_at == "SURVIVED")
    return {
        "targets": len(targets),
        "by_stage": {s: per_stage.get(s, 0) for s in STAGES},
        "by_economy": {e: dict(c) for e, c in by_econ.items()},
        "indicators_with_surviving_evidence":
            f"{sum(ind_ok.values())}/{len(ind_ok)}",
        "indicators_missing": sorted(k for k, v in ind_ok.items() if not v),
    }


def run(economies=("SG", "AU", "MY"), budget_usd: float = 2.0, out_path: str | None = None,
        log: Callable = print) -> tuple[list[Target], dict]:
    targets = build_targets(economies)
    log(f"[trace] {len(targets)} (indicator, law) targets from the panel's evidence")
    trace_corpus(targets)
    log("[trace] corpus stages done: " + json.dumps(summarise(targets)["by_stage"]))
    trace_retrieval(targets, log=log)
    spend = trace_grading(targets, budget_usd=budget_usd, log=log)
    rep = summarise(targets)
    rep["spend"] = spend
    if out_path:
        from pathlib import Path
        Path(out_path).write_text(json.dumps(
            {"summary": rep, "targets": [asdict(t) for t in targets]},
            indent=1, ensure_ascii=False), encoding="utf-8")
    return targets, rep
