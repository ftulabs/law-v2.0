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
CANDIDATE: dict[str, dict[str, object]] = {}
