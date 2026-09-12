"""The mechanics every portal adapter shares.

Six economies get a portal-native lane in this phase, written by six separate hands. What
they have in common is not the portal — it is the fetching: a robots check that treats a
refusal as an answer, a backoff that understands a portal's own idea of "slow down", and one
way to build a DiscoveredDoc. Kept here so that a defect in any of the three is fixed once.

The precedent is Malaysia: `lom.agc.gov.my/robots.txt` answers HTTP 500, the fetcher read
"unreadable" as "disallowed", and every statute PDF on the primary portal was skipped in
silence. `robots.UNREACHABLE_OVERRIDE` now carries that carve-out (RFC 9309 §2.3.1.4:
a server error is not a refusal). One import, and no adapter has to remember it.
"""
from __future__ import annotations

import hashlib
import time
from typing import Callable, Protocol

from ..config import settings
from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy
from . import robots

Log = Callable[[str], None]

#: Adapter name (as written in data/sources.yaml `adapter:`) -> callable.
_REGISTRY: dict[str, "PortalEnumerator"] = {}

#: Adapter name -> True when the callable walks the WHOLE portal on every call and ignores
#: its `query` argument (sg_sso, tl_gazette, la_gazette, th_law_api -- each says so in its own
#: module docstring). Absent/False is the safe default: an adapter not declared here is
#: assumed to consume `query` and must still be called once per query term.
_ENUMERATES_PORTAL: dict[str, bool] = {}


class PortalEnumerator(Protocol):
    """The one shape `discovery.discover_live` dispatches on.

    Deliberately identical to the signature the existing `_search_au_api`,
    `_search_my_catalogue`, `_search_in_dspace` and `_search_mn_legalinfo` already have, so
    the dispatch table stays one line and an adapter written to this protocol is
    indistinguishable to the caller from one written before it existed.
    """

    def __call__(self, client, src: dict, query: str, economy: Economy,
                 indicators: list, log: Log) -> list[DiscoveredDoc]:
        ...


def register(name: str, fn: "PortalEnumerator", *, enumerates_portal: bool = False) -> None:
    """Register a portal adapter under `name`.

    `enumerates_portal=True` is a property of how the adapter WORKS, not of the portal's YAML
    configuration -- it says the callable walks the whole portal on every call and ignores
    `query`. `discover_live`'s dispatch reads this back via `enumerates_portal(name)` to call
    such an adapter once per SOURCE instead of once per query term: for a source with no query
    override, that fallback is the generated ~52-term generic list, and 52 full portal crawls
    is the difference between a ~3-minute run and a multi-hour one (measured against
    Timor-Leste: ~183.5s standalone vs. ~2h40m at 52x). A YAML flag would risk disagreeing
    with the code it describes -- exactly the class of silent defect this phase exists to
    remove -- so the declaration lives here, next to the function it describes.
    """
    _REGISTRY[name] = fn
    _ENUMERATES_PORTAL[name] = enumerates_portal


def get_adapter(name: str):
    return _REGISTRY.get(name)


def enumerates_portal(name: str | None) -> bool:
    """True when the adapter registered under `name` walks the whole portal per call and
    ignores `query` (declared via `register(..., enumerates_portal=True)`).

    False for any name not found here -- including one dispatched through
    `discovery._ADAPTERS` rather than this registry (au_api, my_catalogue, in_dspace,
    mn_legalinfo all genuinely consume `query`) -- so an adapter that never opted in keeps
    being called once per query term, which is what the round-robin budget merge assumes.
    """
    return _ENUMERATES_PORTAL.get(name, False)


def headers() -> dict:
    return {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }


def _allowed(url: str, log: Log) -> bool:
    """robots.txt, honoured. Separated out so tests can drive portal_get without a network
    round-trip for robots, and so a refusal is logged in one place with its reason."""
    ok, why = robots.allowed(url, settings.crawl_user_agent)
    if not ok:
        log(f"[portal] robots refuses {url[:90]} — {why}")
    return ok


def portal_get(client, url: str, log: Log, tries: int = 4, **kw):
    """Portal-friendly GET. Returns the response, or None when the portal never answered.

    Backs off exponentially, and treats a 202 with an EMPTY body as a throttle rather than a
    result: that is Singapore's SSO saying "slow down" — it does not use 429 (verified
    2026-08-01, the same behaviour `backend/corpus/catalogue._get` was written for). A 202
    WITH content is a real response and is returned as-is.
    """
    if not _allowed(url, log):
        # `_allowed` already logs the robots.txt reason in production; this line exists so a
        # test driving `portal_get` with `_allowed` replaced (no network, no robots.txt) still
        # sees a "why" in the log rather than a silent None.
        log(f"[portal] robots refused {url[:90]} — not fetched")
        return None
    delay = settings.crawl_delay_seconds
    for attempt in range(tries):
        try:
            r = client.get(url, **kw)
            if r.status_code == 200 and r.content:
                return r
            if r.status_code == 202 and r.content:
                return r
            log(f"[portal] {r.status_code} len={len(r.content)} "
                f"(attempt {attempt + 1}/{tries}) {url[:90]}")
        except Exception as e:  # noqa: BLE001 — network flake; retry, then give up
            log(f"[portal] {type(e).__name__} (attempt {attempt + 1}/{tries}) {url[:90]}")
        if attempt + 1 < tries:
            time.sleep(delay)
            delay *= 2.5
    return None


