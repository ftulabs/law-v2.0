"""Independent second opinion on exported rows, by a DIFFERENT model, with a control group.

    python tools/audit_rows.py MN --limit 40
    python tools/audit_rows.py SG AU MY CN IN MN --model openai/gpt-oss-120b

Why this exists: across six economies the tool exports 967 distinct provisions where the panel
cites 148. Finding more than the panel is an explicit goal of the brief, so a big number is not
by itself wrong — but nobody had read a single one, and precision is criterion C2b. A thousand
rows is past what a person will check, so the check has to be mechanical.

Three things make this an audit rather than the system marking its own homework:

  A DIFFERENT MODEL. The grader is `settings.openrouter_model`; the auditor must not be, and
  the tool refuses to run if they are the same. Two samples of one model agreeing tells you
  about the sampling, not about the law.

  A DIFFERENT QUESTION. The grader is asked "does this satisfy the test?", which invites a
  yes. The auditor is asked to find the operative words and quote them, and to answer NO when
  it cannot — a provision that merely mentions the topic has nothing to quote.

  A CONTROL GROUP. Rows the PANEL itself cited are audited too, unlabelled and shuffled in with
  the rest. If the auditor rejects those at the same rate it rejects ours, it is not measuring
  our precision, it is just strict, and its verdict on the new rows means nothing. That number
  is printed first, before any conclusion is drawn from the rest.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                                  # noqa: E402
from backend.rdtii import get_indicator                              # noqa: E402
from tools.provision_scorecard import (_same_law, _same_provision,   # noqa: E402
                                       key_provisions, newest)

#: Cheap by design — this is a checking pass over a thousand rows, not the graded engine.
DEFAULT_AUDITOR = "openai/gpt-oss-120b"

SYSTEM = (
    "You are auditing one line of a legal-evidence submission. You are NOT the grader that "
    "produced it; your job is to disagree where disagreement is warranted.\n"
    "You are given an INDICATOR's legal test and a VERBATIM provision. Decide whether the "
    "provision's own operative words satisfy that test.\n"
    "Method: find the words in the provision that CREATE the obligation, permission or "
    "prohibition the test asks about, and quote them exactly. If you cannot quote such words — "
    "because the provision only mentions the topic, defines a term, states a purpose, confers "
    "an unrelated power, or is a heading — the answer is NO.\n"
    "Judge only the text given. Do not credit the provision for what the wider law probably "
    "says. Do not reject it for being short, sectoral, subordinate, or in a language other "
    "than English.\n"
    'Return ONLY JSON: {"quote": "<exact words from the provision, or empty>", '
    '"satisfies": true|false, "why": "<one sentence>"}'
)


def audit_prompt(indicator_id: str, snippet: str) -> str:
    ind = get_indicator(indicator_id)
    return (f"<INDICATOR>{indicator_id} — {ind.title}</INDICATOR>\n"
            f"<LEGAL_TEST>{ind.legal_test}</LEGAL_TEST>\n"
            f"<PROVISION>{(snippet or '')[:4000]}</PROVISION>")


def load_rows(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            law = (row.get("Law Name") or "").strip()
            if not law or "no evidence" in law.lower():
                continue
            out.append(row)
    return out


def split_rows(econ: str, path: str) -> tuple[list[dict], list[dict]]:
    """(rows the panel also cites → the control, rows only we cite → the subject)."""
    from tools.provision_scorecard import our_rows
    parsed, raw = our_rows(path), load_rows(path)
    keys = key_provisions(econ)
    confirmed = set()
    for k in keys:
        for i, r in enumerate(parsed):
            if _same_law(k, r) and _same_provision(r["section"], k["section"]) \
                    and r["indicator"] == k["indicator"]:
                confirmed.add(i)
    return ([raw[i] for i in sorted(confirmed)],
            [r for i, r in enumerate(raw) if i not in confirmed])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("economies", nargs="*", default=["SG", "AU", "MY", "CN", "IN", "MN"])
    ap.add_argument("--model", default=DEFAULT_AUDITOR)
    ap.add_argument("--limit", type=int, default=60, help="new rows sampled per economy")
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument("--out", default="logs/row_audit.json")
    ap.add_argument("--workers", type=int, default=12,
                    help="a thousand rows at ~20s a call is six hours sequential")
    a = ap.parse_args()

    if a.model == settings.openrouter_model:
        print(f"refusing: the auditor ({a.model}) is the grader. Two samples of one model "
              f"agreeing measures the sampling, not the law.")
        return 2

    from backend.providers.llm_openrouter import OpenRouterLLM
    llm = OpenRouterLLM(settings.openrouter_api_key, model=a.model)
    rnd = random.Random(a.seed)
    results, tally = [], Counter()

    for econ in [e.upper() for e in a.economies]:
        path = newest(econ)
        if not path:
            print(f"{econ}: no run found")
            continue
        control, subject = split_rows(econ, path)
        sample = rnd.sample(subject, min(a.limit, len(subject)))
        # The control is audited too, and the auditor is told nothing about which is which.
        def one(item):
            kind, row = item
            ind = (row.get("Indicator ID") or "").strip()
            ind = {f"{p}.{i}": f"P{p}-I{i}" for p in (6, 7) for i in range(1, 6)}.get(ind, ind)
            try:
                v = llm.complete_json(SYSTEM, audit_prompt(ind, row.get("Verbatim Snippet")))
            except Exception:                              # noqa: BLE001
                return (kind, None, None)
            return (kind, row, ind if v is None else (v, ind))

        work = [("panel-confirmed", r) for r in control] + [("ours-only", r) for r in sample]
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
            for kind, row, payload in pool.map(one, work):
                if row is None or not isinstance(payload, tuple):
                    tally[f"{econ}/{kind}/error"] += 1
                    continue
                v, ind = payload
                ok = bool(v.get("satisfies"))
                tally[f"{econ}/{kind}/{'yes' if ok else 'no'}"] += 1
                results.append({"economy": econ, "kind": kind, "indicator": ind,
                                "law": (row.get("Law Name") or "")[:90],
                                "section": row.get("Article / Section"),
                                "satisfies": ok, "quote": (v.get("quote") or "")[:200],
                                "why": (v.get("why") or "")[:200]})
        c_yes, c_no = tally[f"{econ}/panel-confirmed/yes"], tally[f"{econ}/panel-confirmed/no"]
        s_yes, s_no = tally[f"{econ}/ours-only/yes"], tally[f"{econ}/ours-only/no"]
        ctrl = c_yes / max(1, c_yes + c_no)
        print(f"{econ}: control (panel's own rows) upheld {c_yes}/{c_yes + c_no} = {ctrl:.0%}"
              f"   |   ours-only upheld {s_yes}/{s_yes + s_no} = "
              f"{s_yes / max(1, s_yes + s_no):.0%}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"auditor": a.model, "grader": settings.openrouter_model, "seed": a.seed,
         "tally": dict(tally), "rows": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("written:", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
