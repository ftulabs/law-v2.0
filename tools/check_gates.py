"""Measure a candidate indicator gate against the panel's own rows before it ships.

    python tools/check_gates.py --indicator P7-I3

Every gate in `backend/rdtii/indicators.py` carries the claim "this gate costs the answer key
nothing". Until now that was established by reading. A gate is only worth shipping if it
refuses rows an independent auditor refused WITHOUT refusing rows the panel itself cites, and
PROJECT_STATE records what happens when only the first half is measured: the reverted P7-I1
tightening cut 14% of rows and recovered nothing.

Only the mechanically checkable core of a gate can be screened here — "a period must be
stated" can be, "this provision operates the framework rather than constituting it" cannot.
Screening is therefore a cheap first filter, not a substitute for `tools/replay_grade.py`.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.provision_scorecard import _norm, _same_provision      # noqa: E402

AUDIT_JSON = "logs/audit_after_20260831.json"
EXPORT_GLOB = "outputs/after_fixes/*_P67_*.json"

_UNIT = r"(?:year|month|week|day|hour)s?"
_NUMWORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|"
            r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)")
_DURATION = re.compile(rf"(?:\d+|{_NUMWORD})(?:[\s\-]+(?:{_NUMWORD}|and|\d+))*\s+{_UNIT}\b", re.I)
_CEILING = re.compile(r"not\s+exceed|no\s+longer\s+than|maximum\s+(?:period|length|duration|"
                      r"retention)|cease\s+to\s+retain|must\s+(?:be\s+)?destroy", re.I)


def _unreadable(text: str) -> bool:
    """A gate worded in English must fail OPEN on a script it cannot read, exactly as
    `confidence.topical_grounded` does — otherwise every Chinese and Mongolian row is
    refused for being unreadable rather than for being wrong."""
    t = (text or "").strip()
    return bool(t) and sum(c.isascii() for c in t) / len(t) < 0.5


def has_duration(snippet: str) -> bool:
    """P7-I3 gate A: an explicit period must appear in the provision itself."""
    if not snippet or _unreadable(snippet):
        return True
    return bool(_DURATION.search(snippet))


_PENALTY = re.compile(r"\b(?:fine|imprisonment|penalty|convict|offence|offense|liable)\b", re.I)


def is_retention_ceiling(snippet: str) -> bool:
    """P7-I3 gate D: a maximum or a destruction duty is the opposite of a minimum.

    The ceiling wording has to govern the RETENTION. Nearly every statute ends in "a fine not
    exceeding $10,000 or imprisonment for a term not exceeding 12 months", and reading that as
    a retention ceiling refused two of the panel's own rows on 2026-09-06.
    """
    if not snippet or _unreadable(snippet):
        return False
    for m in _CEILING.finditer(snippet):
        window = snippet[max(0, m.start() - 90):m.end() + 90]
        if _PENALTY.search(window):
            continue
        if _RETAIN.search(window) or _RETENTION_PERIOD.search(window):
            return True
    return False


_OBLIGATION = re.compile(r"\b(?:must|shall|is required to|are required to)\b", re.I)
_RETAIN = re.compile(r"\b(?:keep|kept|keeping|retain|retained|retention|preserve|preserved|"
                     r"maintain|maintained|store|stored)\b", re.I)
_PRESCRIBED = re.compile(r"\b(?:period prescribed|prescribed period|period specified|"
                         r"specified period|record retention period|"
                         r"such period as may be prescribed)\b", re.I)


_RETENTION_PERIOD = re.compile(r"\bretention period\b", re.I)


def states_retention_period(snippet: str) -> bool:
    """P7-I3 gate A, refined after measurement.

    A literal duration is NOT required: the panel scores SG Employment Act s.95 ("must make,
    and keep for the period prescribed") under 7.3. What separates it from the refused SG
    Telecommunications Act s.52 is who is bound — s.95 puts a retention DUTY on the record
    holder and delegates only its length, while s.52 grants the regulator a POWER to create
    such a duty later.
    """
    if not snippet or _unreadable(snippet):
        return True
    has_period = bool(_DURATION.search(snippet) or _PRESCRIBED.search(snippet))
    # A modal is the usual carrier of the duty, but not the only one: AU Privacy Act s.20X
    # sets credit-information retention periods in a TABLE and says "must" nowhere.
    duty = ((_OBLIGATION.search(snippet) and _RETAIN.search(snippet))
            or _RETENTION_PERIOD.search(snippet))
    return bool(duty and has_period)


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def evaluate_gate(rows: list[dict], predicate) -> dict:
    """`predicate(snippet) -> True` means the gate ALLOWS the row through."""
    report = {k: 0 for k in ("control_total", "control_harmed", "refused_total",
                             "refused_caught", "upheld_total", "upheld_harmed")}
    for r in rows:
        allowed = predicate(r.get("snippet", ""))
        if r.get("kind") == "panel-confirmed":
            report["control_total"] += 1
            report["control_harmed"] += not allowed
        elif _truthy(r.get("satisfies")):
            report["upheld_total"] += 1
            report["upheld_harmed"] += not allowed
        else:
            report["refused_total"] += 1
            report["refused_caught"] += not allowed
    return report


def _law_matches(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    return bool(x and y and (x in y or y in x or x[:24] == y[:24]))


def load_rows(indicator: str, audit_json: str = AUDIT_JSON,
              export_glob: str = EXPORT_GLOB) -> list[dict]:
    """Audit verdicts joined to the snippet each verdict was passed on."""
    exported: dict[str, list[dict]] = {}
    for path in glob.glob(export_glob):
        econ = os.path.basename(path)[:2]
        with open(path, encoding="utf-8") as fh:
            exported[econ] = [m for m in json.load(fh).get("mappings", [])
                              if m.get("verbatim_snippet")]
    with open(audit_json, encoding="utf-8") as fh:
        audit = json.load(fh)["rows"]

    out, unmatched = [], 0
    for r in audit:
        if r["indicator"] != indicator:
            continue
        hit = next((c for c in exported.get(r["economy"], [])
                    if c["indicator_id"] == r["indicator"]
                    and _same_provision(r["section"], c.get("article_section", ""))
                    and _law_matches(r["law"], c.get("law_name", ""))), None)
        if hit is None:
            unmatched += 1
            continue
        out.append({**r, "snippet": hit["verbatim_snippet"]})
    if unmatched:
        print(f"  warning: {unmatched} audited rows could not be joined to a snippet")
    return out


GATES = {
    # P7-I5 has NO gate, and that is a measured result. Reading the 19 refusals suggested two
    # rules — the object reached must be personal data, and procedural machinery is not the
    # power itself. Both are refuted by the panel's own rows: "the object must be PERSONAL
    # DATA" refuses 19 of its 24 (SG CPC s.39 "Power to access computer", AU DAT Act s.104
    # "Power to require information and documents" — none says "personal data"), and TIA s.110
    # "agencies may APPLY for stored communications warrants" is a panel row of exactly the
    # procedural shape. The panel's test is a state power to COMPEL access to information held
    # by others. The auditor's refusals there are stricter than the scoring authority, so
    # P7-I5's measured 60% precision is itself suspect.
    #
    # Gate D first measured as harming 2 of 9 control rows. That was a DETECTOR fault, not a
    # finding about the panel: both matches were penalty boilerplate ("a fine not exceeding
    # $10,000"), not retention ceilings. Scoped to the retention context it is clean.
    "P7-I3": [("A - a retention DUTY with a period", states_retention_period),
              ("D - a minimum, not a ceiling", lambda s: not is_retention_ceiling(s))],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--indicator", default="P7-I3")
    ap.add_argument("--audit", default=AUDIT_JSON)
    args = ap.parse_args()

    rows = load_rows(args.indicator, args.audit)
    print(f"{args.indicator}: {len(rows)} audited rows joined to snippets\n")
    print(f"{'gate':34}{'control harmed':>16}{'refused caught':>16}{'upheld harmed':>15}")
    for name, predicate in GATES.get(args.indicator, []):
        r = evaluate_gate(rows, predicate)
        verdict = "" if r["control_harmed"] == 0 else "   <-- REJECT THIS GATE"
        print(f"{name:34}{r['control_harmed']:>7}/{r['control_total']:<8}"
              f"{r['refused_caught']:>7}/{r['refused_total']:<8}"
              f"{r['upheld_harmed']:>7}/{r['upheld_total']:<7}{verdict}")


if __name__ == "__main__":
    main()
