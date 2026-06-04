"""RDTII 2.1 indicator definitions for Pillar 6 and Pillar 7.

These are the *targets* of the mapping engine. The `legal_test` field is the
heart of hallucination reduction: it tells the mapper what makes a provision
*legally* relevant (a binding rule of the right scope), not merely *semantically*
related (mentions the same topic). `scope` guards against the classic error of
treating a sectoral instrument (e.g. a MAS notice) as a national framework.

Indicator IDs/titles approximate the UNESCAP RDTII 2.1 structure and are easy to
extend — add rows here and the whole pipeline picks them up.
"""
from __future__ import annotations

from ..schemas import Indicator

INDICATORS: list[Indicator] = [
    # ───────────── Pillar 6 — cross-border data policies ─────────────
    Indicator(
        indicator_id="P6-I1",
        pillar=6,
        title="Cross-border data transfer — general permission",
        description="Whether law permits cross-border transfer of personal data subject to conditions.",
        legal_test=(
            "A binding national provision that expressly ALLOWS transfer of personal data outside "
            "the jurisdiction (with or without conditions). Mere mention of 'data' or 'transfer' "
            "without a permissive legal rule does NOT satisfy this."
        ),
        scope="national",
        query_terms=["transfer of personal data outside", "cross-border", "overseas recipient", "comparable protection"],
    ),
    Indicator(
        indicator_id="P6-I2",
        pillar=6,
        title="Cross-border transfer — accountability / adequacy condition",
        description="Conditions imposed on transfer (comparable protection, consent, contractual safeguards).",
        legal_test=(
            "A national provision that imposes a CONDITION on outbound transfer — e.g. the recipient "
            "must provide a comparable standard of protection, or transfer requires consent / contract. "
            "Must be a binding condition, not guidance."
        ),
        scope="national",
        query_terms=["comparable standard of protection", "prescribed conditions", "transfer limitation", "binding corporate rules"],
    ),
    Indicator(
        indicator_id="P6-I3",
        pillar=6,
        title="Data localisation requirement",
        description="Whether certain data must be stored/processed domestically.",
        legal_test=(
            "A national provision REQUIRING that data be stored or processed within the country "
            "(localisation). Sector-specific localisation should be flagged as sectoral scope, not national."
        ),
        scope="national",
        query_terms=["stored in", "retained within", "data localisation", "kept in the country", "local storage"],
    ),
    # ───────────── Pillar 7 — data protection & cybersecurity ─────────────
    Indicator(
        indicator_id="P7-I1",
        pillar=7,
        title="Comprehensive personal data protection law",
        description="Existence of a national personal data protection statute.",
        legal_test=(
            "A national, economy-wide statute governing collection/use/disclosure of personal data "
            "(e.g. PDPA / Privacy Act). A sectoral instrument (banking, health) does NOT satisfy a "
            "NATIONAL-scope indicator — flag scope mismatch."
        ),
        scope="national",
        query_terms=["personal data protection act", "privacy act", "protection of personal data", "data protection"],
    ),
    Indicator(
        indicator_id="P7-I2",
        pillar=7,
        title="Consent / lawful basis for processing",
        description="Requirement of consent or another lawful basis to process personal data.",
        legal_test=(
            "A binding provision requiring consent (or specifying lawful bases) before collecting or "
            "using personal data. Must state the obligation, not merely define 'consent'."
        ),
        scope="national",
        query_terms=["consent of the individual", "shall not collect", "lawful basis", "purpose limitation"],
    ),
    Indicator(
        indicator_id="P7-I3",
        pillar=7,
        title="Security safeguards obligation",
        description="Obligation to protect personal data with reasonable security arrangements.",
        legal_test=(
            "A binding provision requiring organisations to make reasonable security arrangements to "
            "protect personal data. Sector cybersecurity notices satisfy a SECTORAL indicator only."
        ),
        scope="national",
        query_terms=["reasonable security arrangements", "protect personal data", "security safeguards", "technical and organisational measures"],
    ),
    Indicator(
        indicator_id="P7-I4",
        pillar=7,
        title="Data breach notification",
        description="Mandatory notification of data breaches to a regulator and/or affected individuals.",
        legal_test=(
            "A binding provision requiring notification of a data breach to a regulator and/or affected "
            "individuals within a stated trigger/timeframe."
        ),
        scope="national",
        query_terms=["notify the Commission", "data breach notification", "notifiable data breach", "notify affected individuals"],
    ),
    Indicator(
        indicator_id="P7-I5",
        pillar=7,
        title="National cybersecurity framework",
        description="A national-level cybersecurity law/framework (e.g. critical information infrastructure).",
        legal_test=(
            "A national cybersecurity statute/framework (e.g. a Cybersecurity Act covering critical "
            "information infrastructure). IMPORTANT: a financial-sector cybersecurity notice (e.g. MAS "
            "Notice 655) is SECTORAL and must NOT be mapped here as a national framework."
        ),
        scope="national",
        query_terms=["cybersecurity act", "critical information infrastructure", "national cybersecurity", "computer misuse"],
    ),
]


def get_indicators(pillar: int | None = None) -> list[Indicator]:
    if pillar is None:
        return list(INDICATORS)
    return [i for i in INDICATORS if i.pillar == pillar]


def get_indicator(indicator_id: str) -> Indicator | None:
    return next((i for i in INDICATORS if i.indicator_id == indicator_id), None)
