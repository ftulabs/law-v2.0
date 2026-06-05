"""RDTII 2.1 indicators — Pillars 6 & 7 (OFFICIAL Methodology).

Source of truth = the RDTII Methodology sheet (and the ESCAP indicator slides), confirmed
by the judges' worked examples (Armenia Art.27 -> 6.4; Kazakhstan Art.12(2) -> 6.2).

IMPORTANT — these are the LOCALISATION-centric Pillar-6 indicators (ban / storage /
infrastructure / conditional-flow) and the FRAMEWORK-centric Pillar-7 indicators
(data-protection framework / cybersecurity / retention / DPIA-DPO / government access).
The output `indicator_id` uses the template format P6-I1..P6-I4 / P7-I1..P7-I5, which map
1:1 by number to Methodology 6.1..6.4 / 7.1..7.5. Pillar 6 has FOUR indicators (no I5).

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
            "stored in a database located in the territory of [country]'. Distinguish from P6-I1 (a ban on "
            "transfer/processing — storage rules may still allow a copy to be transferred), from P6-I3 (local "
            "SERVERS/data-centres/infrastructure as a condition for supplying a service, not merely where data "
            "is stored), and from P7-I3 (a minimum RETENTION DURATION, which is about how long, not where)."
        ),
        scope="national",
        query_terms=["stored in a database located", "store within the territory", "kept within the country",
                     "data shall be stored in", "local storage", "retained within", "database located in the territory"],
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
        title="Lack of comprehensive legal framework for data protection",
        description="Does a (comprehensive, cross-sectoral) personal-data-protection legal framework exist?",
        legal_test=(
            "The provision establishes or constitutes a DATA-PROTECTION legal framework — a general personal-"
            "data-protection law: its scope/application, core obligations on organisations to obtain consent and "
            "to protect personal data, definitions, and the regulator. A horizontal (all-sector) law is a "
            "comprehensive framework; a law limited to one sector is a sectoral framework. Distinguish from P7-I2 "
            "(CYBERSECURITY framework, not personal-data protection) and from the SPECIFIC obligations P7-I3 "
            "(retention), P7-I4 (DPIA/DPO) and P7-I5 (government access)."
        ),
        scope="national",
        query_terms=["personal data protection act", "this act applies to", "processing of personal data",
                     "protect personal data", "collect, use or disclose", "consent of the individual",
                     "protection of personal data of individuals"],
    ),
    Indicator(
        indicator_id="P7-I2",          # ≡ Methodology 7.2
        pillar=7,
        title="Lack of dedicated legal framework for cybersecurity",
        description="Does a dedicated (horizontal) cybersecurity legal framework exist?",
        legal_test=(
            "The provision establishes a CYBERSECURITY legal framework — e.g. a Cybersecurity Act: protection of "
            "critical information infrastructure, a cybersecurity authority/commissioner, duties to secure systems "
            "or report cyber incidents. A dedicated horizontal cybersecurity law is the strongest case. Distinguish "
            "from P7-I1 (personal-DATA protection, a different subject) — a cyber-incident duty is NOT a personal-"
            "data measure."
        ),
        scope="national",
        query_terms=["cybersecurity act", "critical information infrastructure", "cybersecurity",
                     "secure computer systems", "cybersecurity incident", "commissioner of cybersecurity",
                     "computer misuse"],
    ),
    Indicator(
        indicator_id="P7-I3",          # ≡ Methodology 7.3
        pillar=7,
        title="Minimum period of data retention requirements",
        description="Does the law impose a MINIMUM period for which (personal) data/records must be retained?",
        legal_test=(
            "The operative rule mandates a MINIMUM RETENTION DURATION — data, records or information must be "
            "kept for at least a stated period. The trigger is the time obligation ('keep for not less than N "
            "years'). Distinguish from P6-I2 (WHERE data is stored, not how long) and from ordinary record-"
            "keeping with no minimum period. (RDTII exception: retention applied only to GOVERNMENT data is "
            "out of scope.)"
        ),
        scope="national",
        query_terms=["keep for a period of", "retain for at least", "minimum period", "retention period",
                     "must be kept for", "not less than", "preserve the records for", "period for keeping"],
    ),
    Indicator(
        indicator_id="P7-I4",          # ≡ Methodology 7.4
        pillar=7,
        title="Data Protection Impact Assessment (DPIA) or Data Protection Officer (DPO) requirements",
        description="Does the law require a DPIA and/or the appointment of a Data Protection Officer?",
        legal_test=(
            "The operative rule requires conducting a DATA PROTECTION IMPACT ASSESSMENT (DPIA) and/or appointing "
            "a DATA PROTECTION OFFICER (DPO). Either obligation satisfies the indicator. Distinguish from the "
            "general framework (P7-I1) — the trigger here is specifically the DPIA/DPO duty."
        ),
        scope="national",
        query_terms=["data protection officer", "data protection impact assessment", "appoint an officer",
                     "designate a data protection officer", "impact assessment", "DPO", "DPIA"],
    ),
    Indicator(
        indicator_id="P7-I5",          # ≡ Methodology 7.5
        pillar=7,
        title="Requirements to allow government access to personal data",
        description="Does the law allow the government to ACCESS personal data (esp. without a court order)?",
        legal_test=(
            "The operative rule ALLOWS the government / a public authority to ACCESS, intercept, or compel "
            "disclosure of personal data. The strongest case is access WITHOUT a court order/warrant. Distinguish "
            "from P7-I2 (cybersecurity duties) and from ordinary regulator powers tied to judicial authorisation. "
            "The trigger is state access to personal data."
        ),
        scope="national",
        query_terms=["government may access", "without a warrant", "without a court order", "lawful interception",
                     "disclose to the authority", "provide information to the Minister", "access by law enforcement",
                     "require the production of"],
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
