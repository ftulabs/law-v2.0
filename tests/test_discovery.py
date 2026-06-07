"""Zone-1 discovery hygiene: de-duplication, version/recency selection, title cleaning,
and law-name recovery. These guard the three failure modes seen in live testing:
  1. the same Act fetched/extracted many times (provision blow-up, LLM cost),
  2. an old/repealed version kept instead of the newest in-force one,
  3. Malaysian laws mislabelled with a generic portal <title>.
"""
from backend.pipeline.discovery import (
    _clean_title, _dedup_by_law_title, _dedup_key, _is_generic_title, _latest_year,
    _law_key, _pick_best, _prefer_english_my, _sg_statute_id, _url_law_key,
)
from backend.pipeline.extraction import _law_name, _recover_law_name
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy


def _doc(title, url, economy=Economy.SG, date=None):
    return DiscoveredDoc(
        doc_id=url, economy=economy, title=title, source_url=url, portal="x",
        fmt=DocFormat.PDF_TEXT, discovery_tag=DiscoveryTag.NEW, amendment_date=date)


# ─────────────────────────── title cleaning ───────────────────────────
def test_clean_title_strips_format_prefix_and_portal_suffix():
    assert _clean_title("Personal Data Protection Act 2012 - Singapore Statutes Online") \
        == "Personal Data Protection Act 2012"
    assert _clean_title("[PDF] Act A1727 - lom.agc.gov.my") == "Act A1727"
    assert _clean_title("Privacy Act 1988 | legislation.gov.au") == "Privacy Act 1988"


def test_generic_titles_detected():
    assert _is_generic_title("Malaysia Federal Legislation")
    assert _is_generic_title("Singapore Statutes Online")
    assert _is_generic_title("Act A1727")          # law-number-only, no real name
    assert _is_generic_title("Akta 709")
    assert _is_generic_title("PDF bc248903-f874-4c36-9844-9e1935038a24 1.")  # UUID/filename blob
    assert not _is_generic_title("Personal Data Protection Act 2012")
    assert not _is_generic_title("Privacy Act 1988")


# ─────────────────────────── bug 1: duplicate laws ───────────────────────────
def test_same_law_under_different_search_titles_collapses():
    """PDPA surfaced as a landing page and a '… - Singapore Statutes Online' result is ONE law."""
    docs = [
        _doc("Personal Data Protection Act 2012 - Singapore Statutes Online",
             "https://sso.agc.gov.sg/Act/PDPA2012?ViewType=Pdf"),
        _doc("Personal Data Protection Act 2012", "https://sso.agc.gov.sg/Act/PDPA2012"),
    ]
    assert len(_dedup_by_law_title(docs)) == 1


def test_year_variants_collapse_to_one():
    docs = [_doc(f"Overseas Telecommunications Act {y}", f"u{y}")
            for y in (1946, 1952, 1968, 1971)]
    assert len(_dedup_by_law_title(docs)) == 1


# ─────────────────────────── bug 2: version / recency ───────────────────────────
def test_pick_best_keeps_newest_year_when_dates_absent():
    """The reported regression: with no amendment_date, year-in-title must break the tie
    toward the newest revision (not first-encountered = oldest)."""
    docs = [_doc("Telecommunications Act 1975", "u1"),
            _doc("Telecommunications Act 1997", "u2"),
            _doc("Telecommunications Act 1989", "u3")]
    assert _pick_best(docs).title == "Telecommunications Act 1997"


def test_pick_best_prefers_inforce_over_repealed():
    docs = [_doc("Data Act 2001", "https://x/historical/data-act-2001"),
            _doc("Data Act 1999", "https://x/data-act-1999")]
    # the 1999 one is in force; the 2001 one sits under a 'historical' path
    assert _pick_best(docs).title == "Data Act 1999"


def test_pick_best_prefers_principal_over_amendment():
    docs = [_doc("Privacy Amendment Act 2022", "u1"),
            _doc("Privacy Act 1988", "u2")]
    assert _pick_best(docs).title == "Privacy Act 1988"


def test_latest_year_reads_date_and_title():
    assert _latest_year("", "Telecommunications Act 1997") == 1997
    assert _latest_year("2020-05-01", "Foo Act 1975") == 2020


# ─────────────────────── bug 3: generic MY titles ───────────────────────
def test_generic_portal_titles_do_not_merge_distinct_laws():
    """Two different MY Acts that both carry the portal-wide 'Malaysia Federal Legislation'
    <title> must stay separate (keyed by URL), not collapse into one."""
    docs = [_doc("Malaysia Federal Legislation", "https://lom.agc.gov.my/akta_709.pdf", Economy.MY),
            _doc("Malaysia Federal Legislation", "https://lom.agc.gov.my/akta_855.pdf", Economy.MY)]
    assert len(_dedup_by_law_title(docs)) == 2


