"""Portal-search keyword packs (Zone 1 discovery).

THREE vocabularies at three levels of specificity:

  BROAD  — PILLAR_SEARCH_TERMS — one query per pillar topic; highest recall.
  MID    — INDICATOR_SEARCH_TERMS — per-indicator, country-agnostic; two sub-types:
             • NAME FRAGMENTS  — short terms that appear in law TITLES (e.g. "health
               records", "critical infrastructure").  Required for portal-internal
               name-based search (AU OData: contains(name,…)) and portal search boxes.
               These are TYPE patterns, not economy-specific: "criminal procedure" finds
               the Criminal Procedure Code in SG, MY, IN, PK, and most common-law
               economies because every such jurisdiction names this instrument the same way.
             • DESCRIPTIVE     — phrases describing the REGULATORY OBLIGATION the law
               imposes.  Work on full-text web search (DuckDuckGo / Serper with site:
               filter), where the crawler indexes the law's actual text, not just title.
               Less effective on name-only portal APIs — the name-fragment queries above
               are the supplement that covers those engines.
  FINE   — indicators.query_terms — within-document discriminative phrases;
            too specific for portal search boxes; used only by the retrieval layer.

All MID and BROAD terms are COUNTRY-AGNOSTIC by design — the same set is used for
SG/AU/MY and generalises to any Finals economy without modification.
"""
from __future__ import annotations

# ── BROAD: pillar-level, high recall ─────────────────────────────────────────
PILLAR_SEARCH_TERMS: dict[int, list[str]] = {
    6: [  # Cross-border Data Policies — ban / storage / infrastructure / conditional flow
        "personal data protection",
        "cross-border transfer of personal data",
        "data localisation",
        "transfer personal data overseas",
        "data transfer restriction",
        "data localisation requirement",
    ],
    7: [  # Domestic Data Protection — framework / cybersecurity / retention / DPO / gov access
        "personal data protection",
        "cybersecurity act",
        "critical information infrastructure",
        "data retention period",
        "data protection officer",
        "government access personal data",
        "law enforcement access data",
    ],
}

