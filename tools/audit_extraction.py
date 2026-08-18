"""Run the extraction audit over the built corpus.

    python tools/audit_extraction.py                 # all economies
    python tools/audit_extraction.py --economy AU --roundtrip 80

Exit code is 1 when any ERROR-severity finding is present, so this can gate a build.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Legal text is full of en-dashes and non-breaking hyphens; the Windows console is cp1252.
# Without this the audit dies while PRINTING its own findings.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/!TextIO streams
        pass

from backend.eval.extraction_audit import audit   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", nargs="*", default=["SG", "AU", "MY"])
    ap.add_argument("--roundtrip", type=int, default=40)
    ap.add_argument("--page-limit", type=int, default=None)
    ap.add_argument("--out", default="logs/extraction_audit.json")
    a = ap.parse_args()

    rep = audit(tuple(e.upper() for e in a.economy), roundtrip_sample=a.roundtrip,
                page_limit=a.page_limit)

    by_check = Counter(f"{f.check}/{f.severity}" for f in rep.findings)
    print("\n=== findings by check ===")
    for k, v in sorted(by_check.items()):
        print(f"  {k:24} {v}")
    errs = rep.errors()
    if errs:
        print(f"\n=== {len(errs)} ERROR findings (first 25) ===")
        for f in errs[:25]:
            print(f"  [{f.check}] {f.economy} {f.law}: {f.detail}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"stats": rep.stats, "findings": [asdict(f) for f in rep.findings]},
        indent=1), encoding="utf-8")
    print("\nwritten:", a.out)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
