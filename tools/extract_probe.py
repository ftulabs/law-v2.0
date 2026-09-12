"""Discovery -> fetch -> extract for every economy, and a few real provisions from each.

WHAT THIS IS FOR. Zone 1 and the first half of Zone 2 can be checked without the grader, and
they should be, because every failure mode either half has is SILENT: a run with no documents,
a run whose documents are news articles, and a run whose "provisions" are a navigation menu all
produce the same complete CSV as a healthy one. This walks the real chain — the same
`discover_live`, the same `fetch_to_cache`, the same `get_document_text` and
`extraction.extract_provisions` the pipeline itself calls — and prints what came out, so the
text can be read rather than trusted.

It deliberately stops BEFORE retrieval and mapping. No LLM is called, nothing is scored, and
the columns are the submission's own minus the ones only the grader can fill.

    python tools/extract_probe.py                       # all eleven, pillar 6
    python tools/extract_probe.py --economies SG IN --pillars 6 7
    python tools/extract_probe.py --docs 3 --per-doc 2  # smaller sample, faster

Writes `outputs/extract_probe/<ECONOMY>_P<pillar>.csv` and prints a summary table. Each
economy is independent: one that times out or throws is reported as such and the rest continue,
because the point is to see all eleven in one view.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The Windows console is cp1252 and this script prints Chinese, Lao, Thai and Mongolian. A bare
# print() of any of them raises UnicodeEncodeError and takes the whole sweep down at whichever
# economy happens to be non-Latin — which is every economy this tool exists to check.
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream)
    if hasattr(_s, "buffer"):
        setattr(sys, _stream, __import__("io").TextIOWrapper(
            _s.buffer, encoding="utf-8", errors="replace", line_buffering=True))

from backend.config import settings                                    # noqa: E402
from backend.console import safe_log                                   # noqa: E402
from backend.schemas import Economy                                    # noqa: E402

#: Every economy the live test can draw from, in the order `backend/schemas.py` lists them.
ALL = ["SG", "AU", "MY", "CN", "IN", "ID", "LA", "MN", "RU", "TH", "TL"]

COLUMNS = ["Economy", "Law Name", "Law Number / Ref", "Article / Section",
           "Verbatim Snippet", "Source URL", "Language of Source", "Chars"]


def _provisions_for(economy: str, pillar: int, max_docs: int, per_doc: int, log):
    """Run the real chain and return (documents, provisions, timings)."""
    from backend.pipeline import discovery, extraction
    from backend.pipeline.fetch import fetch_to_cache
    from backend.pipeline.ocr import get_document_text

    eco = Economy(economy)
    timings: dict[str, float] = {}

    # DISCOVERY RUNS AT FULL SIZE. Passing the sample size through as `max_docs` would not
    # sample the run, it would change it: `discover_live` stops merging candidates at
    # `max_docs * 3`, so asking for four documents also throws away everything after the
    # twelfth candidate and the instrument filter then has almost nothing left to rank. China
    # came back with two documents that way. The sample is taken AFTER discovery has done its
    # real job, which is also the only way the discovered-count column means anything.
    t = time.perf_counter()
    docs = discovery.discover_live(eco, pillar, log=log)
    timings["discovery"] = time.perf_counter() - t

    t = time.perf_counter()
    kept = []
    for d in docs[:max_docs]:
        if d.local_path:
            kept.append(d)
            continue
        fetch_url, _ = discovery._resolve_pdf_url(d.economy, d.source_url)
        fr = fetch_to_cache(fetch_url, log=log)
        if not fr:
            continue
        d.local_path, d.fmt = fr.local_path, fr.fmt
        kept.append(d)
    timings["fetch"] = time.perf_counter() - t

    t = time.perf_counter()
    provisions = []
    for d in kept:
        try:
            raw, ocr_metrics = get_document_text(d, ocr_provider=None)
            provs = extraction.extract_provisions(d, raw, ocr_metrics)
        except Exception as exc:                       # noqa: BLE001 — one bad doc is not fatal
            log(f"[probe] extraction failed for {d.title[:50]}: {type(exc).__name__}: {exc}")
            continue
        provisions.extend(provs[:per_doc])
    timings["extract"] = time.perf_counter() - t
    return docs, kept, provisions, timings


def _row(p) -> dict:
    """One provision, in the submission's own column names."""
    text = (p.verbatim_snippet or "").strip()
    return {
        "Economy": p.economy.value if hasattr(p.economy, "value") else p.economy,
        "Law Name": p.law_name or "",
        "Law Number / Ref": p.law_number or "",
        "Article / Section": p.article_section or "",
        # Kept whole in the CSV — a truncated snippet cannot be checked against the source.
        "Verbatim Snippet": text,
        "Source URL": p.source_url or "",
        "Language of Source": getattr(p, "language", "") or "",
        "Chars": len(text),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economies", nargs="*", default=ALL, metavar="CODE")
    ap.add_argument("--pillars", nargs="*", type=int, default=[6], metavar="N")
    ap.add_argument("--docs", type=int, default=5,
                    help="documents to fetch and extract per economy (default 5)")
    ap.add_argument("--per-doc", type=int, default=3,
                    help="provisions to keep per document (default 3)")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "extract_probe"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []

    for code in args.economies:
        for pillar in args.pillars:
            print(f"\n{'=' * 78}\n{code} pillar {pillar}\n{'=' * 78}", flush=True)
            t0 = time.perf_counter()
            try:
                docs, kept, provs, timings = _provisions_for(
                    code, pillar, args.docs, args.per_doc, safe_log)
                err = None
            except Exception:                          # noqa: BLE001 — report and carry on
                docs = kept = provs = []
                timings = {}
                err = traceback.format_exc().strip().splitlines()[-1]

            path = out_dir / f"{code}_P{pillar}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS)
                w.writeheader()
                for p in provs:
                    w.writerow(_row(p))

            chars = [len((p.verbatim_snippet or "").strip()) for p in provs]
            summary.append({
                "economy": code, "pillar": pillar,
                "discovered": len(docs), "fetched": len(kept), "provisions": len(provs),
                "median_chars": sorted(chars)[len(chars) // 2] if chars else 0,
                "seconds": round(time.perf_counter() - t0, 1), "error": err, "csv": path,
            })
            if err:
                print(f"  ERROR: {err}", flush=True)
            else:
                print(f"  {len(docs)} discovered -> {len(kept)} fetched -> {len(provs)} "
                      f"provisions  ({', '.join(f'{k} {v:.0f}s' for k, v in timings.items())})",
                      flush=True)
                for p in provs[:2]:
                    snippet = " ".join((p.verbatim_snippet or "").split())[:150]
                    print(f"    · {(p.law_name or '?')[:46]} | {p.article_section} | {snippet}",
                          flush=True)

    print(f"\n{'=' * 92}\nSUMMARY\n{'=' * 92}")
    print(f"{'eco':4} {'pil':4} {'found':>6} {'fetched':>8} {'provs':>6} {'med chars':>10} "
          f"{'secs':>7}  note")
    for s in summary:
        note = s["error"] or ("NO PROVISIONS" if not s["provisions"] else "")
        print(f"{s['economy']:4} {s['pillar']:<4} {s['discovered']:>6} {s['fetched']:>8} "
              f"{s['provisions']:>6} {s['median_chars']:>10} {s['seconds']:>7}  {note[:44]}")
    print(f"\nCSVs in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