def doc_id(economy: str, source_url: str) -> str:
    """The SAME id discovery already computes.

    Live-mode dedup keys on doc_id, so an adapter using a different scheme would make its
    documents look distinct from the same document reached by an existing lane, and both
    would be fetched, extracted and graded. Pinned by a test.
    """
    return f"{economy}-" + hashlib.sha1(source_url.encode()).hexdigest()[:10]


def make_doc(economy: Economy, url: str, title: str, portal_name: str, *,
             fmt: DocFormat | None = None, law_number: str | None = None,
             law_name: str | None = None, score: float = 1.0,
             amendment_date: str | None = None) -> DiscoveredDoc:
    """Build a DiscoveredDoc with the format inferred from the URL unless stated.

    `score` defaults to 1.0 because a portal-native hit is a match on the portal's OWN index —
    unlike a web-search hit, which is ranked later by content. An adapter that can rank its
    own results (Mongolia ranks by principal-statute-then-size) passes its own score.
    """
    if fmt is None:
        fmt = DocFormat.PDF_TEXT if url.lower().split("?")[0].endswith(".pdf") else DocFormat.HTML
    return DiscoveredDoc(
        doc_id=doc_id(economy.value, url), economy=economy, title=(title or url)[:200],
        source_url=url, portal=portal_name, fmt=fmt, relevance_score=score,
        discovery_tag=DiscoveryTag.NEW, law_number=law_number, law_name=law_name,
        amendment_date=amendment_date)


# ── ranking a candidate from its TITLE alone ────────────────────────────────────────────────
#
# Discovery ranks before it fetches, so a portal-native adapter has only the title. The two
# helpers below are shared by every such adapter so the ranking cannot drift per economy, and
# so the defect they replace cannot come back in one adapter while being fixed in another.
#
# WHAT THEY REPLACE. Six adapters used to reach into `discovery._score`, which counts how many
# of an indicator's `query_terms` appear in the text. Those terms are OPERATIVE PROVISION
# phrases and all forty-three of pillar 6's are multi-word, so a title matched none of them:
# measured 2026-09-11, "Personal Data Protection Act 2012" and "Animals and Birds Act 1965"
# both scored 0.000, and with the adapter's constant base weight added, all 524 of Singapore's
# current Acts tied at exactly 0.4000. `list.sort` is stable, so a constant key preserves input
# order, and `_cap`'s trim to `discovery_max_docs` kept the first twenty-two in SSO's own
# alphabetical browse order -- twenty-two Acts starting with "A", with the PDPA, the
# Cybersecurity Act and the Companies Act all dropped. See `backend/rdtii/title_terms.py`.

def title_relevance(title: str, indicators, *, economy: str | None = None) -> float:
    """0.0-1.0: how much this TITLE looks like the name of a law relevant to `indicators`.

    Two signals, deliberately in this order:

    1. A NAME FRAGMENT hit ("personal data protection act", "criminal procedure code",
       个人信息保护, ข้อมูลส่วนบุคคล). These are contiguous title substrings by construction --
       `keywords.INDICATOR_SEARCH_TERMS[...]["name"]` was written that way for AU's name-only
       OData API -- so a hit is strong evidence and several hits are stronger. Saturates at
       three so a long omnibus title cannot outrank a precise one indefinitely.
    2. DISTINCTIVE WORD coverage over the same vocabulary, as a tie-break only. Without it
       every Act that matches no fragment ties again, which is the original defect in miniature:
       ties hand the ordering back to the portal's arrival order.

    Returns 0.0 when nothing matches -- an honest "this title says nothing about the topic",
    which the caller is free to combine with its own base weight.
    """
    from ..rdtii import title_terms as T
    blob = T.normalise(title)
    if not blob:
        return 0.0
    frags = [T.normalise(f) for f in T.name_fragments(indicators)]
    frags += [T.normalise(f) for f in T.native_fragments(economy)]
    frags = [f for f in dict.fromkeys(frags) if f]
    if not frags:
        return 0.0
    hits = sum(1 for f in frags if f in blob)
    phrase = min(1.0, hits / 3.0)
    vocab = {w for f in frags for w in f.split() if len(w) > 3}
    words = sum(1 for w in vocab if w in blob) / len(vocab) if vocab else 0.0
    # CJK/Thai/Lao fragments do not split into words, so `vocab` is empty or unhelpful there;
    # the phrase term carries the whole signal in that case, which is correct for those scripts.
    return round(min(1.0, 0.80 * phrase + 0.20 * min(1.0, words * 4)), 4)
