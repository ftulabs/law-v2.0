"""Russia's principal Federal Laws: found, ranked first, and fetched at their CURRENT text.

The 2026-09-25 RU run produced 44 documents and not one was 152-ФЗ "О персональных данных".
Four silent defects, each pinned here against bytes saved from the live portal on 2026-09-26:

  1. `a1` is the TITLE field, and the configured terms were full-text phrases (HTTP 204).
  2. No `sort=` was sent, so every list was the twenty OLDEST matches.
  3. Nothing asked for a Federal Law, so the principal statute was never in the twenty.
  4. `rdk=0` is the ORIGINAL 2006 text: no article 18.1, and no article 18 part 5 — the
     data-localisation rule that is Russia's whole 6.2 answer.

Plus one extraction trap the fix exposed: an inserted article is numbered with a CSS
superscript ("Статья 18<span class=W9>1</span>"), which split as a second "Статья 18".
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path

import pytest

from backend.config import settings
from backend.pipeline import adapter_russia as RU
from backend.pipeline import portal
from backend.pipeline.extraction import extract_provisions
from backend.pipeline.ocr import _html_to_text
from backend.rdtii.indicators import get_indicators
from backend.schemas import DocFormat, Economy, OCRMetrics

FIXTURES = Path(__file__).parent / "fixtures"
FZ_LIST = FIXTURES / "ru_ips_list_frame_fz_oldest.html"     # a1=персональных данных, FZ, sort=-7
BODY_152 = FIXTURES / "ru_ips_152fz_current_excerpt.html"   # arts 1, 12, 18, 18.1, 19 at rdk=38

#: The autocomplete answer for "Федеральный закон", byte for byte (captured 2026-09-26). The
#: whole line is percent-encoded — the tab too — which the first parser missed.
AUTOCOMPLETE = ("%D4%E5%E4%E5%F0%E0%EB%FC%ED%FB%E9 %EA%EE%ED%F1%F2%E8%F2%F3%F6%E8%EE%ED%ED"
                "%FB%E9 %E7%E0%EA%EE%ED%09102000506\n"
                "%D4%E5%E4%E5%F0%E0%EB%FC%ED%FB%E9 %E7%E0%EA%EE%ED%09102000505\n")
#: The list iframe of `?docbody=&nd=102108261`, as served.
FRAMESET = ('<iframe id="list" frameborder="0" '
            'src="?doc_itself=&nd=102108261&page=1&rdk=38" onload="onDocRefsLoaded();">')


# ── the URLs ─────────────────────────────────────────────────────────────────────────────

def test_every_list_url_states_its_sort_order():
    """Omitting `sort` does NOT get the form's default (newest); it gets oldest-first. That is
    how "базы данных на территории" spent its twenty rows on 1990s treaties."""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(RU._list_url("персональных данных")).query,
                              encoding="cp1251", keep_blank_values=True)
    assert q["sort"] == [str(RU.SORT_NEWEST)]
    assert "a3" not in q


def test_the_principal_pass_asks_for_federal_laws_oldest_first():
    url = RU._list_url("персональных данных", sort=RU.SORT_OLDEST, type_code="102000505")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, encoding="cp1251",
                              keep_blank_values=True)
    assert q["a1"] == ["персональных данных"]
    assert q["a3"] == ["102000505"] and q["sort"] == ["-7"]


def test_the_type_code_is_read_by_exact_name_from_the_portals_own_autocomplete():
    """The constitutional-law line comes FIRST in the real answer; a prefix match takes it."""
    assert RU.parse_type_code(AUTOCOMPLETE) == "102000505"
    assert RU.parse_type_code(AUTOCOMPLETE, "Федеральный конституционный закон") == "102000506"
    assert RU.parse_type_code("") is None


def test_the_current_redaction_is_read_from_the_frameset():
    assert RU.parse_current_rdk(FRAMESET) == 38
    assert RU.parse_current_rdk("<html>no frame</html>") is None
    assert RU.body_url("102108261", 38).endswith("nd=102108261&page=1&rdk=38")
    assert RU.body_url("102108261").endswith("rdk=0")


def test_with_changes_is_recognised_even_with_the_portals_latin_c():
    """The portal writes "Действует c изменениями" with a LATIN c (U+0063)."""
    assert RU._has_redactions({"status": "Действует c изменениями"})
    assert not RU._has_redactions({"status": "Действует без изменений"})


# ── the ranking ──────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fz_rows():
    return RU.parse_rows(FZ_LIST.read_text(encoding="utf-8"))


def test_the_federal_law_pass_contains_the_principal_statute(fz_rows):
    """The measured fact the whole fix rests on: title + type + oldest-first reaches it."""
    assert any(r["subject"] == "О персональных данных" and "152-ФЗ" in r["designation"]
               for r in fz_rows)


@pytest.mark.parametrize("pillar", [6, 7])
def test_the_principal_law_outranks_every_other_row_of_its_own_list(fz_rows, pillar):
    """Its amendments quote its title, and before the class adjustment 152-ФЗ and 261-ФЗ tied
    at 0.5748. The stemmer's personnel ("персонала") laws must not get the principal bonus."""
    inds = get_indicators(pillar)
    for r in fz_rows:
        r["terms"] = ["персональных данных"]
    scored = sorted(((RU._relevance(r, inds), r) for r in fz_rows if RU.in_force(r)),
                    key=lambda t: -t[0])
    assert scored[0][1]["subject"] == "О персональных данных"
    personnel = [s for s, r in scored if "персонал" in r["subject"].lower()
                 and "персональных" not in r["subject"].lower()]
    amending = [s for s, r in scored if RU.is_amending(r)]
    assert personnel and amending
    assert max(personnel + amending) < scored[0][0] - 0.15


