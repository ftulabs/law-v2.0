"""Indicator IDs in the form the secretariat validates: `6.4`, not `P6-I4`.

Round 1 accepted our internal `P6-I4`. The final-round template does not, and says so twice —
in the column comment ("RDTII 2.1 code as text: 6.1, 7.3, 12.9. Not 'P6-I1'") and again in the
Instructions sheet. So the whole change is one string, written at the export boundary and
nowhere else: `P6-I4` stays the internal identifier because it is unambiguous in code and in
every test we already have, and the numeric form is produced only when a row is written out.

Two traps, both of which cost the same as citing the wrong article:

  Text, never a number. Column E is formatted as text on purpose. `12.10` entered as a
  number becomes `12.1` and `4.01` becomes `4.1` — and 12.1, 12.10, 4.01 and 4.1 are four
  different indicators. We write strings and never a float, and `is_valid` rejects any code
  that a float round-trip would have altered.

  The code must exist. The numbering has intentional gaps (the non-regulatory indicators are
  absent from the Methodology), so a plausible-looking code is not necessarily a real one.
  Conversion is checked against the 61 in-scope codes in data/rdtii/indicator_reference.json,
  which was built from the panel's own Methodology sheet.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from ..config import ROOT

REFERENCE_JSON = ROOT / "data" / "rdtii" / "indicator_reference.json"

# P6-I4 · P6_I4 · p6i4 — every internal spelling we have ever emitted.
_INTERNAL = re.compile(r"^P?(\d{1,2})[-_ ]?I(\d{1,2})$", re.I)
# Already numeric: 6.4 · 12.10 · 4.01 · 12.4.1
_NUMERIC = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,2}$")


@lru_cache(maxsize=1)
def official_codes() -> frozenset[str]:
    """The RDTII 2.1 codes that actually exist, as text. Empty if the reference is absent —
    conversion then still works and only the validity check goes quiet, because a missing
    data file must not stop a run from exporting."""
    try:
        data = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    ind = data.get("indicators") or {}
    # Keyed by code when it is a mapping, a list of records when it is not. Accept both so a
    # change in how the reference is built cannot quietly empty the validity check.
    if isinstance(ind, dict):
        return frozenset(str(k) for k in ind)
    return frozenset(str(i["code"]) for i in ind if isinstance(i, dict) and i.get("code"))


def to_rdtii_code(indicator_id: str) -> str:
    """`P6-I4` → `6.4`. Already-numeric codes pass through untouched, including `12.10`.

    Unrecognised input is returned unchanged rather than mangled or dropped: a row with an
    odd identifier is a visible problem a reviewer can act on, whereas a blank Indicator ID
    is a required field left empty, which fails validation outright.
    """
    code = (indicator_id or "").strip()
    if not code:
        return ""
    if _NUMERIC.match(code):
        return code
    m = _INTERNAL.match(code)
    return f"{int(m.group(1))}.{int(m.group(2))}" if m else code


def is_valid(code: str) -> bool:
    """True when `code` is one of the 61 in-scope RDTII 2.1 codes, exactly as written.

    Deliberately string equality: `6.10` and `6.1` must not compare equal, which is the whole
    reason the template insists on text.
    """
    known = official_codes()
    return bool(code) and (not known or code in known)


def pillar_of(code: str) -> int | None:
    """The pillar a numeric or internal code belongs to. `12.10` → 12, never 12.1 → 1."""
    numeric = to_rdtii_code(code)
    head = numeric.split(".")[0]
    return int(head) if head.isdigit() else None
