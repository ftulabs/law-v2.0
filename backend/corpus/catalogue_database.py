"""L0 for the economies that have no portal enumerator yet — seeded from the panel's Database.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is an EVALUATION corpus. It reads the instruments the RDTII panel itself cited in
`ESCAP-RDTII-2.1_ Round 2 Database.xlsx`, resolves each to a URL the panel gave, and writes L0
rows so `corpus.build` can fetch, extract and split them like any other corpus.

It is NOT discovery, and it must never be mistaken for it. The scored path takes an economy and
a pillar and finds the law itself; seeding from the answer key would be exactly the "baked
corpus" the rules forbid. Two things keep the separation real rather than promised:

  * The live pipeline never reads the corpus store. `backend/pipeline/*` imports nothing from
    `backend/corpus/*` — checked, not assumed — so nothing seeded here can reach a submission.
  * Every row is stamped `seed: rdtii_database` in `catalogue_json`, and `sweep_database()`
    refuses to run for an economy that has a real portal enumerator in `catalogue.ADAPTERS`.

Why it is worth having: without a corpus an economy cannot be measured at all. Retrieval recall,
the per-economy call budget, extraction quality and the splitter's behaviour on an unfamiliar
drafting style are all measured against a built corpus, which is why every number this project
holds today comes from SG, AU and MY. This makes the other seven answerable.

THE HARD PART IS URL ATTRIBUTION
--------------------------------
A Database row lists several instruments and several references with no correspondence between
them — `backend/eval/linkage.py` records the same trap, where taking a row's URLs as keys for
each of its names linked "Privacy Act 1988" to the Security of Critical Infrastructure Act. So
a URL is attached to a law only when:

  * the row cites exactly ONE instrument, so the pairing is unambiguous, or
  * the URL's own path spells out the instrument — at least two distinctive tokens of the law
    name, covering at least half of them. That is the identical test linkage.py uses, and it is
    what rescues a regulator PDF whose filename is descriptive while its title is a blob.

Anything else is left unattached and REPORTED BY NAME, because a wrong URL silently corrupts
every number computed from the corpus afterwards, and a silent hole is the expensive kind.
"""
from __future__ import annotations

import json
import re
from typing import Callable
from urllib.parse import urlsplit

from . import store

Log = Callable[[str], None]

#: Hosts that are the economy's own official publisher. The panel frequently cites a commercial
#: mirror instead — for Russia, 24 of 28 references are base.garant.ru or consultant.ru — and
#: the distinction is recorded per row rather than used to drop anything: for MEASUREMENT the
#: text is what matters, but a reader has to be able to see which rows rest on an unofficial copy.
OFFICIAL_HOSTS = re.compile(
    r"(\.gov\.[a-z]{2}$|\.gov\.[a-z]{2}\.[a-z]{2}$|\.gov$"
    r"|\.go\.(?:id|th|jp|kr)$|\.gov\.cn$|nic\.in$|legalinfo\.mn$"
    r"|pravo\.gov\.ru$|zan\.kz$|krisdika\.go\.th$|mj\.gov\.tl$"
    r"|samr\.gov\.cn$|cac\.gov\.cn$|sac\.gov\.cn$|pbc\.gov\.cn$|miit\.gov\.cn$)", re.I)


def _host(url: str) -> str:
    return (urlsplit(url).netloc or "").lower().removeprefix("www.")


def _is_official(url: str) -> bool:
    return bool(OFFICIAL_HOSTS.search(_host(url)))


def _url_names_this_law(url: str, law: str) -> bool:
    """Does the URL's own path spell out this instrument? (linkage.py's test, same thresholds.)"""
    from ..eval.linkage import _tokens
    want = _tokens(law)
    if len(want) < 2:
        return False
    words = set(re.findall(r"[a-z]{3,}", urlsplit(url).path.lower()))
    hit = want & words
    return len(hit) >= 2 and len(hit) / len(want) >= 0.5