def test_critical_infrastructure_law_outranks_its_amendment_for_pillar_7():
    inds = get_indicators(7)
    law = {"designation": "Федеральный закон от 26.07.2017 № 187-ФЗ",
           "subject": "О безопасности критической информационной инфраструктуры Российской "
                      "Федерации", "terms": ["критической информационной инфраструктуры"]}
    amend = {"designation": "Федеральный закон от 07.04.2025 № 58-ФЗ",
             "subject": 'О внесении изменений в Федеральный закон "О безопасности критической '
                        'информационной инфраструктуры Российской Федерации"',
             "terms": ["критической информационной инфраструктуры"]}
    assert RU.is_principal(law) and not RU.is_principal(amend)
    assert RU._relevance(law, inds) > RU._relevance(amend, inds) + 0.15


def test_a_chamber_vote_on_a_law_is_not_a_measure():
    assert RU.is_chamber_vote({"subject": 'О Федеральном законе "О персональных данных"'})
    assert not RU.is_chamber_vote({"subject": "О персональных данных"})
    # A ratification is a Federal Law but not a principal one.
    assert not RU.is_principal({"designation": "Федеральный закон от 19.12.2005 № 160-ФЗ",
                                "subject": "О ратификации Конвенции Совета Европы"})


def test_names_term_separates_personal_data_from_personnel():
    assert RU.names_term("О персональных данных", "персональных данных")
    assert not RU.names_term("О порядке предоставления военного и гражданского персонала",
                             "персональных данных")
    assert RU.names_term("Об информации, информационных технологиях и о защите информации",
                         "защите информации")


# ── the body ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def provisions_152():
    html = RU.normalise_superscripts(BODY_152.read_text(encoding="utf-8"))
    doc = portal.make_doc(Economy.RU, RU.body_url("102108261", 38), "О персональных данных",
                          "IPS", fmt=DocFormat.HTML, law_number="Федеральный закон № 152-ФЗ")
    return extract_provisions(doc, _html_to_text(html), OCRMetrics())


def test_the_superscript_article_becomes_its_own_provision(provisions_152):
    labels = [p.article_section for p in provisions_152]
    assert "Статья 18.1" in labels, labels
    assert labels.count("Статья 18") == 1, f"18.1 split as a second 'Статья 18': {labels}"
    assert {"Статья 1", "Статья 12", "Статья 18", "Статья 19"} <= set(labels)


