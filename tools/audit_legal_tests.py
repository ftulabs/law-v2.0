"""Find BLIND SPOTS in the indicator definitions, by disagreement across model families.

A grader that gets a case wrong may simply be a weak model. A grader that gets it wrong the
SAME way as two unrelated models is not the problem — the definition it was given is. This
runs the frozen bake-off set through several distinct model families with the production
prompt and sorts the cases by that distinction:

    all three agree, and right     the definition works
    they split                     borderline for the models; may or may not be definitional
    MAJORITY wrong                 a shared lean; worth reading
    ALL wrong                      a definitional blind spot, and voting cannot fix it

That last row is the point of the tool. A cross-model panel (`mapping._crosscheck_rejection`)
assumes members fail INDEPENDENTLY; where they fail together, a 2-1 majority ratifies the error
instead of cancelling it. So the panel's value is bounded by exactly what this measures, and a
blind spot has to be fixed in the definition, never by another vote.

    python tools/audit_legal_tests.py
    python tools/audit_legal_tests.py --models a,b,c --out logs/audit.json

WHAT `label` MEANS, because it decides how to read every result: the bake-off set is built by
`tools/build_bakeoff_set.py`, which joins the panel's own answer key to our extracted text.
`label=True` means the panel CITES this article under this indicator — not that the measure is
restrictive. The panel records restrictiveness separately, in its Raw Score column, and it
cites the governing law even when that score is 0 ("we checked this Act; there is no ban").
Our `legal_test` asks the restrictiveness question and lets it decide whether a row exists at
all, so every score-0 citation in the key reads to us as "no provision found". Cases labelled
positive that all models reject are usually THIS, and not a reading failure.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings                                   # noqa: E402
from backend.pipeline.mapping import SYSTEM, _user_prompt             # noqa: E402
from backend.rdtii import get_indicator                               # noqa: E402
from backend.schemas import OCRMetrics, Provision                     # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "grader_bakeoff.json"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: Three DISTINCT open-weight families. Distinct lineage is the whole measurement: two models
#: from one family share their training and therefore their blind spots, so agreement between
#: them is not evidence that a definition is clear.
DEFAULT_MODELS = ("mistralai/mistral-small-3.2-24b-instruct",
                  "openai/gpt-oss-120b",
                  "qwen/qwen3-30b-a3b-instruct-2507")


def _load() -> list[dict]:
    data = json.loads(BENCH.read_text(encoding="utf-8"))
    return data.get("cases", data) if isinstance(data, dict) else data


def _provision(c: dict) -> Provision:
    return Provision(provision_id=c["id"], doc_id=c["id"], economy=c["economy"],
                     law_name=c["law_name"], article_section=c["article_section"],
                     verbatim_snippet=c["text"], source_url=c["source_url"], ocr=OCRMetrics())


def _grade(job):
    c, model = job
    user = _user_prompt(get_indicator(c["indicator_id"]), _provision(c))
    body = {"model": model, "temperature": 0, "max_tokens": settings.openrouter_max_tokens,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                 "Content-Type": "application/json"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=180).read())
        text = data["choices"][0]["message"]["content"] or "{}"
        m = re.search(r"\{.*\}", text, re.S)
        out = json.loads(m.group(0)) if m else {}
        rel = out.get("relevant")
        if rel is None:
            rel = bool(out.get("satisfies_target")) and not out.get("better_sibling")
        return c["id"], model, bool(rel), out.get("better_sibling"), (out.get("rationale") or "")
    except Exception as e:                     # noqa: BLE001 — an outage is a datum, not a crash
        return c["id"], model, "ERR", None, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="logs/legaltest_audit.json")
    ap.add_argument("--indicator", help="restrict to one indicator id")
    args = ap.parse_args()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    cases = _load()
    if args.indicator:
        cases = [c for c in cases if c["indicator_id"] == args.indicator]
    print(f"{len(cases)} cases x {len(models)} model families "
          f"({sum(1 for c in cases if c['label'])} labelled positive)\n")

    verdicts: dict = collections.defaultdict(dict)
    detail: dict = collections.defaultdict(dict)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for cid, model, rel, sibling, rationale in ex.map(_grade,
                                                          [(c, m) for c in cases for m in models]):
            verdicts[cid][model] = rel
            detail[cid][model] = {"better_sibling": sibling, "rationale": rationale}

    by = collections.defaultdict(lambda: collections.Counter())
    blind: list[dict] = []
    for c in cases:
        truth = bool(c["label"])
        got = [verdicts[c["id"]][m] for m in models if verdicts[c["id"]].get(m) != "ERR"]
        if not got:
            continue
        wrong = sum(1 for g in got if g != truth)
        b = by[c["indicator_id"]]
        b["n"] += 1
        if len(set(got)) > 1:
            b["split"] += 1
        if wrong > len(got) / 2:
            b["majority_wrong"] += 1
        if wrong == len(got):
            b["all_wrong"] += 1
            blind.append({"case": c, "detail": detail[c["id"]]})

    print(f"{'indicator':10} {'n':>4} {'split':>6} {'maj.wrong':>10} {'ALL wrong':>10}")
    for k in sorted(by):
        b = by[k]
        print(f"{k:10} {b['n']:>4} {b['split']:>6} {b['majority_wrong']:>10} {b['all_wrong']:>10}")

    covered = set(by)
    missing = {f"P{p}-I{i}" for p, n in ((6, 4), (7, 5)) for i in range(1, n + 1)} - covered
    if missing:
        print(f"\nNOT COVERED by the frozen set (unaudited): {', '.join(sorted(missing))}")

    if blind:
        print(f"\n{'=' * 78}\nBLIND SPOTS — every family wrong the same way\n")
        for item in blind:
            c = item["case"]
            print(f"  {c['indicator_id']} · {c['economy']} · {c['law_name'][:44]} "
                  f"· {c['article_section']}  (label={bool(c['label'])})")
            print(f"    {c['text'][:150].replace(chr(10), ' ')}")
            for m, d in item["detail"].items():
                print(f"      {m.split('/')[-1][:22]:22} sibling={d['better_sibling']} "
                      f":: {d['rationale'][:100]}")
            print()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"models": models,
         "per_indicator": {k: dict(v) for k, v in by.items()},
         "verdicts": {k: dict(v) for k, v in verdicts.items()},
         "detail": {k: dict(v) for k, v in detail.items()}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
