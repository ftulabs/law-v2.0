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


def test_lxml_truncation_is_version_dependent_and_the_fallback_is_still_earned():
    """The guard rail for the guard rail — and it has already fired once, so read this.

    The original form of this test asserted flatly that lxml truncates here, on the reasoning
    that if a future lxml stopped honouring the stray tag then `_soup`'s fallback would be dead
    weight to reconsider rather than leave in place uncomprehended. That reasoning was right and
    the assertion was wrong: the behaviour is not a property of lxml, it is a property of the
    **bundled libxml2**, and the two disagree across installs of the same requirement line.

    Measured 2026-09-09 on the same commit:
      · lxml 6.1.0 / libxml2 2.11.9 (a developer machine)  -> TRUNCATES, 21 characters survive
      · the lxml CI resolves from `lxml>=5.2`               -> does NOT truncate
    So the flat assertion passed locally and failed in CI, which is the least useful place for
    a test to disagree with itself.

    `requirements.txt` pins only `lxml>=5.2`, so an install today can land on either side. The
    fallback therefore stays, and it is free where it is not needed: `_soup` compares the yield
    against `_visible_estimate` and returns the lxml parse untouched when nothing collapsed, so
    a modern libxml2 never pays for the second parse.

    What this test now pins is the honest pair: whichever way this environment's libxml2
    behaves, the statute must survive `_html_to_text`. The day EVERY supported lxml stops
    truncating, `requirements.txt` can raise its floor and the fallback can go — this test will
    say so rather than fail obscurely.
    """
    from bs4 import BeautifulSoup

    lxml_only = BeautifulSoup(PREMATURE_CLOSE, "lxml").get_text(strip=True)
    truncates = "第一条" not in lxml_only

    # Either way, the pipeline's own path must not lose the statute. This is the claim that
    # actually protects the corpus, and it holds on both sides of the version split.
    assert "第一条" in _html_to_text(PREMATURE_CLOSE)

    if not truncates:
        import lxml.etree as _et
        pytest.skip(
            f"this libxml2 ({'.'.join(map(str, _et.LIBXML_VERSION))}, lxml {_et.__version__}) "
            f"no longer honours the premature </html>, so the fallback is not exercised here. "
            f"It is still earned on older builds — requirements.txt allows lxml>=5.2. Raise "
            f"that floor and ocr._soup's fallback can be removed.")

    # This environment DOES truncate, so prove the fallback is what saves the document.
    assert len(lxml_only) < 60, (
        f"lxml kept {len(lxml_only)} characters — the collapse this test describes is not "
        f"happening as measured; re-examine ocr._soup rather than adjusting this number")


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
