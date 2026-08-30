"""Retrieval evaluation harness.

Loads the built corpus, runs a candidate-selection strategy for every (economy, indicator),
and scores it against the judges' Database. No LLM is involved: the question here is purely
*does the right provision reach the shortlist at all*, which is the ceiling on everything the
grader can possibly get right afterwards.

Metrics, and why each one:

  law_recall@k       — did ANY provision of a law the judges cited reach the top k?
                       This is the ceiling for the mapping stage: a law that never appears
                       cannot be graded, so it can never be answered.
  prov_recall@k      — did the SPECIFIC provision the judges named reach the top k?
                       Stricter, and the one that decides whether the exported snippet and
                       article citation can match the panel's.
  coverage           — how many (economy, indicator) pairs got any candidate at all.
  target_density@k   — share of the top k drawn from cited laws. NOT precision: a law the
                       panel did not cite may still be a legitimate find (finding MORE than
                       the panel is an explicit goal). It is a cheap signal for "is the
                       shortlist full of junk", to be read alongside recall.
  n_calls            — shortlist size summed over indicators = LLM calls the config would
                       cost. Recall is meaningless without it; anyone can hit 100 % recall
                       by grading everything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..corpus import store
from ..rdtii import get_indicators
from ..schemas import Economy, Provision

ECONOMIES = ("SG", "AU", "MY")


# ─────────────────────────── corpus loading ───────────────────────────
def load_provisions(economy: str) -> list[Provision]:
    """Corpus rows → Provision objects, the shape retrieval already expects."""
    out = []
    for r in store.load_provisions(economy):
        out.append(Provision(
            provision_id=r["provision_id"], doc_id=r["version_id"], economy=Economy(economy),
            law_name=r["law_name"] or "", law_number=r["law_number"],
            article_section=r["article_section"] or "", verbatim_snippet=r["text"] or "",
            source_url="", location_ref=r["location_ref"],
            char_span=(r["char_start"] or 0, r["char_end"] or 0),
        ))
    return out


def law_id_of(p: Provision, version_to_law: dict[str, str]) -> str | None:
    return version_to_law.get(p.doc_id)


def version_law_map(economy: str) -> dict[str, str]:
    from sqlalchemy import select
    from ..corpus.store import corpus_version
    from ..storage.engine import get_engine
    with get_engine().connect() as c:
        return {r[0]: r[1] for r in c.execute(
            select(corpus_version.c.version_id, corpus_version.c.law_id)
            .where(corpus_version.c.economy == economy))}


# ─────────────────────────── section matching ───────────────────────────
_SEC_NUM_RE = re.compile(r"(\d{1,4}[A-Za-z]{0,2}(?:\.\d+)*)")
_APP_RE = re.compile(r"\bapp\s*(\d+(?:\.\d+)?)", re.I)
# Structural containers, not provisions. The panel cites "Section 199" / "APP 8"; counting
# "Division 4" as a match for the label "4" would manufacture hits that are not the cited law
# text at all.
_STRUCTURAL_RE = re.compile(r"^\s*(part|division|chapter|schedule|subdivision)\b", re.I)


_HAN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
               "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_HAN_UNITS = {"十": 10, "百": 100, "千": 1000}
_HAN_ARTICLE_RE = re.compile(r"第([〇零一二三四五六七八九十百千两]+)[条條]")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _han_to_int(s: str) -> int | None:
    """三十五 → 35. None when the string is not a Han numeral.

    The panel writes its citations in Arabic numerals ("Article 35") while a Chinese statute
    numbers its articles 第三十五条, and _SEC_NUM_RE looks for digits. Every Chinese provision
    therefore keyed to None, so China's measured provision recall was 0.000 BY CONSTRUCTION —
    at k = the whole corpus, where retrieval could not affect it either way. A metric that
    cannot rise is not a measurement, and this one was about to be reported as a finding.
    """
    total, part, seen = 0, 0, False
    for ch in s:
        if ch in _HAN_DIGITS:
            part = _HAN_DIGITS[ch]
            seen = True
        elif ch in _HAN_UNITS:
            # "十五" is 15: a bare 十 with nothing before it means one ten.
            total += (part or 1) * _HAN_UNITS[ch]
            part = 0
            seen = True
        else:
            return None
    return total + part if seen else None


def section_key(article_section: str) -> str | None:
    """'Section 199' → '199'; 'APP 8' → 'app8'; 'Regulation 3.1.1' → '3.1.1';
    '第三十五条' → '35'; 'มาตรา ๑๐' → '10'.
    Structural headings (Part/Division/Schedule) return None — they are not provisions."""
    s = (article_section or "").strip()
    m = _APP_RE.search(s)
    if m:
        return "app" + m.group(1)
    if _STRUCTURAL_RE.match(s):
        return None
    # Native numerals first: China and Thailand both number articles in a script the
    # Arabic-digit pattern cannot see, and both are on the panel's list.
    m = _HAN_ARTICLE_RE.search(s)
    if m:
        n = _han_to_int(m.group(1))
        if n is not None:
            return str(n)
    if any("๐" <= c <= "๙" for c in s):
        s = s.translate(_THAI_DIGITS)
    m = _SEC_NUM_RE.search(s)
    return m.group(1).lower() if m else None


def label_section_key(label: str) -> str | None:
    """'11(3)' → '11'; 'APP 8' → 'app8'; '3.1.1' → '3.1.1'; '187C' → '187c'."""
    s = (label or "").strip()
    m = _APP_RE.search(s)
    if m:
        return "app" + m.group(1)
    m = _SEC_NUM_RE.search(s)
    return m.group(1).lower() if m else None


def section_matches(provision_section: str, label_sections: list[str]) -> bool:
    got = section_key(provision_section)
    if not got:
        return False
    for lab in label_sections:
        want = label_section_key(lab)
        if not want:
            continue
        if got == want:
            return True
        # a code-of-practice label ('3.1.1') is satisfied by its parent clause ('3.1')
        if "." in want and (want.startswith(got + ".") or got.startswith(want + ".")):
            return True
    return False


# ─────────────────────────── evaluation ───────────────────────────
@dataclass
class IndicatorResult:
    economy: str
    indicator_id: str
    n_candidates: int
    law_hit: bool
    prov_hit: bool
    law_expected: bool          # the panel cited a locatable law for this indicator
    prov_expected: bool         # …and named a specific provision
    target_in_top: int
    best_target_rank: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    rows: list[IndicatorResult]
    n_calls: int

    def summary(self) -> dict:
        law_rows = [r for r in self.rows if r.law_expected]
        prov_rows = [r for r in self.rows if r.prov_expected]
        cand = [r.n_candidates for r in self.rows]
        return {
            "law_recall": round(sum(r.law_hit for r in law_rows) / max(len(law_rows), 1), 3),
            "prov_recall": round(sum(r.prov_hit for r in prov_rows) / max(len(prov_rows), 1), 3),
            "law_hits": f"{sum(r.law_hit for r in law_rows)}/{len(law_rows)}",
            "prov_hits": f"{sum(r.prov_hit for r in prov_rows)}/{len(prov_rows)}",
            "coverage": f"{sum(1 for r in self.rows if r.n_candidates > 0)}/{len(self.rows)}",
            "target_density": round(sum(r.target_in_top for r in self.rows) / max(sum(cand), 1), 3),
            "median_rank_of_target": _median([r.best_target_rank for r in self.rows
                                              if r.best_target_rank is not None]),
            "n_calls": self.n_calls,
        }


def _median(xs: list[int]):
    xs = sorted(x for x in xs if x is not None)
    return None if not xs else xs[len(xs) // 2]


def targets_by_indicator(economy: str) -> dict[str, dict]:
    """{indicator_id: {"law_ids": {...}, "sections": {law_id: [labels]}, "has_provision": bool}}"""
    from .ground_truth import load_labels
    from .linkage import link_all
    links = {lk.label_law: lk for lk in link_all()[economy]}
    out: dict[str, dict] = {}
    for row in load_labels():
        if row.economy != economy or row.kind != "provision":
            continue
        e = out.setdefault(row.indicator_id, {"law_ids": set(), "sections": {}, "rows": 0})
        e["rows"] += 1
        for law in row.laws:
            lk = links.get(law)
            if lk and lk.law_id:
                e["law_ids"].add(lk.law_id)
                if row.sections:
                    e["sections"].setdefault(lk.law_id, []).extend(row.sections)
    return out


def evaluate(economy: str, selector: Callable[[str, list[Provision]], list],
             provisions: list[Provision] | None = None) -> EvalReport:
    """`selector(indicator_id, provisions)` → ranked list of Retrieved (or Provision)."""
    provisions = provisions if provisions is not None else load_provisions(economy)
    v2l = version_law_map(economy)
    targets = targets_by_indicator(economy)
    rows, calls = [], 0
    for ind in get_indicators(None):
        picked = selector(ind.indicator_id, provisions)
        cands = [getattr(x, "provision", x) for x in picked]
        calls += len(cands)
        t = targets.get(ind.indicator_id)
        want_laws = t["law_ids"] if t else set()
        want_secs = t["sections"] if t else {}
        law_hit = prov_hit = False
        in_top, best_rank = 0, None
        for rank, p in enumerate(cands, 1):
            lid = law_id_of(p, v2l)
            if lid and lid in want_laws:
                in_top += 1
                law_hit = True
                best_rank = best_rank or rank
                if want_secs.get(lid) and section_matches(p.article_section, want_secs[lid]):
                    prov_hit = True
        rows.append(IndicatorResult(
            economy=economy, indicator_id=ind.indicator_id, n_candidates=len(cands),
            law_hit=law_hit, prov_hit=prov_hit,
            law_expected=bool(want_laws), prov_expected=bool(want_secs),
            target_in_top=in_top, best_target_rank=best_rank))
    return EvalReport(rows=rows, n_calls=calls)


def evaluate_all(selector_factory: Callable[[str], Callable], economies=ECONOMIES,
                 provisions_by_economy: dict[str, list[Provision]] | None = None) -> dict:
    """Run one strategy across economies. `selector_factory(economy)` → selector."""
    per, all_rows, calls = {}, [], 0
    for econ in economies:
        provisions = (provisions_by_economy or {}).get(econ) or load_provisions(econ)
        rep = evaluate(econ, selector_factory(econ), provisions)
        per[econ] = rep.summary()
        all_rows.extend(rep.rows)
        calls += rep.n_calls
    overall = EvalReport(rows=all_rows, n_calls=calls).summary()
    return {"overall": overall, "per_economy": per}