def enumerate_from_database(economy: str, log: Log = print) -> list[dict]:
    """L0 rows for one economy, from the panel's own citations."""
    from ..eval.ground_truth import load_labels

    economy = economy.upper()
    by_law: dict[str, dict] = {}
    unattached: list[str] = []

    # Attribution is a join on the LAW NAME across every row, not a decision taken row by row.
    # The panel cites the same instrument from several indicators, and it is often unambiguous
    # in one of them and buried in a four-law list in the next: Mongolia's Law on Personal Data
    # Protection is alone in the 6.2 row and one of four in the 6.3 row. Deciding per row
    # reported it as unattached and dropped it from the corpus — while its URL was sitting in
    # the row above. Collect first, judge once at the end.
    for row in load_labels():
        if row.economy != economy or row.kind != "provision":
            continue
        urls = list(dict.fromkeys(row.portal_urls + row.other_urls))   # official first, deduped
        for law in row.laws:
            if len(law) < 5:
                continue
            e = by_law.setdefault(law, {"urls": [], "indicators": set()})
            e["indicators"].add(row.indicator_id)
            mine = urls if len(row.laws) == 1 else [
                u for u in urls if _url_names_this_law(u, law)]
            for u in mine:
                if u not in e["urls"]:
                    e["urls"].append(u)

    for law, e in list(by_law.items()):
        if not e["urls"]:
            del by_law[law]
            unattached.append(f"{','.join(sorted(e['indicators']))} · {law[:60]}")

    rows: dict[str, dict] = {}
    for law, e in sorted(by_law.items()):
        # Prefer the economy's own publisher; fall back to whatever the panel gave.
        url = next((u for u in e["urls"] if _is_official(u)), e["urls"][0])
        lid = store.law_id(economy, url)
        if lid in rows:
            # Two cited instruments resolving to one document is normal — an Act and the
            # amendment that inserted the article both point at the consolidated text. Keep the
            # first title and record the other, rather than fetching the same body twice.
            extra = json.loads(rows[lid]["catalogue_json"])
            extra.setdefault("also_cited_as", []).append(law)
            rows[lid]["catalogue_json"] = json.dumps(extra, ensure_ascii=False)
            continue
        rows[lid] = {
            "law_id": lid, "economy": economy, "portal": _host(url),
            "title": re.sub(r"\s+", " ", law).strip()[:400],
            "law_number": None, "source_url": url, "body_url": None,
            "collection": "act", "status": "active",
            "catalogue_json": json.dumps({
                "seed": "rdtii_database",
                "official_publisher": _is_official(url),
                "indicators": sorted(e["indicators"]),
                "all_cited_urls": e["urls"][:8],
            }, ensure_ascii=False),
        }

    official = sum(1 for r in rows.values()
                   if json.loads(r["catalogue_json"])["official_publisher"])
    log(f"[catalogue] {economy}: {len(rows)} instruments from the Database "
        f"({official} on an official publisher, {len(rows) - official} on a mirror)")
    if unattached:
        log(f"[catalogue] {economy}: {len(unattached)} cited instrument(s) had no URL that "
            f"identifies them, so they are NOT in the corpus:")
        for u in unattached[:12]:
            log(f"[catalogue]   - {u}")
    return list(rows.values())


def sweep_database(economy: str, log: Log = print) -> dict:
    """Enumerate from the Database and upsert into `corpus_law`."""
    from .catalogue import ADAPTERS

    economy = economy.upper()
    if economy in ADAPTERS:
        raise ValueError(
            f"{economy} has a real portal enumerator (catalogue.ADAPTERS) — use that. Seeding "
            f"an economy we can already discover from the answer key would make every number "
            f"measured on it meaningless.")
    store.init()
    before = {r["law_id"] for r in store.list_laws(economy)}
    rows = enumerate_from_database(economy, log=log)
    store.save_laws(rows)
    new = {r["law_id"] for r in rows} - before
    store.log_check(economy, "catalogue_database_seed", None, len(rows), len(new),
                    {"seed": "rdtii_database", "new": len(new)})
    report = {"economy": economy, "enumerated": len(rows), "new": len(new),
              "source": "rdtii_database (EVALUATION corpus, not discovery)"}
    log(f"[catalogue] {economy}: {report}")
    return report
