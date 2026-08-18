"""Measure every installed OCR engine on the bundled scanned sample.

Why this exists: the engine bench in the dashboard used to show per-document timings that
nobody had taken — they read as measurements but were estimates. Either a number on that
screen comes from here, or the card says the engine was not measured. There is no third
option, because an engine comparison that quietly invents figures is worse than none.

What is measured, on `data/samples/SG/mas_notice_655.pdf` (a genuine image-only PDF, proven
by tests/test_scanned_ocr.py):
  • character error rate against the human-checked reference transcript
  • wall-clock seconds for the whole document, and per page
Both on THIS machine — the numbers are hardware-dependent, which is why the output records
the CPU and the date next to them.

    python tools/bench_ocr.py            # measure whatever is installed
    python tools/bench_ocr.py --engine rapidocr paddle

Writes data/benchmarks/ocr_bench.json, which frontend/enginebench.py reads. Engines that
are not installed are left out of the file entirely, so an absent engine can never be shown
with a stale figure from a machine that did have it.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCAN_PDF = ROOT / "data" / "samples" / "SG" / "mas_notice_655.pdf"
SCAN_REF = ROOT / "data" / "samples" / "SG" / "mas_notice_655.ocr.txt"
OUT = ROOT / "data" / "benchmarks" / "ocr_bench.json"


def _provider(name: str):
    """Build one engine, or return None if it is not installed here."""
    try:
        from backend.providers.ocr_factory import get_ocr_provider
        return get_ocr_provider(name)
    except Exception as e:  # noqa: BLE001 — a missing engine is an expected outcome
        print(f"  {name:12s} skipped ({type(e).__name__}: {e})")
        return None


def measure(name: str, pdf: Path) -> dict | None:
    from backend.providers.registry import ocr_availability

    av = ocr_availability(name)
    if not av.ready:
        print(f"  {name:12s} skipped (not available: {av.note})")
        return None
    prov = _provider(name)
    if prov is None:
        return None

    # Two passes. The first includes loading (and, for Paddle, compiling) the model, which
    # happens once per process — reporting it as the per-page cost overstates every page
    # after the first by two orders of magnitude. The second pass is the steady-state number,
    # and the cold one is kept separately because a judge running a single document pays it.
    t0 = time.perf_counter()
    try:
        res = prov.ocr_pdf(str(pdf))
    except Exception as e:  # noqa: BLE001 — record the failure rather than crashing the sweep
        print(f"  {name:12s} FAILED ({type(e).__name__}: {e})")
        return None
    cold = time.perf_counter() - t0

    t1 = time.perf_counter()
    try:
        res = prov.ocr_pdf(str(pdf))
        secs = time.perf_counter() - t1
    except Exception:  # noqa: BLE001 — a one-shot engine keeps its cold number
        secs = cold

    text = getattr(res, "text", "") or ""
    pages = len(getattr(res, "pages", []) or [])   # OCRResult.pages is a list of page results
    row: dict = {"seconds": round(secs, 2), "first_call_seconds": round(cold, 2),
                 "pages": pages,
                 "seconds_per_page": round(secs / pages, 2) if pages else None,
                 "chars": len(text)}
    conf = getattr(res, "mean_confidence", None)
    if conf is not None:
        row["mean_confidence"] = round(float(conf), 3)

    # MarkItDown reads the text layer; this sample has none, so its "error rate" against the
    # reference is meaningless rather than good. Only score engines that actually rasterise.
    # (Measured on a sidecar-free copy — see main(). Scored in place, MarkItDown fell back to
    # reading mas_notice_655.ocr.txt, which IS the reference, and scored a perfect 0.00%.)
    if text.strip():
        from backend.pipeline.cer import character_error_rate
        row["cer"] = round(character_error_rate(SCAN_REF.read_text(encoding="utf-8"), text), 4)
    else:
        row["cer"] = None
        row["note"] = "produced no text on an image-only PDF"

    cer_s = f"CER {row['cer']:.2%}" if row["cer"] is not None else "no text"
    print(f"  {name:12s} warm {secs:7.2f}s (first call {cold:7.1f}s)  "
          f"{pages} page(s)  {cer_s}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", nargs="*", help="engines to measure (default: all known)")
    args = ap.parse_args()

    from backend.providers.registry import OCR_PROVIDERS

    if not SCAN_PDF.exists():
        print(f"missing sample: {SCAN_PDF}")
        return 1

    names = args.engine or [n for n in OCR_PROVIDERS if n != "mock"]
    print(f"sample: {SCAN_PDF.relative_to(ROOT)}")

    # Measure on a COPY, in a directory with no `.ocr.txt` beside it. Two providers fall back
    # to that sidecar when they extract nothing, and the sidecar is the reference transcript —
    # so scoring in place hands those engines the answer key and reports 0.00% error.
    with tempfile.TemporaryDirectory(prefix="vt_ocrbench_") as tmp:
        pdf = Path(tmp) / SCAN_PDF.name
        shutil.copyfile(SCAN_PDF, pdf)
        results = {}
        for n in names:
            row = measure(n, pdf)
            if row:
                results[n] = row

    # Merge, so re-measuring one fast engine does not wipe a slow one's figure.
    payload = {}
    if OUT.exists():
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    engines = payload.get("engines", {})
    engines.update(results)
    for gone in [n for n in names if n not in results]:
        engines.pop(gone, None)      # not installed here any more: drop, never keep stale
    payload = {
        "sample": str(SCAN_PDF.relative_to(ROOT)).replace("\\", "/"),
        "measured_on": date.today().isoformat(),
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "engines": engines,
    }
    results = engines
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} — {len(results)} engine(s) measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
