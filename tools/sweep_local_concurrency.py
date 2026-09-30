#!/usr/bin/env python3
"""Measure the grading-call concurrency curve of a self-hosted endpoint.

`LocalLLM.suggested_concurrency` carries a measured table for the 13-node CPU cluster. A
vLLM server is a different shape — its ceiling is `max_num_seqs`, not a node count — so it
needs its own measurement rather than the CPU cluster's number.

Sends REAL grading prompts — and a DIFFERENT provision on every call, which is the whole
methodology. The first version of this tool sent one identical request N times and reported
429 calls/min at 64 threads; the real pipeline then managed 125 calls/min at the same setting.
The gap was not noise. vLLM's prefix cache was serving the entire repeated prompt (measured
77.7% hit rate on this server), so the sweep was timing a cache, not the model. A concurrency
number taken from identical prompts will always be too optimistic, and the error grows with
the shared prefix — which here is 64% of the prompt by design.

    python tools/sweep_local_concurrency.py --base-url http://127.0.0.1:18082/v1 \
        --model Qwen3.6-35B-A3B --levels 8,16,32,48,64 --calls 64

Read the FAILURE RATE column, not just throughput: a failed grading call is not free — the
mapper counts it, skips that provision, and the run loses evidence.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline import discovery, extraction, mapping            # noqa: E402
from backend.pipeline.ocr import get_document_text                     # noqa: E402
from backend.rdtii import get_indicators                               # noqa: E402
from backend.schemas import Economy                                    # noqa: E402


def sample_prompts(n: int) -> list[str]:
    """`n` DISTINCT real user prompts: every (indicator, provision) pair the sample corpus
    offers, cycled. Distinctness is the point — see the module docstring."""
    provs = []
    for pillar in (6, 7):
        for d in discovery.discover_from_samples(Economy.SG, pillar=pillar):
            raw, ocr = get_document_text(d)
            provs += extraction.extract_provisions(d, raw, ocr)
    seen, uniq = set(), []
    for p in provs:
        if p.provision_id not in seen:
            seen.add(p.provision_id)
            uniq.append(p)
    inds = get_indicators(6) + get_indicators(7)
    pairs = [mapping._user_prompt(i, p) for i in inds for p in uniq]
    if not pairs:
        raise SystemExit("no sample provisions")
    return [pairs[k % len(pairs)] for k in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18082/v1")
    ap.add_argument("--model", default="Qwen3.6-35B-A3B")
    ap.add_argument("--levels", default="8,16,32,48,64")
    ap.add_argument("--calls", type=int, default=64, help="calls per level")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    url = a.base_url.rstrip("/") + "/chat/completions"
    system = mapping.SYSTEM
    users = sample_prompts(a.calls)
    print(f"prompt: {len(system):,} char system + ~{len(users[0]):,} char user · "
          f"{len(set(users))} DISTINCT prompts · {a.calls} calls per level\n")

    def one(k):
        t = time.perf_counter()
        body = json.dumps({"model": a.model, "temperature": 0, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": users[k % len(users)]}]}).encode()
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.load(r)
            return time.perf_counter() - t, j["usage"]["completion_tokens"], None
        except Exception as e:                       # noqa: BLE001 — a failure IS the datum
            return time.perf_counter() - t, 0, type(e).__name__

    rows = []
    print(f"{'threads':>8} {'calls/min':>10} {'failed':>7} {'p50 s':>7} {'p90 s':>7} "
          f"{'max s':>7} {'out tok/s':>10}")
    for lvl in [int(x) for x in a.levels.split(",") if x.strip()]:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=lvl) as ex:
            res = list(ex.map(one, range(a.calls)))
        wall = time.perf_counter() - t0
        lat = sorted(r[0] for r in res if r[2] is None)
        fails = [r[2] for r in res if r[2] is not None]
        toks = sum(r[1] for r in res)
        ok = len(res) - len(fails)
        row = {"threads": lvl, "wall_s": round(wall, 1), "ok": ok, "failed": len(fails),
               "calls_per_min": round(ok / wall * 60, 1),
               "p50": round(lat[len(lat)//2], 2) if lat else None,
               "p90": round(lat[min(len(lat)-1, int(len(lat)*0.9))], 2) if lat else None,
               "max": round(lat[-1], 2) if lat else None,
               "out_tok_per_s": round(toks / wall, 1),
               "errors": sorted(set(fails))}
        rows.append(row)
        print(f"{lvl:>8} {row['calls_per_min']:>10.1f} "
              f"{len(fails)*100//len(res):>6}% {row['p50'] or 0:>7.2f} "
              f"{row['p90'] or 0:>7.2f} {row['max'] or 0:>7.2f} {row['out_tok_per_s']:>10.1f}"
              + (f"  {','.join(row['errors'])}" if row["errors"] else ""))

    if a.out:
        Path(a.out).write_text(json.dumps({"model": a.model, "base_url": a.base_url,
                                           "measured_on": time.strftime("%Y-%m-%d"),
                                           "levels": rows}, indent=1))
        print(f"\nwritten: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
