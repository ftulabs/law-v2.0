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

from ..schemas import DiscoveredDoc, Economy, OCRMetrics, Provision

HEADING_MARK = "\x1e"   # font-detected heading sentinel emitted by ocr._pdf_text_layer
PAGE_MARK = "\x0c"      # page sentinel emitted by ocr._join_pages, as "\x0c<page>\x0c"
PAGE_MARK_RE = re.compile(r"\x0c(\d+)\x0c")

# Provision-boundary markers, line-anchored so cross-references mid-sentence ("apart from",
# "under section 26") never match. Covers the drafting conventions across SG/AU/MY and the
# Finals economies: keyword forms (Section/Article/Regulation/Paragraph/Clause/Rule/By-law/
# Schedule/Part/Division), the Privacy-Act "Australian Privacy Principle N" (APP), and bare
# numbered clauses ("26. Foo"). Part/Division/Schedule REQUIRE a following number so the
# words alone ("Part from", "Schedule of fees") don't trigger.
SECTION_RE = re.compile(
    r"(?im)^[ \t]*(?:"
    r"\x1e[ \t]*(\d{1,3}[A-Za-z]{0,2})\b"                        # group 1: FONT-marked heading number ("77 Requirement…")
    r"|("                                                         # group 2: keyword / numbered markers
    r"(?:australian\s+privacy\s+principle|app)\s*\d+[A-Za-z]?"   #   APP 8 / Australian Privacy Principle 8
    r"|(?:section|sec\.?|s\.)\s*\d+[A-Za-z]{0,2}"                #   Section 26 / Sec. 12B / S. 13
    r"|(?:article|art\.?)\s*\d+[A-Za-z]{0,2}"                    #   Article 13
    r"|(?:regulation|reg\.?)\s*\d+[A-Za-z]{0,2}"
    r"|(?:paragraph|para\.?)\s*\d+[A-Za-z]{0,2}"
    r"|(?:clause|cl\.?)\s*\d+[A-Za-z]{0,2}"
    r"|(?:rule)\s*\d+[A-Za-z]{0,2}"
    r"|(?:by[- ]?law)\s*\d+[A-Za-z]{0,2}"
    r"|(?:schedule|sch\.?)\s+\d+[A-Za-z]{0,2}"                   #   Schedule 3 (needs a number)
    r"|(?:part|division)\s+\d+[A-Za-z]{0,2}(?=\s|$)"             #   Part 5 / Division 2 (needs a number)
    r"|(?:principle)\s+\d+[A-Za-z]?"                             #   Principle 8
    r"|§\s*\d+[A-Za-z]{0,2}"
    r"|\d{1,4}[A-Za-z]{0,2}\.\s*[‐-―]?\s*\(\d+[A-Za-z]?\)"       #   SG "11.—(1)" / MY "20. (1)" section body
    r"|\d+[A-Za-z]{0,2}\.\s+(?=[A-Z])"                           #   "26.  Foo" bare numbered clause
    r")"
    r")"
)

# On a font-marked PDF the markers already pin every numbered section, so we add ONLY the
# structural dividers the number-markers can't see (Schedule/Part/Division) and skip the
# Section/bare-number regex — which on those PDFs only re-matches running headers
# ("Section 77A" page tops) and list items, doubling the count. NOTE: the APP keyword is
# deliberately NOT here — in AU the real "Australian Privacy Principle N—…" headings are
# font-marked (so _MARK_RE catches them, relabelled to "APP N" in extract_provisions), while
# the keyword form ONLY ever appears as a cross-reference ("…Australian Privacy Principle 8.3
# prescribing a country") or a page running-header — both of which it would wrongly split on.
_MARK_RE = re.compile(r"(?im)^[ \t]*\x1e[ \t]*(\d{1,3}[A-Za-z]{0,2})\b")
_STRUCT_RE = re.compile(
    r"(?im)^[ \t]*("
    r"(?:schedule|sch\.?)\s+\d+[A-Za-z]{0,2}"
    r"|(?:part|division)\s+\d+[A-Za-z]{0,2}(?=\s|$)"
    r")")
# AU structural headings carry an em-dash + Title ("Schedule 1—Australian Privacy Principles",
# "Part 1—Preliminary"); the inline CROSS-REFERENCES that would otherwise match ("set out in
# Schedule 2 to the…", "Part IIIA of the Act", "My Health Record … Part 5") have no em-dash, so
# requiring it skips them — the same cross-ref trap as the APP keyword. Without this, a stray
# "Schedule N"/"Part N" reference becomes a boundary and mis-scopes the sections that follow.
_STRUCT_RE_AU = re.compile(
    r"(?im)^[ \t]*((?:schedule|part|division)\s+\d+[A-Za-z]?)\s*[—–]\s*(?=[A-Z])")
