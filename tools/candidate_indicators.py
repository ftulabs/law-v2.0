"""Staging area for a proposed indicator-definition change, so it can be measured before it ships.

`tools/replay_grade.py --variant candidate` applies whatever is in CANDIDATE on top of the
shipped definitions and re-grades rows we already exported. Put the proposed text here, measure,
and only then edit `backend/rdtii/indicators.py`. CANDIDATE is empty between changes — an empty
dict makes `--variant candidate` a no-op, which is the correct reading of "nothing is proposed".

The workflow this file exists to enforce:

  1. Read the rows an independent auditor refused (`logs/audit_*.json`), and group them by WHY.
     Not by indicator, and not by a hypothesis — the P7-I1 tightening of 2026-08-30 was written
     from a hypothesis, cost forty minutes of live re-runs, recovered nothing and was reverted.
  2. Write the gate against a group you actually read, and say in the comment which rows it is
     aimed at.
  3. `replay_grade.py --variant baseline` then `--variant candidate`. Ship only if CONTROL (the
     panel's own rows) is untouched, UPHELD is untouched, and REJECTED falls.
  4. Copy the text into `backend/rdtii/indicators.py` with the comment, empty this dict, and add
     the gate to `tests/test_localisation_gates.py`.

Worked example, kept because the numbers are the argument for the process: the 2026-08-31
localisation gates (P6-I1 "what is restricted must be data", P6-I2 "a location must be named",
P6-I3 "physical infrastructure must be named and located") were staged here and measured over
107 exported rows. CONTROL 11/11 held, UPHELD 8/8 held, and auditor-REJECTED rows dropped from
4 to 14 of 24 — reproduced exactly on a second independent sampling. They then shipped.
"""
from __future__ import annotations

#: {indicator_id: {field: value}} — e.g. {"P6-I2": {"legal_test": "…"}}. Empty when nothing is
#: staged. Fields are whatever `backend.schemas.Indicator` declares (legal_test, query_terms…).
CANDIDATE: dict[str, dict[str, object]] = {
    # Staged 2026-09-06. Two gates for P7-I3, the worst indicator we file (the
    # 2026-08-31 audit upheld 13 of our 47 against 7 of the panel's 9). Written against
    # groups read in logs/audit_after_20260831.json: a period governing something other
    # than retention (SG Income Tax s.13G(16), MY Income Tax s.11), a record-keeping duty
    # naming no period (MY Companies s.190(4), IN CGST s.35), a power to make regulations
    # about retention (SG Telecom s.52), and a ceiling read as a floor (IN PMLA s.20).
    # Pre-screened by tools/check_gates.py: 22 of 34 refusals caught, 0 of 9 panel rows
    # and 0 of 13 upheld rows harmed.
    "P7-I3": {"legal_test": "The operative rule mandates a MINIMUM RETENTION DURATION — data, records or information must be kept for AT LEAST a stated period ('keep for not less than N years'; e.g. business e-commerce records kept 6 years). It is NOT the same as 'do not keep data longer than necessary' (a purpose-/storage-limitation rule) — that is the OPPOSITE and does NOT satisfy this indicator. Distinguish from P6-I2 (WHERE data is stored, not how long). (RDTII exception: retention applied only to GOVERNMENT data is out of scope.) A RETENTION DUTY AND A PERIOD MUST BOTH BE PRESENT. Quote a duty to keep, retain or preserve the data or records, AND the period it must be kept for. The period may be stated outright ('not less than 5 years'), may be expressly left to be prescribed ('keep for the period prescribed' — this DOES satisfy, the duty is here and only its length is elsewhere), and may be set in a table rather than a sentence. What does NOT satisfy: a power to MAKE REGULATIONS about retention, which creates the duty somewhere else and not here; a record-keeping, production or lodgement duty that names no period at all, however detailed; a provision that merely defines a retention term; and a period that governs anything other than how long the data is kept — a registration, a tax exemption, an allowance, a filing or accounting deadline, a period of business continuity, the circulation of a report. If you cannot quote both halves, answer false. A CEILING IS NOT A MINIMUM. A maximum period, a duty to destroy, or a duty to CEASE retaining sets an upper bound and does not satisfy this indicator, which asks for a floor. Read the ceiling in its context: 'a fine not exceeding $10,000' and 'imprisonment for a term not exceeding 12 months' are PENALTY wording and say nothing about retention — a provision is only disqualified when the ceiling governs how long the data itself may be kept."},
}

