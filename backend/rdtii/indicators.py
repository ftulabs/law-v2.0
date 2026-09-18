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
            "The operative rule is either (a) a BAN on transferring data abroad, or (b) a requirement to "
            "PROCESS data within the country. These are TWO INDEPENDENT LIMBS and only limb (a) is about "
            "bans: a local-processing mandate satisfies this indicator outright, whether or not transfer is "
            "also restricted. "
            "'PROCESSING' IS BROAD. The RDTII 2.1 guide (p.50) takes it from the GDPR sense — collection, "
            "organisation, structuring, STORAGE, adaptation, use, disclosure and dissemination — so a rule "
            "compelling any of those activities to happen domestically is limb (b). "
            "THE DATA NEED NOT BE PERSONAL. The guide scores a measure covering personal data or applying "
            "horizontally at 1 and one covering non-personal data or a specific data set at 0.5, so BOTH are "
            "in scope: do not reject a ban on exporting map data, survey data, credit data, health records "
            "or accounting records for not being 'personal data'. "
            "GOVERNMENT DATA IS EXCLUDED. A measure applying only to the Government's own data is not scored "
            "— the indicator is about measures affecting commercial transactions. "
            "Distinguish from P6-I4 (Conditional flow): where transfer REMAINS legally possible once "
            "conditions (consent / adequacy / approval) are met, limb (a) is not made out — that is a "
            "conditional regime, and P6-I4 is where it belongs. This does NOT touch limb (b): a duty to "
            "process locally stays here even though data may also be transferable under conditions. "
            "Distinguish from P6-I2 (storage of data in-country, which may still permit transfer of a copy) "
            "and P6-I3 (local servers/infrastructure). "
            # Added 2026-08-31. An independent auditor (tools/audit_rows.py) refused 83% of the
            # rows we filed here; reading them, the commonest fault by far was that the provision
            # was not about data at all. India's Chemical Weapons Convention Act s.15-16 bans the
            # "transfer of toxic Chemicals or Precursors" and was exported as a cross-border DATA
            # ban; Australia's Insurance Act s.15(1)(f) is revocation of an authorisation. Each
            # shares vocabulary with this test — transfer, prohibited — and nothing else.
            "WHAT IS RESTRICTED MUST BE DATA. The subject of the ban has to be data, information, "
            "records or personal information. A prohibition or restriction on moving anything ELSE "
            "across a border — goods, chemicals, weapons, currency, securities, property, persons — "
            "does NOT satisfy this indicator however absolutely it is worded, and neither does an "
            "export-control, customs or non-proliferation rule that happens to use the word 'transfer'. "
            "Nor is it satisfied by: revoking, suspending or refusing a registration, licence or "
            "authorisation; conditions for granting one; a duty to operate systems or premises "
            "securely; or an arrangement for recognising foreign authorities or certificates. If you "
            "cannot quote words that stop DATA leaving the country or compel it to be processed inside "
            "it, answer false."
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
            "The operative rule requires data to be STORED / kept (a copy) in a database or facility "
            "located within the territory (data-localisation for storage). The RDTII 2.1 guide (p.50) "
            "defines it as a mandate 'that A COPY of certain data be stored within the economy' — data may "
            "still cross the border, so long as a copy stays. Example: 'personal data shall be stored in a "
            "database located in the territory of [country]'. The rule may equally be phrased NEGATIVELY — "
            "'records must not be held / kept / taken outside the country' imposes the same obligation (the "
            "data must remain stored in-country) and SATISFIES this indicator. "
            "THE DATA NEED NOT BE PERSONAL. The guide scores personal-data or horizontal measures at 1 and "
            "non-personal or specific-data-set measures at 0.5 — both are in scope, so accounting, tax, "
            "health or telecom records qualify without being labelled 'personal data'. "
            "GOVERNMENT DATA IS EXCLUDED: a measure applying only to the Government's own data is not "
            "scored. "
            "Because a mandatory local copy is the whole test, rules that permit records to be kept ABROAD "
            "only if copies, accounts or returns are sent to and KEPT IN-COUNTRY (classic companies/tax "
            "accounting-records drafting) SATISFY it — do not reject them for permitting the originals "
            "offshore. "
            "Where the SAME measure imposes both local processing and local storage, the guide records it "
            "under both indicators (its worked example is Australia's health records), so judge this "
            "indicator on its own terms and do NOT treat P6-I1 as a better fit. "
            # Added 2026-08-31 alongside the P6-I1 gate above, from the same audit. Six refusals
            # here were record-keeping duties that name no place — SG Income Tax Act s.67(1)(a),
            # Confiscation of Benefits Act s.43 — and the auditor's own words, five times over,
            # were "does not specify a geographical location". Storage localisation without a
            # location is not storage localisation. This gate costs the answer key nothing: every
            # P6-I2 provision the panel accepts names a place (SG Companies Act s.199 "at the
            # registered office … or such other place in Singapore", CN PIPL art.36 "within the
            # territory", IN Companies Act s.128 "accessible in India").
            "A LOCATION MUST BE NAMED. The rule has to fix WHERE the data or records sit: inside the "
            "country or its territory, at a registered office or facility in the country, on domestic "
            "premises, accessible from within the country — or, negatively, not outside it. A duty to "
            "keep, retain, maintain, preserve, produce, lodge or safeguard records that is SILENT about "
            "where they are held does NOT satisfy this indicator, no matter how detailed the duty is: "
            "that is a retention or record-keeping rule (see P7-I3 if it states a minimum period), not "
            "a localisation rule. Neither do generic data-security or safe-custody obligations, nor "
            "conditions on transferring data OUT of the country (P6-I4). If you cannot quote the words "
            "naming the place, answer false. "
            "Distinguish from P6-I3 (local SERVERS/data-centres/infrastructure as a "
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
            "The operative rule requires the provider to ESTABLISH, own or dedicate LOCAL physical "
            "infrastructure — a data centre, server or computing facility — AS A PRECONDITION for supplying "
            "a service. Example: 'providers of websites, social networks and online games must maintain at "
            "least one local server'. "
            "THE PRECONDITION, NOT THE LOCATION, IS WHAT SEPARATES THIS FROM P6-I2. The RDTII 2.1 guide "
            "(p.51) puts it squarely: local storage 'only mandates that data be stored within the economy "
            "but does not require the service provider to build or own a data centre; the provider may rent "
            "or use an existing local facility or server', whereas an infrastructure requirement 'requires "
            "the service provider to establish or use dedicated local physical infrastructure as a "
            "precondition for offering services'. So asking only where data sits is P6-I2; compelling the "
            "provider to stand up or dedicate the facility itself is this indicator. "
            "OPERATIONAL AND TECHNICAL RULES FOR DATA CENTRES ARE NOT SCORED. The guide says so explicitly: "
            "the indicator looks for infrastructure mandated as a BARRIER to data movement, not for "
            "security, certification, uptime or engineering standards that apply to a data centre once it "
            "exists. "
            "GOVERNMENT DATA IS EXCLUDED. "
            # Added 2026-08-31, same audit. Both refusals here were a provision setting out what a
            # MINISTRY does — China's domain-name measures art.4, Mongolia's public-information law
            # art.32 — read as an infrastructure mandate. Describing an agency's functions is not
            # requiring anyone to site a server.
            "PHYSICAL INFRASTRUCTURE MUST BE NAMED AND LOCATED. Quote the words identifying the thing — "
            "server, data centre, node, equipment, computing facility, premises — and the words placing "
            "it inside the country (or making it reachable only from inside). Without both, answer "
            "false. In particular these do NOT satisfy it: a provision setting out the functions, "
            "powers or responsibilities of a ministry, regulator or agency; a licensing or approval "
            "requirement that names no infrastructure; generic information-security, risk-management, "
            "business-continuity or system-administration duties; and a requirement about where DATA is "
            "held with no equipment mandated (that is P6-I2). "
            "Distinguish from P6-I2 (where DATA is stored — "
            "here the trigger is mandated local INFRASTRUCTURE/equipment) and from P6-I1 (a processing ban)."
        ),
        scope="national",
        query_terms=["local server", "maintain at least one server", "data centre located", "establish a server",
                     "infrastructure within the country", "place servers in", "local data centre",
                     # The guide's own examples are phrased as an obligation to STAND UP a facility as
                     # a precondition of service (Chile's contingency processing centre, Viet Nam's
                     # "at least one local server", Kazakhstan's local management system). The
                     # location-only terms above rank those below ordinary storage rules.
                     "contingency data processing centre", "shall establish a data centre",
                     "physically located within", "servers located within the territory",
                     "as a condition for providing the service", "local system of centralized management"],
    ),
    Indicator(
        indicator_id="P6-I4",          # ≡ Methodology 6.4
        pillar=6,
        title="Conditional flow regimes",
        description="Is cross-border transfer ALLOWED ONLY IF conditions are met (consent, adequacy, contract, approval, evaluation)?",
        legal_test=(
            "The operative rule ALLOWS cross-border transfer provided CONDITIONS are satisfied. THE JOB HERE "
            "IS TO IDENTIFY THE CONDITION AND SAY WHAT IT IS — not to decide whether the provision is a ban. "
            "Name the gateway in `operative_rule`: whose consent, whose assessment, whose approval, which "
            "standard the destination must meet. The RDTII 2.1 guide (p.52) organises the indicator by WHO "
            "decides, and all four shapes satisfy it: (i) the DATA SUBJECT consents; (ii) the BUSINESS itself "
            "evaluates whether the destination's protection is adequate or equivalent; (iii) the GOVERNMENT "
            "determines which destinations are adequate, or authorises the transfer in advance; (iv) a "
            "prescribed contract, certification or security assessment stands in for any of these. A "
            "provision listing SEVERAL alternative gateways (consent OR adequacy OR contract) maps here. "
            "THE DATA NEED NOT BE PERSONAL: the guide scores a regime covering personal data at 1, a "
            "horizontal regime at 1 even for non-personal data, and a non-personal or sector-specific regime "
            "at 0.5 — all are in scope. GOVERNMENT DATA IS EXCLUDED. "
            "Distinguish from P6-I1 only in this narrow sense: where NO condition can ever unlock the "
            "transfer, it is a ban and belongs there instead. "
            # Added after a live India run rejected the panel's OWN answer. DPDP 2023 s.16 reads
            # "The Central Government may, by notification, restrict the transfer of personal data
            # ... to such country or territory outside India as may be so notified", and every
            # model refused it as "a delegation of power, not an operative rule". That reasoning
            # is coherent and wrong for RDTII: the panel cites exactly this section for 6.4,
            # because the resulting regime IS conditional — transfer is lawful unless and until
            # the notification issues. The same shape appears in China, so this is a
            # class of provision, not one statute.
            "A DELEGATED POWER also maps here: a provision empowering the government to restrict, "
            "notify, blacklist, or permit transfers to particular countries creates a CONDITIONAL "
            "regime, because transfer stays lawful unless and until that power is exercised. Do "
            "NOT reject such a provision on the ground that it is 'only a delegation' or 'not "
            "itself operative' — the notification is the condition. Worked example that MUST "
            "satisfy: 'The Central Government may, by notification, restrict the transfer of "
            "personal data by a Data Fiduciary for processing to such country or territory "
            "outside India as may be so notified.'"
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
            "The provision establishes or constitutes a personal-DATA-PROTECTION framework: its "
            "scope/application, core obligations to obtain consent and to protect personal data, definitions, "
            "the regulator, or — equally — any of the DATA-SUBJECT RIGHTS that make a framework comprehensive. "
            "The RDTII 2.1 guide (p.58) states the criteria: 'broad, cross-sectoral (i.e., horizontal) "
            "applicability and detailed provisions on the scope and application of rights and obligations of "
            "data subjects… empowers individuals to control their personal data, such as the RIGHT TO ACCESS, "
            "RECTIFICATION, ERASURE, and DATA PORTABILITY, and encompasses various activities, such as data "
            "collection, data processing and the transfer of personal data across borders'. A section "
            "conferring any one of those rights, or governing any of those activities, is part of the "
            "framework and satisfies this indicator. "
            "COMPREHENSIVENESS IS SHOWN BY ENUMERATION, so cite every qualifying provision rather than one "
            "keystone section, and do not reject a provision for being 'only' one right among many — the "
            "framework may also be spread across SEVERAL instruments rather than one Act. "
            "RDTII records BOTH a horizontal/comprehensive data-protection law (governs personal data "
            "generally) AND a SECTORAL data-privacy law — e.g. one protecting telecom data or health data "
            "specifically — so a sectoral privacy provision STILL maps here (mark Coverage = Sectoral; it "
            "does not disqualify, it is what separates a score of 0.5 from 0). "
            "Distinguish from P7-I2 (CYBERSECURITY, a different subject) and from the SPECIFIC obligations "
            "P7-I3 (retention), P7-I4 (DPIA/DPO) and P7-I5 (government access)."
        ),
        scope="national",
        query_terms=["personal data protection act", "this act applies to", "processing of personal data",
                     "protect personal data", "collect, use or disclose", "consent of the individual",
                     "protection of personal data", "privacy of telecommunications", "health information privacy",
                     # principles-based framework drafting: the operative core of an omnibus privacy Act is
                     # often one terse section binding entities to a schedule of privacy principles (AU s15
                     # style: "must not breach a privacy principle") — without these phrasings that keystone
                     # section ranks below verbose sectoral rules and the framework law misses the shortlist.
                     # NOTE: phrase-bonus matching is literal — keep these as substrings that
                     # actually occur in statutes ("breaches an Australian Privacy Principle").
                     "privacy principle", "privacy principles", "breaches a privacy principle",
                     "breaches an australian privacy principle",
                     "interference with the privacy of an individual"],
    ),
    Indicator(
        indicator_id="P7-I2",          # ≡ Methodology 7.2
        pillar=7,
        title="Dedicated legal framework for cybersecurity",
        description="Does a dedicated cybersecurity legal framework / set of cybersecurity obligations exist?",
        legal_test=(
            "The provision is a CYBERSECURITY obligation: protection of critical information infrastructure, "
            "ENCRYPTION / cryptographic controls, secure remote access, network-security architecture, duties "
            "to monitor, detect, prevent, mitigate or manage incidents, duties to report them, or a "
            "cybersecurity authority. "
            "'DEDICATED' IS A PROPERTY OF THE INSTRUMENT, NOT OF THE CLAUSE. The RDTII 2.1 guide (p.59) "
            "defines a dedicated framework as one where the economy 'establishes broadly applicable "
            "cybersecurity-specific laws (horizontal) OR cybersecurity-focused laws applicable to specific "
            "sectors (sectoral)', and a NON-dedicated one as an economy that 'does not implement specific "
            "cybersecurity laws but relies on OTHER laws to govern threats arising from cybercrime'. So say "
            "in the rationale which kind you are looking at: a Cybersecurity Act, a critical-infrastructure "
            "law or a sector cybersecurity regulation is dedicated (and a sectoral one still counts, scoring "
            "0.5 rather than 0); a stray security clause inside a banking, companies or privacy Act is the "
            "non-dedicated case. Both are recorded — being non-dedicated lowers the score, it does not make "
            "the provision irrelevant. "
            "Distinguish from P7-I1 (personal-DATA protection) — encryption and network-security duties are "
            "cybersecurity, not data-privacy."
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
            "The operative rule mandates a MINIMUM RETENTION DURATION — data, records or information must be "
            "kept for AT LEAST a stated period ('keep for not less than N years'; e.g. business e-commerce "
            "records kept 6 years). It is NOT the same as 'do not keep data longer than necessary' (a "
            "purpose-/storage-limitation rule): the RDTII 2.1 guide (p.60) calls that a MAXIMUM period and "
            "says it is not scored in version 2.1. A requirement that exists but fixes no period likewise "
            "scores 0. A PERMANENT retention duty does satisfy the indicator. "
            "THE RANK OF THE INSTRUMENT DOES NOT MATTER. The guide does not require the period to sit in "
            "primary legislation, so a duty to retain 'for the prescribed period' — where the period is set "
            "by regulations, by a ministerial or regulatory order, or by a licence condition issued under a "
            "proper statutory power — SATISFIES this indicator. The binding obligation is what counts, not "
            "which kind of instrument states the number; do not reject such a provision because the figure "
            "is fixed elsewhere. "
            "Distinguish from P6-I2 (WHERE data is stored, not how long). Retention applied only to "
            "GOVERNMENT data is out of scope."
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
            "accountability such as a mandated data auditor tied to the DPO/DPIA regime counts too). "
            "THE DPO DUTY IS THE ONE THAT WEIGHS. The RDTII 2.1 guide (p.61) scores a DPO requirement (alone "
            "or with DPIA) applying horizontally at 1, the same requirement confined to a specific sector at "
            "0.5, and a DPIA-only requirement at 0.25 — 'the scoring metric focuses more on the presence of "
            "the DPO requirement'. So say in the rationale WHICH duty the provision imposes and whether it "
            "binds all sectors or one; a DPIA-only rule still maps here but must not be described as a DPO "
            "requirement. A duty framed functionally — 'designate one or more individuals responsible for "
            "ensuring compliance' — is a DPO requirement whatever the title used. "
            "Distinguish from the general framework (P7-I1) — the trigger here is specifically the DPO/DPIA "
            "duty."
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
            "The operative rule lets the government, police or a public authority ACCESS, search, inspect, copy, "
            "intercept or compel disclosure of PERSONAL DATA — and does so WITHOUT requiring the explicit "
            "authorisation of an INDEPENDENT JUDICIAL BODY. That second half is the test, not a strengthening "
            "factor: the RDTII 2.1 guide (p.62) asks 'whether the Government can access personal data without the "
            "explicit authorization of an independent judicial body, such as a court decision, a judicial warrant "
            "or an equivalent order issued by a truly independent tribunal with due process safeguards'. So a power "
            "exercisable only on a court order or judicial warrant does NOT satisfy this indicator, however "
            "sweeping the access it grants; the absence of judicial oversight is what the indicator measures. "
            "AUTHORISATION BY A NON-JUDICIAL BODY STILL SATISFIES IT, and so does the PROCEDURE for obtaining such "
            "authorisation: a minister, a regulator, a commission, a police superintendent or an undefined "
            "'competent authority' is not an independent tribunal, and the guide's own examples are of exactly "
            "that shape (Cambodia's undefined 'legitimate authority'; India's ISPs handing subscriber logs to "
            "intelligence agencies on demand; Sri Lanka's operators opening their databases to the "
            "telecommunications regulator on request). Such measures live BEYOND privacy law: in criminal procedure "
            "codes, surveillance / lawful-access / interception laws and telecom law. "
            "THE OBJECT MUST BE PERSONAL DATA. A power to seize goods, premises or things generally is out of "
            "scope; where a production power is worded broadly ('any document or other thing'), it counts only "
            "when it reaches data about identifiable individuals. "
            "Distinguish from P7-I2 (cybersecurity duties on private entities, not state access)."
        ),
        scope="national",
        query_terms=["police officer", "authorised person", "arrestable offence", "access, inspect", "search any data",
                     "make a copy of any such data", "lawful interception", "without a warrant", "law enforcement",
                     "production order", "require the production of", "national security",
                     # What the indicator actually measures is access NOT authorised by a court, so
                     # the discriminating words are the non-judicial authoriser and the bare demand.
                     # (RDTII 2.1 guide p.62 — Cambodia's undefined "legitimate authority", India's
                     # subscriber logs on demand, Sri Lanka's regulator-initiated database access.)
                     "upon request by the", "on the direction of the Minister", "competent authority may require",
                     "shall provide access to", "furnish such information as may be required",
                     "subscriber information", "authorised by the Commission", "intelligence agencies"],
    ),
]


