"""Where, exactly, does each provision the panel cites and we miss fall out of the pipeline?

    python tools/missing_ladder.py                 # all six committed economies
    python tools/missing_ladder.py CN --detail

`tools/provision_scorecard.py` reports 68 MISSING across the six economies and stops there.
That single number is not actionable, because "missing" is five different failures wearing one
label, and each takes a different fix and a different amount of work:

  NOT CATALOGUED    the law is not in the catalogue at all — a DISCOVERY failure. The crawler
                    never proposed the document, so nothing downstream could have saved it.
  FETCH FAILED      catalogued, but the body never arrived: link rot, robots, a WAF, a timeout.
                    The stored `error` says which, and that decides whether it is our bug or the
                    panel's dead link.
  NOT SPLIT         fetched, but the text never became article-level provisions — a shell (a
                    landing page, a JS frame) or a splitter that found no headings.
  ARTICLE ABSENT    the law split into provisions, but not into the one cited. Usually the
                    numbering form: a clause the splitter merged into its parent, an amendment
                    that renumbered, or a heading style the pattern does not match.
  IN CORPUS         the exact article IS in the corpus, extracted and citable. Nothing upstream
                    is at fault — it was not retrieved for that indicator, or it was retrieved
                    and the grader refused it. This is the only bucket a definition or ranking
                    change can move, and the only one where re-running is worth the money.

The ladder is deliberately checked top-down and stops at the first rung that fails, because a
law that was never fetched cannot also have a splitting bug — reporting both would double-count
the same root cause and inflate whichever fix is measured next.

Matching reuses the scorecard's rules (law by normalised name OR document URL, article by
parent/child containment), so a provision counted MISSING there is looked up the same way here.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.corpus import store                          # noqa: E402
from backend.eval.harness import section_key              # noqa: E402
from backend.eval.linkage import _norm                    # noqa: E402
from tools.compare_to_key import url_keys                 # noqa: E402
from tools.provision_scorecard import (_same_provision, key_provisions,  # noqa: E402
                                       newest, our_rows, _same_law)

RUNGS = ("NOT CATALOGUED", "FETCH FAILED", "NOT SPLIT", "ARTICLE ABSENT", "IN CORPUS")


def catalogue(econ: str) -> list[dict]:
    """Every catalogued law for an economy, with its latest version row attached."""
    laws = store.list_laws(econ)
    vers = store.versions_for([l["law_id"] for l in laws])
    for l in laws:
        l["_version"] = vers.get(l["law_id"])
        l["_names"] = {n for n in (_norm(l.get("title") or ""),) if n}
        l["_urls"] = url_keys(l.get("source_url") or "") | url_keys(l.get("body_url") or "")
    return laws


def law_matches(k: dict, law: dict) -> bool:
    """Same law-identity rule the scorecard uses, plus the act number.

    The act number is not decoration. Malaysia's "Services Tax Act (Act 807) 2018" is
    catalogued as "SERVICE TAX ACT 2018": the names differ by a plural and a year-versus-number,
    so containment fails both ways, and the panel cites a mirror so the URLs do not meet either.
    Reported as NOT CATALOGUED — a discovery failure — when the Act was sitting in the
    catalogue with law_number '807'. `linkage.link_law` has always keyed on the act number
    first, for exactly this reason; this is the same key, applied here.
    """
    for ours in law["_names"]:
        if any(n in ours or ours in n for n in k["names"]):
            return True
    if k.get("act_nos") and (law.get("law_number") or "").upper() in k["act_nos"]:
        return True
    return bool(k["urls"] & law["_urls"])


def diagnose(econ: str, detail: bool = False) -> tuple[Counter, list[dict]]:
    path = newest(econ)
    rows = our_rows(path) if path else []
    cat = catalogue(econ)
    # Provisions are loaded once per economy and indexed by version — 18k rows for Australia,
    # and the per-law loop below would otherwise re-read them for every missing citation.
    by_version: dict[str, list[dict]] = defaultdict(list)
    for p in store.load_provisions(econ):
        by_version[p["version_id"]].append(p)

    tally, found = Counter(), []
    for k in key_provisions(econ):
        # MISSING = the panel cites it and no exported row covers that (law, article) at all.
        if any(_same_law(k, r) and _same_provision(r["section"], k["section"]) for r in rows):
            continue
        hits = [l for l in cat if law_matches(k, l)]
        if not hits:
            rung, note = "NOT CATALOGUED", ""
        else:
            # Judge the law on its BEST version: one broken mirror does not make the law missing.
            states = {(l["_version"] or {}).get("state") for l in hits}
            if "split" not in states:
                errs = [((l["_version"] or {}).get("error") or "")[:70] for l in hits]
                if "shell" in states or "extracted" in states or "fetched" in states:
                    rung, note = "NOT SPLIT", next((s for s in states if s), "")
                else:
                    rung, note = "FETCH FAILED", next((e for e in errs if e), "no error recorded")
            else:
                provs = [p for l in hits if (l["_version"] or {}).get("state") == "split"
                         for p in by_version.get(l["_version"]["version_id"], [])]
                if any(_same_provision(section_key(p["article_section"] or ""), k["section"])
                       for p in provs):
                    rung, note = "IN CORPUS", f"{len(provs)} provisions in the law"
                else:
                    rung, note = "ARTICLE ABSENT", \
                        f"{len(provs)} provisions, none covering {k['section']}"
        tally[rung] += 1
        found.append({"economy": econ, "indicator": k["indicator"], "label": k["label"],
                      "section": k["section"], "rung": rung, "note": note})
    return tally, found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("economies", nargs="*", default=["SG", "AU", "MY", "CN", "IN", "MN"])
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()

    grand, rows = Counter(), []
    print(f"{'ec':4} " + " ".join(f"{r:>15}" for r in RUNGS) + "   total")
    for econ in [e.upper() for e in a.economies]:
        tally, found = diagnose(econ, a.detail)
        grand.update(tally)
        rows += found
        print(f"{econ:4} " + " ".join(f"{tally[r]:>15}" for r in RUNGS)
              + f"   {sum(tally.values()):>5}")
    print(f"{'ALL':4} " + " ".join(f"{grand[r]:>15}" for r in RUNGS)
          + f"   {sum(grand.values()):>5}")

    if a.detail:
        for rung in RUNGS:
            hits = [r for r in rows if r["rung"] == rung]
            if not hits:
                continue
            print(f"\n── {rung} ({len(hits)})")
            for r in hits:
                print(f"   {r['economy']} {r['label'][:78]}"
                      + (f"   [{r['note']}]" if r["note"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
