"""A parser that gives up must not be mistaken for a page with no law in it.

www.gov.cn — where China's State Council publishes its administrative regulations — emits a
stray `</html>` in the page header, thousands of bytes before the real one. lxml obeys it,
treats the document as finished and discards everything after, INCLUDING the entire statute.
It does not raise, warn, or return an error: it returns a short, perfectly valid string.

The cost was nine of the ten Chinese documents the corpus had recorded as "shell", losing 25x
to 155x of statute text — the Counter-Espionage Law, the Network Data Security Regulation, the
Industrial and Telecom Data Protection Measures among them, and with them thirteen of the
twenty provisions the panel cites for China that our submission missed. Every one of those runs
completed normally and reported no evidence, which reads exactly like an economy whose law does
not exist.

`ocr._soup` therefore checks the parse against a regex estimate of the visible text and retries
with html.parser when the yield has collapsed. These tests pin both halves: that the collapse
is detected, and that a page which really is nearly empty is still reported as nearly empty.
"""
from __future__ import annotations

import pytest

from backend.pipeline.ocr import _html_to_text, _soup, _visible_estimate

# The gov.cn shape, reduced to the one construct that matters. The statute text sits AFTER a
# premature </html>; a parser that honours it returns the site chrome and nothing else.
PREMATURE_CLOSE = """<!DOCTYPE html>
<html><head><title>网络出版服务管理规定_中国政府网</title></head>
<body>
<div class="head"><a href="/">首页</a> | <a href="/en">EN</a></div>
</html>
<div class="article">
  <div class="pages_content" id="UCAP-CONTENT">
    <p>网络出版服务管理规定</p>
    <p>第一条 为了规范网络出版服务秩序，根据国务院有关规定，制定本规定。</p>
    <p>第七条 图书、音像、电子、报纸、期刊出版单位从事网络出版服务，应当具备下列条件。</p>
  </div>
</div>
</body></html>
"""


def test_the_statute_after_a_premature_close_tag_is_not_lost():
    text = _html_to_text(PREMATURE_CLOSE)
    assert "第一条" in text, "the operative article was discarded with the rest of the document"
    assert "第七条" in text
    assert len(text) > 60


def test_lxml_alone_really_does_lose_it():
    """The guard rail for the guard rail. If a future lxml stops honouring the stray tag this
    test fails, and `_soup`'s fallback becomes dead weight that should be reconsidered rather
    than left in place uncomprehended."""
    from bs4 import BeautifulSoup

    lxml_only = BeautifulSoup(PREMATURE_CLOSE, "lxml").get_text(strip=True)
    assert "第一条" not in lxml_only, "lxml no longer truncates here — re-examine ocr._soup"


def test_a_genuinely_short_page_stays_short():
    """The fallback must not manufacture text. openstd.samr.gov.cn's record page is 561
    characters under both parsers and is correctly left alone; only a COLLAPSE triggers the
    retry, not merely a small page."""
    tiny = "<html><body><div class='head'>标准信息</div><p>GB/T 35273</p></body></html>"
    assert len(_html_to_text(tiny)) < 40


def test_the_estimate_ignores_script_and_style_bodies():
    """The estimate is the trigger, so it must not count a megabyte of JavaScript as text that
    a parse ought to have produced — every script-heavy portal page would then retry."""
    page = ("<html><body><script>var x = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';</script>"
            "<style>.a{color:#fff;background:#000;font-family:serif}</style>"
            "<!-- a comment that is quite long and says nothing at all -->"
            "<p>Section 1. The real text.</p></body></html>")
    assert _visible_estimate(page) < 40


@pytest.mark.parametrize("html", [PREMATURE_CLOSE, "<html><body><p>Section 1. Text.</p></body></html>"])
def test_soup_always_returns_a_usable_parse(html):
    assert _soup(html).get_text(strip=True)
