"""The evaluation corpus, built from the panel's own reference data.

Two sources, both already in the repo and both checked in, so a run is offline and
byte-reproducible:

  data/ground_truth/rdtii_reference_p67.csv
      The RDTII 2.1 reference rows -- (economy, indicator, instrument) as the panel
      recorded them. 180 rows over six economies and nine indicators. This is the
      gold: an instrument named here IS the answer for that indicator.

  data/catalogues/MN_titles.json
      36,017 law titles harvested from legalinfo.mn. The file says what it is:
      "Titles only -- a table of contents. No provision text, no indicator, no
      mapping." That is exactly what a distractor pool should be. They are real
      legal titles in the real script, so a Mongolian query has to beat genuine
      Mongolian competition rather than a synthetic one.

**A document is the title as its own portal serves it.** The reference CSV writes
Chinese instruments bilingually -- "Cybersecurity Law of the People's Republic of
China《中华人民共和国网络安全法》" -- because the panel worked in English. A Chinese
portal serves only the second half. Indexing the English translation would measure
the panel's spreadsheet rather than the corpus a crawler actually meets, and it
would hide the failure this benchmark exists to expose, so `native_title()` keeps
the native form where the row carries one.

Mongolia needs one step more. The panel recorded its instruments under English
names only -- "Law on Personal Data Protection" -- while legalinfo.mn serves them
in Mongolian, and no string comparison bridges that. It is the same wall
`tools/score_round2.py` hit, where scoring Mongolia at 0 of 9 turned out to be a
measurement error rather than a result. The fix there is the fix here: match on
the portal id inside the URL, which is language-independent, and take the title
the catalogue gives. An unresolved row keeps its English name and is counted, so
the share of the Mongolian arm that is genuinely Cyrillic is a reported number
rather than an assumption.

Nothing here reads the network, an LLM, or a database.
"""
from __future__ import annotations

import csv
import json
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

# The repo root, three levels up from bench/corpus.py.
ROOT = Path(__file__).resolve().parent.parent

REFERENCE_CSV = ROOT / "data" / "ground_truth" / "rdtii_reference_p67.csv"
MN_CATALOGUE = ROOT / "data" / "catalogues" / "MN_titles.json"

# The panel writes economies by UN name; the pipeline keys everything by code.
ECONOMY_CODE = {
    "Singapore": "SG",
    "Australia": "AU",
    "Malaysia": "MY",
    "China": "CN",
    "India": "IN",
    "Mongolia": "MN",
}

# A CJK title in its own brackets: 《中华人民共和国网络安全法》
_NATIVE_BRACKET_RE = re.compile(r"《([^》]+)》")

# legalinfo.mn's own instrument id, from either URL form the panel recorded:
#   https://legalinfo.mn/mn/detail?lawId=16390288615991
#   https://legalinfo.mn/mn/detail/523
# Searched over the whole string rather than a parsed host, because several rows
# are wrapped in a web.archive.org snapshot URL that carries the real one inside.
# Deliberately narrower than `tools/score_round2.url_key`: that function answers
# "are these the same document across portals", this one answers "which catalogue
# row is this", and only the second can be looked up in MN_titles.json.
_MN_LAW_ID_RE = re.compile(r"lawid=(\d{2,})|legalinfo\.mn/[a-z]{2}/detail/(\d{2,})", re.I)


@dataclass(frozen=True)
class Document:
    """One indexable instrument: an id and the text a portal would serve for it."""

    doc_id: str
    economy: str
    text: str
    is_distractor: bool


@dataclass(frozen=True)
class GoldPair:
    """The panel's answer: this instrument satisfies this indicator for this economy."""

    economy: str
    indicator_id: str
    doc_id: str


def native_title(law_name: str) -> str:
    """The instrument's title in the language its own portal publishes it in.

    Where the reference row carries a bracketed native title, that IS the document
    and the English gloss is dropped -- a crawler on cac.gov.cn never sees the
    gloss. Where it does not, the name is returned unchanged with any stray
    brackets stripped.
    """
    found = _NATIVE_BRACKET_RE.search(law_name)
    if found:
        return found.group(1).strip()
    return _NATIVE_BRACKET_RE.sub("", law_name).strip()


def _doc_id(economy: str, title: str) -> str:
    """Stable id for an instrument. Title-derived, so the same law lands once."""
    key = re.sub(r"\s+", " ", title.strip().lower())
    return "%s::%s" % (economy, key)


