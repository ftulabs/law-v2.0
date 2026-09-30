"""Split a grading call's cost into prefill and decode, on the V100 host.

Each request carries a unique nonce so vLLM's prefix cache (77.7% hit rate) cannot serve it —
otherwise this measures the cache, which is the error that made the first concurrency sweep
fiction. Sequential, one call at a time: this asks how fast ONE call is, not how many fit.
"""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.pipeline import discovery, extraction, mapping
from backend.pipeline.ocr import get_document_text
from backend.rdtii import get_indicators
from backend.schemas import Economy

import os
URL = os.environ.get("VT_BENCH_URL", "http://127.0.0.1:18082/v1") .rstrip("/") + "/chat/completions"
M = os.environ.get("VT_BENCH_MODEL", "Qwen3.6-35B-A3B")
d = discovery.discover_from_samples(Economy.SG, pillar=6)[0]
raw, o = get_document_text(d)
p = [x for x in extraction.extract_provisions(d, raw, o) if x.article_section == "Section 26"][0]
ind = {i.indicator_id: i for i in get_indicators(6)}["P6-I4"]
USER = mapping._user_prompt(ind, p)

def call(system, user, max_tok, timeout=300):
    body = {"model": M, "temperature": 0, "max_tokens": max_tok,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    r = urllib.request.Request(URL, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        j = json.load(resp)
    return time.perf_counter() - t, j["usage"]

n = [0]
def nonce(s):
    n[0] += 1
    return s + f"\n<!-- unique {time.time_ns()} {n[0]} -->"

print(f"{'what':34} {'sec':>7} {'in':>7} {'out':>6} {'note'}")
rows = {}
for label, mt in [("full prompt, 1 output token", 1),
                  ("full prompt, 32 output", 32),
                  ("full prompt, 128 output", 128)]:
    ds = []
    for _ in range(3):
        dt, u = call(mapping.SYSTEM, nonce(USER), mt)
        ds.append(dt)
    dt = sum(ds) / len(ds)
    rows[mt] = dt
    print(f"{label:34} {dt:>7.2f} {u['prompt_tokens']:>7,} {u['completion_tokens']:>6}")

ds = []
for _ in range(3):
    dt, u = call("Answer in JSON.", nonce("Reply {\"ok\":true} only."), 32)
    ds.append(dt)
tiny = sum(ds) / len(ds)
print(f"{'tiny prompt, 32 output':34} {tiny:>7.2f} {u['prompt_tokens']:>7,} "
      f"{u['completion_tokens']:>6}")

print()
prefill = rows[1]
per_tok = (rows[128] - rows[32]) / 96
print(f"prefill of ~3,900 tokens (uncached) : {prefill:.2f}s")
print(f"decode, per output token           : {per_tok*1000:.0f} ms  "
      f"({1/per_tok:.1f} tok/s single stream)")
print(f"a real 152-token answer            : prefill {prefill:.2f}s "
      f"+ decode {per_tok*152:.2f}s = {prefill + per_tok*152:.2f}s")
