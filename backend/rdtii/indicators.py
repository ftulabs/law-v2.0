"""RDTII 2.1 indicators — Pillars 6 & 7 (OFFICIAL Methodology).

Source of truth = the "RDTII 2.1 Methodology" sheet in the official Round-1 Database
(ESCAP-RDTII-2.1_ Round 1 Database.xlsx, in repo root), confirmed indicator-by-indicator by
the worked answer key for the mandatory economies, e.g. Singapore:
  6.1 ← PDPA (no ban)  · 6.2 ← Companies Act §199  · 6.4 ← PDPA §26 (conditional transfer)
  7.1 ← PDPA  · 7.2 ← Cybersecurity Act 2018  · 7.3 ← PDPA §25 / Telecom / Income Tax
  7.4 ← PDPA §11(3) DPO  · 7.5 ← Criminal Procedure Code §39-40 (police access).

IMPORTANT — these are the LOCALISATION-centric Pillar-6 indicators (ban / storage /
infrastructure / conditional-flow) and the FRAMEWORK-centric Pillar-7 indicators
(data-protection framework / cybersecurity / retention / DPIA-DPO / government access).
The output `indicator_id` uses the template format P6-I1..P6-I4 / P7-I1..P7-I5, which map
1:1 by number to Methodology 6.1..6.4 / 7.1..7.5. Pillar 6 has FOUR extractable indicators
(6.5 "binding commitments" is a non-regulatory, third-party-sourced indicator — out of crawl
scope per the internal guide, so it is excluded here).

CAVEAT (do not "fix" the definitions to match it): the OUTPUT_TEMPLATE_31MAY.xlsx
"Indicator Reference" sheet mislabels these with generic GDPR names (P6-I1 "general
prohibition", P7-I2 "purpose limitation"). That sheet is an erroneous artifact — the scored
answer key (the Database above) uses the localisation/framework definitions coded below.

The Methodology's scoring criteria (1/0.5/0) live in the scoring layer (Zone 3, optional);
here we keep what's needed to IDENTIFY which indicator a provision satisfies:
  • legal_test  — the operative rule that satisfies THIS indicator, with explicit
    "Distinguish from …" notes against the indicators most often confused with it.
  • query_terms — discriminative phrases used by retrieval and the mock grader.
"""
from __future__ import annotations

from ..schemas import Indicator

INDICATORS: list[Indicator] = [
    # ───────────── Pillar 6 — Cross-border Data Policies (data localisation) ─────────────
    Indicator(
        indicator_id="P6-I1",          # ≡ Methodology 6.1
        pillar=6,
        title="Ban and local processing requirements",
        description="Does the law BAN cross-border data transfer, or require data to be PROCESSED locally?",
        legal_test=(
            "The operative rule is either (a) a BAN on transferring personal data abroad, or (b) a "
            "requirement to PROCESS personal data within the country. This is the most restrictive case — "
            "it prevents or strongly constrains cross-border data use. Distinguish from P6-I4 (Conditional "
            "flow): if transfer REMAINS legally possible once conditions (consent/adequacy/etc.) are met, it "
            "is NOT a total ban → map to P6-I4, not here. Distinguish from P6-I2 (storage of data in-country, "
            "which may still permit transfer of a copy) and P6-I3 (local servers/infrastructure)."
        ),
        scope="national",
        query_terms=["shall not transfer", "prohibited from transferring", "may not be transferred",
                     "must be processed within", "processed locally", "ban on cross-border transfer",
                     "transfer is prohibited"],
    ),
    Indicator(
        indicator_id="P6-I2",          # ≡ Methodology 6.2
        pillar=6,
        title="Local storage requirements",
        description="Does the law require personal data to be STORED in a database located in the country?",
        legal_test=(
            "The operative rule requires personal data to be STORED / kept (a copy) in a database or facility "
            "located within the territory (data-localisation for storage). Example: 'personal data shall be "
            "stored in a database located in the territory of [country]'. The rule may equally be phrased "
            "NEGATIVELY — 'records must not be held / kept / taken outside the country' imposes the same "
            "obligation (the data must remain stored in-country) and SATISFIES this indicator. Such a "
            "prohibition typically satisfies BOTH P6-I1 (ban) and P6-I2 (local storage) — the RDTII "
            "methodology scores it under both, so judge this indicator on its own terms and do NOT treat "
            "P6-I1 as a better fit. Distinguish from P6-I3 (local SERVERS/data-centres/infrastructure as a "
            "condition for supplying a service, not merely where data is stored), and from P7-I3 (a minimum "
            "RETENTION DURATION, which is about how long, not where)."
        ),
        scope="national",
        query_terms=["stored in a database located", "store within the territory", "kept within the country",
                     "data shall be stored in", "local storage", "retained within", "database located in the territory",
                     # negative phrasing of the same obligation ("must not hold records outside the
                     # country" ≡ "must store in-country") — without these, ban-worded localisation
                     # sections rank low for THIS indicator and only surface under P6-I1.
                     "not hold or take records outside", "must not be held outside",
                     "shall not be kept outside", "records outside the country",
                     # business/accounting/tax record-keeping vocabulary: corporate & tax Acts phrase the
                     # in-country obligation as "keep accounting records / books of account, kept at the
                     # registered office; if kept outside the country, copies must be sent to and kept
                     # locally" (e.g. SG Companies Act s199(4)). Without these the indicator's data-centric
                     # terms rank such provisions far below the shortlist and they are never graded.
                     "accounting records", "books of account", "kept at the registered office",
                     "records kept at a place", "kept at a place in the country",
                     "accounting records kept outside", "business records kept", "financial records kept"],
    ),
    Indicator(
        indicator_id="P6-I3",          # ≡ Methodology 6.3
        pillar=6,
        title="Infrastructure requirements",
        description="Does the law require local servers / data centres / infrastructure as a condition to supply a service?",
        legal_test=(
            "The operative rule requires LOCAL servers, data centres, or local data infrastructure AS A "
            "CONDITION for supplying a service. Example: 'providers of websites, social networks and online "
            "games must maintain at least one local server'. Distinguish from P6-I2 (where DATA is stored — "
            "here the trigger is mandated local INFRASTRUCTURE/equipment) and from P6-I1 (a processing ban)."
        ),
        scope="national",
        query_terms=["local server", "maintain at least one server", "data centre located", "establish a server",
                     "infrastructure within the country", "place servers in", "local data centre"],
    ),
    Indicator(
        indicator_id="P6-I4",          # ≡ Methodology 6.4
        pillar=6,
        title="Conditional flow regimes",
        description="Is cross-border transfer ALLOWED ONLY IF conditions are met (consent, adequacy, contract, approval, evaluation)?",
        legal_test=(
            "The operative rule ALLOWS cross-border transfer provided CONDITIONS are satisfied — e.g. the "
            "individual's consent, the destination's adequate level of protection, contractual safeguards, "
            "prior approval, or an evaluation/assessment. Because transfer remains legally possible once the "
            "condition is met, this is NOT a total ban (do not map to P6-I1). A provision listing SEVERAL "
            "alternative gateways (consent OR adequacy OR contract) maps here. Distinguish from P6-I1 (outright "
            "ban with no liftable condition)."
        ),
        scope="national",
        query_terms=["may be transferred unless", "with the consent of the individual", "adequate level of protection",
                     "prescribed country", "subject to conditions", "with the approval of", "comparable standard of protection",
                     "binding corporate rules", "standard contractual clauses", "where the recipient ensures"],
    ),
    # ───────────── Pillar 7 — Domestic Data Protection & Privacy ─────────────
    Indicator(
        indicator_id="P7-I1",          # ≡ Methodology 7.1
        pillar=7,
        title="Comprehensive legal framework for data protection",
        description="Does a personal-data-protection legal framework exist (horizontal, OR a sectoral data-privacy law)?",
        legal_test=(
            "The provision establishes or constitutes a personal-DATA-PROTECTION framework: its scope/application, "
            "core obligations to obtain consent and to protect personal data, definitions, or the regulator. RDTII "
            "records BOTH a horizontal/comprehensive data-protection law (governs personal data generally) AND a "
            "SECTORAL data-privacy law — e.g. one protecting telecom data or health data specifically — so a "
            "sectoral privacy provision STILL maps here (mark Coverage = Sectoral; it does not disqualify). "
            "Distinguish from P7-I2 (CYBERSECURITY, a different subject) and from the SPECIFIC obligations P7-I3 "
            "(retention), P7-I4 (DPIA/DPO) and P7-I5 (government access)."
        ),
        scope="national",
        query_terms=["personal data protection act", "this act applies to", "processing of personal data",
                     "protect personal data", "collect, use or disclose", "consent of the individual",
                     "protection of personal data", "privacy of telecommunications", "health information privacy"],
    ),
    Indicator(
        indicator_id="P7-I2",          # ≡ Methodology 7.2
        pillar=7,
        title="Dedicated legal framework for cybersecurity",
        description="Does a dedicated cybersecurity legal framework / set of cybersecurity obligations exist?",
        legal_test=(
            "The provision is a CYBERSECURITY obligation — more than scattered data-security clauses: protection of "
            "critical information infrastructure, ENCRYPTION / cryptographic controls, secure remote access, "
            "network-security architecture, duties to secure systems or report cyber incidents, or a cybersecurity "
            "authority. A dedicated cybersecurity framework is the strongest case. Distinguish from P7-I1 "
            "(personal-DATA protection) — encryption / network-security duties are cybersecurity, not data-privacy."
        ),
        scope="national",
        query_terms=["cybersecurity", "critical information infrastructure", "strong encryption",
                     "cryptographic controls", "network security", "secure remote access",
                     "mitigate cybersecurity risks", "cybersecurity incident", "secure computer systems"],
    ),
    Indicator(
        indicator_id="P7-I3",          # ≡ Methodology 7.3
        pillar=7,
        title="Minimum period of data retention requirements",
        description="Does the law require data/records to be retained for AT LEAST a specified minimum period?",
        legal_test=(
            "The operative rule mandates a MINIMUM RETENTION DURATION — data, records or information must be kept "
            "for AT LEAST a stated period ('keep for not less than N years'; e.g. business e-commerce records kept "
            "6 years). It is NOT the same as 'do not keep data longer than necessary' (a purpose-/storage-"
            "limitation rule) — that is the OPPOSITE and does NOT satisfy this indicator. Distinguish from P6-I2 "
            "(WHERE data is stored, not how long). (RDTII exception: retention applied only to GOVERNMENT data is "
            "out of scope.)"
        ),
        scope="national",
        query_terms=["retain for at least", "kept for a period of", "minimum period", "not less than",
                     "must be kept for", "retained for", "preserve the records for", "period for keeping",
                     "store the records for at least",
                     # same record-keeping vocabulary as P6-I2: the minimum-retention duration lives in the
                     # corporate/tax/employment Acts ("retain the accounting records for not less than 5
                     # years", SG Companies Act s199(2)), which the duration-only terms above under-rank.
                     "accounting records", "books of account", "retain the records for",
                     "retain the accounting records", "keep the records for"],
    ),
    Indicator(
        indicator_id="P7-I4",          # ≡ Methodology 7.4
        pillar=7,
        title="DPO and DPIA requirements",
        description="Does the law require appointing a Data Protection Officer and/or conducting a DPIA?",
        legal_test=(
            "The operative rule requires appointing a DATA PROTECTION OFFICER (DPO) and/or conducting a DATA "
            "PROTECTION IMPACT ASSESSMENT (DPIA) — either obligation satisfies the indicator (related "
            "accountability such as a mandated data auditor tied to the DPO/DPIA regime counts too). Distinguish "
            "from the general framework (P7-I1) — the trigger here is specifically the DPO/DPIA duty."
        ),
        scope="national",
        query_terms=["data protection officer", "data protection impact assessment", "appoint a data protection officer",
                     "appoint one or more data protection officers", "impact assessment", "data auditor",
                     "significant data fiduciary",
                     # FUNCTIONAL phrasings — many laws impose the DPO/DPIA duty without the literal term
                     # (SG PDPA s11(3): "designate one or more individuals to be responsible for ensuring …
                     # complies"), which the lexical retriever otherwise never surfaces:
                     "designate an individual responsible", "designate one or more individuals",
                     "individual responsible for ensuring compliance", "responsible for ensuring the organisation complies",
                     "person responsible for data protection", "assessment of the impact on the privacy"],
    ),
    Indicator(
        indicator_id="P7-I5",          # ≡ Methodology 7.5
        pillar=7,
        title="Requirements to allow government access to personal data",
        description="Does the legal framework enable or require GOVERNMENT / law-enforcement access to personal data?",
        legal_test=(
            "The operative rule ENABLES or REQUIRES the government, police, or a public authority to ACCESS, search, "
            "inspect, copy, intercept, or compel disclosure of personal data — often for law-enforcement, "
            "surveillance, or national-security purposes. Such measures live BEYOND privacy law: in criminal "
            "procedure codes, surveillance / lawful-access / interception laws, telecom law, etc. (e.g. a police "
            "officer investigating an arrestable offence may access and copy any data on a computer). The strongest "
            "case is access WITHOUT a court order. Distinguish from P7-I2 (cybersecurity duties on private entities, "
            "not state access)."
        ),
        scope="national",
        query_terms=["police officer", "authorised person", "arrestable offence", "access, inspect", "search any data",
                     "make a copy of any such data", "lawful interception", "without a warrant", "law enforcement",
                     "production order", "require the production of", "national security"],
    ),
]


def get_indicators(pillar: int | None = None) -> list[Indicator]:
    if pillar is None:
        return list(INDICATORS)
    return [i for i in INDICATORS if i.pillar == pillar]


def get_indicator(indicator_id: str) -> Indicator | None:
    return next((i for i in INDICATORS if i.indicator_id == indicator_id), None)


def siblings(indicator_id: str) -> list[Indicator]:
    """Other indicators in the same pillar — used to disambiguate the mapping."""
    ind = get_indicator(indicator_id)
    if ind is None:
        return []
    return [i for i in INDICATORS if i.pillar == ind.pillar and i.indicator_id != indicator_id]