# Chinese statutes number articles as 第<numeral>条, with the numeral written in Han digits
# (第四十条) far more often than Arabic (第40条); chapters use 章 and are the structural divider.
# Line-anchored, because 第X条 also appears mid-sentence as a cross-reference ("依照本法第四十条
# 的规定"), which is exactly the trap the Latin patterns above guard against.
# Spaces are permitted BETWEEN the characters because PDF text extraction routinely inserts
# them into CJK runs: the Hainan Informatisation Regulations extract as "第 一 条", and the
# unspaced pattern found 3 headings in a 56-article statute — a 95% loss that nothing reports.
# The separator class is [ \t　] and deliberately NOT \s: \s matches a newline, which would
# let a "heading" straddle two lines and swallow unrelated text.
_STRUCT_RE_CN = re.compile(
    r"(?m)^[ \t　]*(第[ \t　]*(?:[一二三四五六七八九十百千零〇两0-9][ \t　]*){1,8}[条章节])")
# Mongolian statutes head each article "<n> дүгээр зүйл." (ordinal suffix varies with vowel
# harmony: дүгээр/дугаар, and дэх/дахь for some drafting). The 14.1 / 20.1.5 forms below it are
# CLAUSES inside the article — splitting on those would shatter one article into a dozen
# fragments and destroy the verbatim context the grader needs.
# The ordinal is written in DIGITS in modern drafting ("14 дүгээр зүйл") and SPELLED OUT in
# older instruments ("Хоёрдугаар зүйл" = article 2, "Гучингуравдугаар зүйл" = article 33 —
# both from the Constitution, which is cited by operative laws and so reaches extraction).
# A digits-only pattern found nothing in those and the whole instrument collapsed into one
# block, with no error: the quiet failure this economy specialises in. Mongolian builds the
# ordinal as a compound, so up to two Cyrillic words are allowed before the suffix ("Арван
# нэгдүгээр" = eleventh); a single \w+ would miss it.
# The trailing lookahead rejects the GENITIVE/DATIVE forms "зүйлийн" and "зүйлд", which is how
# a cross-reference reads ("…хуулийн 9 дүгээр зүйлийн 1 дэх хэсэг"). Those DO start a line in
# a preamble, so without it the recital that cites another Act becomes an article boundary —
# the same cross-reference trap the Latin and Han patterns above guard against.
_STRUCT_RE_MN = re.compile(
    r"(?im)^[ 	]*("
    r"(?:\d{1,3}|(?:[А-ЯӨҮЁа-яөүё]+[ 	]+){0,1}[А-ЯӨҮЁа-яөүё]+)"
    r"[ 	]*(?:д[үу]г[эа]{0,2}р|дэх|дахь)[ 	]+з[үу]йл)(?![а-яөүё])")
_APP_HEADING_RE = re.compile(
    r"^\s*(?:\d{1,3}[A-Za-z]{0,2}\s+)?Australian Privacy Principle\s+(\d+[A-Za-z]?)\b", re.I)
_DOTTED_TOC_RE = re.compile(r"(?m)^.*\.{4,}.*$")        # a table-of-contents dotted-leader line

# AU consolidated PDFs print page furniture BETWEEN and WITHIN provisions that is not law text
# and slips past the repeated-line stripper because the page number varies each page:
#   • a short-title footer ± page number — "356 Privacy Act 1988", "My Health Records Act 2012 89"
#   • a page-top header naming the current section/structural unit in WORD form — "Section 77A",
#     "Schedule 1 Australian Privacy Principles". The REAL headings are font-marked (sections) or
#     carry an em-dash (Schedule/Part), so these word forms are only running headers — note the
#     structural pattern deliberately stops before an em-dash so it never eats a real heading.
_AU_FURNITURE = [
    re.compile(r"(?im)^[ \t]*\d{0,4}[ \t]*[A-Z][A-Za-z ]+? Act (?:19|20)\d{2}[ \t]*\d{0,4}[ \t]*$"),
    # "Section 77A" / "Section 30CB" (two-letter suffix) / "Clause 8" page-top headers
    re.compile(r"(?im)^[ \t]*(?:Section|Clause)\s+\d+[A-Za-z]{0,2}[ \t]*$"),
    # left-aligned page header: "Division 3A …", "Schedule 1 Australian Privacy Principles"
    re.compile(r"(?im)^[ \t]*(?:Schedule|Part|Division)\s+\d+[A-Za-z]{0,2}(?:\s+[A-Z][^\n—–]*)?[ \t]*$"),
    # right-aligned page header: the unit TITLE then the marker last — "Assessments by, or at the
    # direction of, the Commissioner Division 3A". A Title-case line with NO em-dash (so the real
    # "Division 3A—Title" heading is untouched) and the marker as the final token (so a sentence
    # ending in "… Division 3A." keeps its full stop and is not matched).
    re.compile(r"(?im)^(?![ \t]*[(\d])[ \t]*[A-Z][^\n—–]{2,110}?[ \t](?:Division|Part)[ \t]+\d{1,3}[A-Za-z]{0,2}[ \t]*$"),
]


def _strip_au_chrome(text: str) -> str:
    for rx in _AU_FURNITURE:
        text = rx.sub("", text)
    return text


def _strip_au_table_continuation(text: str) -> str:
    """When a table spans a page, AU repeats its caption + column-header row at the top of the
    next page ("Permitted CRB disclosures" / "Item  If the disclosure is to … the condition or
    conditions are …"). Keep the FIRST occurrence (the real table header, part of the verbatim
    provision) and drop later repeats — plus the caption line directly above a repeat. A
    column-header row is recognised by its ' … ' (space-ellipsis) column gaps, which body
    prose effectively never has."""
    lines = text.split("\n")
    seen: set[str] = set()
    drop: set[int] = set()
    for i, ln in enumerate(lines):
        n = ln.strip()
        if " ... " in n and len(n) <= 160:             # a table column-header row
            if n in seen:
                drop.add(i)
                j = i - 1
                while j >= 0 and not lines[j].strip():  # skip blanks up to the repeated caption
                    j -= 1
                if j >= 0:
                    drop.add(j)
            else:
                seen.add(n)
    if not drop:
        return text
    return "\n".join(l for k, l in enumerate(lines) if k not in drop)

# SG/MY drafting: a section is NUMBERED at the margin — "11.—(1)" (SG em-dash), "20. (1)" (MY
# space-paren), "26. Foo" (bare). The "Section/Regulation/Paragraph/Article N" keyword forms in
# these statutes are ALWAYS cross-references to the parent Act ("…under section 28 of the Act"),
# so treating them as boundaries shreds a provision into cross-ref fragments. This profile keeps
# the numbered + structural (Part/Division/Schedule/APP) markers and DROPS the keyword forms.
_NUMBERED_RE = re.compile(
    r"(?im)^[ \t]*("
    r"(?:australian\s+privacy\s+principle|app)\s*\d+[A-Za-z]?"
    r"|(?:schedule|sch\.?)\s+\d+[A-Za-z]{0,2}"
    r"|(?:part|division)\s+\d+[A-Za-z]{0,2}(?=\s|$)"
    r"|(?:principle)\s+\d+[A-Za-z]?"
    r"|\d{1,4}[A-Za-z]{0,2}\.\s*[‐-―]?\s*\(\d+[A-Za-z]?\)"       # "11.—(1)" / "20. (1)"
    r"|\d+[A-Za-z]{0,2}\.\s+(?=[A-Z])"                           # "26. Foo" bare numbered clause
    r")")

MAX_SNIPPET = 20000  # the template asks for the FULL, exact provision text — quote the
                     # whole section; only a pathological multi-page section is capped here.


# ── SG SSO page chrome ───────────────────────────────────────────────────────
# Consolidated SSO PDFs print running headers/footers BETWEEN provisions that are NOT part of
# the law text: the consolidation stamp, the statute number (± page number), and bracketed
# amendment annotations on their own line. Left in, they pollute every verbatim snippet
# ("S 63/2021\n(4) This Part…") and split sections at the wrong place. Worse, these footers are
# BOLD, so ocr.py marks them with HEADING_MARK — and the page numbers in "1 S 63/2021" then
# masquerade as font-marked section headings (labels 1,3,5,…), forcing the marked path so the
# REAL sections are never found. So the leading mark is consumed here too, clearing the page
# furniture AND its spurious marks; the doc then falls back to the regex path correctly.
_M = r"[ \t]*\x1e?[ \t]*"                                                   # optional leading heading-mark
_SG_CHROME = [
    re.compile(rf"(?im)^{_M}Informal Consolidation\b.*$"),
    re.compile(rf"(?im)^{_M}S\s*\d+/\d+(?:\s+\d+)?[ \t]*$"),                # "S 63/2021" / "S 63/2021 14"
    re.compile(rf"(?im)^{_M}\d+\s+S\s*\d+/\d+[ \t]*$"),                     # "14 S 63/2021"
    re.compile(rf"(?im)^{_M}\[\s*S?\s*\d+/\d+(?:\s+wef\b[^\]]*)?\s*\][ \t]*$"),  # "[40/2020]" / "[S 734/2021 wef …]"
]

# SSO subsidiary-legislation "Published" snapshot pages (…/SL-Supp/S519-2018/Published) render
# a print-selection checkbox tree before the real text: "Select the provisions you wish to
# print…", Select All/Clear All/Print buttons, then a Table of Contents whose entries are bare
# section TITLES with no body ("Part 2 PROVIDING INFORMATION TO COMMISSIONER", "3 Information
# to ascertain…"). The Part/Division-style entries pass the structural boundary regex with
# nothing but a title as their "body" — one bogus provision per Part/Division, its "verbatim
# snippet" just the next few TOC labels or trailing page chrome. Drop the whole preamble up to
# the citation line ("No. S 519…") that starts the REAL instrument text — the same anchor SG
# law-name recovery already relies on for these documents (see _BOILERPLATE_RE below).
_SSO_PRINT_WIDGET_RE = re.compile(r"Select the provisions you wish to print", re.I)
_SSO_CITATION_NO_RE = re.compile(r"(?m)^No\.\s*S\s*\d+", re.I)


