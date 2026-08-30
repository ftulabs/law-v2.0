"""Did the cheaper run still reach the panel's own answers? Measured on the CSV, not the shortlist.

    python tools/compare_to_key.py SG MY AU

The per-economy retrieval budget was chosen on RETRIEVAL recall — whether the provision the
panel cited reaches the shortlist at all. That is the ceiling on everything the grader can get
right, and it needs no LLM call, which is why it was measured first. It is not the same claim
as "the submission still contains the answer", because a provision can reach the shortlist and
still be rejected by the grader. This closes that gap: it reads the exported CSV of two runs
and asks, per indicator, whether a law the panel accepted appears in ours.

Law names are matched on the linkage module's normalised form (case, punctuation, year and
instrument-type noise removed), in both containment directions, because the panel writes
"Personal Data Protection Act 2012" where a portal writes "Personal Data Protection Act 2012
(Singapore)".
"""
from __future__ import annotations

import csv
import glob
import re
import sys
from urllib.parse import unquote, urlsplit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.eval.ground_truth import load_labels     # noqa: E402
from backend.eval.linkage import _norm                # noqa: E402

IND = {f"{p}.{i}": f"P{p}-I{i}" for p in (6, 7) for i in range(1, 6)}


_ARCHIVE_RE = re.compile(r"^https?://web\.archive\.org/web/\d+[a-z_]*/(https?://.+)$", re.I)
_ID_RE = re.compile(r"(\d{2,})")


def url_keys(url: str) -> set[str]:
    """Comparable forms of a document URL, so a match survives the portal's own URL shapes.

    Matching on the law NAME alone gives a false zero wherever the panel writes the name in
    English and the statute is published in another language. Mongolia is the case that forced
    this: our run cited «ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ» and the key says "Law on
    Personal Data Protection" — no normalisation can bridge those — while both point at
    legalinfo.mn lawId=16390288615991. Reported as 0/8; it was not 0.

    Two shapes are folded together deliberately: `/mn/detail?lawId=108` and `/mn/detail/108`
    are the same law on the same portal, so the host plus the longest numeric id is emitted as
    a key alongside the literal path. A collision would need two different laws to share an id
    on one host, which is what an id is for.
    """
    u = (url or "").strip()
    if not u:
        return set()
    m = _ARCHIVE_RE.match(u)          # the key cites Wayback snapshots; unwrap to the original
    if m:
        u = m.group(1)
    s = urlsplit(u)
    host = s.netloc.lower().removeprefix("www.")
    path = unquote(s.path).lower().rstrip("/")
    out = {f"{host}{path}"}
    if s.query:
        out.add(f"{host}{path}?{s.query.lower()}")
    ids = _ID_RE.findall(path + " " + s.query)
    if ids:
        out.add(f"{host}#{max(ids, key=len)}")
    return out


def key_targets(econ: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(names, urls) the panel accepted, per indicator."""
    names: dict[str, set[str]] = {}
    urls: dict[str, set[str]] = {}
    for r in load_labels():
        if r.economy != econ or r.kind != "provision":
            continue
        names.setdefault(r.indicator_id, set()).update(
            n for n in (_norm(l) for l in r.laws if len(l) > 4) if n)
        for u in r.portal_urls + r.other_urls:
            urls.setdefault(r.indicator_id, set()).update(url_keys(u))
    return names, urls


def rows_of(path: str) -> dict[str, tuple[set[str], set[str]]]:
    """{indicator: (normalised law names, url keys)} for one exported run."""
    out: dict[str, tuple[set[str], set[str]]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ind = (row.get("Indicator ID") or row.get("Indicator_ID") or "").strip()
            ind = IND.get(ind, ind)
            law = (row.get("Law Name") or row.get("Law/Regulation Name") or "").strip()
            # "No evidence" rows are a deliberate output, not a citation — see the placeholder
            # stage in the orchestrator. Counting them as coverage would score an absence as a hit.
            if not law or "no evidence" in law.lower():
                continue
            names, urls = out.setdefault(ind, (set(), set()))
            names.add(_norm(law))
            urls |= url_keys(row.get("Source URL") or "")
    return out


def score(path: str, names: dict[str, set[str]], urls: dict[str, set[str]]):
    """A row counts for an indicator when it cites a law the panel accepted — matched by NAME,
    or by the document URL when the two sides name it in different languages."""
    got = rows_of(path)
    hit, detail = 0, []
    for ind in sorted(set(names) | set(urls)):
        our_names, our_urls = got.get(ind, (set(), set()))
        by_name = any(w in o or o in w for w in names.get(ind, set()) for o in our_names)
        by_url = bool(our_urls & urls.get(ind, set()))
        found = by_name or by_url
        hit += found
        detail.append((ind, found, len(our_names), "url" if (by_url and not by_name) else ""))
    return hit, len(set(names) | set(urls)), detail, sum(len(v[0]) for v in got.values())


def newest(pattern: str) -> str | None:
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def main() -> int:
    econs = [e.upper() for e in (sys.argv[1:] or ["SG", "MY", "AU"])]
    for econ in econs:
        names, urls = key_targets(econ)
        old = newest(f"outputs/rt_check/{econ}_P67_*.csv")
        new = newest(f"outputs/budget_check/{econ}_P67_*.csv")
        print(f"\n=== {econ}")
        for label, path in (("before (untuned budget)", old), ("after  (measured budget)", new)):
            if not path:
                print(f"  {label}: no run found")
                continue
            h, t, detail, n = score(path, names, urls)
            miss = [i for i, ok, _, _ in detail if not ok]
            viaurl = [i for i, ok, _, how in detail if ok and how == "url"]
            print(f"  {label}: {h}/{t} answer-key indicators reached · {n} law-rows exported"
                  + (f" · matched by URL only: {viaurl}" if viaurl else "")
                  + (f" · MISSED {miss}" if miss else ""))
            print(f"      {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
