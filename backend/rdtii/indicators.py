"""RDTII 2.1 indicators — Pillars 6 & 7 (OFFICIAL reference).

IDs, titles and the `question` field come from the hackathon's official Indicator
Reference. These indicators are deliberately CLOSE to one another (e.g. P6-I1 vs the
four transfer *exceptions* P6-I2..P6-I5; P7-I1 vs P7-I2 vs P7-I3), so an LLM mislabels
easily. Two defences live here:

  • `legal_test` — a precise rule for what satisfies THIS indicator, with explicit
    "Distinguish from …" notes pointing at the sibling that is most often confused.
  • `query_terms` — discriminative phrases, chosen to separate siblings (used by the
    mock grader's argmax-over-pillar logic and by retrieval).

The mapper additionally shows the LLM every sibling indicator in the pillar and asks
it to pick the BEST fit (see pipeline/mapping.py), so a provision is only mapped here
when no sibling fits better.
"""
from __future__ import annotations

from ..schemas import Indicator

INDICATORS: list[Indicator] = [
    # ───────────── Pillar 6 — Cross-border Data Flows ─────────────
    Indicator(
        indicator_id="P6-I1",
        pillar=6,
        title="General prohibition / restriction",
        description="Does the law restrict cross-border transfer of personal data as a default?",
        legal_test=(
            "The provision states the DEFAULT RULE that personal data may not be transferred outside "
            "the jurisdiction (typically 'shall not transfer ... unless'). Map here when the operative "
            "content is the baseline RESTRICTION itself. Distinguish from P6-I2/P6-I3/P6-I4/P6-I5, which "
            "cover the specific EXCEPTIONS that lift the restriction — if the snippet's operative content "
            "is an exception mechanism (adequacy, contract, consent, other), map to that sibling instead."
        ),
        scope="national",
        query_terms=["transfer personal data", "to a country or territory", "territory outside",
                     "place outside", "overseas recipient", "disclose to an overseas recipient",
                     "shall not transfer", "cross-border transfer"],
    ),
    Indicator(
        indicator_id="P6-I2",
        pillar=6,
        title="Adequacy standard",
        description="Can data be transferred to countries deemed to have adequate protection?",
        legal_test=(
            "An EXCEPTION permitting transfer where the destination country/recipient ensures an "
            "ADEQUATE or COMPARABLE level/standard of protection (adequacy decision, whitelist, "
            "'prescribed country', minister-specified destinations). Distinguish from P6-I3 (contract-based) "
            "and P6-I4 (consent-based): the trigger here is the destination's level of protection, not a "
            "contract or the individual's consent."
        ),
        scope="national",
        query_terms=["comparable standard of protection", "adequate level of protection",
                     "prescribed country", "deemed adequate", "specified by the Minister", "whitelist"],
    ),
    Indicator(
        indicator_id="P6-I3",
        pillar=6,
        title="Contractual safeguards",
        description="Are standard contractual clauses or binding corporate rules accepted as transfer mechanisms?",
        legal_test=(
            "An EXCEPTION recognising CONTRACTUAL / intra-group instruments as a transfer basis: standard "
            "contractual clauses (SCCs), binding corporate rules (BCRs), or other legally enforceable "
            "obligations imposed on the recipient. Distinguish from P6-I2 (country adequacy) and P6-I4 "
            "(consent): the trigger here is a binding instrument/clause, not the destination or consent."
        ),
        scope="national",
        query_terms=["binding corporate rules", "standard contractual clauses", "legally enforceable obligations",
                     "contractual clauses", "binding scheme", "intra-group agreement"],
    ),
    Indicator(
        indicator_id="P6-I4",
        pillar=6,
        title="Consent exception",
        description="Can transfer proceed with individual consent?",
        legal_test=(
            "An EXCEPTION permitting cross-border transfer where the INDIVIDUAL has consented to that "
            "transfer. The operative trigger is the data subject's consent to the transfer specifically. "
            "Distinguish from P7-I1 (consent as a basis for general PROCESSING, not transfer) and from "
            "P6-I2/P6-I3 (adequacy/contract triggers)."
        ),
        scope="national",
        query_terms=["consent to the transfer", "consented to the transfer", "with the consent of the individual",
                     "data subject has given his consent to the transfer", "individual consents to the transfer"],
    ),
    Indicator(
        indicator_id="P6-I5",
        pillar=6,
        title="Other exceptions",
        description="What other lawful bases permit cross-border transfer (vital interests, public interest, etc.)?",
        legal_test=(
            "An EXCEPTION permitting transfer on a lawful basis OTHER than adequacy (P6-I2), contract "
            "(P6-I3) or consent (P6-I4): e.g. necessary for performance of a contract with/for the "
            "individual, vital interests, public interest, legal proceedings, or similar statutory grounds."
        ),
        scope="national",
        query_terms=["vital interests", "public interest", "necessary for the performance of a contract",
                     "legal proceedings", "necessary for the conclusion", "statutory ground"],
    ),
    # ───────────── Pillar 7 — Domestic Data Protection ─────────────
    Indicator(
        indicator_id="P7-I1",
        pillar=7,
        title="Legal basis for processing",
        description="Does the law require a lawful basis for collecting/processing personal data?",
        legal_test=(
            "The provision REQUIRES a lawful basis (typically consent) BEFORE collecting, using or "
            "disclosing personal data ('shall not collect/use/disclose ... unless ... consent'). "
            "Distinguish from P7-I2 (limiting use to the original PURPOSE) and P6-I4 (consent to a "
            "cross-border TRANSFER). The trigger here is lawfulness of the processing itself."
        ),
        scope="national",
        query_terms=["shall not collect", "shall not process", "consent of the individual",
                     "consent to the processing", "lawful basis for processing", "collect use or disclose",
                     "process personal data unless", "given his consent to the collection"],
    ),
    Indicator(
        indicator_id="P7-I2",
        pillar=7,
        title="Purpose limitation",
        description="Is data restricted to the purpose for which it was collected?",
        legal_test=(
            "The provision LIMITS use/disclosure of personal data to the PURPOSE for which it was "
            "collected (or a compatible/appropriate purpose), and bars use for unrelated purposes. "
            "Distinguish from P7-I1 (needing a basis to collect at all): the trigger here is the "
            "purpose constraint after collection."
        ),
        scope="national",
        query_terms=["purpose for which", "only for purposes", "another purpose", "purpose limitation",
                     "reasonable person would consider appropriate", "purposes that a reasonable person"],
    ),
    Indicator(
        indicator_id="P7-I3",
        pillar=7,
        title="Data subject rights",
        description="Do individuals have rights to access, correct, or delete their data?",
        legal_test=(
            "The provision GRANTS individuals rights over their own personal data — to access, correct/"
            "rectify, erase/delete, or port it. The right-holder is the individual/data subject. "
            "Distinguish from P7-I1/P7-I2 (obligations on the organisation about collection/use) — those "
            "are duties, not individual rights."
        ),
        scope="national",
        query_terms=["right to access", "request access to", "correction of personal data", "rectify",
                     "erase", "data portability", "individual may request"],
    ),
    Indicator(
        indicator_id="P7-I4",
        pillar=7,
        title="Data breach notification",
        description="Is there a mandatory data breach notification requirement?",
        legal_test=(
            "The provision MANDATES notifying a regulator and/or affected individuals of a PERSONAL DATA "
            "breach within a stated trigger/timeframe. Distinguish from generic cyber-incident reporting "
            "(e.g. a Cybersecurity Act 'report cybersecurity incidents' duty) — that is NOT a personal "
            "data breach notification and must not be mapped here."
        ),
        scope="national",
        query_terms=["data breach notification", "notifiable data breach", "notify the Commission",
                     "notify affected individuals", "eligible data breach", "personal data breach"],
    ),
    Indicator(
        indicator_id="P7-I5",
        pillar=7,
        title="Enforcement & penalties",
        description="Is there a supervisory authority and penalty regime?",
        legal_test=(
            "The provision ESTABLISHES a supervisory/regulatory authority OR a penalty/offence regime "
            "for non-compliance (financial penalties, fines, offences, enforcement directions/powers). "
            "Distinguish from substantive duties (P7-I1..P7-I4): the trigger here is oversight/sanction, "
            "not the underlying data-protection obligation."
        ),
        scope="national",
        query_terms=["financial penalty", "guilty of an offence", "fine not exceeding", "civil penalty",
                     "the Commission may", "enforcement direction", "supervisory authority"],
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
