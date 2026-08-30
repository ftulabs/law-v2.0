"""Two measurement bugs that each produced a confident, wrong ZERO.

Neither was a pipeline defect. Both were in the code that SCORES the pipeline, which is worse:
a broken metric does not fail, it reports. Both were about to be handed over as findings —
"Mongolia reaches 0 of 8 answer-key indicators", "China's provision recall is 0.000" — and
both were artefacts of comparing two languages with an English-only comparator.

The tell in each case was that the number could not rise. China's provision recall was
measured with k set to the ENTIRE corpus, so retrieval had no way to affect it; a metric that
cannot move is not measuring anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.eval.harness import _han_to_int, section_key      # noqa: E402
from tools.compare_to_key import url_keys                      # noqa: E402


# ── the panel numbers in Arabic, the statute numbers in its own script ────────────────────
def test_han_numbered_articles_are_comparable_with_the_key():
    """A Chinese statute numbers its articles 第三十五条 and the panel cites "Article 35". The
    Arabic-digit pattern sees no digits at all, so every Chinese provision keyed to None and
    the measured recall was 0.000 by construction — at k = the whole corpus."""
    assert section_key("第一条") == "1"
    assert section_key("第十条") == "10"
    assert section_key("第三十五条") == "35"
    assert section_key("第一百零八条") == "108"


def test_thai_numbered_articles_are_comparable_with_the_key():
    assert section_key("มาตรา ๑๐") == "10"
    assert section_key("มาตรา ๗") == "7"


def test_han_numerals_convert_the_way_chinese_actually_writes_them():
    assert _han_to_int("十") == 10          # a bare 十 is one ten, not zero
    assert _han_to_int("十五") == 15
    assert _han_to_int("二十") == 20
    assert _han_to_int("一百零八") == 108
    assert _han_to_int("hello") is None


def test_the_existing_keys_still_behave():
    """The Round-1 economies are the ones with measured numbers; nothing here may move them."""
    assert section_key("Section 199") == "199"
    assert section_key("Regulation 3.1.1") == "3.1.1"
    assert section_key("APP 8") == "app8"
    assert section_key("Part 3") is None, "a structural heading is not a provision"
    assert section_key("32 дугаар зүйл") == "32"


# ── the panel names the law in English, the portal publishes it in another language ───────
def test_a_run_and_the_key_are_joined_on_the_document_url():
    """Our Mongolian run cited «ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ»; the key says "Law on
    Personal Data Protection". No normalisation bridges those — but both point at the same
    legalinfo.mn document, and the comparator reported 0 of 8 until it looked."""
    ours = url_keys("https://legalinfo.mn/mn/detail?lawId=16390288615991")
    theirs = url_keys("https://legalinfo.mn/mn/detail?lawId=16390288615991")
    assert ours & theirs


def test_the_same_law_under_two_url_shapes_still_joins():
    """legalinfo.mn serves one law as both /mn/detail/108 and /mn/detail?lawId=108."""
    assert url_keys("https://legalinfo.mn/mn/detail/108") & \
           url_keys("https://legalinfo.mn/mn/detail?lawId=108")


def test_a_wayback_snapshot_joins_to_the_live_url():
    """The key cites Wayback snapshots for several Mongolian instruments."""
    live = url_keys("https://legalinfo.mn/mn/detail?lawId=16390263044601")
    snap = url_keys("https://web.archive.org/web/20250301225053/"
                    "https://legalinfo.mn/mn/detail?lawId=16390263044601")
    assert live & snap


def test_different_documents_do_not_join():
    assert not url_keys("https://legalinfo.mn/mn/detail/108") & \
               url_keys("https://legalinfo.mn/mn/detail/523")
    assert not url_keys("https://www.gov.cn/a/content_5616919.htm") & \
               url_keys("https://www.cac.gov.cn/b/c_1119867116.htm")