def mn_law_id(source_url: str) -> "str | None":
    """The legalinfo.mn catalogue id inside a URL, or None."""
    found = _MN_LAW_ID_RE.search(source_url or "")
    if not found:
        return None
    return found.group(1) or found.group(2)


@lru_cache(maxsize=1)
def load_reference() -> "tuple[tuple[Document, ...], tuple[GoldPair, ...]]":
    """(instruments, gold pairs) from the panel's reference CSV.

    Cached because every cell of the matrix reads the same file and the file does
    not change within a run; the hash that identifies a record already covers it.
    """
    if not REFERENCE_CSV.is_file():
        raise FileNotFoundError(
            "the RDTII reference set is missing at %s -- it is checked in, so a "
            "missing file means a partial clone, not a step you skipped" % REFERENCE_CSV
        )
    docs: dict[str, Document] = {}
    pairs: set[GoldPair] = set()
    catalogue = _mn_catalogue()
    with REFERENCE_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            economy = ECONOMY_CODE.get((row.get("Economy") or "").strip())
            indicator = (row.get("Indicator ID") or "").strip()
            law_name = (row.get("Law Name") or "").strip()
            if not economy or not indicator or not law_name:
                continue
            title = native_title(law_name)
            if economy == "MN":
                # Resolve the English name the panel wrote back to the Mongolian
                # title its own portal serves. Unresolved rows keep the English
                # name; `native_share()` reports how many that is.
                law_id = mn_law_id(row.get("Source URL") or "")
                title = catalogue.get(law_id or "", title)
            if not title:
                continue
            did = _doc_id(economy, title)
            docs.setdefault(did, Document(did, economy, title, is_distractor=False))
            pairs.add(GoldPair(economy, indicator, did))
    return tuple(sorted(docs.values(), key=lambda d: d.doc_id)), tuple(
        sorted(pairs, key=lambda p: (p.economy, p.indicator_id, p.doc_id))
    )


@lru_cache(maxsize=1)
def _mn_catalogue() -> "dict[str, str]":
    """legalinfo.mn catalogue id -> title, as harvested. Titles are Mongolian."""
    if not MN_CATALOGUE.is_file():
        raise FileNotFoundError("the MN catalogue is missing at %s" % MN_CATALOGUE)
    payload = json.loads(MN_CATALOGUE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for law in payload.get("laws") or []:
        title = (law.get("title") or "").strip()
        law_id = str(law.get("id") or "").strip()
        if title and law_id:
            out[law_id] = title
    return out


@lru_cache(maxsize=1)
def _mn_titles() -> "tuple[str, ...]":
    return tuple(sorted(set(_mn_catalogue().values())))


def script_of(text: str) -> str:
    """The dominant writing system of a title. Coarse on purpose -- three buckets
    is what the tokeniser actually branches on."""
    if any("一" <= c <= "鿿" for c in text):
        return "Han"
    if any("Ѐ" <= c <= "ԯ" for c in text):
        return "Cyrillic"
    return "Latin"


def native_share(economy: str) -> "tuple[int, int]":
    """(instruments not in Latin script, instruments) for one economy.

    Reported rather than assumed: the Mongolian arm is only a Cyrillic retrieval
    task to the extent that the id linkage above actually resolved.
    """
    instruments, _ = load_reference()
    mine = [d for d in instruments if d.economy == economy]
    return sum(1 for d in mine if script_of(d.text) != "Latin"), len(mine)


def distractors(n: int, seed: int, exclude: Iterable[str]) -> "list[Document]":
    """A seeded draw of `n` real Mongolian legal titles that are not gold.

    Seeded rather than fixed so the sample is an axis of the matrix: a result that
    only holds for one lucky draw of distractors is not a result, and Ledger
    reports the spread across draws rather than a single number.
    """
    taken = set(exclude)
    pool = [t for t in _mn_titles() if _doc_id("MN", t) not in taken]
    rng = random.Random(seed)
    drawn = pool if n >= len(pool) else rng.sample(pool, n)
    return [
        Document(_doc_id("DISTRACTOR", t), "MN", t, is_distractor=True)
        for t in sorted(drawn)
    ]


def build(n_distractors: int, seed: int) -> "tuple[list[Document], tuple[GoldPair, ...]]":
    """The index for one cell: every economy's instruments, plus seeded distractors.

    One pooled index rather than six, because that is the setting the claim is
    about. A harness that serves several regions holds them in one corpus, and the
    question is whether indexing Mongolia alongside Singapore degrades either.
    """
    instruments, pairs = load_reference()
    noise = distractors(n_distractors, seed, exclude={d.doc_id for d in instruments})
    return list(instruments) + noise, pairs
