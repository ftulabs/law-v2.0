"""Is this provision already in the 2025 RDTII baseline, or did we find it ourselves?

`Discovery Tag` is the column that says whether a row is a discovery. The final-round template
defines it per PROVISION — *"NEW = your tool found it and it is not in the 2025 baseline you
hold"* — and the live-test short note asks for the count of provisions *"you believe absent from
the 2025 baseline"*. Until now we answered that question per LAW: `sample_kit.is_known()` takes a
law name and a URL and no section at all. The consequence is that we give away our own credit —
if the panel cites PDPA s.26 and our tool independently surfaces PDPA s.11(3), both come back
KNOWN, and the provision we actually discovered is reported as one we were handed.

The baseline is `data/ground_truth/rdtii_reference_p67.csv`, built from the panel's own Round-1
and Round-2 databases: 180 rows across six economies, 101 of which name an article.

Three outcomes, and the middle one is the honest part:

    KNOWN            the law AND the article both appear in the baseline
    KNOWN (law only) the baseline cites this law for this indicator but records no article, so
                     we cannot tell whether this particular provision was known. We report
                     KNOWN and say why in Notes.
    NEW              neither matches

We never claim NEW where we cannot tell. Overstating our own discovery is the one error a judge
can check by opening the database they wrote.

Matching has to survive four drafting conventions at once. The baseline records the panel's
prose citation ("Section 199", "APP 8", "Article 20.2", "Regulation 53(2)") while our extractor
emits the source's own heading — which for China is 第四十条 in Han numerals and for Mongolia is
"14 дүгээр зүйл". So both sides are reduced to a numeric spine: an article number plus any
sub-numbering, with the label word discarded.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import ROOT

BASELINE_CSV = ROOT / "data" / "ground_truth" / "rdtii_reference_p67.csv"

# Words that name the kind of provision rather than identify it. Dropped from both sides before
# comparison, so "Section 26" and "s. 26" and "Art. 26" all reduce to the same spine.
_LABEL_WORDS = re.compile(
    r"\b(?:articles?|sections?|regulations?|rules?|clauses?|paragraphs?|paras?|schedules?"
    r"|arts?|secs?|ss|s|r|reg)\b\.?", re.I)

_HAN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9}
_CN_ARTICLE = re.compile(r"第\s*([一二三四五六七八九十百千零〇两0-9]+)\s*[条章节]")
_MN_ARTICLE = re.compile(r"(\d{1,3})\s*(?:д[үу]г[эа]{0,2}р|дэх|дахь)\s+з[үу]йл", re.I)
_APP = re.compile(r"\bAPP\s*(\d+(?:\.\d+)?)", re.I)

# Law-name tokens that carry no identity.
_STOP = {"the", "of", "on", "and", "or", "a", "an", "to", "for", "in", "act", "law", "laws",
         "no", "republic", "people", "peoples"}


def _han_to_int(s: str) -> int | None:
    """第四十条 -> 40. Chinese statutes number articles in Han digits far more often than Arabic,
    and the panel's database records them as 'Article 40' — so one side must be converted."""
    if s.isdigit():
        return int(s)
    total, section, digit = 0, 0, 0
    for ch in s:
        if ch in _HAN_DIGITS:
            digit = _HAN_DIGITS[ch]
        elif ch == "十":
            section += (digit or 1) * 10
            digit = 0
        elif ch == "百":
            section += (digit or 1) * 100
            digit = 0
        elif ch == "千":
            total += (section + (digit or 1)) * 1000
            section = digit = 0
        else:
            return None
    return total + section + digit


