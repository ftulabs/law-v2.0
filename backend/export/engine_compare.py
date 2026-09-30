"""Provision-by-provision comparison of two engine passes — the live test's comparison note.

The submission form (Section 5) asks for a comparison "covering every provision either engine
produced", stating for each one *which engine found it* and, for provisions both found, *how
the indicator, the article citation or the quoted words differed*. Counting rows is not that:
the earlier comparison keyed rows on (indicator, law, article), so a provision both engines
found but mapped to different indicators came out as two "only this engine" rows — the
disagreement the note exists to show was reported as two independent finds.

Identity. Engine B re-reads engine A's documents, and extraction is deterministic, so one
provision carries the same `provision_id` (`doc_id#p<n>`) in both passes; that is the key.
Rows without one (older traces) fall back to (law, article) after light normalisation. The
case neither key catches — the same words cited to a different provision — is recovered by a
second pass over the leftovers that pairs rows of the same law whose quotes overlap, and
reports the citation as differing.

Pure functions over EvidenceMapping-like objects (attributes read with defaults), so the
Streamlit screen, the CSV export and the tests all share one implementation.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

from ..rdtii.codes import to_rdtii_code
from ..schemas import PLACEHOLDER_LAW_NAMES, SUBMITTABLE_STATUSES

#: Column order of the exported sheet. Plain words, because the reader is a steward.
COLUMNS = [
    "Provision #", "Law name", "Article (engine A)", "Article (engine B)", "Found by",
    "Indicators (engine A)", "Indicators (engine B)", "Indicator", "Article citation",
    "Quoted words", "What differs", "Quote (engine A)", "Quote (engine B)",
    "Confidence (engine A)", "Confidence (engine B)", "Status (engine A)", "Status (engine B)",
    "Source URL",
]

BOTH, A_ONLY, B_ONLY = "Both engines", "Engine A only", "Engine B only"
SAME, DIFFERS, NA = "Same", "Differs", "—"
OVERLAP = "Overlaps"            # one quote contains the other: same words, different extent


def _status(m) -> str:
    s = getattr(m, "review_status", "")
    return str(getattr(s, "value", s) or "")


def exported(mappings) -> list:
    """The rows an engine actually handed in: not placeholders, and a submittable status —
    the same set `csv_text` writes to that engine's evidence file."""
    out = []
    for m in mappings or []:
        if (getattr(m, "law_name", "") or "") in PLACEHOLDER_LAW_NAMES:
            continue
        st = _status(m)
        if st and st not in SUBMITTABLE_STATUSES:
            continue
        out.append(m)
    return out


def _norm(text: str) -> str:
    """Case-, width- and whitespace-insensitive form. NFKC folds full-width digits and
    punctuation, which Chinese and Japanese statutes mix freely with ASCII."""
    t = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"\s+", " ", t).strip()


def _law_key(name: str) -> str:
    return re.sub(r"[^\w]+", " ", _norm(name)).strip()


def _article_key(art: str) -> str:
    t = _norm(art)
    return re.sub(r"[\s.,;:]+", "", t)


def _quote_key(q: str) -> str:
    # Punctuation and spacing differ between extractions of the same text more often than the
    # words do; compare the words.
    return re.sub(r"[\W_]+", "", _norm(q))


def _quote_match(qa: str, qb: str) -> str:
    ka, kb = _quote_key(qa), _quote_key(qb)
    if not ka or not kb:
        return NA
    if ka == kb:
        return SAME
    if ka in kb or kb in ka:
        return OVERLAP
    return DIFFERS


@dataclass
class _Side:
    """One engine's view of one provision: every indicator it mapped the provision to."""
    law: str
    article: str
    indicators: list = field(default_factory=list)
    quote: str = ""
    confidence: float | None = None
    status: str = ""
    url: str = ""
    known: bool = False                        # any row of it matches the 2025 baseline

    def add(self, m) -> None:
        code = to_rdtii_code(getattr(m, "indicator_id", "") or "")
        if code and code not in self.indicators:
            self.indicators.append(code)
        q = getattr(m, "verbatim_snippet", "") or ""
        if len(q) > len(self.quote):           # the fullest quote stands for the provision
            self.quote = q
        c = getattr(m, "confidence_score", None)
        if isinstance(c, (int, float)) and (self.confidence is None or c > self.confidence):
            self.confidence = float(c)
        st = _status(m)
        if st and (not self.status or st == "pending_review"):
            self.status = st                  # a row needing review outranks an accepted one
        self.url = self.url or (getattr(m, "source_url", "") or "")
        tag = getattr(m, "discovery_tag", "")
        self.known = self.known or str(getattr(tag, "value", tag) or "") == "KNOWN"


def _sides(mappings) -> dict:
    """Group one engine's rows by provision. Key: (law key, provision identity)."""
    out: dict[tuple, _Side] = {}
    for m in exported(mappings):
        law = getattr(m, "law_name", "") or ""
        art = getattr(m, "article_section", "") or ""
        pid = getattr(m, "provision_id", "") or ""
        if pid:
            # `doc_id#p<n>` from extraction: the second pass re-reads the same documents, so
            # the same provision carries the same id in both — the strongest identity there is.
            key = (_law_key(law), "id:" + pid)
        else:
            key = (_law_key(law), _article_key(art))
        if not key[1]:
            # No usable article: fall back to the words, so two whole-document rows of one law
            # are not merged into a single provision.
            key = (key[0], "q:" + _quote_key(getattr(m, "verbatim_snippet", ""))[:120])
        side = out.get(key)
        if side is None:
            side = out[key] = _Side(law=law, article=art)
        side.add(m)
    return out


