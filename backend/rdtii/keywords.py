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
#   AU — legislation.gov.au OData: contains(name,'<q>'); its $search full-text is broken.
#   MY — we filter the portal's own principal-acts JSON catalogue by name (Google barely indexes
#        lom.agc.gov.my), so matching is title-only just like AU.
NAME_ONLY_PORTALS = {"AU", "MY"}

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
    # The other ten pillars. These are broad CONCEPT phrases for a full-text lane, matching what
    # 6 and 7 do above; the discriminating work is done by each indicator's own `query_terms` in
    # `indicators_wide.py`. Unmeasured, like the definitions they serve.
    1: ["anti-dumping duty", "countervailing duty", "safeguard measure",
        "trade remedies investigation"],
    2: ["government procurement", "public procurement of goods and services",
        "tender eligibility", "source code disclosure requirement"],
    3: ["foreign investment law", "foreign equity limit", "investment screening",
        "joint venture requirement", "negative list for foreign investment"],
    4: ["copyright act", "patents act", "trade secrets protection",
        "intellectual property enforcement", "notice and takedown"],
    5: ["telecommunications act", "telecom licensing", "infrastructure sharing",
        "independent regulatory authority", "significant market power"],
    8: ["intermediary liability", "safe harbour for service providers",
        "user identity verification", "obligation to monitor content"],
    9: ["blocking of websites", "online content regulation", "internet content provider licence",
        "online advertising restriction"],
    10: ["import prohibition", "import licensing", "local content requirement",
         "export control", "restricted goods list"],
    11: ["technical standards", "conformity assessment", "type approval",
         "commercial cryptography", "product certification"],
    12: ["electronic commerce law", "electronic transactions act", "payment services act",
         "consumer protection online", "de minimis threshold", "domain name registration"],
}

#: Law-NAME fragments for pillars 1-5 and 8-12, used only on a NAME_ONLY portal (AU's OData
#: `contains(name,…)`, MY's title catalogue). Those lanes match a statute TITLE, so an
#: obligation phrase there returns nothing — the failure is silent, which is precisely why the
#: fallback is explicit rather than left to the generic terms above.
PILLAR_NAME_FRAGMENTS: dict[int, list[str]] = {
    1: ["customs tariff", "customs act", "anti-dumping", "trade remedies"],
    2: ["government procurement", "public contracts", "financial management"],
    3: ["foreign investment", "investment act", "companies act", "competition act"],
    4: ["copyright act", "patents act", "trade marks act", "designs act", "circuit layouts"],
    5: ["telecommunications act", "radiocommunications act", "broadcasting services"],
    8: ["online safety", "criminal code", "copyright act", "broadcasting services"],
    9: ["online safety", "classification", "broadcasting services", "interactive gambling"],
    10: ["customs act", "customs prohibited imports", "export control", "defence trade controls"],
    11: ["standards", "measurement", "electrical safety", "radiocommunications"],
    12: ["electronic transactions", "consumer protection", "payment systems",
         "competition and consumer", "spam act"],
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
        # NB: no "revenue act" / "goods and services tax" — on AU's name-only API those match
        # whole families of irrelevant rate/appropriation acts (GST Imposition, Surplus Revenue…)
        "name": [
            "companies act", "corporations act",     # corporate accounting records (SG §199 / AU)
            "income tax act",                         # tax records kept domestically (MY Act 53)
            "sales tax act", "service tax act", "services tax act",  # MY Act 806/807 record-keeping
            "employment act", "labour act",           # employment / wage records
            "health records act",                     # health-data storage mandates (AU 6.2)
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
            "cyber security act",                   # AU/MY: Cyber Security Act (two words)
            "cybersecurity act",                    # SG spelling
            "security of critical infrastructure",  # AU SOCI Act
            "critical infrastructure act",
            "computer misuse act",                  # SG cybercrime law
            "computer crimes act",                  # MY/other variant of the cybercrime law
            "communications and multimedia",        # MY CMA-type comms/network framework
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
            "income tax act",                        # tax-record minimum (MY Act 53)
            "sales tax act", "service tax act", "services tax act",  # MY Act 806/807
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
            "criminal code act", "crimes act", "penal code",      # criminal/crimes/penal instruments
            "interception and access",                            # lawful interception + stored access
            "surveillance devices act", "surveillance legislation",  # surveillance-warrant regimes
            "intelligence services act", "security intelligence",    # intelligence-agency enabling acts
            "data availability", "data sharing act",              # public-sector data sharing → access
            "computer misuse act", "computer crimes act",         # cybercrime investigation powers
            "cyber security act", "cybersecurity act",
            "official secrets act",                               # state-secrecy / protected-info access
            "communications and multimedia",                     # comms interception/access (MY CMA etc.)
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


def portal_search_queries(economy: str, pillar: int | None = None,
                          name_only: bool | None = None) -> list[str]:
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
    if name_only is None:   # infer from the portal type; a full-text lane passes False explicitly
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
            terms = INDICATOR_SEARCH_TERMS.get(ind.indicator_id)
            if terms is None:
                # Pillars outside 6 and 7 have no hand-tuned name/desc split. Their own
                # `query_terms` are obligation phrases, so they go in the full-text lane; a
                # NAME_ONLY portal (AU OData, MY catalogue) matches titles, and firing an
                # obligation phrase at it returns nothing at all — so those lanes fall back to
                # the pillar's law-name fragments instead of quietly searching for nothing.
                frags = ([] if name_only else list(ind.query_terms))
            else:
                frags = list(terms.get("name", []))
                if not name_only:
                    frags += list(terms.get("desc", []))
            if frags:
                ind_lists.append(frags)
    if name_only:
        for p in pillars:
            if not any(INDICATOR_SEARCH_TERMS.get(i.indicator_id) for i in get_indicators(p)):
                ind_lists.append(list(PILLAR_NAME_FRAGMENTS.get(p, [])))
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