def get_indicators(pillar: int | None = None) -> list[Indicator]:
    """Indicators for one pillar, or the measured nine when no pillar is named.

    `pillar=None` returns ONLY pillars 6 and 7, and that is deliberate rather than an
    oversight. The evaluation harness (`backend/eval/*`) calls it that way to build its corpus,
    and the retrieval parameters in `docs/retrieval-redesign.md` were swept against exactly
    that set; widening it here would silently re-baseline every measurement we hold. A caller
    that genuinely wants all sixty-one asks for each pillar, or reads
    `indicators_wide.INDICATORS_WIDE` directly.
    """
    if pillar is None:
        return list(INDICATORS)
    ours = [i for i in INDICATORS if i.pillar == pillar]
    if ours:
        return ours
    # Pillars 1-5 and 8-12: declared in indicators_wide, not measured. Imported lazily so the
    # nine-indicator path has no dependency on the fifty-two.
    from .indicators_wide import get_wide
    return get_wide(pillar)


def get_indicator(indicator_id: str) -> Indicator | None:
    hit = next((i for i in INDICATORS if i.indicator_id == indicator_id), None)
    if hit is not None:
        return hit
    from .indicators_wide import INDICATORS_WIDE
    return next((i for i in INDICATORS_WIDE if i.indicator_id == indicator_id), None)


def siblings(indicator_id: str) -> list[Indicator]:
    """Other indicators in the same pillar — used to disambiguate the mapping.

    The mapper shows these to the model so it can tell 6.1 from 6.4. That matters more outside
    pillars 6 and 7, not less: 12.4 splits into seven limbs that differ only in which aspect of
    a payment they restrict, and a grader shown one limb in isolation will map any payment rule
    to it.
    """
    ind = get_indicator(indicator_id)
    if ind is None:
        return []
    return [i for i in get_indicators(ind.pillar) if i.indicator_id != indicator_id]