def _strip_sso_print_tree(text: str) -> str:
    widget = _SSO_PRINT_WIDGET_RE.search(text)
    if not widget:
        return text
    real_start = _SSO_CITATION_NO_RE.search(text, widget.end())
    if not real_start:
        return text
    return text[:widget.start()] + "\n" + text[real_start.start():]


def _strip_page_chrome(text: str, economy) -> str:
    if economy != Economy.SG:                      # the patterns are SSO-specific
        return text
    text = _strip_sso_print_tree(text)              # print-selection checkbox TOC, if present
    for rx in _SG_CHROME:
        text = rx.sub("", text)
    return text


# SG SSO *Act* (vs subsidiary-legislation) PDFs print a footer where the short title WRAPS across
# the page bottom with a page number + revised-edition tag — pdfplumber renders it as e.g.
#   Personal Data Protection
#   33 Act 2012 2020 Ed.
# Anchor on the edition tag ("… 2020 Ed.") and drop that line + the title-fragment line above it.
_SG_EDITION_RE = re.compile(r"\b(?:19|20)\d{2}\s+Ed\.\s*$")


def _strip_sg_act_footer(text: str, law_name: str) -> str:
    title_words = set(re.findall(r"[a-z]+", (law_name or "").lower()))
    lines = text.split("\n")
    drop: set[int] = set()
    for i, ln in enumerate(lines):
        if not _SG_EDITION_RE.search(ln):
            continue
        drop.add(i)                                # the "… 2020 Ed." footer line
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and title_words:                 # the wrapped title fragment directly above
            w = set(re.findall(r"[a-z]+", lines[j].lower()))
            if w and w <= title_words and not re.search(r"[.;:]$", lines[j].strip()):
                drop.add(j)
    if not drop:
        return text
    return "\n".join(l for k, l in enumerate(lines) if k not in drop)


# ── "Arrangement of Sections/Provisions" table of contents ───────────────────
# Statute PDFs open with a TOC whose entries ("199. Accounting records…", "11. Legally
# enforceable obligations") have no dotted leaders, so the bare-number rule would turn each
# into a bogus provision. The real body begins at the FIRST of: the enacting formula, a
# section opening with a subsection ("N.—(1)" / "N. (1)"), or a font-marked heading.
_SECTION_BODY_RE = re.compile(r"(?m)^\s*\d{1,4}[A-Za-z]{0,2}\.\s*[‐-―]?\s*\(\d")
_ARRANGEMENT_HDR_RE = re.compile(r"ARRANGEMENT OF\b", re.I)
_ENACTING_RE = re.compile(r"\b(?:ENACTED by|Be it enacted|enacts as follows|hereby enact)", re.I)


def _strip_arrangement_toc(text: str) -> str:
    hdr = _ARRANGEMENT_HDR_RE.search(text)
    if not hdr:
        return text
    cands = []
    enact = _ENACTING_RE.search(text, hdr.end())
    if enact:
        cands.append(enact.start())
    body = _SECTION_BODY_RE.search(text, hdr.end())
    if body:
        cands.append(body.start())
    mark = text.find(HEADING_MARK, hdr.end())
    if mark >= 0:
        cands.append(mark)
    if not cands:
        return text
    return text[:hdr.start()] + "\n" + text[min(cands):]


def _strip_running_headers(text: str, min_repeats: int = 4, max_len: int = 80) -> str:
    """Remove page running-headers/footers that repeat across pages — the act title, the
    "Schedule 1 Australian Privacy Principles" banner, "Compilation No. N", page strips. They
    otherwise match the Schedule/Part rules and fragment a provision at every page break (AU's
    APP 8 was cut after 8.1 by the per-page "Schedule 1…" header). The FIRST occurrence of each
    is KEPT so the real "Schedule N" heading that starts a schedule still anchors it."""
    from collections import Counter
    lines = text.split("\n")
    def norm(l: str) -> str:
        return l.replace(HEADING_MARK, "").strip()
    counts: Counter = Counter()
    for l in lines:
        n = norm(l)
        if 0 < len(n) <= max_len:
            counts[n] += 1
    repeated = {s for s, c in counts.items() if c >= min_repeats}
    if not repeated:
        return text
    out, seen = [], set()
    for l in lines:
        n = norm(l)
        if n in repeated:
            if n in seen:
                continue                            # drop all but the first occurrence
            seen.add(n)
        out.append(l)
    return "\n".join(out)


# A marginal section heading (SG sentence-case "Legally enforceable obligations") sits on the
# line directly above the numbered body "11.—(1)". It belongs to THIS section, so the snippet
# should begin there — not leak into the previous section's tail (and the previous section
# should END before it).
def _is_marginal_heading(line: str) -> bool:
    line = line.strip()
    if not (3 <= len(line) <= 80):
        return False
    if line[-1] in ".;:,":                         # a sentence/clause end is body, not a heading
        return False
    if re.match(r"^[\d(\[]", line):                # numbered / subsection / annotation line
        return False
    return bool(line[0].isupper() and re.search(r"[A-Za-z]", line))