def test_article_18_carries_the_localisation_rule_verbatim(provisions_152):
    """Absent from the rdk=0 text entirely: it was inserted by 242-ФЗ in 2014."""
    art18 = next(p for p in provisions_152 if p.article_section == "Статья 18")
    assert ("персональных данных граждан Российской Федерации с использованием баз данных, "
            "находящихся за пределами территории Российской Федерации, не допускаются"
            in " ".join(art18.verbatim_snippet.split()))


def test_article_12_is_the_cross_border_transfer_article(provisions_152):
    art12 = next(p for p in provisions_152 if p.article_section == "Статья 12")
    assert "Трансграничная передача персональных данных" in art12.verbatim_snippet
    assert "Оператор до начала осуществления деятельности по трансграничной передаче" in (
        " ".join(art12.verbatim_snippet.split()))


def test_superscripts_only_touch_numbers_in_the_documents_own_superscript_classes():
    css = "<style>.W9{vertical-align:super;} .B{font-weight:bold}</style>"
    assert RU.normalise_superscripts(css + 'Статья 18<span class="W9" style="">1</span>.') \
        .endswith("Статья 18.1.")
    assert RU.normalise_superscripts(css + 'Статья 10<span class="W9">2-1</span>.') \
        .endswith("Статья 10.2-1.")
    untouched = css + 'Статья 18<span class="B">1</span>.'
    assert RU.normalise_superscripts(untouched) == untouched


# ── the whole adapter, offline ───────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, text: str):
        self.content = text.encode("cp1251", "replace")
        self.status_code = 200


def test_the_adapter_fetches_the_principal_first_at_its_current_redaction(monkeypatch):
    list_html = FZ_LIST.read_text(encoding="utf-8")
    body = BODY_152.read_text(encoding="utf-8")
    seen: list[str] = []
    seeded: dict[str, bytes] = {}

    def fake_get(_client, url, _log, tries=4, **_kw):
        seen.append(url)
        if "autocomplete" in url:
            return _Resp(AUTOCOMPLETE)
        if "list_itself" in url:
            # The Federal-Law pass returns the saved list; the newest pass finds nothing (204).
            return _Resp(list_html) if "a3=" in url else None
        if "docbody" in url:
            return _Resp(FRAMESET.replace("102108261", url.split("nd=")[1].split("&")[0]))
        if "doc_itself" in url:
            return _Resp(body)
        return None

    import backend.pipeline.fetch as fetch
    monkeypatch.setattr(portal, "portal_get", fake_get)
    monkeypatch.setattr(fetch, "seed_cache",
                        lambda url, data, *_a, **_k: seeded.__setitem__(url, data))
    monkeypatch.setattr(settings, "discovery_max_docs", 3)

    said: list[str] = []
    docs = RU.search_ru_ips(None, {"name": "IPS", "queries_p6": ["персональных данных"]},
                            "", Economy.RU, get_indicators(6), log=said.append)

    assert len(docs) == 3, "the budget bounds the fetches"
    assert docs[0].title == "О персональных данных"
    assert docs[0].source_url.endswith("nd=102108261&page=1&rdk=38"), docs[0].source_url
    # Only budgeted rows had a body fetched: 3 bodies, not one per row of the list.
    assert sum("doc_itself" in u for u in seen) == 3
    assert set(seeded) == {d.source_url for d in docs}
    # And the seeded body is the superscript-normalised one.
    assert "Статья 18.1".encode("utf-8") in seeded[docs[0].source_url]
    # Both passes ran, each with an explicit sort.
    lists = [u for u in seen if "list_itself" in u]
    assert any("sort=-7" in u and "a3=102000505" in u for u in lists)
    assert any("sort=7" in u and "a3=" not in u for u in lists)


def test_without_a_type_code_the_lane_says_the_principal_pass_was_skipped(monkeypatch):
    monkeypatch.setattr(portal, "portal_get", lambda *_a, **_k: None)
    said: list[str] = []
    out = RU.search_ru_ips(None, {"name": "IPS", "queries_p6": ["персональных данных"]}, "",
                           Economy.RU, get_indicators(6), log=said.append)
    assert out == []
    assert any("principal-law pass is SKIPPED" in m for m in said), said
