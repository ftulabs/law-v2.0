"""Trailing-furniture trimming, and the provisions it silently deleted.

`_trim_trailing_furniture` was added so the last provision of a Chinese web page would stop
carrying the site's footer into the Verbatim Snippet — PIPL article 74 was arriving with a
close button, a WeChat link and a CMS stamp attached. Its docstring claimed it was
"conservative by construction: it can only ever eat the tail".

That is true of a multi-line page and false of a body that is ONE line, which is exactly how
India Code publishes a section. Two things then went wrong at once:

  * `produced by` is in the CMS pattern to catch a "Produced by …" footer, and it was matched
    with `.search()` against the whole line. Indian statutory prose says "the hash result
    produced by the algorithm" (IT Act s.3) and "have been produced by a computer" (s.43), so
    the pattern fired in the middle of the law;
  * the line was the entire provision, so popping it left nothing.

Sections 3 and 43 of the Information Technology Act 2000 therefore extracted as ZERO
provisions. No error, no log line, no empty-looking output — the Act simply had two fewer
sections than it has.
"""
import pytest

from backend.pipeline.extraction import _is_furniture_line, _trim_trailing_furniture


def test_a_single_line_provision_survives():
    """The regression in one assertion. Trimming must never return nothing."""
    body = ("3. Authentication of electronic records. --(1) Subject to the provisions of this "
            "section any subscriber may authenticate an electronic record by affixing his "
            "digital signature.")
    assert _trim_trailing_furniture(body) == body


@pytest.mark.parametrize("line", [
    "the hash result produced by the algorithm; (b) that two electronic records can produce "
    "the same hash result using the algorithm",
    "records that have been produced by a computer, computer system or computer network and "
    "are intended to be used in evidence",
])
def test_statutory_prose_is_not_mistaken_for_a_cms_footer(line):
    """A footer is short. A clause that happens to contain the same words is not."""
    assert not _is_furniture_line(line)


@pytest.mark.parametrize("line", [
    "关闭",
    "微信",
    "（责编：张栋）",
    "版权所有 京ICP备05070218号",
    "Produced by CMS",
])
def test_real_page_furniture_is_still_trimmed(line):
    assert _is_furniture_line(line)


def test_the_chinese_page_footer_is_still_removed():
    """The reason the function exists: PIPL article 74 was carrying the site's chrome into the
    Verbatim Snippet column."""
    body = "第七十四条 本法自2021年11月1日起施行。\n关闭\n微信\n扫一扫\n打印\n（责编：张栋）"
    assert _trim_trailing_furniture(body) == "第七十四条 本法自2021年11月1日起施行。"


def test_a_page_that_is_nothing_but_furniture_is_left_alone():
    """Returning the input unchanged is the honest outcome: something else decides whether a
    document with no law in it belongs in the corpus. Silently emptying it here would hide
    that decision."""
    body = "关闭\n微信\n打印"
    assert _trim_trailing_furniture(body) == body


def test_only_the_tail_is_trimmed_on_a_multi_line_body():
    body = ("Article 1. This is the operative text of the provision and it ends properly.\n"
            "More operative text, also ending in a full stop.\n"
            "关闭")
    out = _trim_trailing_furniture(body)
    assert out.endswith("also ending in a full stop.")
    assert "关闭" not in out
