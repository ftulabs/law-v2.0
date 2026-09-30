#!/usr/bin/env python3
"""How many workers should extraction use?

`extraction_concurrency` is 8 and has never been measured on this box. Extraction+OCR is the
largest COLD stage of a live run (617s of a 744s cold fetch+extract on live SG pillar-7,
2026-09-14), so the setting is worth a number rather than a guess.

Runs over the bodies already in the fetch cache with the EXTRACTION cache disabled, so it
times real parsing and needs no network — which also means it can be run while a portal is
throttling us.

REPORTS PEAK MEMORY, because that turned out to be the binding constraint and not CPU: the
first attempt at 16 workers was killed by the OOM reaper on a 16 GB box whose largest cached
document is 4 MB. MarkItDown/pdfplumber expand a PDF enormously while parsing it, so the safe
worker count is set by RAM per worker, not by core count.

    python tools/bench_extraction_concurrency.py --workers 4,8,12,16
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings                                    # noqa: E402
from backend.pipeline import extraction                                # noqa: E402
from backend.pipeline.ocr import _extract_document_text                # noqa: E402
from backend.schemas import DiscoveredDoc, DocFormat, Economy          # noqa: E402

_FMT = {".pdf": DocFormat.PDF_TEXT, ".html": DocFormat.HTML, ".htm": DocFormat.HTML,
        ".txt": DocFormat.TEXT, ".doc": DocFormat.TEXT, ".docx": DocFormat.TEXT}


def cached_docs(limit: int | None) -> list[DiscoveredDoc]:
    d = settings.cache_path
    files = sorted(p for p in d.glob("*") if p.is_file() and p.suffix.lower() in _FMT)
    if limit:
        files = files[:limit]
    return [DiscoveredDoc(
        doc_id=f"BENCH-{p.stem}", economy=Economy.SG, title=p.name,
        source_url=f"https://sso.agc.gov.sg/{p.stem}", fmt=_FMT[p.suffix.lower()],
        discovery_tag="NEW", relevance_score=1.0, portal="sso.agc.gov.sg",
        local_path=str(p)) for p in files]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", default="1,4,8,12,16")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    from backend.providers import get_ocr_provider
    ocr = get_ocr_provider("markitdown")
    docs = cached_docs(a.limit or None)
    if not docs:
        print("no cached bodies — run a live crawl first")
        return 1
    mb = sum(Path(d.local_path).stat().st_size for d in docs) / 1e6
    print(f"{len(docs)} cached bodies, {mb:.1f} MB · extraction cache DISABLED\n")

    def one(d):
        raw, m = _extract_document_text(d, ocr)      # bypasses get_document_text's cache
        return len(extraction.extract_provisions(d, raw, m))

    import resource
    import threading

    def peak_rss_mb() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    print(f"{'workers':>8} {'seconds':>9} {'speedup':>8} {'peak MB':>9} "
          f"{'MB/worker':>10} {'provisions':>11}")
    base = None
    for w in [int(x) for x in a.workers.split(",")]:
        before = peak_rss_mb()
        hi = [before]
        stop = threading.Event()

        def sample():                       # ru_maxrss is a high-water mark; sample anyway
            while not stop.wait(0.25):      # so a level's OWN peak is visible, not the run's
                hi[0] = max(hi[0], peak_rss_mb())

        watcher = threading.Thread(target=sample, daemon=True)
        watcher.start()
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=w) as ex:
            n = sum(ex.map(one, docs))
        dt = time.perf_counter() - t0
        stop.set()
        watcher.join()
        peak = max(hi[0], peak_rss_mb())
        base = base or dt
        print(f"{w:>8} {dt:>9.1f} {base/dt:>7.2f}x {peak:>9.0f} "
              f"{(peak - before) / w:>10.0f} {n:>11,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
