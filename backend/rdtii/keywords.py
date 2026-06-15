"""Portal-search keyword packs (Zone 1 discovery).

Each indicator's terms are split into TWO sub-types, because the two discovery engines match
very differently:

  • "name"  — NAME FRAGMENTS: short subject tokens that appear as a CONTIGUOUS substring of a
              law's TITLE. These are what work on a name-only portal API — notably AU's OData
              `contains(name,'<q>')`, which matches the query against the Act title and NOTHING
              else (its `$search` full-text endpoint is broken — it ignores the term). They are
              TYPE patterns, not economy-specific: "criminal code act", "surveillance devices act",
              "interception and access", "security intelligence" name the same instrument family
              across common-law jurisdictions. KEEP THEM SHORT: AU titles insert parentheses and
              extra words ("Telecommunications (Interception and Access) Act", "...Security
              Intelligence Organisation Act"), so a long guessed title misses — a 1–2 word
              distinctive token (verified live against the AU OData API) is what hits.

  • "desc"  — DESCRIPTIVE phrases describing the REGULATORY OBLIGATION. These only work on
              FULL-TEXT web search (SG via Serper/DDG `site:sso.agc.gov.sg`, MY likewise), where
              the engine indexes the law's body, not just its title. They are inert on a name-only
              API, so they are NOT fired at one (see NAME_ONLY_PORTALS) — firing them there just
              spends the query budget on calls that can never return a hit.

  FINE  — indicators.query_terms — within-document discriminative phrases; too specific for
          portal search; used only by the retrieval layer.

All terms are COUNTRY-AGNOSTIC: name fragments are shared naming conventions, descriptive terms
are obligations any satisfying law imposes. No specific law title is hardcoded as "the answer".
"""
from __future__ import annotations

# Portals whose search matches the query ONLY against the law TITLE (no working full-text search).
# For these we fire NAME FRAGMENTS ONLY — descriptive phrases can never match a title there.
NAME_ONLY_PORTALS = {"AU"}   # legislation.gov.au OData: contains(name,'<q>'); $search is broken

# ── BROAD: pillar-level, high recall (full-text engines only — concept phrases) ──────────────
PILLAR_SEARCH_TERMS: dict[int, list[str]] = {
    6: [
        "personal data protection",
        "cross-border transfer of personal data",
        "data localisation",
        "transfer personal data overseas",
        "data transfer restriction",
        "data localisation requirement",
    ],
    7: [
        "personal data protection",
        "cybersecurity act",
        "critical information infrastructure",
        "data retention period",
        "data protection officer",
        "government access personal data",
        "law enforcement access data",
    ],
}

