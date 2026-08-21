"""Reconnaissance on the Round-2 portals, before any of them is trusted.

`data/sources.yaml` marks the China / India / Mongolia lanes `verified: false`. That flag is
honest but useless on its own — it does not say WHICH way they fail, and the three failure
modes need completely different fixes:

    unreachable   the host does not answer us at all (geo-block, WAF, TLS)      -> browser fetch
    JS shell      HTTP 200 with no statute text in the body, only an app shell  -> portal API
    not indexed   the host is fine but the search engine has almost nothing     -> own catalogue

Malaysia already taught us the third one: Google returned only the homepage for
`site:lom.agc.gov.my`, so the websearch lane silently produced zero Acts until we wrote an
adapter against the portal's own JSON catalogue. This tool asks that question up front instead
of discovering it during a judged run.

robots.txt is fetched and reported FIRST. A portal that disallows us is a compliance answer,
not an obstacle to route around — `peraturan.bpk.go.id` already sits in that category.

    python tools/probe_portals.py                 # every unverified lane
    python tools/probe_portals.py --economy CN
    python tools/probe_portals.py --no-search     # skip the search-index probe (saves API quota)
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                        # noqa: E402
from backend.pipeline.discovery import load_sources        # noqa: E402
from backend.schemas import Economy                        # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

# Text that means "an app shell rendered this, the law is not in the HTML we got".
_JS_SHELL = re.compile(r"<app-root|ng-version|__NEXT_DATA__|<div id=\"root\">\s*</div>"
                       r"|please enable javascript|window\.__NUXT__", re.I)
# Statute-ish vocabulary per script, used only to answer "is there legal text in this body?"
_LEGAL_MARKERS = {
    "CN": ("第", "条", "规定", "办法", "法"),
    "MN": ("зүйл", "хууль", "заалт"),
    "IN": ("Act", "Section", "Rules", "Chapter"),
}


@dataclass
class Probe:
    economy: str
    name: str
    url: str
    status: str = ""
    verdict: str = ""
    detail: list[str] = field(default_factory=list)


def _client():
    import httpx
    return httpx.Client(timeout=25, follow_redirects=True,
                        headers={"User-Agent": UA, "Accept-Language": "en,zh,mn;q=0.8"})


def robots(client, base: str) -> tuple[str, bool]:
    """(summary, may_we_crawl). Reported before anything else — a disallow ends the probe."""
    host = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    try:
        r = client.get(f"{host}/robots.txt")
    except Exception as exc:
        return f"robots.txt unreachable ({type(exc).__name__})", True
    if r.status_code != 200:
        return f"no robots.txt (HTTP {r.status_code})", True
    body = r.text[:4000]
    # A blanket "User-agent: * / Disallow: /" is the only case we treat as a hard stop; anything
    # narrower is a path question the crawler handles per-URL.
    blocks = re.split(r"(?im)^user-agent:", body)
    for b in blocks:
        agent = b.strip().split("\n", 1)[0].strip().lower()
        if agent in ("*", "claudebot"):
            if re.search(r"(?im)^\s*disallow:\s*/\s*$", b):
                return f"DISALLOWS {agent or '*'} on / — do not crawl", False
    return f"robots.txt present, no blanket disallow ({len(body)} B)", True


def fetch(client, url: str, economy: str) -> tuple[str, list[str]]:
    """(verdict, notes) for one URL."""
    notes: list[str] = []
    try:
        r = client.get(url)
    except Exception as exc:
        return "UNREACHABLE", [f"{type(exc).__name__}: {str(exc)[:110]}"]
    notes.append(f"HTTP {r.status_code} · {r.headers.get('content-type', '?').split(';')[0]} "
                 f"· {len(r.content)} B")
    if r.status_code >= 400:
        return "HTTP_ERROR", notes
    body = r.text
    if _JS_SHELL.search(body):
        notes.append("body is an app shell — statute text is not in this HTML")
        return "JS_SHELL", notes
    text = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    markers = _LEGAL_MARKERS.get(economy, ())
    hits = sum(1 for m in markers if m in text)
    notes.append(f"{len(text)} chars of visible text · {hits}/{len(markers)} legal markers")
    if len(text) < 500:
        return "EMPTY_BODY", notes
    return ("OK" if hits >= 2 else "NO_LEGAL_TEXT"), notes


def search_index(economy: Economy, site: str, queries: list[str]) -> tuple[str, list[str]]:
    """Does the search engine actually hold this site? The Malaysia lesson, asked directly."""
    from backend.pipeline import websearch
    if not settings.serper_api_key:
        return "SKIPPED", ["no SERPER_API_KEY configured"]
    notes, total = [], 0
    for q in queries[:3]:
        try:
            res = websearch.find_law_urls(economy, q, max_results=5, site=site)
        except Exception as exc:
            notes.append(f"{q!r}: {type(exc).__name__}")
            continue
        total += len(res)
        notes.append(f"{q!r} -> {len(res)} hits" + (f" e.g. {res[0][0][:70]}" if res else ""))
    return ("OK" if total >= 3 else "THIN_INDEX" if total else "NOT_INDEXED"), notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economy", help="restrict to one economy code")
    ap.add_argument("--no-search", action="store_true", help="skip the search-index probe")
    args = ap.parse_args()

    sources = [s for s in load_sources()
               if (not args.economy or s.get("economy") == args.economy.upper())
               and (args.economy or not s.get("verified"))]
    if not sources:
        print("No matching sources.")
        return 1

    results: list[Probe] = []
    with _client() as client:
        for s in sources:
            econ, base = s["economy"], s.get("base_url", "")
            p = Probe(economy=econ, name=s.get("name", "?"), url=base)
            print(f"\n{'=' * 78}\n{econ} · {p.name}\n  {base}")

            summary, allowed = robots(client, base)
            print(f"  robots  : {summary}")
            p.detail.append(f"robots: {summary}")
            if not allowed:
                p.verdict = "ROBOTS_DISALLOW"
                results.append(p)
                continue

            verdict, notes = fetch(client, base, econ)
            p.verdict = p.status = verdict
            for n in notes:
                print(f"  fetch   : {n}")
            print(f"  verdict : {verdict}")
            p.detail += notes

            if not args.no_search and s.get("adapter") == "websearch":
                site = s.get("site") or urlparse(base).netloc
                queries = s.get("queries") or []
                if not queries:
                    from backend.rdtii.keywords import portal_search_queries
                    queries = portal_search_queries(econ, None, name_only=False)
                sv, snotes = search_index(Economy(econ), site, queries)
                for n in snotes:
                    print(f"  search  : {n}")
                print(f"  index   : {sv}")
                p.detail.append(f"index: {sv}")
                if sv in ("NOT_INDEXED", "THIN_INDEX") and verdict == "OK":
                    p.verdict = f"{verdict}/{sv}"

            results.append(p)

    print(f"\n{'=' * 78}\nSUMMARY\n")
    for p in results:
        print(f"  {p.economy:<3} {p.name[:44]:<44} {p.verdict}")
    print("""
  OK                  body carries statute text -> the websearch lane can work
  OK/THIN_INDEX       host fine, engine holds little -> needs the portal's own catalogue (the MY fix)
  OK/NOT_INDEXED      same, worse -> a portal adapter is REQUIRED, not optional
  JS_SHELL            HTTP 200, no text -> needs the portal API or a browser fetch
  UNREACHABLE         geo-block / WAF / TLS -> browser fetch, or the economy is not viable from here
  ROBOTS_DISALLOW     do not crawl. This is an answer, not an obstacle.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
