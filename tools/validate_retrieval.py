"""End-to-end check that the SHIPPED retrieval path reproduces the swept result.

tools/sweep_retrieval.py measures a parameterised re-implementation (backend/eval/rank_lab.py).
That is what makes sweeping possible, but it also means the winning numbers are only real if
the production code — `retrieval.retrieve` + `mapping._diverse_shortlist`, driven by
`settings` — behaves identically. This runs the real functions over the same corpus and the
same labels, so a divergence shows up as a number, not a surprise in production.

    python tools/validate_retrieval.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                       # noqa: E402
from backend.eval import harness                          # noqa: E402
from backend.pipeline.mapping import _diverse_shortlist   # noqa: E402


def effective_top_k(n: int) -> int:
    """The shortlist size map_provisions computes for a corpus of n provisions."""
    return min(n, settings.retrieve_max_top_k,
               max(settings.retrieve_top_k, math.ceil(n * settings.retrieve_fraction)))


def main() -> int:
    out = {}
    for econ in ("SG", "AU", "MY"):
        provisions = harness.load_provisions(econ)
        k = effective_top_k(len(provisions))

        def sel(indicator_id, provs, k=k):
            return _diverse_shortlist(indicator_id, provs, k,
                                      settings.retrieve_per_law_k, log=lambda m: None)

        rep = harness.evaluate(econ, sel, provisions)
        out[econ] = {"provisions": len(provisions), "shortlist_k": k, **rep.summary()}
        print(f"{econ}: n={len(provisions)} k={k} -> {json.dumps(out[econ])}")

    rows = []
    for econ in out:
        rows.append(out[econ])
    print("\nsettings in force:", json.dumps({
        "hybrid_alpha": settings.hybrid_alpha,
        "retrieve_top_k": settings.retrieve_top_k,
        "retrieve_max_top_k": settings.retrieve_max_top_k,
        "retrieve_fraction": settings.retrieve_fraction,
        "retrieve_per_law_k": settings.retrieve_per_law_k,
        "dense_recall_extra": settings.dense_recall_extra,
        "cross_encoder": settings.cross_encoder,
    }, indent=1))
    Path("logs/validate_retrieval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
