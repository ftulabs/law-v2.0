"""Link the judges' law NAMES to catalogue law_ids.

The Database cites laws by name and often links a third-party mirror (mohre.um.edu.my,
cyrilla.org, lokekinggoh.com) rather than the official portal, so URL matching is useless —
the name is the only stable join key. Malaysian entries additionally carry the act number
("Personal Data Protection Act (Act 709) 2010"), which is an exact key when present.

Matching is deliberately conservative: an ambiguous match is reported as unmatched rather
than guessed, because a wrong link silently corrupts every recall number computed from it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from ..corpus import store

# Only genuinely contentless words are stripped. Instrument-TYPE words (code, practice,
# standard, strategy, regulations, guideline…) are kept and enforced separately by
# `_TYPE_WORDS` — dropping them is what made "Code of Practice for Licensees under the
# Communications and Multimedia Act" score 0.67 against the plain "Personal Data Protection
# Act 2010" and link to the wrong instrument.
_NOISE_RE = re.compile(
    r"\b(?:act|akta|ordinance|enactment|of|the|for|and|under|no|cap|chapter|"
    r"revised|edition|reprint)\b", re.I)
_ACTNO_RE = re.compile(r"\bact\s*([A-Z]?\d{1,4}[A-Z]?)\b", re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# A cited name carrying one of these is a DIFFERENT KIND of instrument from a principal Act.
# If the label says "Code of Practice" / "Strategy" / "Regulations" and the candidate title
# does not, it is not the same document however well the remaining words overlap.
_TYPE_WORDS = ("code of practice", "code", "standard", "strategy", "guideline", "guide",
               "regulations", "rules", "licence", "license", "terms and conditions",
               "impact assessment", "advisory")


# Malay → English for instrument naming. The judges cite Malaysian instruments by their
# English names, but the regulator catalogues some of them only in Bahasa Malaysia
# ("Standard Perlindungan Data Peribadi 2015", "KOD TATA AMALAN … SEKTOR KOMUNIKASI"), so a
# purely English token comparison scored 0.00 against a document that WAS discovered. This is
# an evaluation-side normalisation only — the pipeline itself never needs it, because retrieval
# runs on provision text through a multilingual embedder.
_MS_EN = [
    (re.compile(r"\bkod\s+tata\s+amalan\b|\bkod\s+amalan\b", re.I), "code of practice"),
    (re.compile(r"\bperlindungan\s+data\s+peribadi\b", re.I), "personal data protection"),
    (re.compile(r"\bdata\s+peribadi\b", re.I), "personal data"),
    (re.compile(r"\bsektor\s+komunikasi\b", re.I), "communications sector"),
    (re.compile(r"\bsektor\s+perbankan\b|\bsektor\s+kewangan\b", re.I), "banking sector"),
    (re.compile(r"\bgaris\s+panduan\b", re.I), "guideline"),
    (re.compile(r"\bperaturan\b", re.I), "regulations"),
    (re.compile(r"\buntuk\b|\bbagi\b|\bdan\b", re.I), " "),
]


def _norm(text: str) -> str:
    # Separators are flattened BEFORE translating: regulator filenames are hyphen-joined
    # ("KOD-TATA-AMALAN-PERLINDUNGAN-DATA-PERIBADI-UNTUK-SEKTOR-KOMUNIKASI"), so phrase
    # patterns written with \s+ silently failed to match the very titles they exist for.
    t = re.sub(r"[^\w\s]", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t)
    for rx, en in _MS_EN:
        t = rx.sub(en, t)
    t = _YEAR_RE.sub(" ", t)
    t = _NOISE_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(text: str) -> set[str]:
    return {w for w in _norm(text).split() if len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> tuple[float, float]:
    """(coverage of the cited name, coverage of the candidate title)."""
    if not a or not b:
        return 0.0, 0.0
    inter = len(a & b)
    return inter / len(a), inter / len(b)


def _type_compatible(label: str, title: str) -> bool:
    """Both sides must agree on the kind of instrument (see _TYPE_WORDS).

    Compared on the NORMALISED forms, so a Malay title still declares its type: checking the
    raw strings rejected "KOD TATA AMALAN … SEKTOR KOMUNIKASI" for a label reading "Code of
    Practice …", i.e. it discarded the right document for being in the other official language.
    """
    low_l, low_t = _norm(label).lower(), _norm(title).lower()
    for w in _TYPE_WORDS:
        # Word-boundary match. Substring matching made "Licensees" (who the code binds) look
        # like the instrument type "license", so a Code of Practice for Licensees was rejected
        # against its own Malay title for a type conflict that did not exist.
        rx = re.compile(rf"\b{re.escape(w)}\b")
        if rx.search(low_l) and not rx.search(low_t):
            return False
    return True


@dataclass
class Link:
    label_law: str
    economy: str
    law_id: str | None
    matched_title: str | None
    score: float
    how: str            # act_number | name | none


def _url_key(url: str) -> str:
    """Comparable form of a document URL: host without www + decoded path, no query."""
    from urllib.parse import unquote, urlsplit
    s = urlsplit((url or "").strip())
    host = s.netloc.lower().removeprefix("www.")
    path = unquote(s.path).lower().rstrip("/")
    return f"{host}{path}"


def link_law(economy: str, label_law: str, catalogue: list[dict],
             min_score: float = 0.62, label_urls: list[str] | None = None) -> Link:
    """Best catalogue entry for one cited law name (and, for regulator instruments, its URL)."""
    # 1. exact act number (MY: "(Act 709)" / "Act A1727")
    m = _ACTNO_RE.search(label_law or "")
    if m:
        want = m.group(1).upper()
        for row in catalogue:
            if (row.get("law_number") or "").upper() == want:
                return Link(label_law, economy, row["law_id"], row["title"], 1.0, "act_number")
    # 2. URL identity — but ONLY for a URL that demonstrably names THIS instrument.
    #    A Database row lists several laws and several references with no correspondence
    #    between them, so taking the row's URLs as keys for each of its names links whatever
    #    happens to be first: it matched "Privacy Act 1988" to the Security of Critical
    #    Infrastructure Act, and the PDPC children's guidelines to the PDPA. So a URL is only
    #    usable as a key when its own path spells out the instrument's distinctive words —
    #    which is exactly the case that matters, because a regulator instrument's catalogue
    #    title is often a filename blob ("A9") while its URL is descriptive.
    want_tokens = _tokens(label_law)
    for u in (label_urls or []):
        want = _url_key(u)
        if not want or "/" not in want:
            continue
        url_words = set(re.findall(r"[a-z]{3,}", want))
        # At least TWO distinctive tokens must appear. With one, the test is trivially
        # satisfiable and wrong: "Privacy Act 1988" normalises to the single token "privacy"
        # (the type word and the year are stripped), so every OAIC URL containing "privacy"
        # qualified — and the Act was linked to a data-breach blog page instead of the
        # 389-provision statute, turning three correct results into phantom failures.
        if len(want_tokens) < 2:
            continue
        if len(want_tokens & url_words) / len(want_tokens) < 0.5:
            continue                      # this URL does not identify this instrument
        if len(want_tokens & url_words) < 2:
            continue
        for row in catalogue:
            for cand in (row.get("source_url"), row.get("body_url")):
                got = _url_key(cand or "")
                if not got:
                    continue
                if got == want or (len(want) > 30 and (want in got or got in want)):
                    return Link(label_law, economy, row["law_id"], row["title"], 1.0, "url")
    # 2. name overlap — BOTH directions must be covered, so a short generic title can no
    #    longer swallow a long specific one ("…Act 2010" vs "Code of Practice for Licensees
    #    under the Communications and Multimedia Act"), and the instrument type must agree.
    # Score every candidate, then collapse by normalised title before judging ambiguity. The
    # catalogue legitimately holds the SAME instrument under several URLs (a regulator lists a
    # guideline as both a landing page and a PDF), and counting those as rival candidates made
    # the ambiguity guard reject correct, unambiguous matches — "Telecommunications Act 1999"
    # scored 1.00 and was still discarded. Statute-portal rows win ties over regulator rows, so
    # a bare Act name links to the Act rather than to a regulator page discussing it.
    _PORTAL_FIRST = {"act": 0, "amendment": 1, "subsidiary": 2}
    scored: dict[str, tuple[float, dict]] = {}
    for row in catalogue:
        title = row.get("title") or ""
        if not _type_compatible(label_law, title):
            continue
        cov_label, cov_title = _overlap(want_tokens, _tokens(title))
        s = min(cov_label, cov_title)          # symmetric: the weaker side decides
        if s <= 0:
            continue
        # Group by TOKEN SET, not by the normalised string: the same regulator PDF is listed
        # twice with titles differing only by a trailing "1", which as distinct strings tied at
        # 0.67 and tripped the ambiguity guard against the correct document.
        key = frozenset(_tokens(title))
        rank = _PORTAL_FIRST.get(row.get("collection") or "", 9)
        prev = scored.get(key)
        if prev is None or s > prev[0] or (
                s == prev[0] and rank < _PORTAL_FIRST.get(prev[1].get("collection") or "", 9)):
            scored[key] = (s, row)
    ranked = sorted(scored.values(), key=lambda t: -t[0])
    best_score, best = ranked[0] if ranked else (0.0, None)
    runner = ranked[1][0] if len(ranked) > 1 else 0.0
    if best and best_score >= min_score and best_score - runner >= 0.02:
        return Link(label_law, economy, best["law_id"], best["title"], round(best_score, 3), "name")
    return Link(label_law, economy, None, best["title"] if best else None,
                round(best_score, 3), "none")


@lru_cache(maxsize=8)
def link_all(min_score: float = 0.62) -> dict[str, list[Link]]:
    """Link every law named anywhere in the label set. Returns {economy: [Link, …]}.

    Cached: this is a pure function of two files that do not change inside a process, and it
    costs ~38s (every cited name scored against a 29k-row catalogue). Every sweep re-derives
    targets per configuration, so an uncached call multiplied that cost by the ladder length —
    ten minutes of a budget measurement was this function alone.
    """
    from .ground_truth import load_labels
    labels = load_labels()
    out: dict[str, list[Link]] = {}
    # Economies come from the LABELS, not a hardcoded triple: the Round-2 database labels
    # seven more. An economy whose corpus has not been built yet has an empty catalogue and
    # is skipped — reporting "0 laws linked" for it would read as a linkage failure when the
    # real state is "no corpus to link against yet".
    for econ in sorted({r.economy for r in labels}):
        catalogue = store.list_laws(econ)
        if not catalogue:
            continue
        urls_by_name: dict[str, list[str]] = {}
        for r in labels:
            if r.economy != econ:
                continue
            for law in r.laws:
                urls_by_name.setdefault(law, []).extend(r.portal_urls + r.other_urls)
        names = {law for r in labels if r.economy == econ for law in r.laws}
        out[econ] = [link_law(econ, n, catalogue, min_score, urls_by_name.get(n))
                     for n in sorted(names)]
    return out


def target_law_ids() -> dict[str, set[str]]:
    """{economy: {law_id, …}} for every law the judges cited and we can locate."""
    return {e: {lk.law_id for lk in links if lk.law_id}
            for e, links in link_all().items()}


if __name__ == "__main__":
    total = matched = 0
    for econ, links in link_all().items():
        ok = [lk for lk in links if lk.law_id]
        total += len(links)
        matched += len(ok)
        print(f"\n=== {econ}: {len(ok)}/{len(links)} cited laws found in the catalogue")
        for lk in links:
            flag = "OK " if lk.law_id else "MISS"
            print(f"  {flag} [{lk.how:10} {lk.score:.2f}] {lk.label_law[:58]}"
                  f"{'  ->  ' + (lk.matched_title or '')[:52] if lk.law_id else ''}")
    print(f"\nTOTAL {matched}/{total}")
