#!/usr/bin/env python3
"""Zone-1 DISCOVERY evaluation — does the app FIND the right laws on its own?

    python evaluate_discovery.py --economy Australia --live
    python evaluate_discovery.py --economy Singapore --use-samples   # offline dry-run

Measures document-level recall of live discovery against the judges' sample list
(data/ground_truth/gov_portals_p6_p7.csv). Only ground-truth rows hosted on the
economy's OFFICIAL portal are "in-scope" (a single-portal crawl can't reach a law
published on a third-party site) — those off-portal rows are reported separately so
the number is honest about what crawling one root can and cannot surface.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from backend.pipeline import discovery as disc
from backend.schemas import Economy
from main import parse_economy

GT_CSV = Path(__file__).resolve().parent / "data" / "ground_truth" / "gov_portals_p6_p7.csv"

# The single official portal root the judges hand us per economy.
OFFICIAL_HOST = {Economy.SG: "sso.agc.gov.sg",
                 Economy.AU: "legislation.gov.au",
                 Economy.MY: "lom.agc.gov.my"}

COUNTRY_TO_ECON = {"singapore": Economy.SG, "australia": Economy.AU, "malaysia": Economy.MY}
_STOP = {"act", "the", "of", "and", "for", "to", "on", "1", "2", "no"}


def _norm_host(u: str) -> str:
    return urlparse(u).netloc.lower().replace("www.", "")


def _path_stem(u: str) -> str:
    """Last meaningful path segment, lowercased (e.g. .../Act/PDPA2012 → pdpa2012)."""
    path = urlparse(u).path.rstrip("/")
    seg = path.split("/")[-1] if path else ""
    return re.sub(r"\.(pdf|html?|aspx)$", "", seg.lower())


def _title_tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOP and len(w) > 2}


def _matches(gt_url: str, gt_title: str, discovered) -> bool:
    gt_stem = _path_stem(gt_url)
    gt_tok = _title_tokens(gt_title)
    for d in discovered:
        if gt_stem and gt_stem in _path_stem(d.source_url):
            return True
        dt = _title_tokens(d.title)
        if gt_tok and len(gt_tok & dt) / len(gt_tok) >= 0.6:   # strong title overlap
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="VeriTrade Zone-1 discovery evaluation")
    ap.add_argument("--economy", required=True)
    ap.add_argument("--pillar", nargs="+", type=int, default=[6, 7])
    ap.add_argument("--use-samples", action="store_true", help="offline dry-run (no crawl)")
    ap.add_argument("--csv", default=str(GT_CSV))
    args = ap.parse_args()

    economy = parse_economy(args.economy)
    host = OFFICIAL_HOST[economy]
    country_name = {Economy.SG: "singapore", Economy.AU: "australia", Economy.MY: "malaysia"}[economy]
    df = pd.read_csv(args.csv, dtype=str).fillna("")
    rows = df[df["country"].str.lower() == country_name]
    # dedupe ground-truth by (title, url)
    gt = rows[["Act.and.or.practice", "References"]].drop_duplicates().values.tolist()
    in_scope = [(t, u) for t, u in gt if _norm_host(u).endswith(host)]
    off_portal = [(t, u) for t, u in gt if not _norm_host(u).endswith(host)]

    discovered = []
    for p in args.pillar:
        discovered.extend(disc.discover(economy, p, use_samples=args.use_samples))
    # dedupe discovered by source_url
    seen, uniq = set(), []
    for d in discovered:
        if d.source_url not in seen:
            seen.add(d.source_url)
            uniq.append(d)

    found = [(t, u) for t, u in in_scope if _matches(u, t, uniq)]
    missed = [(t, u) for t, u in in_scope if (t, u) not in found]
    recall = len(found) / len(in_scope) if in_scope else 0.0

    print(f"== Discovery eval: {economy.value} (pillars {args.pillar}, "
          f"{'samples' if args.use_samples else 'LIVE'}) ==")
    print(f"ground-truth rows (unique)      : {len(gt)}")
    print(f"  on official portal ({host:<18}): {len(in_scope)}")
    print(f"  off-portal (not crawlable here): {len(off_portal)}")
    print(f"discovered documents            : {len(uniq)}")
    print(f"recall (in-scope GT found)      : {len(found)}/{len(in_scope)} = {recall:.0%}")
    if missed:
        print("missed (in-scope, not found):")
        for t, u in missed[:20]:
            print(f"  - {t[:60]}  ({u})")


if __name__ == "__main__":
    main()
