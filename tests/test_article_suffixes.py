"""Inserted-article suffixes that make a DIFFERENT article: Thai ทวิ/ตรี (bis/ter) and Russian
"10.2-1". Without them two articles shared one label (measured 2026-09-26: 3 in TH's District
Courts Act, 2 in the Revenue Code; duplicate 10.2 / 15.x in RU 149-FZ)."""
from backend.pipeline.extraction import _ARTICLE_RE_RU, _ARTICLE_RE_TH


def test_thai_bis_ter_are_part_of_the_label():
    t = "มาตรา ๗ ทวิ ให้\nมาตรา ๗ ตรี ก\nมาตรา ๘ ผู้ใด\nมาตรา ๙ ฉบับนี้"
    assert [m.group(1) for m in _ARTICLE_RE_TH.finditer(t)] == [
        "มาตรา ๗ ทวิ", "มาตรา ๗ ตรี", "มาตรา ๘", "มาตรา ๙"]   # "ฉบับ" is a word, not ฉ (sexies)


def test_russian_hyphenated_article_is_its_own_label():
    t = "Статья 10.2-1. Особенности\nСтатья 10.2. Особенности\nСтатья 12. Трансграничная"
    assert [m.group(1) for m in _ARTICLE_RE_RU.finditer(t)] == [
        "Статья 10.2-1", "Статья 10.2", "Статья 12"]
