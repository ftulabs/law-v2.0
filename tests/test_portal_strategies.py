"""paginated_index: the shape shared by Laos, China and any portal with a page parameter."""
from backend.pipeline import portal, portal_strategies


class _Resp:
    def __init__(self, text):
        self.status_code = 200
        self.text = text
        self.content = text.encode()


class _Client:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return _Resp(self._pages.get(url, "<html></html>"))


_PAGE1 = """<html><body>
  <a href="/index.php?r=site/display&id=11">Law on Electronic Data Protection</a>
  <a href="/index.php?r=site/display&id=12">Law on Cybersecurity</a>
  <a href="/index.php?r=site/index&Document_page=2">next</a>
</body></html>"""

_PAGE2 = """<html><body>
  <a href="/index.php?r=site/display&id=13">Law on Telecommunications</a>
</body></html>"""


def test_paginated_index_walks_pages_and_returns_absolute_urls(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page={page}"
    client = _Client({base.format(page=1): _PAGE1, base.format(page=2): _PAGE2})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=2)
    urls = [u for u, _ in rows]
    assert len(rows) == 3
    assert all(u.startswith("https://laoofficialgazette.gov.la/") for u in urls)
    assert "id=13" in urls[-1], "page 2 must have been walked"


def test_paginated_index_stops_when_a_page_adds_nothing_new(monkeypatch):
    """A portal that ignores its own page parameter returns the same rows forever. Laos'
    detail ids come from the list page, so a runaway walk is real cost for zero documents."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://example.gov/list?p={page}"
    client = _Client({base.format(page=n): _PAGE1 for n in range(1, 12)})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=10)
    assert len(rows) == 2, "identical pages must collapse, not accumulate"
    assert len(client.calls) == 2, "the walk must stop at the first page adding nothing"


def test_paginated_index_deduplicates_across_pages(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://example.gov/list?p={page}"
    client = _Client({base.format(page=1): _PAGE1, base.format(page=2): _PAGE1 + _PAGE2})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=2)
    assert len({u for u, _ in rows}) == len(rows) == 3
