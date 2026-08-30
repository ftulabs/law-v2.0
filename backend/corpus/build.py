"""L1–L3 — turn catalogue entries into stored, split, verbatim provisions.

Deliberately stops at L3. Candidate selection (L4) and LLM grading (L5) are pending the
retrieval redesign, so nothing here consults an indicator or calls a model: the output is a
neutral, reusable corpus of provisions that ANY retrieval strategy can be measured against.

Every stage reuses the shipped pipeline code rather than reimplementing it —
`fetch.fetch_to_cache`, `ocr.get_document_text`, `extraction.extract_provisions` — so a
corpus-built provision is byte-identical to one the live path would produce. Only the
*scheduling* is new: work is keyed to a law version, is resumable, and never repeats.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from ..schemas import DiscoveredDoc, DocFormat, Economy
from . import store, version as versioning

Log = Callable[[str], None]

# States that mean "this version is finished"; a rebuild skips them unless forced.
DONE = "split"


def _doc_for(law: dict, body_url: str, fmt: DocFormat) -> DiscoveredDoc:
    return DiscoveredDoc(
        doc_id=law["law_id"], economy=Economy(law["economy"]),
        title=law.get("title") or "", source_url=law.get("source_url") or body_url,
        portal=law.get("portal") or "corpus", fmt=fmt,
        law_number=law.get("law_number"), relevance_score=1.0,
    )


def _body_urls(law: dict) -> list[str]:
    """Every URL that has to be downloaded to hold this law's full text.

    Usually one. AU publishes large Acts as MULTI-VOLUME compilations, and the single-file
    URL 404s for those (see discovery._au_compilation_pdf_urls), so a law can legitimately
    map to several PDFs that must be read together."""
    from ..pipeline.discovery import _au_compilation_pdf_urls, _au_title_id, _resolve_pdf_url
    if law.get("economy") == "AU":
        tid = law.get("law_number") or _au_title_id(law.get("source_url") or "")
        if tid:
            urls = _au_compilation_pdf_urls(tid)
            if urls:
                return urls
    if law.get("body_url"):
        return [law["body_url"]]
    url, _ = _resolve_pdf_url(Economy(law["economy"]), law["source_url"])
    return [url]


def _fetch_one(law: dict, log: Log) -> tuple[dict, dict | None]:
    """L1 — resolve the body URL(s) and download them. Returns (law, fetch-info | None)."""
    import hashlib

    from ..pipeline.fetch import fetch_to_cache
    parts = []
    # The fetcher explains itself and this function used to throw the explanation away — the
    # log callback was silenced and the version was then recorded as "fetch failed", for a
    # 404, a WAF block, a DNS failure and a timeout alike. Diagnosing twenty of them meant
    # re-probing every URL by hand. Keep the last line instead; it is the one that says why.
    said: list[str] = []
    for url in _body_urls(law):
        fr = fetch_to_cache(url, log=said.append)
        if fr:
            parts.append({"url": url, "local_path": fr.local_path, "fmt": fr.fmt,
                          "sha256": fr.sha256})
    if not parts:
        return law, {"error": (said[-1] if said else "fetch failed").replace("[fetch] ", "")[:200]}
    sha = (parts[0]["sha256"] if len(parts) == 1 else
           hashlib.sha256("|".join(p["sha256"] for p in parts).encode()).hexdigest())
    return law, {"body_url": parts[0]["url"], "local_path": parts[0]["local_path"],
                 "fmt": parts[0]["fmt"], "sha256": sha, "parts": parts}


def _process_one(law: dict, fetched: dict, ocr_provider, log: Log) -> dict:
    """L2 + L3 — extract text (OCR if needed) and split into provisions."""
    from ..pipeline.extraction import extract_provisions
    from ..pipeline.ocr import get_document_text

    vkey, amendment_date = versioning.version_signal(law)
    vid = store.version_id(law["law_id"], vkey, fetched["sha256"])
    doc = _doc_for(law, fetched["body_url"], fetched["fmt"])
    doc.local_path = fetched["local_path"]

    base = {
        "version_id": vid, "law_id": law["law_id"], "economy": law["economy"],
        "version_key": vkey, "amendment_date": amendment_date,
        "content_sha256": fetched["sha256"], "body_path": fetched["local_path"],
        "fmt": fetched["fmt"].value, "fetched_at": store.now(),
        "extraction_version": store.EXTRACTION_VERSION, "state": "fetched",
    }
    try:
        from pathlib import Path
        base["bytes"] = Path(fetched["local_path"]).stat().st_size
    except Exception:  # noqa: BLE001
        pass
    store.save_version(base)

    # Multi-part law (AU multi-volume compilation): extract AND SPLIT each volume separately,
    # then merge. Concatenating the volumes first loses law text: each volume is a self-
    # contained PDF with its own contents table and page numbering, so the splitter treated
    # volume 2's opening body as a table of contents and dropped it — measured on the
    # Telecommunications (Interception and Access) Act 1979, whose data-retention Part 5-1A
    # (ss 187A-187N, the RDTII 7.3 answer) vanished entirely. Splitting per volume keeps it.
    # A section straddling the volume boundary is cut in two; that is rare and visible, where
    # the previous failure was silent.
    parts = fetched.get("parts") or [{"local_path": fetched["local_path"], "fmt": fetched["fmt"]}]
    provisions, metrics, total_chars = [], None, 0
    for n, part in enumerate(parts):
        doc.local_path, doc.fmt = part["local_path"], part["fmt"]
        text, m = get_document_text(doc, ocr_provider=ocr_provider)
        total_chars += len(text)
        provs = extract_provisions(doc, text, m)
        for p in provs:                                   # keep ids unique across volumes
            if len(parts) > 1:
                p.provision_id = f"{p.provision_id}v{n}"
        provisions.extend(provs)
        if metrics is None:
            metrics = m
        else:
            metrics.pages += m.pages
            metrics.used = metrics.used or m.used
    doc.local_path, doc.fmt = fetched["local_path"], fetched["fmt"]
    store.set_state(vid, "extracted", chars=total_chars, pages=metrics.pages,
                    ocr_used=int(bool(metrics.used)), ocr_provider=metrics.provider,
                    cer=metrics.cer)
    n = store.save_provisions(vid, law["economy"], provisions)
    shell = _looks_like_a_shell(provisions, total_chars)
    if shell:
        # NOT "split". The provisions stay on disk for audit, but `store.load_provisions`
        # filters on state == "split", so this document cannot enter retrieval, a budget
        # measurement or a recall figure while it holds no law.
        store.set_state(vid, "shell", error=shell, provisions_n=n)
        log(f"[build] SHELL — {shell}: {law.get('title', '')[:52]}")
    else:
        store.set_state(vid, DONE, provisions_n=n)
    return {"law_id": law["law_id"], "version_id": vid, "provisions": 0 if shell else n,
            "chars": total_chars, "pages": metrics.pages, "ocr": bool(metrics.used),
            "title": law.get("title") or "", "scanned": bool(metrics.used),
            "shell": bool(shell)}


def _looks_like_a_shell(provisions: list, chars: int) -> str | None:
    """Is this a landing page, a viewer frame or an abstract rather than the law? Reason, or None.

    This guard exists because its absence was expensive and completely silent. Indonesia's
    corpus was nine `peraturan.bpk.go.id` ABSTRACT pages — "MATERI POKOK PERATURAN Abstrak…",
    a summary of the statute with not one article in it — and Russia's was the IPS frameset,
    586 characters of chrome around an iframe. Both were recorded as documents built
    successfully, each contributing exactly one provision, and every number computed from
    those corpora silently included them. The symptom that eventually gave it away was
    chars-per-provision, which nothing was watching.

    The test is deliberately narrow: ONE provision, that provision being the whole document
    (so no article marker of any kind was found, in any of the languages the splitter knows),
    and short. A genuinely short single-article instrument does exist — a one-article amending
    decree — so the length bound is what keeps this from swallowing one, and even then the
    document is marked rather than deleted.
    """
    if len(provisions) != 1 or chars >= 8_000:
        return None
    if (provisions[0].article_section or "").strip() != "(document)":
        return None
    return (f"no article marker found in {chars} characters — this is probably a landing page, "
            f"viewer frame or abstract, not the instrument")


def build(economy: str, laws: list[dict] | None = None, log: Log = print,
          limit: int | None = None, force: bool = False,
          ocr_provider_name: str | None = None, extract_workers: int | None = None) -> dict:
    """Fetch → extract → split every law in `laws` (default: the whole catalogue).

    Fetching is SEQUENTIAL on purpose — one host, `crawl_delay_seconds` apart; SSO already
    answers a burst with an empty 202. Extraction/splitting is CPU/IO-bound and independent
    per document, so it runs on a thread pool behind the fetch loop.
    """
    from ..config import settings
    from ..providers import get_ocr_provider
    store.init()
    economy = economy.upper()
    laws = laws if laws is not None else store.list_laws(economy)
    if limit:
        laws = laws[:limit]
    ocr = get_ocr_provider(ocr_provider_name, economy=economy) if ocr_provider_name \
        else get_ocr_provider(economy=economy)

    known = store.versions_for([law["law_id"] for law in laws])
    todo = []
    for law in laws:
        v = known.get(law["law_id"])
        if not force and v and v.get("state") == DONE:
            continue
        todo.append(law)
    log(f"[build] {economy}: {len(laws)} laws, {len(laws)-len(todo)} already built, {len(todo)} to do")

    workers = extract_workers or settings.extraction_concurrency
    t0 = time.perf_counter()
    done = failed = provisions = 0
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = []
        for i, law in enumerate(todo, 1):
            law2, fetched = _fetch_one(law, log)
            if fetched is None or "error" in fetched:
                failed += 1
                why = (fetched or {}).get("error", "fetch failed")
                vid = store.version_id(law["law_id"], None, None)
                store.save_version({"version_id": vid, "law_id": law["law_id"],
                                    "economy": economy, "state": "failed", "error": why})
                log(f"[build] {i}/{len(todo)} FETCH-FAIL [{why[:48]}] {law.get('title','')[:44]}")
                continue
            futures.append(pool.submit(_process_one, law2, fetched, ocr, log))
            if i % 25 == 0 or i == len(todo):
                log(f"[build] {economy} fetched {i}/{len(todo)} "
                    f"({time.perf_counter()-t0:.0f}s elapsed)")
        for fut in as_completed(futures):
            try:
                res = fut.result()
                results.append(res)
                done += 1
                provisions += res["provisions"]
                if done % 25 == 0:
                    log(f"[build] {economy} processed {done}/{len(futures)} "
                        f"({provisions} provisions)")
            except Exception as e:  # noqa: BLE001 — one bad document must not stop the corpus
                failed += 1
                log(f"[build] process error: {type(e).__name__}: {e}")
    report = {"economy": economy, "attempted": len(todo), "built": done, "failed": failed,
              "shells": sum(1 for r in results if r.get("shell")),
              "provisions": provisions, "seconds": round(time.perf_counter() - t0, 1),
              "scanned_docs": sum(1 for r in results if r["scanned"]),
              "pages": sum(r["pages"] or 0 for r in results)}
    log(f"[build] {report}")
    return report
