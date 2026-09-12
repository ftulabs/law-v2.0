"""OCR on a script it has no model for does not fail. It transliterates.

Measured 2026-09-12 against `laoofficialgazette.gov.la`, whose gazette PDFs are scans. The
shipped engine is RapidOCR, whose models are Latin and Han. Asked to read the Lao Cybersecurity
Law it returned, confidently and with no error:

    "144. lani. ./Uun Ueaguyojojj?u, 5un..06.aamn.2025.. nneian Bww 6 1 2ey an ge 1 uan 77/awg"

That is 100% Latin characters and not one word of any language, and it flowed through extraction
into four provisions that would have reached the Verbatim Snippet column as a citation of a real
Lao statute. A false citation of a law that exists is worse than a missing row, because it
looks like evidence.

`backend/pipeline/ocr.py` now returns "" for it — the same call the pipeline already makes for
an unrendered JS shell, where site chrome would otherwise be mapped as law — and the
orchestrator says which engine and what to change.

THE TEST THAT MATTERS MOST HERE IS THE NEGATIVE ONE. Several of these portals publish an
English translation beside the native text; `laoofficialgazette.gov.la` carries "Accounting Law
2013 - engl revised 5 nov 2014". An English translation also scores 0% on the Lao script, so a
rule that only looked at script coverage would delete it.
"""
from __future__ import annotations

import pytest

from backend.pipeline.ocr import looks_like_english, script_coverage, text_is_unreadable

GIBBERISH = ("144. lani. ./Uun Ueaguyojojj?u, 5un..06.aamn.2025.. nneian Bww 6 1 2ey an ge 1 "
             "uan 77/awg, ou 20 tauju 2025; tgc auuan 163/awg, 6u 25 jnu 2025; na&nn ") * 6
ENGLISH = ("Article 1. This Law defines the principles and regulations on the accounting of "
           "enterprises and organisations in order to ensure that information is accurate and "
           "may be used by the State for the purposes of this Act. ") * 5
LAO = "ກົດໝາຍວ່າດ້ວຍ ຄວາມປອດໄພໄຊເບີ ມາດຕາ ໜຶ່ງ ຈຸດປະສົງ ຂອງກົດໝາຍສະບັບນີ້ " * 12


def test_transliterated_noise_is_dropped():
    assert text_is_unreadable(GIBBERISH, "LA")


def test_an_english_translation_is_kept():
    """The negative case the rule exists to protect. This is a real Lao gazette document."""
    assert script_coverage(ENGLISH, "LA") == 0.0, "the premise: it has no Lao characters at all"
    assert looks_like_english(ENGLISH)
    assert not text_is_unreadable(ENGLISH, "LA")


def test_the_native_text_is_kept():
    assert not text_is_unreadable(LAO, "LA")


@pytest.mark.parametrize("economy", ["SG", "AU", "MY", "IN"])
def test_a_latin_script_economy_is_never_touched(economy):
    """There is nothing to check: Latin characters in a Latin-script economy prove nothing
    either way, so the rule must not have an opinion."""
    assert script_coverage(ENGLISH, economy) is None
    assert not text_is_unreadable(ENGLISH, economy)
    assert not text_is_unreadable(GIBBERISH, economy)


def test_too_little_text_is_not_judged():
    """A title page or a cover sheet is not evidence that the document is unreadable."""
    assert script_coverage("144. lani.", "LA") is None
    assert not text_is_unreadable("144. lani.", "LA")


@pytest.mark.parametrize("economy, text", [
    ("CN", "第一条 为了规范数据出境活动，保护个人信息权益，维护国家安全和社会公共利益，" * 8),
    ("TH", "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล มาตรา หนึ่ง พระราชบัญญัตินี้เรียกว่า " * 12),
    ("MN", "1 дүгээр зүйл.Хуулийн зорилт 1.1.Энэ хуулийн зорилт нь Монгол Улсад " * 12),
    ("RU", "Об утверждении Правил принятия решения о запрещении трансграничной передачи " * 12),
])
def test_every_non_latin_economy_keeps_its_own_script(economy, text):
    assert not text_is_unreadable(text, economy), economy
