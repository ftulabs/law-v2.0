"""Russia's lane, driven against the portal's own saved HTML.

The fixture is the THIRD frame of `pravo.gov.ru`'s IPS search, captured live on 2026-09-12.
`data/sources.yaml` had recorded, from a probe that stopped one frame short, that these rows
"are injected client-side: neither plain HTTP nor a default browser render surfaces a single
nd= id". They are not injected at all — the probe had measured the frame that HOLDS the list.
Keeping the real bytes here is what makes that checkable instead of re-litigable.
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path

import pytest

from backend.pipeline import adapter_russia as RU
from backend.rdtii import instrument
from backend.rdtii.indicators import get_indicators
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "ru_ips_list_frame.html"


@pytest.fixture(scope="module")
def rows():
    return RU.parse_rows(FIXTURE.read_text(encoding="utf-8"))


def test_the_rows_are_in_the_html_and_the_parser_finds_them(rows):
    assert len(rows) >= 6
    assert all(r["nd"].isdigit() for r in rows)
    assert all(r["subject"] for r in rows), "a row with no subject line is a parse failure"


def test_the_portal_states_in_force_status_and_we_read_it(rows):
    """Russia is the one economy here that answers this in the listing. Mongolia has to fetch a
    second page to find out, and Singapore cannot find out at all."""
    kept = [r for r in rows if RU.in_force(r)]
    dropped = [r for r in rows if not RU.in_force(r)]
    assert dropped, "the fixture was chosen to contain repealed rows; it no longer does"
    assert all("Утратил силу" in r["status"] for r in dropped)
    assert all("Действует" in r["status"] for r in kept)


def test_an_unlabelled_row_is_kept():
    """Silence is not a repeal. Deleting evidence on an absent field is the worse mistake."""
    assert RU.in_force({"status": ""}) is True
    assert RU.in_force({}) is True


def test_the_query_is_encoded_as_windows_1251_not_utf8():
    """The trap that makes a wrong answer look like a right one: UTF-8 Cyrillic reaches this
    server as a different word, the search SUCCEEDS, and it returns results for something
    else. There is no error to notice."""
    url = RU._list_url("персональных данных")
    query = urllib.parse.urlsplit(url).query
    # Read back as cp1251: it round-trips, which is the whole claim.
    assert urllib.parse.parse_qs(query, encoding="cp1251")["a1"][0] == "персональных данных"
    # And read back as UTF-8 it does NOT, which is what the server would have received had the
    # encoding been left to the default. This half is the one that fails if someone "fixes" the
    # encoding to UTF-8, because the URL would then look correct in every other respect.
    assert urllib.parse.parse_qs(query)["a1"][0] != "персональных данных"
    assert "%EF%E5%F0" in url.upper(), f"query is not cp1251-percent-encoded: {url}"
    assert "%D0%BF" not in url.upper(), "UTF-8-encoded Cyrillic leaked into the query"


def test_the_body_url_is_the_document_not_the_frameset():
    """`?docbody=&nd=<id>` is a frameset carrying 586 characters of chrome and no law — a page
    that looks fine and contains nothing. The body is `?doc_itself=`."""
    u = RU.body_url("102010435")
    assert "doc_itself=" in u and "docbody=" not in u
    assert "nd=102010435" in u


def test_a_federal_law_outranks_a_ministerial_order_at_equal_relevance():
    inds = get_indicators(6)
    subject = "О персональных данных"
    law = RU._relevance({"designation": "Федеральный закон от 27.07.2006 № 152-ФЗ",
                         "subject": subject}, inds)
    order = RU._relevance({"designation": "Приказ Минкомсвязи России от 01.01.2020 № 1",
                           "subject": subject}, inds)
    assert law > order


def test_relevance_separates_on_subject_not_only_on_type():
    """The failure this ordering exists to avoid: a type weight large enough to decide the
    ranking makes every instrument of that type tie, which is what happened in the Thai and
    Lao lanes."""
    inds = get_indicators(6)
    desig = "Постановление Правительства Российской Федерации от 01.01.2020 № 1"
    on_topic = RU._relevance(
        {"designation": desig,
         "subject": "Об утверждении Правил принятия решения о запрещении трансграничной "
                    "передачи персональных данных"}, inds)
    off_topic = RU._relevance(
        {"designation": desig,
         "subject": "О выплате ежемесячных надбавок к тарифным ставкам за выслугу лет"}, inds)
    assert on_topic > off_topic


def test_a_chamber_resolution_on_a_BILL_is_classified_as_a_draft():
    """These arrive in bulk from this portal when the principal statute is not itself indexed.
    Before this they read as AMENDING — a status that survives all the way to the submission,
    because an amending act is real law and only its citation is wrong. A bill is not."""
    assert instrument.classify(
        'О проекте федерального закона № 47571-7 "О безопасности критической информационной '
        'инфраструктуры Российской Федерации"') is instrument.Status.DRAFT


def test_the_adapter_declines_rather_than_guessing_when_no_terms_are_configured():
    said = []
    out = RU.search_ru_ips(None, {"name": "IPS"}, "", Economy("RU"), get_indicators(6),
                           log=said.append)
    assert out == []
    assert any("no Russian query terms" in m for m in said), said


def test_the_configured_queries_are_russian_and_precise():
    """Two measured constraints in one assertion. The portal indexes Russian, so an English
    term matches nothing; and its list frame returns the twenty OLDEST matches with no working
    pagination, so a broad term spends all twenty on Soviet-era decrees. Both mean the terms in
    `data/sources.yaml` have to be narrow statutory phrases."""
    import yaml
    rows = yaml.safe_load(Path("data/sources.yaml").read_text(encoding="utf-8"))
    rows = rows.get("sources", rows) if isinstance(rows, dict) else rows
    src = next(s for s in rows if s.get("adapter") == "ru_ips")
    terms = (src.get("queries_p6") or []) + (src.get("queries_p7") or [])
    assert terms, "the ru_ips source carries no queries, so the lane can do nothing"
    for t in terms:
        assert any("Ѐ" <= ch <= "ӿ" for ch in t), f"{t!r} is not Russian"
        assert len(t.split()) >= 3, f"{t!r} is too broad for a twenty-row, oldest-first list"
