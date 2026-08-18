"""E0 characterisation + E1 depth sweep. Offline, no LLM.

    python tools/sweep_depth.py --stage both --out logs/sweep_depth.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from backend.eval import depth_lab, harness, rank_lab, trace          # noqa: E402
from backend.eval.depth_lab import DepthConfig                        # noqa: E402
from backend.rdtii import get_indicators                              # noqa: E402

ECON = ("SG", "AU", "MY")
BASE = rank_lab.RankConfig(alpha=0.65, cross_weight=0.5, dense_recall_extra=0)


def load_state():
    targets = trace.build_targets()
    trace.trace_corpus(targets)
    data, v2l = {}, {}
    for e in ECON:
        data[e] = harness.load_provisions(e)
        v2l[e] = harness.version_law_map(e)
        print(f"[load] {e}: {len(data[e])} provisions")
    return targets, data, v2l


def warm(data):
    t0 = time.perf_counter()
    for e, provs in data.items():
        for ind in get_indicators(None):
            rank_lab.components(e, ind.indicator_id, provs)
        print(f"[warm] {e} ready ({time.perf_counter() - t0:.0f}s)")


def eval_config(cfg, targets, data, v2l):
    live = [t for t in targets if not t.lost_at]
    by_ei = defaultdict(list)
    for t in live:
        by_ei[(t.economy, t.indicator_id)].append(t)

    calls = added_total = added_useful = 0
    results = {}
    for econ in ECON:
        provs = data[econ]
        pid_index = {p.provision_id: i for i, p in enumerate(provs)}
        for ind in get_indicators(None):
            key = (econ, ind.indicator_id)
            chosen, added = depth_lab.shortlist(ind.indicator_id, provs, cfg, econ)
            calls += len(chosen)
            chosen_set = set(chosen)
            target_laws = {t.law_id for t in by_ei.get(key, [])}
            for i in added:
                added_total += 1
                if v2l[econ].get(provs[i].doc_id) in target_laws:
                    added_useful += 1
            for t in by_ei.get(key, []):
                idx = pid_index.get(t.matched_provision_id)
                hit = idx is not None and idx in chosen_set
                if not hit and not t.sections:
                    hit = any(v2l[econ].get(provs[i].doc_id) == t.law_id for i in chosen)
                results[id(t)] = hit

    def rate(ts):
        if not ts:
            return 0.0, "0/0"
        n = sum(1 for t in ts if results.get(id(t)))
        return round(n / len(ts), 3), f"{n}/{len(ts)}"

    acts = [t for t in live if trace.is_statute(t.collection)]
    r_act, s_act = rate(acts)
    r_all, s_all = rate(live)
    return {"config": cfg.label(), "act_recall": r_act, "act_hits": s_act,
            "all_recall": r_all, "all_hits": s_all, "calls": calls, "added": added_total,
            "added_useful_pct": round(added_useful / added_total, 3) if added_total else None}


def _scores(econ, indicator_id, provs):
    comp = rank_lab.components(econ, indicator_id, provs)
    return rank_lab.fuse(comp, BASE)


def stage_e0(targets, data, v2l):
    print("\n=== E0a: distinct laws inside the global top-300 ===")
    per_ind = []
    for econ in ECON:
        provs = data[econ]
        for ind in get_indicators(None):
            sc = _scores(econ, ind.indicator_id, provs)
            order = sorted(range(len(provs)), key=lambda i: sc[i], reverse=True)[:300]
            per_ind.append(len({provs[i].doc_id for i in order}))
    print(f"  median={statistics.median(per_ind):.0f} min={min(per_ind)} max={max(per_ind)} "
          f"p90={sorted(per_ind)[int(.9 * len(per_ind))]}")

    print("\n=== E0b: absolute global rank of targets the flat top-300 misses ===")
    live = [t for t in targets if not t.lost_at]
    ranks = []
    for econ in ECON:
        provs = data[econ]
        pid_index = {p.provision_id: i for i, p in enumerate(provs)}
        for ind in get_indicators(None):
            ts = [t for t in live if t.economy == econ
                  and t.indicator_id == ind.indicator_id and t.matched_provision_id]
            if not ts:
                continue
            sc = _scores(econ, ind.indicator_id, provs)
            order = sorted(range(len(provs)), key=lambda i: sc[i], reverse=True)
            pos = {idx: r + 1 for r, idx in enumerate(order)}
            for t in ts:
                idx = pid_index.get(t.matched_provision_id)
                if idx is not None and pos[idx] > 300:
                    ranks.append([pos[idx], t.economy, t.indicator_id, t.law_label[:34],
                                  t.primary_section, trace.is_statute(t.collection)])
    ranks.sort(key=lambda r: r[0])
    print(f"  {len(ranks)} targets rank beyond 300")
    for r, e, i, law, sec, act in ranks:
        print(f"    rank {r:6}  {e} {i}  {'ACT    ' if act else 'non-act'} {law:34} s{sec}")
    rr = [r[0] for r in ranks]
    ra = [r[0] for r in ranks if r[5]]
    for cut in (450, 600, 900, 1500, 3000):
        print(f"    flat K={cut}: recovers {sum(1 for r in rr if r <= cut)}/{len(rr)} "
              f"(acts {sum(1 for r in ra if r <= cut)}/{len(ra)})")
    return ranks


def stage_e1b(targets, data, v2l):
    """Focused: locate the flat-K knee, and test whether anything adds to it."""
    cfgs = [DepthConfig(k=300, name="BASELINE flat K=300 (production)")]
    for k in (330, 360, 400, 425, 450, 475, 500):
        cfgs.append(DepthConfig(k=k))
    cfgs.append(DepthConfig(k=450, neighbours=1, name="flat K=450 + adjacent +/-1"))
    cfgs.append(DepthConfig(k=450, law_score="count_topk", n_laws=10, m_per_law=10,
                            name="flat K=450 + A(count_topk,N10,m10)"))
    rows = []
    print("E1b: %d configurations" % len(cfgs))
    print(f"{'config':50} {'ACT':>14} {'ALL':>14} {'calls':>7} {'added':>6} {'useful':>7}")
    for cfg in cfgs:
        r = eval_config(cfg, targets, data, v2l)
        rows.append(r)
        print(f"{r['config'][:50]:50} {r['act_recall']:5.3f} {r['act_hits']:>8} "
              f"{r['all_recall']:5.3f} {r['all_hits']:>8} {r['calls']:7} {r['added']:6} "
              f"{str(r['added_useful_pct']):>7}")
    return rows


def stage_e1(targets, data, v2l):
    cfgs = [DepthConfig(k=300, name="BASELINE flat K=300 (production)")]
    for k in (450, 600, 900):
        cfgs.append(DepthConfig(k=k))
    for score in ("max", "mean_top3", "sum_top5", "count_topk"):
        for n in (10, 20, 40):
            for m in (10, 20):
                cfgs.append(DepthConfig(k=300, law_score=score, n_laws=n, m_per_law=m))
    cfgs.append(DepthConfig(k=300, law_score="mean_top3", n_laws=20, m_per_law=10, adaptive=True))
    cfgs.append(DepthConfig(k=300, law_score="count_topk", n_laws=20, m_per_law=10, adaptive=True))
    cfgs.append(DepthConfig(k=300, neighbours=2, name="D: adjacent sections +/-2"))
    cfgs.append(DepthConfig(k=300, law_score="mean_top3", n_laws=20, m_per_law=10,
                            neighbours=2, name="A(mean_top3,N20,m10) + D"))
    rows = []
    print(f"\n=== E1: {len(cfgs)} configurations ===")
    hdr = f"{'config':50} {'ACT':>14} {'ALL':>14} {'calls':>7} {'added':>6} {'useful':>7}"
    print(hdr)
    for cfg in cfgs:
        r = eval_config(cfg, targets, data, v2l)
        rows.append(r)
        print(f"{r['config'][:50]:50} {r['act_recall']:5.3f} {r['act_hits']:>8} "
              f"{r['all_recall']:5.3f} {r['all_hits']:>8} {r['calls']:7} {r['added']:6} "
              f"{str(r['added_useful_pct']):>7}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="both", choices=("e0", "e1", "e1b", "both"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    targets, data, v2l = load_state()
    warm(data)
    out = {}
    if a.stage in ("e0", "both"):
        out["e0"] = stage_e0(targets, data, v2l)
    if a.stage in ("e1", "both"):
        out["e1"] = stage_e1(targets, data, v2l)
    if a.stage == "e1b":
        out["e1b"] = stage_e1b(targets, data, v2l)
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print("\nwritten:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
