"""Corpus CLI.

    python -m backend.corpus.cli catalogue --economy MY
    python -m backend.corpus.cli catalogue --economy SG --kinds Act SL
    python -m backend.corpus.cli build     --economy MY --limit 50
    python -m backend.corpus.cli stats
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="corpus", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalogue", help="enumerate an economy's in-force laws (L0)")
    c.add_argument("--economy", required=True)
    c.add_argument("--kinds", nargs="*", default=None,
                   help="SG: Act / SL. AU: Act / LegislativeInstrument.")
    c.add_argument("--max-items", type=int, default=None)
    c.add_argument("--no-codes", action="store_true", help="MY: skip the pdp.gov.my codes")

    b = sub.add_parser("build", help="fetch + extract + split (L1-L3)")
    b.add_argument("--economy", required=True)
    b.add_argument("--limit", type=int, default=None)
    b.add_argument("--force", action="store_true")
    b.add_argument("--ocr", default=None)
    b.add_argument("--workers", type=int, default=None)

    s = sub.add_parser("stats", help="what is in the corpus store")
    s.add_argument("--economy", default=None)

    f = sub.add_parser("freshness", help="live-verify stored versions of an economy's laws")
    f.add_argument("--economy", required=True)
    f.add_argument("--limit", type=int, default=20)

    a = ap.parse_args(argv)
    from . import store
    store.init()

    if a.cmd == "catalogue":
        from .catalogue import sweep
        kw: dict = {}
        econ = a.economy.upper()
        if a.kinds:
            kw["kinds" if econ == "SG" else "collections"] = tuple(a.kinds)
        if a.max_items:
            kw["max_items"] = a.max_items
        if econ == "MY" and a.no_codes:
            kw["include_codes"] = False
        print(json.dumps(sweep(a.economy, **kw), indent=1))
    elif a.cmd == "build":
        from .build import build
        print(json.dumps(build(a.economy, limit=a.limit, force=a.force,
                               ocr_provider_name=a.ocr, extract_workers=a.workers), indent=1))
    elif a.cmd == "stats":
        print(json.dumps(store.stats(a.economy.upper() if a.economy else None), indent=1))
    elif a.cmd == "freshness":
        from .version import check_freshness
        laws = store.list_laws(a.economy.upper())[: a.limit]
        res = check_freshness(a.economy, [law["law_id"] for law in laws])
        print(json.dumps({k: len(v) for k, v in res.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
