"""Sweep retrieval configurations against the judges' Database.

    python tools/sweep_retrieval.py --stage shape      # candidate budget + law allocation
    python tools/sweep_retrieval.py --stage fusion     # scoring weights
    python tools/sweep_retrieval.py --stage final

Every number printed is measured on the built corpus (backend/eval/corpus_sample.py) against
labels derived from the RDTII Round-1 Database (backend/eval/ground_truth.py). `n_calls` is
the LLM cost the config would incur, so recall is never read in isolation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.eval import harness, rank_lab                      # noqa: E402
from backend.eval.rank_lab import RankConfig                    # noqa: E402

ECON = ("SG", "AU", "MY")


def _load():
    data = {}
    for e in ECON:
        provs = harness.load_provisions(e)
        data[e] = provs
        print(f"[sweep] {e}: {len(provs)} provisions from "
              f"{len({p.doc_id for p in provs})} law versions")
    return data


def warm(data) -> None:
    """Precompute the alpha-independent component scores (embedding + cross-encoder)."""
    from backend.rdtii import get_indicators
    t0 = time.perf_counter()
    for e, provs in data.items():
        for ind in get_indicators(None):
            rank_lab.components(e, ind.indicator_id, provs)
        print(f"[sweep] components ready for {e} ({time.perf_counter()-t0:.0f}s)")


def run(configs: list[RankConfig], data) -> list[dict]:
    rows = []
    for cfg in configs:
        res = harness.evaluate_all(lambda e, c=cfg: rank_lab.selector(c, e),
                                   economies=ECON, provisions_by_economy=data)
        rows.append({"config": cfg.label(), **res["overall"],
                     "per_economy": {k: {"law": v["law_recall"], "prov": v["prov_recall"]}
                                     for k, v in res["per_economy"].items()}})
        r = rows[-1]
        print(f"  {cfg.label():52} law={r['law_recall']:.3f} ({r['law_hits']:>7})  "
              f"prov={r['prov_recall']:.3f} ({r['prov_hits']:>7})  "
              f"dens={r['target_density']:.3f}  calls={r['n_calls']}")
    return rows


def stage_shape(data) -> list[RankConfig]:
    cfgs = [rank_lab.baseline_config(len(data["SG"]))]
    for k in (40, 80, 150, 300):
        for per_law in (0, 1, 3):
            cfgs.append(RankConfig(k=k, per_law_k=per_law, dense_recall_extra=max(2, k // 10),
                                   name=f"k={k} perlaw={per_law}"))
    for pre in (5, 10, 25, 50):
        for k in (80, 150, 300):
            cfgs.append(RankConfig(k=k, per_law_k=0, law_prefilter=pre,
                                   dense_recall_extra=max(2, k // 10),
                                   name=f"prefilter={pre} k={k}"))
    return cfgs


def stage_fusion(data, k: int, pre: int, per_law: int = 1) -> list[RankConfig]:
    def base(**kw):
        return RankConfig(k=k, law_prefilter=pre, per_law_k=per_law,
                          dense_recall_extra=max(2, k // 10), **kw)
    cfgs = []
    for alpha in (0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0):
        cfgs.append(base(alpha=alpha, name=f"alpha={alpha}"))
    for cw in (0.0, 0.25, 0.5, 0.75, 1.0):
        cfgs.append(base(cross_weight=cw, use_cross=cw > 0, name=f"cross_w={cw}"))
    cfgs.append(base(phrase_bonus=False, name="no phrase bonus"))
    cfgs.append(base(sibling_penalty=False, name="no sibling penalty"))
    cfgs.append(base(phrase_bonus=False, sibling_penalty=False, name="no bonus, no penalty"))
    cfgs.append(RankConfig(k=k, per_law_k=per_law, dense_recall_extra=0,
                           name="no dense-recall guarantee"))
    for extra in (k // 4, k // 2):
        cfgs.append(RankConfig(k=k, per_law_k=per_law, dense_recall_extra=extra,
                               name=f"dense_extra={extra}"))
    for floor in (0.4, 0.55, 0.7):
        cfgs.append(RankConfig(k=k, per_law_k=per_law, dense_recall_extra=max(2, k // 10),
                               dense_recall_floor=floor, name=f"dense_floor={floor}"))
    return cfgs


def stage_budget(data) -> list[RankConfig]:
    """How far does more budget keep buying recall, and does the per-law guarantee still pay?"""
    cfgs = []
    for k in (300, 500, 800, 1200):
        for per_law in (0, 1, 2):
            cfgs.append(RankConfig(k=k, per_law_k=per_law, dense_recall_extra=max(2, k // 10),
                                   name=f"k={k} perlaw={per_law}"))
    return cfgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="shape",
                    choices=("shape", "fusion", "budget", "stage2", "final"))
    ap.add_argument("--k", type=int, default=150)
    ap.add_argument("--per-law", type=int, default=1)
    ap.add_argument("--prefilter", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    data = _load()
    warm(data)
    if a.stage == "shape":
        cfgs = stage_shape(data)
    elif a.stage == "fusion":
        cfgs = stage_fusion(data, a.k, a.prefilter, a.per_law)
    elif a.stage == "budget":
        cfgs = stage_budget(data)
    elif a.stage == "stage2":
        cfgs = stage_budget(data) + stage_fusion(data, a.k, a.prefilter, a.per_law)
    else:
        # Head-to-head on the corrected corpus: what ships today, the shape knobs that moved
        # the numbers, and the two candidate configurations (full budget and half budget).
        cfgs = [rank_lab.baseline_config(len(data["SG"]))]
        for k in (40, 150, 300):
            for per_law in (0, 1, 3):
                cfgs.append(RankConfig(k=k, per_law_k=per_law,
                                       dense_recall_extra=max(2, k // 10),
                                       name=f"k={k} perlaw={per_law}"))
        cfgs.append(RankConfig(k=300, per_law_k=1, alpha=0.65, cross_weight=0.5,
                               dense_recall_extra=0, name="CANDIDATE k=300 perlaw=1 a=.65"))
        cfgs.append(RankConfig(k=150, per_law_k=1, alpha=0.65, cross_weight=0.5,
                               dense_recall_extra=0, name="CANDIDATE-half k=150 perlaw=1 a=.65"))
        cfgs.append(RankConfig(k=300, per_law_k=1, alpha=0.5, cross_weight=0.5,
                               dense_recall_extra=0, name="CANDIDATE a=.50 (control)"))
    print(f"\n[sweep] {len(cfgs)} configurations\n")
    rows = run(cfgs, data)
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print("written:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