def article_spine(text: str) -> set[str]:
    """The numeric identity of one or more provision citations, label words removed.

    "Section 199; Section 4"  -> {"199", "4"}
    "s. 26(1)"                -> {"26(1)", "26"}      — the bare article too, so a baseline
                                                        recording "Section 26" still matches
    "Article 20.1.5"          -> {"20.1.5", "20"}
    "第四十条"                 -> {"40"}
    "14 дүгээр зүйл"          -> {"14"}
    "APP 8"                   -> {"app8"}
    """
    if not text:
        return set()
    out: set[str] = set()

    for m in _CN_ARTICLE.finditer(text):
        n = _han_to_int(m.group(1))
        if n is not None:
            out.add(str(n))
    for m in _MN_ARTICLE.finditer(text):
        out.add(m.group(1))
    for m in _APP.finditer(text):
        out.add("app" + m.group(1))

    cleaned = _LABEL_WORDS.sub(" ", text)
    for chunk in re.split(r"[;,]| and ", cleaned):
        chunk = chunk.strip()
        # 199 · 26(1) · 20.1.5 · 12B · 3.1.4 · 45(2)(a)(i)
        m = re.match(r"^\s*(\d{1,4}[A-Za-z]{0,2}(?:\.\d{1,3})*)((?:\([^)\s]{1,8}\))*)\s*$", chunk)
        if m:
            base, subs = m.group(1), m.group(2)
            out.add((base + subs).lower())
            out.add(base.lower())
            if "." in base:                     # 20.1.5 also answers to article 20
                out.add(base.split(".")[0].lower())
    return {s for s in out if s}


def law_tokens(name: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z]{3,}", (name or "").lower()) if w not in _STOP)


@dataclass(frozen=True)
class BaselineEntry:
    economy: str
    indicator_id: str
    law_name: str
    tokens: frozenset[str]
    spine: frozenset[str]


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict[tuple[str, str], list[BaselineEntry]]:
    """(economy, indicator_id) -> the panel's entries. Empty dict if the file is absent, so a
    missing baseline degrades to 'everything is NEW' rather than crashing a run."""
    p = Path(path) if path else BASELINE_CSV
    if not p.exists():
        return {}
    index: dict[tuple[str, str], list[BaselineEntry]] = {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            economy = (row.get("Economy") or "").strip()
            indicator = (row.get("Indicator ID") or "").strip()
            law = (row.get("Law Name") or "").strip()
            if not economy or not indicator or not law:
                continue
            index.setdefault((economy, indicator), []).append(BaselineEntry(
                economy=economy, indicator_id=indicator, law_name=law,
                tokens=law_tokens(law),
                spine=frozenset(article_spine(row.get("Article / Section") or "")),
            ))
    return index


def _same_law(a: frozenset[str], b: frozenset[str]) -> bool:
    """Token overlap against the SHORTER name, so 'Personal Data Protection Act 2012' still
    matches the baseline's 'Personal Data Protection Act (Act 709) 2010' style variance while a
    subsidiary regulation does not swallow its parent Act."""
    if not a or not b:
        return False
    return len(a & b) / max(min(len(a), len(b)), 1) >= 0.75


def classify(economy: str, indicator_id: str, law_name: str,
             article_section: str) -> tuple[str, str | None]:
    """(tag, note) for one provision. `tag` is "NEW" or "KNOWN"; `note` explains a KNOWN that
    rests on the law alone, and is None otherwise."""
    entries = load().get((economy, indicator_id))
    if not entries:
        return "NEW", None

    ours = article_spine(article_section)
    law_hit = False
    for e in entries:
        if not _same_law(law_tokens(law_name), e.tokens):
            continue
        law_hit = True
        if ours and e.spine and (ours & e.spine):
            return "KNOWN", None
    if not law_hit:
        return "NEW", None

    # The law is in the baseline but this article is not. Two different situations, and they
    # deserve opposite answers.
    matched = [e for e in entries if _same_law(law_tokens(law_name), e.tokens)]
    if any(e.spine for e in matched):
        # The panel recorded articles for this law and ours is not among them. The definition is
        # about the provision — "not in the 2025 baseline" — so this IS a discovery, and calling
        # it KNOWN would hand back exactly the credit this module exists to recover. The note
        # states the relationship openly, so nobody can read the NEW as a claim that the LAW was
        # unknown to the panel.
        return "NEW", ("Baseline cites this law for this indicator at a different article; "
                       "this provision is not cited there.")
    # The panel named the law but no article at all, so whether they had this provision in mind
    # is unknowable. Report KNOWN: overstating our own discovery is the more expensive error,
    # and it is the one a judge can check by opening the database they wrote.
    return "KNOWN", "Baseline cites this law for this indicator without naming an article."


def stats() -> dict:
    idx = load()
    return {
        "rows": sum(len(v) for v in idx.values()),
        "economy_indicator_pairs": len(idx),
        "economies": sorted({k[0] for k in idx}),
        "rows_with_article": sum(1 for v in idx.values() for e in v if e.spine),
    }