# ── MID: per-indicator, country-agnostic, split into name fragments + descriptive obligations ──
INDICATOR_SEARCH_TERMS: dict[str, dict[str, list[str]]] = {

    # ── P6-I1 — OUTRIGHT BAN on cross-border transfer OR local-processing requirement ──
    "P6-I1": {
        "name": [
            "health records act",      # health-sector localisation bans (AU My Health Records s77)
            "data protection act",
            "privacy act",
        ],
        "desc": [
            "medical data transfer prohibited",
            "personal data must not be transferred outside country",
            "prohibition on transfer of personal data overseas",
            "data must be processed locally",
            "records must not be held outside the country",
            "health data may not leave country",
            "ban cross-border transfer personal data",
        ],
    },

    # ── P6-I2 — LOCAL STORAGE: data / business records kept within national territory ──
    "P6-I2": {
        "name": [
            "companies act", "corporations act",     # corporate accounting records (SG §199 / AU)
            "income tax act", "revenue act",          # tax records kept domestically
            "employment act", "labour act",           # employment / wage records
            "health records act",                     # health-data storage mandates
        ],
        "desc": [
            "personal data stored within country",
            "data must be retained locally",
            "accounting records kept within territory",
            "tax records minimum storage requirement",
            "financial records kept in country",
            "business records must be maintained locally",
            "accounting records and systems of control",
            "keeping of accounting records",
            "records kept at registered office",
            "books of account",
        ],
    },

    # ── P6-I3 — INFRASTRUCTURE: mandatory local servers / data centres ──
    "P6-I3": {
        "name": [
            "electronic commerce act", "electronic transactions act",
        ],
        "desc": [
            "online platform server requirement",
            "local server requirement service provider",
            "data centre within country territory",
            "servers must be located domestically",
            "infrastructure requirement digital services",
            "maintain server within national territory",
        ],
    },

    # ── P6-I4 — CONDITIONAL FLOW: transfer allowed only on consent / adequacy / contract ──
    "P6-I4": {
        "name": [
            "personal data protection act",     # PDPA-type law (SG/MY/ASEAN)
            "privacy act",                      # AU/NZ naming
            "data protection act",
        ],
        "desc": [
            "banking sector code of practice cross-border",
            "communications sector data code",
            "transfer personal data overseas with consent",
            "cross-border transfer adequate level of protection",
            "personal data transfer subject to conditions",
            "overseas recipient data protection standard",
            "binding corporate rules data transfer",
            "standard contractual clauses data transfer",
            "data export requires prior approval",
        ],
    },

    # ── P7-I1 — COMPREHENSIVE DATA-PROTECTION FRAMEWORK ──
    "P7-I1": {
        "name": [
            "personal data protection act", "privacy act",
            "personal information protection act", "data protection act",
            "health records act",               # health-sector frameworks also qualify
            "data availability",                 # public-sector data frameworks (AU Data Availability)
            "data sharing act",                  # data-sharing frameworks (other economies)
        ],
        "desc": [
            "data protection framework obligations",
            "consent personal data collection",
            "data subject rights protection",
            "personal information privacy law",
            "privacy legislation framework",
            "public sector data sharing scheme",
            "authorised data sharing accredited user",
        ],
    },

    # ── P7-I2 — DEDICATED CYBERSECURITY FRAMEWORK ──
    "P7-I2": {
        "name": [
            "cyber security act",                   # AU spells it two words (Cyber Security Act 2024)
            "cybersecurity act",                    # SG/MY spelling
            "security of critical infrastructure",  # AU SOCI Act
            "critical infrastructure act",
            "computer misuse act",                  # cybercrime / misuse laws (SG/MY)
            "criminal code act",                    # criminal codes with cyber offences
            "network security act",
        ],
        "desc": [
            "critical information infrastructure protection",
            "cyber incident reporting obligation",
            "network security encryption requirement",
            "cybersecurity authority obligations",
            "computer security law obligations",
        ],
    },

    # ── P7-I3 — MINIMUM RETENTION DURATION ──
    "P7-I3": {
        "name": [
            "companies act", "corporations act",     # accounting-record minimum period
            "income tax act", "revenue act",         # tax-record minimum
            "employment act", "labour act",          # employee-record minimum
            "telecommunications act",                # call/billing record retention
            "interception and access",               # telecom data-retention regime (AU 1979 Act)
            "data retention",                        # dedicated data-retention amendments
            "electronic communications act",
            "banking act", "financial services act", # financial-institution records
        ],
        "desc": [
            "records must be kept not less than years",
            "accounting records retained minimum period",
            "tax records kept minimum years",
            "employment records retention period",
            "telecommunications records minimum retention",
            "mandatory data retention period communications",
            "service provider retain telecommunications data",
            "financial records preservation minimum period",
            "business records kept minimum years",
            "retain the records for a period of not less than",
            "preservation of records",
        ],
    },

    # ── P7-I4 — DPO / DPIA ──
    "P7-I4": {
        "name": [
            "personal data protection act", "privacy act", "data protection act",
        ],
        "desc": [
            "data protection officer appointment requirement",
            "data protection impact assessment obligation",
            "privacy impact assessment requirement",
            "appoint data protection officer organisation",
            "significant data fiduciary obligations",
        ],
    },

    # ── P7-I5 — GOVERNMENT ACCESS TO PERSONAL DATA ──
    # Police / authority powers to access, intercept, compel disclosure. These live in criminal,
    # interception, surveillance, intelligence, data-sharing and telecom instruments. Name fragments
    # are SHORT distinctive tokens verified to hit the AU OData API (e.g. "security intelligence" →
    # ASIO Act 1979; "interception and access" → Telecommunications (Interception and Access) Act).
    "P7-I5": {
        "name": [
            "criminal procedure code", "criminal procedure act",  # common-law: SG/MY/IN/PK
            "criminal code act", "crimes act",                    # criminal/crimes acts (search/seizure)
            "interception and access",                            # lawful interception + stored access
            "surveillance devices act", "surveillance legislation",  # surveillance-warrant regimes
            "intelligence services act", "security intelligence",    # intelligence-agency enabling acts
            "data availability", "data sharing act",              # public-sector data sharing → access
            "computer misuse act", "cyber security act", "cybersecurity act",
            "telecommunications act", "data retention",           # compelled telecom data
            "police act", "national security act", "security offences act",
        ],
        "desc": [
            "police access computer data investigation",
            "law enforcement access personal data",
            "criminal investigation electronic records",
            "lawful interception of communications",
            "stored communications access warrant",
            "surveillance device warrant access data",
            "intelligence agency access to personal data",
            "technical assistance notice decryption",
            "international production order cross-border data",
            "compelled disclosure of telecommunications data",
            "government authority inspect computer",
            "national security data access powers",
            "production order disclosure personal data",
            "search and seizure electronic data",
            "authorized person access computer records",
        ],
    },
}


def portal_search_queries(economy: str, pillar: int | None = None) -> list[str]:
    """De-duplicated, order-preserving search queries for (economy, pillar).

    Order:
      1. Broad pillar terms (full-text engines only — they are concept phrases that can't match a
         title, so they are SKIPPED for name-only portals).
      2. Indicator terms, ROUND-ROBIN across indicators — each indicator's Nth term before any
         indicator's (N+1)th, so no indicator is starved when the list is truncated. Within an
         indicator, name fragments come first; descriptive phrases follow ONLY for full-text
         portals.

    For a NAME_ONLY portal (AU OData) we fire NAME FRAGMENTS ONLY: descriptive phrases there are
    dead-weight — `contains(name,…)` can't match them and `$search` is broken — so dropping them
    keeps the whole query budget on queries that can actually return a law (the fix for AU P7
    missing telecom/criminal-code/surveillance/intelligence/data-availability instruments).
    """
    from .indicators import get_indicators
    pillars = [6, 7] if pillar is None else [pillar]
    name_only = (economy or "").upper() in NAME_ONLY_PORTALS

    out: list[str] = []

    # 1. Broad pillar terms — full-text engines only (concept phrases never match a title).
    if not name_only:
        for p in pillars:
            out.extend(PILLAR_SEARCH_TERMS.get(p, []))

    # 2. Per-indicator terms, interleaved round-robin. Name fragments always; descriptive phrases
    #    only where a full-text engine can index them.
    ind_lists: list[list[str]] = []
    for p in pillars:
        for ind in get_indicators(p):
            terms = INDICATOR_SEARCH_TERMS.get(ind.indicator_id, {})
            frags = list(terms.get("name", []))
            if not name_only:
                frags += list(terms.get("desc", []))
            if frags:
                ind_lists.append(frags)
    depth = max((len(l) for l in ind_lists), default=0)
    for rank in range(depth):
        for l in ind_lists:
            if rank < len(l):
                out.append(l[rank])

    # Deduplicate while preserving order (first occurrence wins)
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq
