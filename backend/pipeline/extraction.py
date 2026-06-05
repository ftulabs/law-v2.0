"""ZONE 2b — provision extraction.

Splits a document's raw text into Provisions keyed by article/section markers,
preserving VERBATIM wording and recording character spans into the raw text so
any snippet can later be re-verified against source. The law name is derived from
the document title; amendment dates flow from discovery metadata.

Regex covers the common Commonwealth/ASEAN drafting conventions:
  Section 26.  |  Art. 13  |  Article 13  |  Regulation 4  |  Clause 8  |  § 12
"""
from __future__ import annotations

import re

from ..schemas import DiscoveredDoc, OCRMetrics, Provision

SECTION_RE = re.compile(
    r"(?im)^\s*("
    r"(?:section|sec\.?|s\.)\s*\d+[A-Z]?"        # Section 26 / S. 13
    r"|(?:article|art\.?)\s*\d+[A-Z]?"            # Article 13 / Art. 13
    r"|(?:regulation|reg\.?)\s*\d+[A-Z]?"
    r"|(?:paragraph|para\.?)\s*\d+[A-Z]?"
    r"|(?:clause)\s*\d+[A-Z]?"
    r"|§\s*\d+[A-Z]?"
    r"|\d+[A-Z]?\.\s+(?=[A-Z])"                   # "26.  Foo" bare numbered clause
    r")\s*[.\-—:]?\s*"
)

MAX_SNIPPET = 20000  # the template asks for the FULL, exact provision text — quote the
                     # whole section; only a pathological multi-page section is capped here.


def _law_name(doc: DiscoveredDoc) -> str:
    return doc.title.strip()


def _location_ref(ocr: OCRMetrics, start: int, total_len: int, label: str) -> str:
    """Template 'Location Reference': PDF → page number; HTML/text → URL anchor/path."""
    if ocr.used and ocr.pages:
        page = min(ocr.pages, max(1, int(start / max(total_len, 1) * ocr.pages) + 1))
        return f"p. {page}"
    # HTML/text → an anchor-style ref (e.g. "Section 26D" -> "#sec26D")
    num = re.search(r"\d+[A-Za-z]?", label)
    prefix = re.sub(r"[^a-z]", "", label.split()[0].lower())[:4] if label.split() else "s"
    return f"#{prefix}{num.group(0)}" if num else label


def extract_provisions(doc: DiscoveredDoc, raw_text: str, ocr: OCRMetrics) -> list[Provision]:
    text = raw_text or ""
    total = len(text)
    matches = list(SECTION_RE.finditer(text))
    provisions: list[Provision] = []

    if not matches:
        # whole-doc fallback: still emit one provision so nothing is silently dropped
        snippet = text.strip()[:MAX_SNIPPET]
        if snippet:
            loc = _location_ref(ocr, 0, total, "(document)")
            provisions.append(_mk(doc, "(document)", snippet, (0, len(snippet)), loc, ocr, 0))
        return provisions

    for i, m in enumerate(matches):
        label = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".-—:").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        snippet = body[:MAX_SNIPPET]
        norm = _normalise_label(label)
        # template requires article AND paragraph ("never write just Art. 26"): if the
        # section body opens with a sub-paragraph marker (e.g. "26.—(1)(a)"), append it.
        para = re.match(r"^[\s.\-—:]*(\(\d+[A-Za-z]?\)(?:\([a-z]+\))?)", body)
        if para:
            norm = f"{norm}{para.group(1)}"
        loc = _location_ref(ocr, start, total, norm)
        provisions.append(_mk(doc, norm, snippet, (start, start + len(snippet)), loc, ocr, i))
    return provisions


def _normalise_label(label: str) -> str:
    label = label.replace("Sec.", "Section").replace("S.", "Section").replace("Art.", "Article").replace("Reg.", "Regulation")
    return label[:1].upper() + label[1:]


def _mk(doc: DiscoveredDoc, label: str, snippet: str, span, location_ref: str, ocr: OCRMetrics, idx: int) -> Provision:
    return Provision(
        provision_id=f"{doc.doc_id}#p{idx}",
        doc_id=doc.doc_id,
        economy=doc.economy,
        law_name=_law_name(doc),
        law_number=doc.law_number,
        article_section=label,
        verbatim_snippet=snippet,
        source_url=doc.source_url,
        amendment_date=doc.amendment_date,
        location_ref=location_ref,
        source_pdf_path=doc.local_path,
        char_span=span,
        ocr=ocr,
    )
