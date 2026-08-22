"""What can this tool actually do, per economy — generated, not asserted.

The final-round README asks for a "Supported Economies and Portals" table with a column that
reads "Run end to end?", and the Instructions sheet says of the nine live-test economies:
"State honestly which of these your tool has actually been run against." Those two sentences
are the same request, and a table typed by hand answers it from memory. This one is derived
from the registries the pipeline actually reads, so it cannot claim a capability the code does
not have.

Four levels, and the distinction between the middle two is the one that matters:

    DECLARED   the economy resolves, has a language profile and an OCR engine. Nothing more.
    REACHABLE  a portal answered us, and we recorded how and when.
    EXTRACTED  provisions were produced from that portal's documents.
    MEASURED   a full run was scored against the panel's own 2025 database.

Only MEASURED is a claim about quality. Everything below it is a claim about plumbing, and
saying so is worth more than a green tick a reviewer can disprove in a minute.

    python tools/readiness.py              # the table
    python tools/readiness.py --markdown   # the same, ready to paste into the README
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                        # noqa: E402

from backend.config import ROOT                                    # noqa: E402
from backend.providers import engine_profile as EP                 # noqa: E402
from backend.providers.ocr_factory import UnavailableOCR, get_ocr_provider  # noqa: E402
from backend.schemas import ECONOMY_UN_NAME, LIVE_TEST_NINE, ROUND1_ECONOMIES  # noqa: E402

DECLARED, REACHABLE, EXTRACTED, MEASURED = "declared", "reachable", "extracted", "measured"

#: Economies with a corpus built and a run scored against the panel's database. Kept as an
#: explicit list rather than inferred, because "we ran it once" is a human judgement and
#: inferring it from a stray output file would be exactly the kind of green tick this file
#: exists to avoid. Update it when a run is actually done, and not before.
RUN_END_TO_END = {
    "SG": MEASURED, "AU": MEASURED, "MY": MEASURED,
    "CN": EXTRACTED,      # 21 rows / 11 laws / 105s / $2.48 on pillar 6, real LLM
    "IN": EXTRACTED,   # DPDP Act 2023 s.16 -> 6.4, live, matching the panel's answer key
    "MN": DECLARED,
}


def _sources() -> dict[str, list[dict]]:
    data = yaml.safe_load((ROOT / "data" / "sources.yaml").read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for s in data.get("sources", []):
        out.setdefault(s.get("economy", "?"), []).append(s)
    return out


def level(code: str, portals: list[dict]) -> str:
    """The highest level this economy has actually reached."""
    stated = RUN_END_TO_END.get(code, DECLARED)
    if stated in (EXTRACTED, MEASURED):
        return stated
    # Not run, so the ceiling is whatever the portals demonstrated.
    if any(p.get("verified") is True for p in portals):
        return REACHABLE
    if any("HTTP 200" in (p.get("reachable") or "") and "JS shell" not in (p.get("reachable") or "")
           for p in portals):
        return REACHABLE
    return DECLARED


def blocker(code: str, portals: list[dict], lvl: str) -> str:
    """The single next thing standing between this economy and the level above."""
    if lvl == MEASURED:
        return "—"
    if lvl == EXTRACTED:
        return "no scored run against the 2025 database yet"
    if not portals:
        return "no portal in data/sources.yaml"
    if lvl == REACHABLE:
        return "portal answers; no discovery adapter has produced provisions from it"
    reasons = [p.get("reachable", "") for p in portals if p.get("reachable")]
    if not reasons:
        return "portal never probed"
    for r in reasons:                       # report the most actionable failure, not the first
        if "JS shell" in r:
            return "portal is a JS shell — 200 with no statute text in the body"
        if "404" in r:
            return "reachable, document path unknown (404 on every path tried)"
        if "403" in r:
            return "WAF returns 403; browser lane needed"
        if "did not resolve" in r or "does not resolve" in r:
            return "host does not resolve — the portal URL itself is wrong"
    return reasons[0][:70]


def _primary(portals: list[dict]) -> str:
    """The portal a reader should think of as THE source for this economy.

    Not simply the first in the file: an economy can list a regulator's site alongside the
    statute book, and Malaysia lists the data-protection department first. A dedicated
    adapter (an API or the portal's own catalogue) is the strongest signal that a host is the
    primary law source, since nobody writes one for a secondary site.
    """
    if not portals:
        return "—"
    ranked = sorted(portals, key=lambda p: (p.get("adapter", "websearch") == "websearch",
                                            not p.get("verified")))
    host = ranked[0]["base_url"].replace("https://", "").replace("http://", "").rstrip("/")
    return f"{host} (+{len(portals) - 1})" if len(portals) > 1 else host


def rows() -> list[dict]:
    src = _sources()
    order = list(LIVE_TEST_NINE) + [c for c in ROUND1_ECONOMIES]
    out = []
    for code in order:
        portals = src.get(code, [])
        prof = EP.profile_for(code)
        engine = get_ocr_provider(economy=code)
        lvl = level(code, portals)
        out.append({
            "code": code,
            "economy": ECONOMY_UN_NAME.get(code, code),
            "nine": code in LIVE_TEST_NINE,
            "language": prof.language_of_source,
            "lane": prof.lane,
            "portal": _primary(portals),
            "portals": len(portals),
            "ocr": "—" if isinstance(engine, UnavailableOCR) else engine.name,
            "reranker": prof.reranker.value or "off",
            "level": lvl,
            "blocker": blocker(code, portals, lvl),
        })
    return out


def render(markdown: bool) -> str:
    data = rows()
    if markdown:
        head = ("| Economy | Live-test nine | Language of source | Portal | Lane | OCR | "
                "Reranker | Run end to end? | Next blocker |")
        lines = [head, "| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
        for r in data:
            lines.append(
                f"| {r['economy']} | {'yes' if r['nine'] else '—'} | {r['language']} | "
                f"{r['portal']} | {r['lane']} | {r['ocr']} | {r['reranker']} | "
                f"**{r['level']}** | {r['blocker']} |")
        return "\n".join(lines)
    w = max(len(r["economy"]) for r in data)
    lines = []
    for r in data:
        flag = "9" if r["nine"] else " "
        lines.append(f"{flag} {r['economy']:<{w}}  {r['language']:<12} {r['lane']:<11} "
                     f"{r['ocr']:<9} {r['level']:<9}  {r['blocker']}")
    counts = {lv: sum(1 for r in data if r["level"] == lv and r["nine"])
              for lv in (MEASURED, EXTRACTED, REACHABLE, DECLARED)}
    lines.append("")
    lines.append("of the nine live-test economies: " +
                 " · ".join(f"{v} {k}" for k, v in counts.items()))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markdown", action="store_true", help="emit the README table")
    args = ap.parse_args()
    print(render(args.markdown))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
