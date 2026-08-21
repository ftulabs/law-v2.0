"""End-to-end Zone 1 + Zone 2 smoke test for a Round-2 economy, without spending an LLM call.

`tools/probe_portals.py` answers "can we reach the portal and does the search engine hold it".
This answers the next question, which is the one that actually decides whether an economy is
viable: **discover → fetch → extract, does real statute text come out the far end, split into
provisions?**

It stops before grading on purpose. Mapping costs money and depends on a key; extraction does
not, and every Round-2 failure found so far lives below the grader — a tokeniser that returned
nothing, a boundary regex that knew only Latin drafting. Those are all visible here.

What it prints per document: bytes fetched, whether OCR ran, provisions found, the script
validity of the text (the defence against a legacy-encoded PDF that extracts as mojibake with
no OCR involved), and the first provision label + snippet so the split can be eyeballed.

    python tools/smoke_round2.py --economy MN
    python tools/smoke_round2.py --economy CN --max-docs 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.pipeline import discovery, extraction, ocr as ocr_mod     # noqa: E402
from backend.pipeline.fetch import fetch_to_cache                      # noqa: E402
from backend.providers.ocr_factory import get_ocr_provider             # noqa: E402
from backend.providers.ocr_languages import profile_for, script_validity   # noqa: E402
from backend.schemas import Economy, resolve_economy                   # noqa: E402


def run(economy: Economy, pillar: int, max_docs: int, quiet: bool) -> int:
    log = (lambda *_: None) if quiet else print
    prof = profile_for(economy.value)
    print(f"\n=== {economy.value} · pillar {pillar} · {prof.language} / {prof.script} ===")

    docs = discovery.discover_live(economy, pillar, max_docs=max_docs)
    print(f"\nZONE 1 — discovered {len(docs)} documents")
    for d in docs[:max_docs]:
        print(f"  · {d.title[:64]:<64} {d.fmt.value:<10} {d.source_url[:70]}")
    if not docs:
        print("  NOTHING DISCOVERED — the lane is not working; re-run tools/probe_portals.py")
        return 1

    # Resolve OCR the same way the orchestrator does, so the engine and language model named
    # here are the ones a real run would use — not a default that happens to suit Latin text.
    provider = get_ocr_provider(economy=economy.value)
    print(f"\nZONE 2 — fetch + extract with ocr={provider.name} (first {max_docs})")
    total_provisions, ok_docs = 0, 0
    for d in docs[:max_docs]:
        try:
            fetch_url, _ = discovery._resolve_pdf_url(d.economy, d.source_url)
            fr = fetch_to_cache(fetch_url, log=log)
            if not fr:
                print(f"  x {d.title[:50]:<50} fetch failed: {fetch_url[:60]}")
                continue
            d.local_path, d.fmt = fr.local_path, fr.fmt
            text, metrics = ocr_mod.get_document_text(d, provider)
        except Exception as exc:
            print(f"  ✗ {d.title[:50]:<50} extract failed: {type(exc).__name__}: {str(exc)[:70]}")
            continue
        if not text:
            print(f"  ✗ {d.title[:50]:<50} no text extracted")
            continue
        provisions = extraction.extract_provisions(d, text, metrics)
        validity = script_validity(text, economy.value)
        total_provisions += len(provisions)
        ok_docs += bool(provisions)
        flag = ""
        if validity < 0.5:
            # The failure the CER gate structurally cannot see: a text layer encoded with a
            # legacy non-Unicode font extracts "successfully" as mojibake and OCR never runs.
            flag = f"  ⚠ script validity {validity:.2f} — text may be mojibake, not {prof.script}"
        print(f"  {'✓' if provisions else '✗'} {d.title[:50]:<50} "
              f"{len(text):>7} chars · ocr={metrics.provider or 'none'} · "
              f"{len(provisions):>4} provisions{flag}")
        if provisions:
            p = provisions[0]
            snippet = " ".join(p.verbatim_snippet.split())[:110]
            print(f"      first: [{p.article_section}] {snippet}")

    print(f"\nRESULT: {ok_docs}/{min(len(docs), max_docs)} documents split, "
          f"{total_provisions} provisions total")
    if not total_provisions:
        print("  Documents fetched but NOTHING split — check the boundary patterns for this\n"
              "  economy in extraction._boundaries (this is the silent failure mode).")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economy", required=True)
    ap.add_argument("--pillar", type=int, default=6)
    ap.add_argument("--max-docs", type=int, default=3)
    ap.add_argument("--quiet", action="store_true", help="suppress the pipeline's own logging")
    args = ap.parse_args()
    return run(resolve_economy(args.economy), args.pillar, args.max_docs, args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
