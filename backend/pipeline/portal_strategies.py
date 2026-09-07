"""Reusable portal shapes. A portal that does not fit one gets its own module.

India (one record per SECTION) and Mongolia (POST export, fleeting-vowel title matching) are
the standing proof that not every portal fits a shape, and forcing them into one would mean
writing code in YAML. These are the shapes that recur.
"""
from __future__ import annotations

from typing import Callable, Iterable

from .portal import Log, portal_get


def paginated_index(client, log: Log, *, page_url: str, row_selector: str,
                    link_filter: Callable[[str], bool] | None = None,
                    max_pages: int = 50) -> list[tuple[str, str]]:
    """Walk `page_url.format(page=N)` from 1, collecting (absolute_url, title) rows.

    Stops at the first page that adds nothing new. That guard is not defensive padding: a
    portal which IGNORES its own page parameter returns the same rows forever, and Singapore's
    SSO is exactly such a portal (it ignores `CurrentPage` — verified 2026-08-01, which is why
    SG needs a sort-window union rather than this strategy). Without the guard a run pays
    `max_pages` requests for one page of documents.
    """
    import httpx
    from bs4 import BeautifulSoup

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = page_url.format(page=page)
        r = portal_get(client, url, log)
        if r is None:
            log(f"[portal] pagination stopped at page {page}: no response")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        added = 0
        for a in soup.select(row_selector):
            href = a.get("href") or ""
            if not href or (link_filter and not link_filter(href)):
                continue
            absolute = str(httpx.URL(url).join(href))
            if absolute in seen:
                continue
            seen.add(absolute)
            out.append((absolute, a.get_text(" ", strip=True)))
            added += 1
        log(f"[portal] page {page}: +{added} rows ({len(out)} total)")
        if added == 0:
            break
    return out
