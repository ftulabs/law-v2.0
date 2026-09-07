"""Give data/cache a lifecycle. It had none, and grew to 1.3 GB.

Measured 2026-09-07: 843 PDFs, 2,155 HTML pages, 2,854 extraction results — holding BOTH
`_rapidocr_v4` and `_rapidocr_v5` output for the same documents — 210 MB of embedding
caches and 53 MB of LightRAG artefacts that `RETRIEVER=hybrid` cannot read (`RETRIEVER=auto`
CAN, once a corpus crosses `lightrag_min_provisions` — see `backend/pipeline/mapping.py`).

What this tool must NOT reclaim is the more important half:

  _extracted/   the panel requires re-processing already-downloaded documents without
                re-fetching ("the live test may require it"). This IS that mechanism. Only
                SUPERSEDED engine versions of a document go; the newest always stays, and a
                document with a single version is never touched.
  _emb_*.npz    measured at a 16x speedup on repeat runs and rebuilt only at real CPU cost.
  _ce_*.npz     same.
  _search.json  on every successful search, `websearch.search()` now drops entries that are
                already expired (settings.search_cache_max_age_days) when it rewrites the
                file — that is the per-entry lifecycle. This tool still never reclaims it
                directly: a query that never runs again would otherwise sit dead forever,
                but that is a slower leak than this tool exists to police.
  _results/     directory of run-result caches; protected same as above (a directory, so the
                per-file passes below never reach it — listed to make the exemption explicit).

    python tools/cache_gc.py                       # what would go, and why (default)
    python tools/cache_gc.py --apply               # actually delete
    python tools/cache_gc.py --max-age-days 30 --max-gb 2 --apply
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                            # noqa: E402
from backend.console import enable_utf8_stdio                  # noqa: E402

#: Never reclaimed by age or size — see the module docstring for why each one earns it.
#: `_results` is a directory, so the top-level-file passes below never reach it today
#: regardless — listed anyway as cheap insurance in destructive code.
_PROTECTED = ("_search.json", "_index.json", "_results")
_PROTECTED_PREFIX = ("_emb_", "_ce_")

#: `<doc-hash>_<engine>_<version>.json` in _extracted/. The version is what makes one
#: output supersede another for the same document.
_EXTRACTED = re.compile(r"^(?P<doc>[0-9a-f]+)_(?P<engine>[a-z0-9]+)_v(?P<ver>\d+)\.json$")


@dataclass
class Reclaim:
    path: Path
    bytes: int
    reason: str


def _protected(p: Path) -> bool:
    return p.name in _PROTECTED or p.name.startswith(_PROTECTED_PREFIX)


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def plan_gc(root: Path, max_age_days: float, max_gb: float,
            keep_engines: bool) -> list[Reclaim]:
    """What would be reclaimed, and why. Pure — it never deletes."""
    out: list[Reclaim] = []
    now = time.time()
    if not root.exists():
        return out

    # 1. LightRAG artefacts, when the configured retriever cannot read them. Empty-string
    # default matches backend/pipeline/mapping.py:36 ("auto") — the two must not drift, since
    # RETRIEVER=auto DOES build and read LightRAG once a corpus crosses lightrag_min_provisions.
    lr = root / "lightrag"
    if lr.is_dir() and (settings.retriever or "auto").lower() not in ("lightrag", "auto"):
        size = _dir_size(lr)
        if size:
            out.append(Reclaim(lr, size,
                               f"RETRIEVER={settings.retriever} cannot read LightRAG artefacts"))

    # 2. Superseded engine outputs in _extracted/ — newest version per (document, engine) stays.
    ex = root / "_extracted"
    if ex.is_dir() and not keep_engines:
        newest: dict[tuple[str, str], int] = {}
        rows: list[tuple[Path, str, str, int]] = []
        for f in ex.glob("*.json"):
            m = _EXTRACTED.match(f.name)
            if not m:
                continue
            key = (m["doc"], m["engine"])
            ver = int(m["ver"])
            rows.append((f, m["doc"], m["engine"], ver))
            newest[key] = max(newest.get(key, -1), ver)
        for f, doc, engine, ver in rows:
            if ver < newest[(doc, engine)]:
                out.append(Reclaim(f, f.stat().st_size,
                                   f"{engine} v{ver} superseded by "
                                   f"v{newest[(doc, engine)]} for the same document"))

    reclaimed = {r.path for r in out}
    bodies = [f for f in root.iterdir()
              if f.is_file() and not _protected(f) and f not in reclaimed]

    # 3. Document bodies past the age cap. They are content-hashed and re-fetchable.
    if max_age_days > 0:
        for f in bodies:
            age = (now - f.stat().st_mtime) / 86400.0
            if age > max_age_days:
                out.append(Reclaim(f, f.stat().st_size,
                                   f"cached body {age:.0f} days old (cap {max_age_days:g})"))

    # 4. Size cap, oldest first, on whatever the age pass left behind.
    if max_gb > 0:
        left = sorted((f for f in bodies if f not in {r.path for r in out}),
                      key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in left)
        budget = int(max_gb * 1024 ** 3)
        for f in left:
            if total <= budget:
                break
            size = f.stat().st_size
            out.append(Reclaim(f, size, f"over the {max_gb:g} GB cap, oldest first"))
            total -= size
    return out


def main() -> int:
    enable_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="cache directory (default: settings.cache_path)")
    ap.add_argument("--max-age-days", type=float, default=30.0)
    ap.add_argument("--max-gb", type=float, default=0.0, help="0 = no size cap")
    ap.add_argument("--keep-engines", action="store_true",
                    help="keep superseded engine outputs in _extracted/")
    ap.add_argument("--apply", action="store_true", help="delete (default is a dry run)")
    a = ap.parse_args()

    root = Path(a.root) if a.root else settings.cache_path
    plan = plan_gc(root, a.max_age_days, a.max_gb, a.keep_engines)
    if not plan:
        print(f"nothing to reclaim in {root}")
        return 0

    by_reason: dict[str, tuple[int, int]] = {}
    for r in plan:
        kind = r.reason.split(" for the same document")[0].split(" (")[0]
        n, b = by_reason.get(kind, (0, 0))
        by_reason[kind] = (n + 1, b + r.bytes)
    total = sum(r.bytes for r in plan)
    for kind, (n, b) in sorted(by_reason.items(), key=lambda x: -x[1][1]):
        print(f"  {b / 1024**2:9.1f} MB  {n:5d} file(s)  {kind}")
    print(f"  {'-' * 9}")
    print(f"  {total / 1024**2:9.1f} MB  {len(plan):5d} file(s)  TOTAL")

    if not a.apply:
        print("\ndry run — nothing deleted. Re-run with --apply to reclaim.")
        return 0
    for r in plan:
        shutil.rmtree(r.path, ignore_errors=True) if r.path.is_dir() else r.path.unlink(missing_ok=True)
    print(f"\nreclaimed {total / 1024**2:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