def provision_counts(mappings) -> tuple[int, int]:
    """(provisions exported, of those absent from the 2025 baseline) — the short note's
    section-2 figures. Counted per PROVISION, the unit the template names: one provision mapped
    to two indicators is one provision, and it counts as absent from the baseline only when
    none of its rows matched a baseline provision."""
    sides = _sides(mappings)
    return len(sides), sum(1 for s in sides.values() if not s.known)


def _codes_sort(codes) -> list:
    def k(c):
        return [int(p) if p.isdigit() else p for p in re.split(r"[.]", c)]
    return sorted(codes, key=k)


@dataclass
class CompareRow:
    found_by: str
    a: _Side | None
    b: _Side | None
    indicator: str = NA
    citation: str = NA
    quote: str = NA

    @property
    def differs(self) -> str:
        """The sentence the note asks for: what is different, in words."""
        if self.found_by == A_ONLY:
            return "Only engine A mapped this provision"
        if self.found_by == B_ONLY:
            return "Only engine B mapped this provision"
        parts = []
        if self.indicator == DIFFERS:
            ia, ib = set(self.a.indicators), set(self.b.indicators)
            bits = []
            if ia - ib:
                bits.append("A adds " + ", ".join(_codes_sort(ia - ib)))
            if ib - ia:
                bits.append("B adds " + ", ".join(_codes_sort(ib - ia)))
            parts.append("indicator: " + "; ".join(bits))
        if self.citation == DIFFERS:
            parts.append(f"article: A cites {self.a.article!r}, B cites {self.b.article!r}")
        if self.quote == DIFFERS:
            parts.append("quoted words differ")
        elif self.quote == OVERLAP:
            parts.append("one quote is a longer extract of the other")
        return "; ".join(parts) or "No difference"


def compare(a_mappings, b_mappings) -> list[CompareRow]:
    """Every provision either engine exported, with how the two engines' rows differ."""
    sa, sb = _sides(a_mappings), _sides(b_mappings)
    rows: list[CompareRow] = []

    for key in [k for k in sa if k in sb]:
        a, b = sa.pop(key), sb.pop(key)
        rows.append(CompareRow(
            BOTH, a, b,
            indicator=SAME if set(a.indicators) == set(b.indicators) else DIFFERS,
            citation=SAME, quote=_quote_match(a.quote, b.quote)))

    # Same law, same words, different article: one provision cited two ways.
    for ka in list(sa):
        a = sa[ka]
        for kb in [k for k in sb if k[0] == ka[0]]:
            b = sb[kb]
            if _quote_match(a.quote, b.quote) in (SAME, OVERLAP):
                rows.append(CompareRow(
                    BOTH, a, b,
                    indicator=SAME if set(a.indicators) == set(b.indicators) else DIFFERS,
                    citation=DIFFERS, quote=_quote_match(a.quote, b.quote)))
                del sa[ka], sb[kb]
                break

    rows += [CompareRow(A_ONLY, a, None) for a in sa.values()]
    rows += [CompareRow(B_ONLY, None, b) for b in sb.values()]
    order = {BOTH: 0, A_ONLY: 1, B_ONLY: 2}

    def law_of(r):
        s = r.a or r.b
        return (order[r.found_by], _law_key(s.law), _article_key(s.article))
    return sorted(rows, key=law_of)


def summary(rows: list[CompareRow]) -> dict:
    both = [r for r in rows if r.found_by == BOTH]
    return {
        "provisions": len(rows),
        "both": len(both),
        "a_only": sum(r.found_by == A_ONLY for r in rows),
        "b_only": sum(r.found_by == B_ONLY for r in rows),
        "indicator_differs": sum(r.indicator == DIFFERS for r in both),
        "citation_differs": sum(r.citation == DIFFERS for r in both),
        "quote_differs": sum(r.quote in (DIFFERS, OVERLAP) for r in both),
        "identical": sum(r.differs == "No difference" for r in both),
    }


def _conf(s: _Side | None) -> str:
    return "" if s is None or s.confidence is None else f"{s.confidence:.2f}"


def table(rows: list[CompareRow]) -> list[dict]:
    """One dict per provision, keyed by COLUMNS — for the on-screen table and the CSV."""
    out = []
    for i, r in enumerate(rows, 1):
        a, b = r.a, r.b
        s = a or b
        out.append({
            "Provision #": i,
            "Law name": s.law,
            "Article (engine A)": a.article if a else "",
            "Article (engine B)": b.article if b else "",
            "Found by": r.found_by,
            "Indicators (engine A)": ", ".join(_codes_sort(a.indicators)) if a else "",
            "Indicators (engine B)": ", ".join(_codes_sort(b.indicators)) if b else "",
            "Indicator": r.indicator,
            "Article citation": r.citation,
            "Quoted words": r.quote,
            "What differs": r.differs,
            "Quote (engine A)": a.quote if a else "",
            "Quote (engine B)": b.quote if b else "",
            "Confidence (engine A)": _conf(a),
            "Confidence (engine B)": _conf(b),
            "Status (engine A)": a.status if a else "",
            "Status (engine B)": b.status if b else "",
            "Source URL": (a.url if a else "") or (b.url if b else ""),
        })
    return out


def to_csv(rows: list[CompareRow]) -> bytes:
    """The sheet as UTF-8 with a byte-order mark. Without the BOM, Excel on Windows opens
    Thai, Chinese or Mongolian quotes as mojibake — and a steward opens it in Excel."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writeheader()
    w.writerows(table(rows))
    return ("﻿" + buf.getvalue()).encode("utf-8")