def test_url_law_key_distinguishes_acts_but_ignores_reprint_year():
    assert _url_law_key("https://lom.agc.gov.my/akta_709.pdf") \
        != _url_law_key("https://lom.agc.gov.my/akta_855.pdf")
    # the same act as a reprinted edition shares the key
    assert _url_law_key("https://lom.agc.gov.my/act_709.pdf") \
        == _url_law_key("https://lom.agc.gov.my/act_709_reprint_2023.pdf")


def test_recover_law_name_from_header():
    text = ("LAWS OF MALAYSIA\nAct 709\nPERSONAL DATA PROTECTION ACT 2010\n"
            "ARRANGEMENT OF SECTIONS\n1. Short title and commencement")
    assert _recover_law_name(text) == "PERSONAL DATA PROTECTION ACT 2010"


def test_recover_law_name_ignores_prose():
    assert _recover_law_name("this section of the act applies to the transfer of data") is None


def test_law_name_recovers_for_generic_title_else_cleans():
    header = "LAWS OF MALAYSIA\nAct 709\nPERSONAL DATA PROTECTION ACT 2010\n"
    generic = _doc("Malaysia Federal Legislation", "https://lom.agc.gov.my/akta_709.pdf", Economy.MY)
    assert _law_name(generic, header) == "PERSONAL DATA PROTECTION ACT 2010"
    # a good title is cleaned, not replaced
    good = _doc("Privacy Act 1988 - legislation.gov.au", "u", Economy.AU)
    assert _law_name(good, "") == "Privacy Act 1988"


# ─────────────────── SG: statute-ID dedup (one law, many SSO URLs) ───────────────────
def test_sg_statute_id_from_sso_urls():
    assert _sg_statute_id("https://sso.agc.gov.sg/SL/PDPA2012-S63-2021?DocDate=20210930") == "sl-s63-2021"
    assert _sg_statute_id("https://sso.agc.gov.sg/SL-Supp/S63-2021/Published/20210129170000") == "sl-s63-2021"
    assert _sg_statute_id("https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=pr26-") == "act-pdpa2012"
    # distinct subsidiary instruments under the same parent Act stay distinct
    assert _sg_statute_id("https://sso.agc.gov.sg/SL/PDPA2012-S64-2021") == "sl-s64-2021"


def test_sg_same_regulation_under_three_urls_collapses_to_one_named_doc():
    """The PDPA Regulations 2021 (S63-2021) is surfaced as a consolidated /SL/ view, an
    as-published /SL-Supp/.../Published/ snapshot, and a per-provision section heading.
    All three must collapse to ONE doc — and the kept one must be the properly-named,
    in-force consolidated version (not the UUID/as-published or the section heading)."""
    docs = [
        _doc("Transfer of Personal Data Outside Singapore",
             "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021?DocDate=20210129&ProvIds=P13-"),
        _doc("Personal Data Protection Regulations 2021",
             "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021?DocDate=20210930&ViewType=Advance"),
        _doc("PDF bc248903-f874-4c36-9844-9e1935038a24 1",
             "https://sso.agc.gov.sg/SL-Supp/S63-2021/Published/20210129170000?ViewType=Pdf"),
    ]
    out = _dedup_by_law_title(docs)
    assert len(out) == 1
    assert out[0].title == "Personal Data Protection Regulations 2021"
    assert "/Published/" not in out[0].source_url     # as-published snapshot dropped


def test_sg_distinct_statutes_not_merged():
    docs = [_doc("Reg A", "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021"),
            _doc("Reg B", "https://sso.agc.gov.sg/SL/PDPA2012-S64-2021"),
            _doc("Act", "https://sso.agc.gov.sg/Act/PDPA2012")]
    assert len(_dedup_by_law_title(docs)) == 3


# ─────────────────── name recovery: instrument vs parent Act ───────────────────
def test_recover_picks_instrument_not_parent_act():
    """SG subsidiary-legislation header lists the parent Act + citation ABOVE the
    instrument's own name; recovery must return the instrument, not the Act."""
    header = ("1 S 63/2021\nNo. S 63\nPERSONAL DATA PROTECTION ACT 2012\n(ACT 26 OF 2012)\n"
              "PERSONAL DATA PROTECTION\nREGULATIONS 2021\nARRANGEMENT OF REGULATIONS\n"
              "1. Citation and commencement")
    assert _recover_law_name(header) == "PERSONAL DATA PROTECTION REGULATIONS 2021"


def test_recover_skips_citation_line():
    # the bare "(Act 26 of 2012)" citation must never be returned as a name
    assert _recover_law_name("(ACT 26 OF 2012)\nsome running text about the act") != "(ACT 26 OF 2012)"


# ─────────────────────── MY English-preference ───────────────────────
def test_prefer_english_drops_malay_when_english_present():
    docs = [_doc("Akta Perlindungan Data Peribadi 2010", "https://lom.agc.gov.my/akta_709.pdf", Economy.MY),
            _doc("Personal Data Protection Act 2010", "https://lom.agc.gov.my/akta_709e.pdf", Economy.MY)]
    out = _prefer_english_my(docs)
    assert len(out) == 1 and out[0].source_url.endswith("e.pdf")