def _heading_start(text: str, marker_start: int) -> int:
    """Start of the marginal heading line directly above a numbered marker, else the marker's
    own line start (so the 'N.—(1)' marker is kept in the body either way)."""
    ls = text.rfind("\n", 0, marker_start) + 1
    prev_end = ls - 1
    if prev_end <= 0:
        return ls
    prev_start = text.rfind("\n", 0, prev_end) + 1
    if _is_marginal_heading(text[prev_start:prev_end]):
        return prev_start
    return ls


# A plausible law-title line: a law-type keyword, short, not a sentence. Used to recover
# the real name when the discovery title is a generic portal label (MY's portal-wide
# "Malaysia Federal Legislation" <title>, or a "[PDF] … - lom.agc.gov.my" search title).
_LAW_TYPE_RE = re.compile(
    r"\b(act|akta|ordinance|enactment|regulations?|rules|by[- ]?laws?|code|decree|order|"
    r"guidelines?)\b",
    re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# MY's PDP Department issues subsidiary "Guidelines" (not gazetted Acts/Regulations) whose
# cover page states "<SUBJECT> GUIDELINES NO.: <N>/<YYYY>" on one line and the guideline's
# actual TOPIC on the line(s) immediately below (e.g. "CROSS BORDER PERSONAL DATA TRANSFER").
# Recover the topic as the operative name and keep the reference number attached in a sane
# grammatical position — never stranded alone at the front, which is what a mangled search-
# engine title otherwise does (e.g. a bare "3/2025 CROSS BORDER PERSONAL DATA TRANSFER").
_GUIDELINE_HEADER_RE = re.compile(r"^(.+?)\s+GUIDELINES?\s+NO\.?:?\s*([A-Za-z0-9/.\-]+)\s*$", re.I)
_GUIDELINE_META_RE = re.compile(r"^(?:version\b|date of issuance\b)", re.I)


def _recover_guideline_name(lines: list[str]) -> str | None:
    for i, l in enumerate(lines):
        m = _GUIDELINE_HEADER_RE.match(l)
        if not m:
            continue
        prefix, num = m.group(1).strip(), m.group(2).strip()
        topic = []
        for n in lines[i + 1:i + 6]:
            if not n:                                    # PDF cover pages space the topic out
                continue                                  # with a blank line — skip, don't stop
            if _GUIDELINE_META_RE.match(n) or _CITATION_RE.match(n) or _BOILERPLATE_RE.match(n):
                break
            if _is_title_line(n):
                topic.append(n)
            else:
                break
        if topic:
            return re.sub(r"\s+", " ", f"{prefix} Guidelines No. {num} — {' '.join(topic)}").strip()
    return None

# Gazette/statute headers list the instrument's title as the UPPERCASE block immediately
# before an "ARRANGEMENT OF SECTIONS/REGULATIONS" table of contents. The parent Act and a
# "(Act 26 of 2012)" citation appear separately, so the citation acts as a separator that
# isolates a subsidiary instrument's own name from its parent Act's.
_ANCHOR_RE = re.compile(r"^\s*ARRANGEMENT OF\b", re.I)
# A statute CITATION in parens — "(Act 26 of 2012)", "(Cap. 50)", "(No. S 64)". Must contain a
# digit or "Cap"; a parenthetical that is part of the TITLE ("(Notification of Data Breaches)")
# has neither, so it is NOT treated as a citation and stays part of the recovered name.
_CITATION_RE = re.compile(r"^\([^)]*(?:\d|\bcap\b)[^)]*\)\.?$", re.I)
# A line opening with a structural-division word + number ("Part 1 AMENDMENTS TO ACTIVE
# MOBILITY ACT 2017", "Division 3", "Schedule 2") is a heading INSIDE a document, never the
# document's own name — so it must not be recovered as the law name even though it carries a
# law-type word ("ACT") and a year. (Real instrument names don't begin "Part 1 …".)
_STRUCT_TITLE_RE = re.compile(r"^(?:part|division|schedule|chapter)\s+[\dIVXLC]+\b", re.I)
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

    # Subsidiary "Guidelines" cover page (MY PDP Department) — checked first: it has neither
    # an "ARRANGEMENT OF" anchor nor an "Act NNNN" header, and its own pattern is unambiguous.
    guideline = _recover_guideline_name(lines)
    if guideline:
        return guideline

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
        if j >= 0 and _is_title_line(lines[j]) and not _STRUCT_TITLE_RE.match(lines[j]):
            block = [lines[j]]
            # The name may wrap: a line that STARTS with a bare instrument-type word
            # ("REGULATIONS 2021") needs its subject prefix ("PERSONAL DATA PROTECTION")
            # from the line above. A line that starts with a subject ("Cybersecurity Act
            # 2018", "PERSONAL DATA PROTECTION ACT 2010") is already complete — don't reach
            # up into the jurisdiction/number header ("LAWS OF MALAYSIA", "Act 709").
            k = j - 1
            while k >= 0:
                # Keep reaching up while the assembled head is still a bare instrument-type word
                # ("REGULATIONS 2021") OR a parenthetical qualifier ("(Notification of Data
                # Breaches)") that still needs its subject prefix ("PERSONAL DATA PROTECTION") OR
                # carries an UNMATCHED closing paren ("FINANCING) RULES 2023") — the title's
                # opening "(" wrapped to the line above ("TERRORISM (SUPPRESSION OF").
                if not (re.match(r"^(regulations?|rules|order|by[- ]?laws?|act|akta|code)\b",
                                 block[0], re.I) or block[0].startswith("(")
                        or block[0].count(")") > block[0].count("(")):
                    break
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
        if _CITATION_RE.match(line) or _STRUCT_TITLE_RE.match(line):
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
    # A portal that states the statute name separately is more reliable than any heuristic
    # over a title, so it wins outright. See DiscoveredDoc.law_name for when to set it.
    if getattr(doc, "law_name", None):
        return doc.law_name.strip()
    from .discovery import _clean_title, _is_generic_title
    title = doc.title.strip()
    cleaned = _clean_title(title)
    if _is_generic_title(title) or not _LAW_TYPE_RE.search(cleaned):
        recovered = _recover_law_name(raw_text)
        if recovered:
            return recovered
    # never let a titleless blob (a year range "2010-2011", a bare number) stand as a law name
    if len(re.findall(r"[A-Za-z]", cleaned)) < 4:
        return _recover_law_name(raw_text) or cleaned or title
    return cleaned or title


def _location_ref(ocr: OCRMetrics, start: int, total_len: int, label: str,
                  text: str | None = None) -> str:
    """Template 'Location Reference': PDF → page number; HTML/text → URL anchor/path.

    The page is COUNTED, not estimated. `ocr._join_pages` marks every page boundary with
    PAGE_MARK, so the page holding an offset is just the number of marks before it. The old
    formula interpolated (offset/total × pages), which assumes uniform characters per page —
    false for any statute with schedules or tables. An audit that re-read each cited page with
    a second extractor found the interpolated citation wrong roughly half the time even though
    the snippet text was exactly verbatim (see backend/eval/extraction_audit.py, check D).
    Interpolation remains only as the fallback for text with no marks (e.g. an OCR engine that
    returns one undivided block)."""
    if ocr.pages:
        if text is not None and PAGE_MARK in text:
            last = None
            for m in PAGE_MARK_RE.finditer(text, 0, max(start, 1)):
                last = m
            if last is not None:
                return f"p. {min(ocr.pages, int(last.group(1)))}"
        page = min(ocr.pages, max(1, int(start / max(total_len, 1) * ocr.pages) + 1))
        return f"p. {page}"
    # HTML/text → an anchor-style ref (e.g. "Section 26D" -> "#sec26D")
    num = re.search(r"\d+[A-Za-z]?", label)
    prefix = re.sub(r"[^a-z]", "", label.split()[0].lower())[:4] if label.split() else "s"
    return f"#{prefix}{num.group(0)}" if num else label


def _boundaries(text: str, economy=None) -> list[tuple]:
    """Sorted (start, end, raw_label, marked) provision boundaries, chosen PER COUNTRY since
    statutes are not drafted alike: font-marked PDFs (AU) use the markers + structural
    dividers; SG/MY use numbered + structural markers (their 'Section N' keyword forms are
    only cross-references); everything else uses the full SECTION_RE (keyword + numbered)."""
    out: list[tuple] = []
    if economy == Economy.CN:
        # Han-script statutes carry none of the Latin markers, and the font-marked path is
        # meaningless here — 第X条 IS the heading, marked or not.
        # The label is de-spaced so the citation reads 第一条, not the "第 一 条" the PDF layer
        # produced — the snippet keeps the source text untouched, only the label is tidied.
        out = [(m.start(), m.end(), re.sub(r"[ \t　]+", "", m.group(1)), False)
               for m in _STRUCT_RE_CN.finditer(text)]
    elif economy == Economy.MN:
        out = [(m.start(), m.end(), m.group(1), False) for m in _STRUCT_RE_MN.finditer(text)]
        if len(out) < 3:
            # An English translation, or an instrument drafted without зүйл headings. The
            # fallback only wins if it actually finds MORE — a short Mongolian instrument with
            # two real articles must not be thrown away for a Latin regex that matches nothing.
            alt = [(m.start(), m.end(), m.group(2) or m.group(1), bool(m.group(1)))
                   for m in SECTION_RE.finditer(text)]
            if len(alt) > len(out):
                out = alt
    elif economy in (Economy.SG, Economy.MY, Economy.IN):
        # India is here too: the Indian Code prints "3. Definitions.—(1) …", the same numbered
        # margin form as SG/MY, and its statutes are English so nothing else needs to change.
        # SG/MY DON'T font-mark section headings — their numbered "N.—(1)" margin form is the
        # signal. This branch is checked BEFORE the HEADING_MARK one on purpose: a big consolidated
        # PDF (e.g. MY Income Tax Act 1967, 818 pp) can carry a stray bold run that puts a \x1e in
        # the text; letting that force the AU font-marked path below finds only the structural
        # Schedule/Part dividers and loses all 300+ numbered sections (s82 'Duty to keep records'
        # etc.). So SG/MY ALWAYS use the numbered path, ignoring marks.
        out = [(m.start(), m.end(), m.group(1), False) for m in _NUMBERED_RE.finditer(text)]
        if len(out) < 3:                       # sparse → a keyword-style doc; use the full regex
            out = [(m.start(), m.end(), m.group(2) or m.group(1), bool(m.group(1)))
                   for m in SECTION_RE.finditer(text)]
    elif HEADING_MARK in text:
        struct = _STRUCT_RE_AU if economy == Economy.AU else _STRUCT_RE
        out += [(m.start(), m.end(), m.group(1), True) for m in _MARK_RE.finditer(text)]
        out += [(m.start(), m.end(), m.group(1), False) for m in struct.finditer(text)]
        out.sort(key=lambda b: b[0])
    else:
        out = [(m.start(), m.end(), m.group(2) or m.group(1), bool(m.group(1)))
               for m in SECTION_RE.finditer(text)]
    # drop boundaries that collide (within 2 chars) — keeps a marker over a regex re-match
    merged: list[tuple] = []
    for b in out:
        if merged and b[0] - merged[-1][0] <= 2:
            continue
        merged.append(b)
    return merged


_ERROR_PAGE_RE = re.compile(
    r"page not found|page you are looking for cannot be found|404 not found|error 404", re.I)


def extract_provisions(doc: DiscoveredDoc, raw_text: str, ocr: OCRMetrics) -> list[Provision]:
    text = raw_text or ""
    # A dead/redirected portal URL (e.g. an uncommenced act whose PDF 404s) yields a short
    # "Page Not Found" HTML page — never a law. Drop it instead of emitting one bogus provision.
    if _ERROR_PAGE_RE.search(text[:600]) and len(text) < 4000:
        return []
    text = _strip_page_chrome(text, doc.economy)        # drop SSO running headers/footers
    if doc.economy == Economy.AU:                        # AU PDFs: a dotted-leader "Contents" TOC
        text = _DOTTED_TOC_RE.sub("", text)              # ("Schedule 1……… 5") — drop those lines so
        text = _strip_running_headers(text)              # their "Schedule N" entries aren't boundaries
    law_name = _law_name(doc, text)                     # needs the ARRANGEMENT anchor → before TOC strip
    if doc.economy == Economy.AU:                        # drop act-title±page footers + word-form
        text = _strip_au_chrome(text)                    # "Section 77A"/"Clause 8"/"Schedule 1 …" headers
        text = _strip_au_table_continuation(text)        # repeated table caption + column header
    if doc.economy == Economy.SG:
        text = _strip_sg_act_footer(text, law_name)      # wrapped "… Act 2012 2020 Ed." page footer
    if doc.economy in (Economy.SG, Economy.MY):
        # SG/MY headings aren't font-marked; any \x1e here is a stray bold run (a heading word, a
        # captioned table). Drop the marks so they neither pollute the verbatim snippet nor (with
        # the _boundaries guard) risk the font-marked path. Done after the SG footer strip, which
        # itself relies on the leading \x1e to spot bold footers.
        text = text.replace(HEADING_MARK, "")
    text = _strip_arrangement_toc(text)                 # drop the table-of-contents block
    if doc.economy == Economy.AU:
        # AU's "Contents" lists "Schedule 1/2…" BEFORE the body; those entries would set the
        # schedule context early and mis-scope every main section ("Schedule 2, Section 13D").
        # The real body starts at the first font-marked section, so drop everything before it.
        fm = text.find(HEADING_MARK)
        if fm > 0:
            text = text[fm:]
    total = len(text)
    bounds = _boundaries(text, doc.economy)
    provisions: list[Provision] = []

    if not bounds:
        # whole-doc fallback: still emit one provision so nothing is silently dropped
        snippet = PAGE_MARK_RE.sub("", text.replace(HEADING_MARK, "")).strip()[:MAX_SNIPPET]
        if snippet:
            loc = _location_ref(ocr, 0, total, "(document)", text)
            provisions.append(_mk(doc, "(document)", snippet, (0, len(snippet)), loc, ocr, 0, law_name))
        return provisions

    # A bare numbered marker ("11.—(1)", "26. Foo") is preceded by its own marginal heading and
    # KEEPS the marker in the body; a keyword marker ("Section 26") consumes it (the label is
    # already the citation). A font-marked AU heading ALSO keeps the marker — the number and
    # title are one bold run in the source, so the verbatim snippet should open on the number
    # ("26  Cross-border disclosure…"), not skip straight to the title text.
    def _numbered(label: str, marked: bool) -> bool:
        return bool(re.match(r"^\d", label.strip())) and not marked

    heads = [_heading_start(text, b[0]) if _numbered(b[2], b[3]) else b[0] for b in bounds]

    current_schedule = None                             # AU: provisions renumber inside each schedule
    for i, (bstart, bend, raw_label, marked) in enumerate(bounds):
        start = bend if (not _numbered(raw_label, marked) and not marked) else heads[i]
        end = heads[i + 1] if i + 1 < len(bounds) else len(text)
        # Sentinels are stripped from the SNIPPET only; they stay in `text` so char_span and
        # the page count keep indexing the same string. `confidence.snippet_grounding`
        # normalises both sides, so a provision spanning a page break still verifies exactly.
        body = PAGE_MARK_RE.sub("", text[start:end].replace(HEADING_MARK, "")).strip()
        if len(body) < 20:
            # a Part/Division/Schedule heading stub, or a page running-header/footer
            # ("Privacy Act 1988 2", "2020 Ed.") — no substantive provision text.
            continue
        # drop page-furniture boundaries whose own label is a bare year ("2020 Ed.")
        if re.fullmatch(r"(?:19|20)\d{2}[A-Za-z.]*", raw_label.strip()):
            continue
        snippet = body[:MAX_SNIPPET]
        norm = _normalise_label(raw_label, marked=marked)
        if norm.startswith("Schedule "):
            current_schedule = norm                     # subsequent sections belong to this schedule
        if marked:
            # A font-marked heading inside Schedule 1 is an Australian Privacy Principle —
            # relabel "Section 8" → "APP 8" (its full text 8.1–8.x is now one provision, since
            # the keyword/running-header boundaries that cut it after 8.1 are gone). A marked
            # section in any OTHER schedule is scoped ("Schedule 2, Section 1") so its restarted
            # numbering doesn't collide with the main body's "Section 1".
            mapp = _APP_HEADING_RE.match(body)
            if mapp:
                norm = f"APP {mapp.group(1).upper()}"
            elif current_schedule:
                norm = f"{current_schedule}, {norm}"
        # NOTE: no subsection is guessed here — extraction doesn't yet know which part of a
        # multi-subsection section a given indicator mapping actually relies on (could be any
        # subsection, or the whole section). The label stays at section granularity; mapping.py
        # narrows it to "Section 26(2)" per-mapping once the grader identifies the operative
        # subsection, falling back to the bare section (this norm) when it spans the whole thing.
        loc = _location_ref(ocr, start, total, norm, text)
        provisions.append(_mk(doc, norm, snippet, (start, start + len(snippet)), loc, ocr, i, law_name))
    return provisions


_ABBR = [(re.compile(r"^sec\.?(?=\s|\d|$)", re.I), "Section"), (re.compile(r"^s\.\s*", re.I), "Section "),
         (re.compile(r"^art\.?(?=\s|\d|$)", re.I), "Article"), (re.compile(r"^reg\.?(?=\s|\d|$)", re.I), "Regulation"),
         (re.compile(r"^para\.?(?=\s|\d|$)", re.I), "Paragraph"), (re.compile(r"^sch\.?(?=\s|\d|$)", re.I), "Schedule"),
         (re.compile(r"^cl\.?(?=\s|\d|$)", re.I), "Clause"),
         (re.compile(r"^(?:australian\s+privacy\s+principle|principle)\b", re.I), "APP")]


def _normalise_label(label: str, marked: bool = False) -> str:
    """Canonical, clean component label.
      • font-marked AU headings ("77") → "Section 77"
      • expand abbreviations (Sec.→Section, Sch.→Schedule, Australian Privacy Principle→APP)
      • UPPERCASE a trailing letter suffix on the number ("12b"→"12B")
      • collapse an APP sub-paragraph to the principle ("APP 1.2"→"APP 1")
      • strip dangling brackets/punctuation ("Schedule 3)"→"Schedule 3")
    """
    s = re.sub(r"\s+", " ", label).strip()
    if marked:
        s = f"Section {s}"
    # SG/MY body marker "11.—(1)" / "20. (1)" → keep just the number ("11"); the bare-number
    # rule below then makes it "Section 11" (the subsection stays in the verbatim body).
    s = re.sub(r"^(\d+[A-Za-z]{0,2})\.\s*[‐-―]?\s*\(\d.*$", r"\1", s)
    for rx, rep in _ABBR:
        s = rx.sub(rep, s, count=1)
    s = re.sub(r"^(APP)\s*(\d+)\.\d+", r"\1 \2", s, flags=re.I)        # APP 1.2 → APP 1
    s = re.sub(r"(\d+)([A-Za-z]{1,2})\b", lambda m: m.group(1) + m.group(2).upper(), s)  # 12b → 12B
    s = re.sub(r"^([A-Za-z§]+)(\d)", r"\1 \2", s)                      # "Section26" → "Section 26"
    s = re.sub(r"[)\]}.,;:\-—\s]+$", "", s).strip()                    # drop trailing "), ." etc.
    if re.fullmatch(r"\d+[A-Za-z]{0,2}", s):                           # a bare "5" / "12B" → "Section 5"
        s = "Section " + s
    if not re.match(r"^(APP|§)\b", s):
        s = s[:1].upper() + s[1:]
    return s


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