# ── MID: per-indicator, country-agnostic ─────────────────────────────────────
# Each indicator lists NAME FRAGMENTS first (work on name-only portals like AU OData)
# followed by DESCRIPTIVE terms (work on full-text web search via DDG / Serper).
# Both sub-types are country-agnostic: name fragments describe naming conventions shared
# across jurisdictions; descriptive terms describe regulatory obligations any country's
# law would impose when it satisfies the indicator.
INDICATOR_SEARCH_TERMS: dict[str, list[str]] = {

    # ── P6-I1 — OUTRIGHT BAN on cross-border transfer OR local-processing requirement ──
    # NAME FRAGMENTS: laws named after the regulated activity or commodity (health data, etc.)
    # DESCRIPTIVE: the prohibition/mandate language appearing in the law's text
    "P6-I1": [
        # name fragments
        "health records act",          # health-sector bans common (AU My Health Records Act)
        "medical data transfer",       # countries with dedicated health-data law
        "data transfer ban",           # laws with "ban" in title/headings
        # descriptive
        "personal data must not be transferred outside country",
        "prohibition on transfer of personal data overseas",
        "data must be processed locally",
        "health data may not leave country",
        "ban cross-border transfer personal data",
    ],

    # ── P6-I2 — LOCAL STORAGE: data / business records kept within national territory ──
    # Satisfied by data-protection acts AND by corporate, tax, telecom laws requiring local
    # record-keeping.  Cover all instrument types so the crawler surfaces each of them.
    "P6-I2": [
        # name fragments — types of law that impose storage obligations
        "companies act",               # corporate accounting records (SG §199, MY, HK, etc.)
        "corporations act",            # AU equivalent of Companies Act
        "income tax act",              # tax records kept domestically
        "revenue act",                 # variant naming for tax legislation
        "employment act",              # employment / wage records
        "labour act",                  # variant naming for employment legislation
        "health records act",          # health data storage mandates
        # descriptive
        "personal data stored within country",
        "data must be retained locally",
        "accounting records kept within territory",
        "tax records minimum storage requirement",
        "financial records kept in country",
        "business records must be maintained locally",
        # general record-keeping vocabulary (matches the actual text of corporate/tax acts,
        # e.g. SG Companies Act s199 "Accounting records and systems of control"), country-agnostic
        "accounting records and systems of control",
        "keeping of accounting records",
        "records kept at registered office",
        "books of account",
    ],

    # ── P6-I3 — INFRASTRUCTURE: mandatory local servers / data centres ──
    # Rare indicator; narrowly scoped terms avoid false-positive recall.
    "P6-I3": [
        # name fragments
        "online platform regulation",  # platform/service provider acts with server rules
        "electronic commerce act",     # e-commerce acts may include server requirements
        # descriptive
        "local server requirement service provider",
        "data centre within country territory",
        "servers must be located domestically",
        "infrastructure requirement digital services",
        "maintain server within national territory",
    ],

    # ── P6-I4 — CONDITIONAL FLOW: transfer allowed only on consent / adequacy / contract ──
    # Central PDPA-type acts + sectoral codes (banking, telecom) both satisfy this.
    "P6-I4": [
        # name fragments
        "personal data protection act",    # primary PDPA-type law in most ASEAN economies
        "privacy act",                     # AU/NZ naming for PDPA equivalent
        "banking sector code of practice", # banking sectoral data-transfer codes
        "communications sector code",      # telecom/comms sectoral codes
        # descriptive
        "transfer personal data overseas with consent",
        "cross-border transfer adequate level of protection",
        "personal data transfer subject to conditions",
        "overseas recipient data protection standard",
        "binding corporate rules data transfer",
        "standard contractual clauses data transfer",
        "data export requires prior approval",
    ],

    # ── P7-I1 — COMPREHENSIVE DATA-PROTECTION FRAMEWORK ──
    # Horizontal law or sectoral law establishing consent, obligations, and a regulator.
    "P7-I1": [
        # name fragments
        "personal data protection act",
        "privacy act",
        "personal information protection act",
        "data protection act",
        "electronic health records act",   # health-sector frameworks also qualify
        # descriptive
        "data protection framework obligations",
        "consent personal data collection",
        "data subject rights protection",
        "personal information privacy law",
        "privacy legislation framework",
    ],

    # ── P7-I2 — DEDICATED CYBERSECURITY FRAMEWORK ──
    # Separate from data-protection law; covers CII protection, encryption, incident
    # reporting.  Name fragments here are the clearest indicator of instrument type.
    "P7-I2": [
        # name fragments
        "cybersecurity act",                    # direct (SG, MY Act 854, etc.)
        "cyber security act",                   # variant spelling
        "critical infrastructure act",          # SOCI-type laws
        "security of critical infrastructure",  # AU naming pattern
        "computer misuse act",                  # cybercrime / misuse laws
        "criminal code act",                    # criminal codes with cyber offences
        "network security act",                 # dedicated network security laws
        # descriptive
        "critical information infrastructure protection",
        "cyber incident reporting obligation",
        "network security encryption requirement",
        "cybersecurity authority obligations",
        "computer security law obligations",
    ],

    # ── P7-I3 — MINIMUM RETENTION DURATION ──
    # "Must keep for AT LEAST N years."  Satisfied by many instrument types:
    # data-protection acts, corporate acts, tax acts, employment acts, telecom licences.
    # Include name fragments for ALL these types; the same pattern repeats across economies.
    "P7-I3": [
        # name fragments — instrument types that impose minimum retention
        "companies act",               # accounting records minimum period (SG §199, etc.)
        "corporations act",            # AU equivalent
        "income tax act",              # tax records minimum (SG §67, MY §82)
        "revenue act",                 # variant for tax legislation
        "employment act",              # employee records minimum (SG §95)
        "labour act",                  # variant for employment legislation
        "telecommunications act",      # call/billing records minimum period
        "electronic communications act",  # variant for telecom legislation
        "banking act",                 # bank record retention requirements
        "financial services act",      # financial institution records
        # descriptive
        "records must be kept not less than years",
        "accounting records retained minimum period",
        "tax records kept minimum years",
        "employment records retention period",
        "telecommunications records minimum retention",
        "financial records preservation minimum period",
        "business records kept minimum years",
        # general retention vocabulary matching the operative wording of corporate/tax acts
        "retain the records for a period of not less than",
        "accounting records and systems of control",
        "keeping of accounting records",
        "preservation of records",
    ],

    # ── P7-I4 — DPO / DPIA ──
    # Narrow indicator: only laws that mandate appointing a DPO or conducting a DPIA.
    "P7-I4": [
        # name fragments
        "personal data protection act",    # DPO/DPIA most commonly in PDPA-type laws
        "privacy act",
        # descriptive
        "data protection officer appointment requirement",
        "data protection impact assessment obligation",
        "privacy impact assessment requirement",
        "appoint data protection officer organisation",
        "significant data fiduciary obligations",
    ],

    # ── P7-I5 — GOVERNMENT ACCESS TO PERSONAL DATA ──
    # Police / authority empowered to access, search, compel disclosure.  Lives in criminal
    # procedure codes, security acts, cybersecurity acts, telecom laws — many instrument types.
    "P7-I5": [
        # name fragments — generic law-type names shared across common-law jurisdictions
        "criminal procedure code",         # common-law: SG, MY, IN, PK, etc.
        "criminal procedure act",          # variant naming
        "security offences act",           # special security legislation
        "interception of communications act",  # lawful interception laws
        "telecommunications interception act", # AU Telecommunications (Interception) Act
        "computer misuse act",             # access/hacking provisions used for investigation
        "cybersecurity act",               # cybersecurity laws with authority access powers
        "police act",                      # police powers acts
        "national security act",           # national-security data access powers
        # descriptive
        "police access computer data investigation",
        "law enforcement access personal data",
        "criminal investigation electronic records",
        "lawful interception of communications",
        "government authority inspect computer",
        "national security data access powers",
        "production order disclosure personal data",
        "search and seizure electronic data",
        "authorized person access computer records",
    ],
}


def portal_search_queries(economy: str, pillar: int | None = None) -> list[str]:
    """De-duplicated, order-preserving list of search queries for (economy, pillar).

    Order:
      1. Broad pillar terms (highest recall, fewest assumptions)
      2. Indicator-level terms — name fragments first (effective on portal name-based
         search APIs like AU OData contains(name,…) and portal search boxes), then
         descriptive phrases (effective on full-text web search via DDG/Serper).

    Both sets are country-agnostic: the same queries work for any economy.  The
    `economy` parameter is kept for future language variants (Malay/Thai) but does
    not affect query content for Round 1 (SG/AU/MY, all English portals).
    """
    from .indicators import get_indicators
    pillars = [6, 7] if pillar is None else [pillar]

    out: list[str] = []

    # 1. Broad pillar terms — maximum recall, fired first
    for p in pillars:
        out.extend(PILLAR_SEARCH_TERMS.get(p, []))

    # 2. Per-indicator terms (name fragments + descriptive), in indicator order
    for p in pillars:
        for ind in get_indicators(p):
            out.extend(INDICATOR_SEARCH_TERMS.get(ind.indicator_id, []))

    # Deduplicate while preserving order (first occurrence wins)
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq
