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


# A plausible law-title line: a law-type keyword, short, not a sentence. Used to recover
# the real name when the discovery title is a generic portal label (MY's portal-wide
# "Malaysia Federal Legislation" <title>, or a "[PDF] … - lom.agc.gov.my" search title).
_LAW_TYPE_RE = re.compile(
    r"\b(act|akta|ordinance|enactment|regulations?|rules|by[- ]?laws?|code|decree|order)\b",
    re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# Gazette/statute headers list the instrument's title as the UPPERCASE block immediately
# before an "ARRANGEMENT OF SECTIONS/REGULATIONS" table of contents. The parent Act and a
# "(Act 26 of 2012)" citation appear separately, so the citation acts as a separator that
# isolates a subsidiary instrument's own name from its parent Act's.
_ANCHOR_RE = re.compile(r"^\s*ARRANGEMENT OF\b", re.I)
_CITATION_RE = re.compile(r"^\(.*\)\.?$")          # "(Act 26 of 2012)", "(Cap. 50)"
_BOILERPLATE_RE = re.compile(
    r"^(no\.|first published|informal consolidation|reprint|revised edition|"
    r".*gazette|s\s*\d+\s*/|cap\.?\s|chapter\b|p\.?u\.?|\d)", re.I)


_TITLE_CONNECTORS = {"and", "the", "for", "of", "to", "by", "in", "on", "under", "with", "a", "an"}


def _is_title_line(line: str) -> bool:
    """A heading line: ALL-CAPS, or Title Case (most significant words Capitalised). Accepts
    both because SSO consolidated PDFs print the instrument name in Title Case ("Cybersecurity
    Act 2018") while as-made gazettes print it ALL-CAPS — and rejects running prose.

    A clause/sentence colon or semicolon (e.g. the enactment formula "…assented to by the
    President on 2 March 2018:") is never part of a law title, so it disqualifies the line."""
    if re.search(r"[:;]", line):
        return False
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'.-]*", line) if len(w) >= 2]
    if not words:
        return False
    capish = sum(1 for w in words if w[0].isupper() or w.lower() in _TITLE_CONNECTORS)
    return capish / len(words) >= 0.8


def _recover_law_name(text: str) -> str | None:
    """Best-effort law name from a document's header region.

    Primary: the UPPERCASE title block directly above an "ARRANGEMENT OF …" table of
    contents — joined across wrapped lines (e.g. "PERSONAL DATA PROTECTION" + "REGULATIONS
    2021"), stopping at the citation/boilerplate that separates it from the parent Act.
    Fallback (no such anchor): the best title-like line carrying a law-type word + year.
    Returns None when nothing convincing is found so the caller keeps the discovery title."""
    lines = [ln.strip() for ln in text[:8000].splitlines()[:80]]

    anchor = next((i for i, l in enumerate(lines) if _ANCHOR_RE.match(l)), None)
    if anchor is not None:
        # Find the instrument-name line directly above the anchor, skipping the blank /
        # citation / boilerplate lines ("(No. 9 of 2018)", "2020 Ed.", "Informal
        # Consolidation") that sit between the name and the table of contents.
        j = anchor - 1
        while j >= 0:
            l = lines[j]
            if not l or _CITATION_RE.match(l) or _BOILERPLATE_RE.match(l):
                j -= 1
                continue
            break
        if j >= 0 and _is_title_line(lines[j]):
            block = [lines[j]]
            # The name may wrap: a line that STARTS with a bare instrument-type word
            # ("REGULATIONS 2021") needs its subject prefix ("PERSONAL DATA PROTECTION")
            # from the line above. A line that starts with a subject ("Cybersecurity Act
            # 2018", "PERSONAL DATA PROTECTION ACT 2010") is already complete — don't reach
            # up into the jurisdiction/number header ("LAWS OF MALAYSIA", "Act 709").
            k = j - 1
            while k >= 0 and re.match(r"^(regulations?|rules|order|by[- ]?laws?|act|akta|code)\b",
                                      block[0], re.I):
                prev = lines[k]
                if prev and not _CITATION_RE.match(prev) and not _BOILERPLATE_RE.match(prev) \
                        and _is_title_line(prev):
                    block.insert(0, prev)
                    k -= 1
                else:
                    break
            name = re.sub(r"\s+", " ", " ".join(block)).strip()
            if _LAW_TYPE_RE.search(name):
                return name

    # Short amendment acts (MY) have no "ARRANGEMENT OF" — the name is the title block
    # directly BELOW a "LAWS OF MALAYSIA / Act A1727" header (the act-number line, NOT a
    # year line like "ACT 2024"). Collect the wrapped name lines after it.
    for i, l in enumerate(lines):
        m = re.match(r"^(?:act|akta)\s+([A-Za-z]?\d+[A-Za-z]?)$", l, re.I)
        if not m or _YEAR_RE.fullmatch(m.group(1)):
            continue
        block = []
        for n in lines[i + 1:i + 5]:
            if not n or _CITATION_RE.match(n) or _BOILERPLATE_RE.match(n) or _ANCHOR_RE.match(n):
                break
            if _is_title_line(n):
                block.append(n)
            else:
                break
        name = re.sub(r"\s+", " ", " ".join(block)).strip()
        if _LAW_TYPE_RE.search(name):
            return name

    # Fallback: score individual title-like lines (skip bare citations).
    best, best_score = None, 0.0
    for raw in lines[:60]:
        line = raw.strip()
        if not (6 <= len(line) <= 90) or not _LAW_TYPE_RE.search(line):
            continue
        if _CITATION_RE.match(line):
            continue
        letters = [c for c in line if c.isalpha()]
        if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.3:
            continue
        words = [w for w in re.findall(r"[A-Za-z]+", line) if len(w) >= 2]
        if len(words) < 2:
            continue
        score = (1.0 if _YEAR_RE.search(line) else 0.0) + 0.15 * min(len(words), 8)
        if score > best_score:
            best, best_score = line, score
    return best


def _law_name(doc: DiscoveredDoc, raw_text: str = "") -> str:
    """Law name for a provision. Prefer the discovery title, but recover the name from the
    document's own header when the title is a generic portal label (MY's "Malaysia Federal
    Legislation", a UUID) OR a section heading with no law-type word ("Transfer of Personal
    Data Outside Singapore" — an SSO sub-provision title, not the regulation's name)."""
    from .discovery import _clean_title, _is_generic_title
    title = doc.title.strip()
    cleaned = _clean_title(title)
    if _is_generic_title(title) or not _LAW_TYPE_RE.search(cleaned):
        recovered = _recover_law_name(raw_text)
        if recovered:
            return recovered
    return cleaned or title


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
    law_name = _law_name(doc, text)
    matches = list(SECTION_RE.finditer(text))
    provisions: list[Provision] = []

    if not matches:
        # whole-doc fallback: still emit one provision so nothing is silently dropped
        snippet = text.strip()[:MAX_SNIPPET]
        if snippet:
            loc = _location_ref(ocr, 0, total, "(document)")
            provisions.append(_mk(doc, "(document)", snippet, (0, len(snippet)), loc, ocr, 0, law_name))
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
        provisions.append(_mk(doc, norm, snippet, (start, start + len(snippet)), loc, ocr, i, law_name))
    return provisions


def _normalise_label(label: str) -> str:
    label = label.replace("Sec.", "Section").replace("S.", "Section").replace("Art.", "Article").replace("Reg.", "Regulation")
    return label[:1].upper() + label[1:]


def _mk(doc: DiscoveredDoc, label: str, snippet: str, span, location_ref: str, ocr: OCRMetrics,
        idx: int, law_name: str) -> Provision:
    return Provision(
        provision_id=f"{doc.doc_id}#p{idx}",
        doc_id=doc.doc_id,
        economy=doc.economy,
        law_name=law_name,
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
