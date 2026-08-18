"""E3: does raising the shortlist from 300 to 450 cost precision, or only money?

Grades a random sample of the candidates that K=450 ADDS over K=300 and reports how often the
grader accepts them. Two readings matter:

  * acceptance near zero  -> the extra budget buys recall and costs only money;
  * meaningful acceptance -> either we are finding evidence the panel missed (a project goal)
    or we are manufacturing false positives, and the sample must be read by hand to tell which.

`target_density` cannot separate those two, which is why this exists.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from backend.eval import depth_lab, harness, rank_lab                 # noqa: E402
from backend.eval.depth_lab import DepthConfig                        # noqa: E402
from backend.eval.grader_eval import _cost                            # noqa: E402
from backend.rdtii import get_indicator, get_indicators                # noqa: E402

ECON = ("SG", "AU", "MY")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--out", default="logs/e3_precision.json")
    a = ap.parse_args()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    from backend.config import settings
    from backend.pipeline.mapping import SYSTEM, _user_prompt
    from backend.providers import get_llm_provider
    from backend.schemas import Provision

    added_pool = []
    for econ in ECON:
        provs = harness.load_provisions(econ)
        for ind in get_indicators(None):
            lo, _ = depth_lab.shortlist(ind.indicator_id, provs, DepthConfig(k=300), econ)
            hi, _ = depth_lab.shortlist(ind.indicator_id, provs, DepthConfig(k=450), econ)
            extra = [i for i in hi if i not in set(lo)]
            for i in extra:
                added_pool.append((econ, ind.indicator_id, provs[i]))
        print(f"[e3] {econ}: pool now {len(added_pool)}")
    print(f"[e3] total candidates added by K=300 -> K=450: {len(added_pool)}")

    rnd = random.Random(20260819)
    sample = rnd.sample(added_pool, min(a.sample, len(added_pool)))
    llm = get_llm_provider()
    model = getattr(llm, "model_version", "") or settings.openrouter_model
    spend = {"usd": 0.0, "calls": 0}
    stop = {"flag": False}

    def _one(item):
        econ, ind_id, prov = item
        if stop["flag"]:
            return None
        ind = get_indicator(ind_id)
        p = Provision(provision_id=prov.provision_id, doc_id="e3", economy=econ,
                      law_name=prov.law_name, article_section=prov.article_section,
                      verbatim_snippet=prov.verbatim_snippet, source_url="")
        try:
            out = llm.complete_json(SYSTEM, _user_prompt(ind, p))
        except Exception as e:  # noqa: BLE001
            return {"economy": econ, "indicator": ind_id, "error": str(e)[:120]}
        return {"economy": econ, "indicator": ind_id, "law": prov.law_name[:70],
                "section": prov.article_section, "accepted": bool(out.get("satisfied")),
                "legal_match": out.get("legal_match"),
                "rationale": str(out.get("rationale") or "")[:300],
                "text": prov.verbatim_snippet[:300]}

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_one, it) for it in sample]):
            r = fut.result()
            if r is None:
                continue
            results.append(r)
            spend["calls"] += 1
            spend["usd"] += _cost(model, 2000, 3000)
            if spend["usd"] >= a.budget * 0.95:
                stop["flag"] = True
            if spend["calls"] % 50 == 0:
                print(f"[e3] {spend['calls']} calls, ~${spend['usd']:.2f}")

    ok = [r for r in results if "error" not in r]
    acc = [r for r in ok if r["accepted"]]
    print(f"\n=== E3 ===")
    print(f"graded {len(ok)} of the {len(added_pool)} added candidates "
          f"(errors {len(results)-len(ok)}), spend ~${spend['usd']:.2f}")
    print(f"ACCEPTED: {len(acc)}/{len(ok)} = {len(acc)/max(len(ok),1):.3f}")
    print("accepted by indicator:", dict(Counter(r["indicator"] for r in acc)))
    print("\n--- accepted samples for manual classification ---")
    for r in acc[:20]:
        print(f"\n[{r['economy']} {r['indicator']}] {r['law'][:52]} {r['section']}")
        print(f"  legal_match={r['legal_match']} :: {r['rationale'][:180]}")
        print(f"  text: {r['text'][:160]!r}")
    Path(a.out).write_text(json.dumps({"spend": spend, "pool": len(added_pool),
                                       "results": results}, indent=1, ensure_ascii=False),
                           encoding="utf-8")
    print("\nwritten:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
