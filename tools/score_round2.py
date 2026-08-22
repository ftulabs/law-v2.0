"""Score a run against the panel's own Round-2 answer key.

`tools/readiness.py` distinguishes *extracted* (provisions came out) from *measured* (a run was
scored against the panel's database). Until now nothing could produce the second claim for the
Round-2 economies, so China, India and Mongolia sat at "extracted" with the honest blocker
"no scored run against the 2025 database yet". This closes that gap.

    python tools/score_round2.py --economy CN
    python tools/score_round2.py --economy CN IN MN --pillar 6 7 --markdown

**What is scored, and what is deliberately not.** The unit is the INSTRUMENT, not the article.
For each indicator the panel filled in, the key names one or more Acts; the question asked here
is whether our run cited the same Act. That is the claim the tool exists to support — *find the
law* — and it is checkable. Article-level agreement is not scored, for two honest reasons: the
key's "Act and/or practice" column frequently names no article at all, and where a law has
several provisions on one indicator (PIPL arts. 38, 39 and 40 all bear on 6.4) citing a
different one is not an error.

**Recall is the headline; precision is reported but not headlined.** The key is a floor, not a
ceiling — the panel's analysts recorded what they found, and an instrument we cite that they do
not is as likely to be a genuine additional finding as a false positive. Reporting it as
precision would punish exactly the discovery the brief asks for. It is printed as *extra* and
left for a human to judge.

**Two matching signals, and the first one exists because the second was wrong.** A name-only
comparison scored Mongolia at 0 of 9 — and Mongolia is the economy where the run demonstrably
finds the right Act. The key writes the instrument in ENGLISH ("Law on Personal Data
Protection"); legalinfo.mn serves it in Mongolian ("Хүний хувийн мэдээлэл хамгаалах тухай").
No amount of string folding bridges that, and reporting 0% would have been a measurement
error dressed as a result.

So the primary signal is the URL. Every P6/P7 row in the key carries one, and a portal id is
language-independent: `legalinfo.mn/mn/detail?lawId=16390288615991` is the same instrument
whoever names it. The name comparison remains as the fallback, for the case the URL cannot
cover — the key cites India's DPDP Act as a `meity.gov.in` PDF while we cite the same Act on
`indiacode.gov.in`, which is a correct find at a different address.

Name matching is deliberately generous in one direction only: an Act matches if either side's
normalised name contains the other. The key writes "Personal Information Protection Law of the
People's Republic of China《中华人民共和国个人信息保护法》" where a portal serves
"中华人民共和国个人信息保护法", and a strict comparison would score that as a miss.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import ROOT                                        # noqa: E402
from backend.rdtii import codes as rdtii_codes                         # noqa: E402

DB = ROOT / "ESCAP-RDTII-2.1_ Round 2 Database.xlsx"

#: The panel's sheet name per economy code. Only the seven it covers; SG/AU/MY are Round 1 and
#: are scored by `backend/eval` against the Round-1 database instead.
SHEETS = {
    "CN": "China", "IN": "India", "ID": "Indonesia", "LA": "Lao PDR",
    "MN": "Mongolia", "RU": "Russian Federation", "TH": "Thailand",
}

_BRACKET = re.compile(r"[《》()（）\[\]]")
_NOISE = re.compile(r"\b(of the|the|of|law|act|no|the people'?s republic of china|"
                    r"republic of india|mongolia|thailand|indonesia)\b")
_PUNCT = re.compile(r"[^\w\s一-鿿Ѐ-ӿ฀-๿]")
_WS = re.compile(r"\s+")


def _fold(name: str) -> str:
    """A comparable form of an instrument's name.

    Accents, punctuation and the boilerplate every jurisdiction wraps a title in are removed.
    What survives is the distinctive part — "个人信息保护" or "digital personal data
    protection" — which is what actually identifies the Act.
    """
    s = unicodedata.normalize("NFKC", name or "").lower()
    s = _BRACKET.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = _NOISE.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _variants(cell: str) -> list[str]:
    """The instruments named in one answer-key cell.

    A cell can hold several, separated by ';', and each can carry both an English name and the
    original-language one in 《…》. Both forms are kept: a portal may serve either.
    """
    out: list[str] = []
    for part in re.split(r"[;；]", cell or ""):
        part = part.strip()
        if not part:
            continue
        for native in re.findall(r"《([^》]+)》", part):
            out.append(native)
        english = re.sub(r"《[^》]*》", " ", part).strip()
        if english:
            out.append(english)
    return [v for v in out if len(_fold(v)) >= 4]


_ID = re.compile(r"(?:id|lawid|bbbs|handle|no)[=/]?([0-9]{2,})", re.I)


def url_key(url: str) -> str:
    """A language-independent identity for a document: host plus the id inside the URL.

    Query-string ids matter as much as path ones — legalinfo.mn serves all 36,833 of its
    instruments from `/mn/detail?lawId=N`, so the path alone identifies nothing.
    """
    from urllib.parse import urlsplit                                  # noqa: PLC0415

    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return ""
    host = parts.netloc.lower().removeprefix("www.")
    if not host:
        return ""
    ids = _ID.findall(parts.query) + _ID.findall(parts.path)
    if ids:
        return f"{host}#{max(ids, key=len)}"
    stem = parts.path.rstrip("/").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(pdf|html?|aspx|jsp|htm)$", "", stem, flags=re.I)
    return f"{host}/{stem.lower()}" if stem else host


def _matches(ours: str, theirs: str) -> bool:
    a, b = _fold(ours), _fold(theirs)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    # Token overlap, for English titles that differ by a word order or a year.
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.75


def answer_key(economy: str, pillars: list[int] | None = None) -> dict[str, list[dict]]:
    """{indicator code: [citation]} from the panel's sheet.

    A CITATION is one row of the key: the instrument(s) it names and the URL(s) it points at,
    kept together. The two columns do not pair up one-to-one — a row can name two Acts and
    give three links — so a citation is matched if ANY of its names or ANY of its URLs is.
    That is the generous reading, and the right one: the question is whether we found the
    instrument the analyst was looking at, not whether we rendered its title their way.
    """
    import openpyxl                                                    # noqa: PLC0415

    sheet = SHEETS.get(economy)
    if not sheet or not DB.exists():
        return {}
    ws = openpyxl.load_workbook(DB, read_only=True)[sheet]
    out: dict[str, list[dict]] = {}
    for row in list(ws.iter_rows(values_only=True))[1:]:
        code = str(row[1]).strip() if row[1] is not None else ""
        if not rdtii_codes.is_valid(code):
            continue
        if pillars and int(code.split(".")[0]) not in pillars:
            continue
        names = _variants(str(row[3] or ""))
        urls = {url_key(u) for u in re.findall(r"https?://[^\s,;]+", str(row[7] or ""))}
        urls.discard("")
        if names or urls:
            out.setdefault(code, []).append(
                {"names": names, "urls": urls,
                 "label": names[0] if names else next(iter(urls), "—")})
    return out


def latest_run(economy: str, pillar: int) -> Path | None:
    hits = glob.glob(str(ROOT / "outputs" / f"{economy}_P{pillar}_*.csv"))
    hits = [h for h in hits if not h.endswith("_scored.csv")]
    return Path(max(hits, key=os.path.getmtime)) if hits else None


def our_rows(path: Path) -> dict[str, list[dict]]:
    """{indicator code: [{name, url_key}]} from a submission CSV, placeholders dropped."""
    out: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            law = (row.get("Law Name") or "").strip()
            code = (row.get("Indicator ID") or "").strip()
            if not law or law == "No provision found" or not rdtii_codes.is_valid(code):
                continue
            out.setdefault(code, []).append(
                {"name": law, "url": url_key(row.get("Source URL") or "")})
    return out


def _hit(citation: dict, ours: list[dict]) -> str | None:
    """How this citation was matched, or None. The signal is reported, not just the verdict —
    a URL match is exact and a name match is a judgement, and a reader should be able to tell
    which one a number rests on."""
    if citation["urls"] and any(o["url"] and o["url"] in citation["urls"] for o in ours):
        return "url"
    if any(_matches(o["name"], n) for o in ours for n in citation["names"]):
        return "name"
    return None


def score(economy: str, pillars: list[int]) -> dict:
    key = answer_key(economy, pillars)
    ours: dict[str, list[dict]] = {}
    runs: dict[int, str] = {}
    for pillar in pillars:
        path = latest_run(economy, pillar)
        if not path:
            continue
        runs[pillar] = path.name
        for code, rows in our_rows(path).items():
            ours.setdefault(code, []).extend(rows)

    per: list[dict] = []
    for code in sorted(key, key=lambda c: [int(x) for x in c.split(".")]):
        cites = key[code]
        found = ours.get(code, [])
        marks = [(c, _hit(c, found)) for c in cites]
        matched_names = {n for c, m in marks if m for n in c["names"]}
        matched_urls = {u for c, m in marks if m for u in c["urls"]}
        extra = sorted({o["name"] for o in found
                        if o["url"] not in matched_urls
                        and not any(_matches(o["name"], n) for n in matched_names)})
        per.append({
            "code": code,
            "citations": [{"label": c["label"], "how": m} for c, m in marks],
            "hits": sum(1 for _, m in marks if m),
            "by_url": sum(1 for _, m in marks if m == "url"),
            "rows": len(found),
            "extra": extra,
        })

    scored = [p for p in per if p["citations"]]
    return {
        "economy": economy,
        "pillars": pillars,
        "runs": runs,
        "indicators_in_key": len(scored),
        "indicators_hit": sum(1 for p in scored if p["hits"]),
        "citations_in_key": sum(len(p["citations"]) for p in scored),
        "citations_hit": sum(p["hits"] for p in scored),
        "citations_by_url": sum(p["by_url"] for p in scored),
        "rows": sum(p["rows"] for p in per),
        "per_indicator": per,
    }


def render(result: dict, markdown: bool) -> str:
    econ = result["economy"]
    ind_hit, ind_all = result["indicators_hit"], result["indicators_in_key"]
    cit_hit, cit_all = result["citations_hit"], result["citations_in_key"]
    pct = (100.0 * ind_hit / ind_all) if ind_all else 0.0
    head = (f"{econ} · pillars {', '.join(map(str, result['pillars']))} — "
            f"indicators reached {ind_hit}/{ind_all} ({pct:.0f}%) · "
            f"citations matched {cit_hit}/{cit_all} "
            f"({result['citations_by_url']} by URL) · {result['rows']} rows")
    if not result["runs"]:
        return head + "\n  (no run found in outputs/ — run main.py first)"

    lines = [head]
    if markdown:
        lines = [f"### {head}", "",
                 "| Indicator | Panel's citations | Found | Also cited by us |",
                 "| :--- | :--- | :--- | :--- |"]
    for p in result["per_indicator"]:
        if not p["citations"]:
            continue
        got = "".join({"url": "●", "name": "○"}.get(c["how"], "·") for c in p["citations"])
        labels = "; ".join(c["label"][:46] for c in p["citations"][:3])
        if len(p["citations"]) > 3:
            labels += f" (+{len(p['citations']) - 3})"
        extra = "; ".join(e[:34] for e in p["extra"][:2]) or "—"
        if markdown:
            lines.append(f"| {p['code']} | {labels} | `{got}` | {extra} |")
        else:
            lines.append(f"  {got:<6} {p['code']:<7} {labels[:74]}")
            if p["extra"]:
                lines.append(f"         also: {extra[:70]}")
    if markdown:
        lines += ["", "● matched by URL · ○ matched by name · · not found"]
    else:
        lines.append("  ● by URL   ○ by name   · not found")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economy", nargs="+", default=["CN", "IN", "MN"],
                    help="economy codes with a sheet in the Round-2 database")
    ap.add_argument("--pillar", nargs="+", type=int, default=[6, 7])
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        print(f"answer key not found: {DB}")
        return 1
    for econ in args.economy:
        if econ not in SHEETS:
            print(f"{econ}: no sheet in the Round-2 database "
                  f"(it covers {', '.join(sorted(SHEETS))})")
            continue
        print(render(score(econ, args.pillar), args.markdown))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
