"""Portal-search keyword packs (Zone 1 discovery).

TWO vocabularies, deliberately separated:

  • COARSE search terms (here) — high-recall queries fired at a national portal's
    SEARCH box to surface the right *Acts* (e.g. "personal data protection").
  • FINE phrases (indicators.query_terms) — discriminative within-document phrases
    used by retrieval to surface the right *provisions* (e.g. "shall not transfer").

Using the fine phrases as portal queries returns nothing on most search engines;
using the coarse terms for within-doc retrieval is too blunt. Keep them apart.

These are domain priors (what vocabulary a privacy/transfer law uses), NOT an answer
key — the app still has to search, fetch, extract and rank to find the provision.
"""
from __future__ import annotations

# Coarse, high-recall search phrases per pillar. Ordered most→least productive so an
# adapter can stop early once it has enough candidates.
PILLAR_SEARCH_TERMS: dict[int, list[str]] = {
    6: [  # Cross-border Data Policies (localisation: ban / storage / infrastructure / conditional flow)
        "personal data protection",
        "cross-border transfer of personal data",
        "data localisation",
        "local storage of personal data",
        "transfer personal data overseas conditions",
    ],
    7: [  # Domestic Data Protection & Privacy (framework / cybersecurity / retention / DPIA-DPO / gov access)
        "personal data protection",
        "cybersecurity law",
        "data retention period",
        "data protection officer impact assessment",
        "government access to personal data",
    ],
}

# A couple of flagship-law anchors per economy — the instruments every run should try
# to surface first. Plain titles, fired as exact-ish queries. NOT URLs (no answer key).
ECONOMY_ANCHORS: dict[str, list[str]] = {
    "SG": ["Personal Data Protection Act", "Cybersecurity Act"],
    "AU": ["Privacy Act", "Telecommunications Act"],
    "MY": ["Personal Data Protection Act", "Communications and Multimedia Act"],
}


def portal_search_queries(economy: str, pillar: int | None = None) -> list[str]:
    """De-duplicated, order-preserving list of search queries for (economy, pillar)."""
    pillars = [6, 7] if pillar is None else [pillar]
    out: list[str] = []
    for p in pillars:
        out.extend(PILLAR_SEARCH_TERMS.get(p, []))
    out.extend(ECONOMY_ANCHORS.get(economy.upper(), []))
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq
