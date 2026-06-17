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


# ─────────────────── SG: drop redundant amendments + clean source URL ───────────────────
def test_sg_amendment_docs_dropped():
    from backend.pipeline.discovery import _drop_amendment_docs
    docs = [_doc("Personal Data Protection Regulations 2021", "u1"),
            _doc("Personal Data Protection (Amendment) Regulations 2026", "u2"),
            _doc("Personal Data Protection Act 2012", "u3")]
    kept = {d.title for d in _drop_amendment_docs(docs)}
    assert "Personal Data Protection (Amendment) Regulations 2026" not in kept
    assert "Personal Data Protection Regulations 2021" in kept


def test_sg_source_url_stripped_to_law():
    from backend.pipeline.discovery import _clean_source_url
    assert _clean_source_url(Economy.SG, "https://sso.agc.gov.sg/Act/CoA1967?ProvIds=pr26-&DocDate=2020") \
        == "https://sso.agc.gov.sg/Act/CoA1967"
    # non-SG URLs are untouched
    assert _clean_source_url(Economy.AU, "https://www.legislation.gov.au/C2004A03712/x") \
        == "https://www.legislation.gov.au/C2004A03712/x"


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


# ─────────────────── AU: resolve SPA page to authorised PDF ───────────────────
def test_au_title_id_extracted_and_resolved(monkeypatch):
    """legislation.gov.au/{id} is a JS SPA; _resolve_pdf_url must turn it into the static
    authorised-PDF download URL (date from the OData feed, stubbed here)."""
    from backend.pipeline import discovery as D
    monkeypatch.setattr(D, "_au_pdf_download_url",
                        lambda tid: f"https://www.legislation.gov.au/{tid}/2025-06-10/2025-06-10/text/original/pdf")
    url, fmt = D._resolve_pdf_url(Economy.AU, "https://www.legislation.gov.au/C2004A03712")
    assert fmt == DocFormat.PDF_TEXT
    assert url == "https://www.legislation.gov.au/C2004A03712/2025-06-10/2025-06-10/text/original/pdf"


def test_au_resolution_falls_back_to_page_when_api_down(monkeypatch):
    from backend.pipeline import discovery as D
    monkeypatch.setattr(D, "_au_pdf_download_url", lambda tid: None)
    url, fmt = D._resolve_pdf_url(Economy.AU, "https://www.legislation.gov.au/C2004A03712/latest/text")
    assert fmt == DocFormat.HTML  # falls back to the page → JS-shell guard handles it


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
    # Real lom.agc.gov.my convention: English under /LOM/EN/Act…, Malay under /BM/Akta…
    docs = [_doc("Akta Perlindungan Data Peribadi 2010",
                 "https://lom.agc.gov.my/ilims/upload/portal/akta/BM/Akta 709.pdf", Economy.MY),
            _doc("Personal Data Protection Act 2010",
                 "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act 709 2016.pdf", Economy.MY)]
    out = _prefer_english_my(docs)
    assert len(out) == 1 and "/EN/" in out[0].source_url


def test_my_english_pdf_not_misclassified_as_malay():
    """Regression: every MY act lives under /portal/akta/, so matching 'akta' anywhere
    wrongly dropped English PDFs. The English /EN/Act… PDF must be kept."""
    from backend.pipeline.discovery import _is_malay_my
    en = _doc("Act 709", "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act 709 14 6 2016.pdf", Economy.MY)
    ms = _doc("Akta 709", "https://lom.agc.gov.my/ilims/upload/portal/akta/BM/Akta 709.pdf", Economy.MY)
    assert not _is_malay_my(en) and _is_malay_my(ms)


def test_my_act_number_dedup_collapses_reprints_and_landings():
    """All reprints / language / landing-page forms of one MY act share its act number and
    collapse to a single English direct-PDF document."""
    docs = [
        _doc("PDF Act 709-reprint 2023", "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act 709 reprint 2023.pdf", Economy.MY),
        _doc("PDF Online Version of Updated Text", "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act 709 14 6 2016.pdf", Economy.MY),
        _doc("Malaysia Federal Legislation", "https://lom.agc.gov.my/act-detail.php?language=BI&type=principal&act=709", Economy.MY),
        _doc("PDF Act A1727", "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act A1727.pdf", Economy.MY),
    ]
    out = _dedup_by_law_title(docs)
    ids = sorted(_sg_statute_id(d.source_url) or d.source_url for d in out)  # noqa: F841
    from backend.pipeline.discovery import _my_act_id
    assert sorted(_my_act_id(d.source_url) for d in out) == ["my-709", "my-a1727"]
    act709 = [d for d in out if _my_act_id(d.source_url) == "my-709"][0]
    assert act709.source_url.endswith(".pdf")     # direct PDF kept over the act-detail landing


# ─────────────────── round-robin breadth: niche law-type queries not crowded out ───────────────────
def test_websearch_round_robin_keeps_niche_law_types(monkeypatch):
    """Abundant data-protection queries must not fill the budget before a specific law-type
    query ("companies act") runs — round-robin takes each query's top hit first."""
    from backend.pipeline import discovery as D, websearch

    def fake_find(economy, topic, max_results=4, log=None, site=None):
        t = topic.lower()
        if "companies act" in t:
            return [("https://sso.agc.gov.sg/Act/CoA1967", "Companies Act 1967", "")]
        if "income tax" in t:
            return [("https://sso.agc.gov.sg/Act/ITA1947", "Income Tax Act 1947", "")]
        import hashlib
        h = hashlib.md5(t.encode()).hexdigest()[:6]
        return [(f"https://sso.agc.gov.sg/SL/REG-{h}-{i}", f"Reg {h} {i}", "") for i in range(max_results)]

    monkeypatch.setattr(websearch, "find_law_urls", fake_find)
    names = [d.title for d in D.discover_websearch(Economy.SG, 6, max_docs=18)]
    assert any("Companies Act" in n for n in names)
    assert any("Income Tax" in n for n in names)


# ─────────────────── content-relevance gate: snippet ranks on-topic laws above off-topic noise ──────
def test_websearch_snippet_relevance_ranks_ontopic_first(monkeypatch):
    """A law whose TITLE hides the provision (Companies Act → accounting-record storage) must
    still survive the cap because its on-topic search snippet carries the indicator terms, while
    a tangential law (Gambling) whose snippet is off-topic must be dropped when the budget is tight."""
    from backend.pipeline import discovery as D, websearch

    def fake_find(economy, topic, max_results=4, log=None, site=None):
        t = topic.lower()
        # On-topic P6 (cross-border / local storage) snippet, but a name with no data words.
        if "storage" in t or "record" in t:
            return [("https://sso.agc.gov.sg/Act/CoA1967", "Companies Act 1967",
                     "A company must keep its accounting records and retain them, stored within "
                     "Singapore; transfer of records outside Singapore requires approval.")]
        # Off-topic law surfaced by a tangential term — snippet has no indicator coverage.
        return [("https://sso.agc.gov.sg/Act/GamblingControl2022", "Gambling Control Act 2022",
                 "An act to license and regulate gambling and casino operations.")]

    monkeypatch.setattr(websearch, "find_law_urls", fake_find)
    docs = D.discover_websearch(Economy.SG, 6, max_docs=1)   # tight budget forces a choice
    assert docs and "Companies Act" in docs[0].title
    assert docs[0].relevance_score > 0


# ─────────────────── circuit breaker: blocked search engines don't hang the run ───────────────────
def test_websearch_circuit_breaker_stops_hammering_blocked_engines(monkeypatch):
    """When the keyless engines are network-blocked (all return empty), the run must NOT keep
    paying the ~60s Scrapling-retry cost on every remaining query: after _SOFT empties the slow
    Scrapling engine is dropped, after _HARD the circuit opens and search() skips the network."""
    from backend.pipeline import websearch

    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    monkeypatch.setattr(websearch, "_load_cache", lambda: {})
    monkeypatch.setattr(websearch, "_cache_file", lambda: (_ for _ in ()).throw(AssertionError("no write")))
    calls = {"scrapling": 0}

    def empty(client, q, n):
        return []

    def slow(client, q, n):                          # stands in for the 60s Scrapling retry path
        calls["scrapling"] += 1
        return []

    for name in ("_serper", "_ddg_html", "_ddg_lite", "_mojeek"):
        monkeypatch.setattr(websearch, name, empty)
    monkeypatch.setattr(websearch, "_scrapling_ddg", slow)
    monkeypatch.setattr(websearch, "_ENGINES_SCRAPLING_FIRST",
                        [websearch._serper, websearch._scrapling_ddg, websearch._ddg_html,
                         websearch._ddg_lite, websearch._mojeek])
    websearch.reset_circuit()
    for i in range(40):
        assert websearch.search(f"q{i}", site="x", max_results=4, log=lambda *a: None) == []
    assert calls["scrapling"] <= websearch._SOFT      # slow path dropped early, not 40 times
    assert websearch._circuit["empties"] == websearch._HARD   # opened and stays open


# ─────────────────── Malaysia portal-catalogue adapter ───────────────────
def test_my_extract_names_bilingual_picks_english():
    """MY catalogue titles list both languages; the English name (anchor before 'As At') is
    displayed, but matching uses the full bilingual text."""
    from backend.pipeline.discovery import _my_extract_names
    html = ('<a href="act-detail.php?act=854">AKTA KESELAMATAN SIBER 2024</a> '
            '<i>Sebagaimana Pada</i> 26-06-2024<br>'
            '<a href="act-detail.php?act=854&lang=BI">CYBER SECURITY ACT 2024</a> '
            '<i>As At</i> 26-06-2024')
    name, full = _my_extract_names(html)
    assert name == "CYBER SECURITY ACT 2024"          # English anchor (before 'As At'), not Malay
    assert "keselamatan siber" in full.lower()        # full text keeps both languages for matching


def test_my_catalogue_search_matches_english_fragment(monkeypatch):
    """A name fragment matches against the full bilingual text, so an Act whose Malay title
    comes first is still found; the returned doc carries the English name + the _BI PDF URL."""
    from backend.pipeline import discovery as D
    from backend.schemas import Economy
    # Seed the module cache so no network call is made.
    monkeypatch.setattr(D, "_my_catalogue_cache", [
        ("854", "CYBER SECURITY ACT 2024",
         "akta keselamatan siber 2024 cyber security act 2024",
         "https://lom.agc.gov.my/ilims/upload/portal/akta/x_BI/Act 854.pdf"),
        ("709", "PERSONAL DATA PROTECTION ACT 2010",
         "personal data protection act 2010",
         "https://lom.agc.gov.my/ilims/upload/portal/akta/y_BI/ACT 709.pdf"),
    ])
    docs = D._search_my_catalogue(None, {"name": "MY"}, "cyber security act", Economy.MY, [], log=lambda *a: None)
    assert len(docs) == 1
    assert docs[0].title == "CYBER SECURITY ACT 2024"
    assert docs[0].law_number == "854"
    assert docs[0].source_url.endswith(".pdf")


def test_my_is_name_only_portal():
    """MY (catalogue name-filter) fires NAME fragments only — no long descriptive phrases."""
    from backend.rdtii.keywords import portal_search_queries, NAME_ONLY_PORTALS
    assert "MY" in NAME_ONLY_PORTALS
    q = portal_search_queries("MY", 7)
    assert not any(len(s.split()) >= 5 for s in q)     # descriptive phrases excluded
    assert "personal data protection act" in q


# ─────────────────── secondary web-search source: pdf_only filename titles (MY pdp.gov.my codes) ──
def test_pdf_only_websearch_uses_filename_titles_and_keeps_distinct_codes(monkeypatch):
    """The MY PDP Codes of Practice come from a secondary source (pdp.gov.my) via web search.
    Search engines truncate their titles to an identical prefix ('[PDF] THE PERSONAL DATA
    PROTECTION Code of practice'); without filename-based identity, title-dedup would collapse all
    sectors into one. pdf_only must (a) keep only PDF hits, (b) title them from the filename, so the
    distinct sector codes survive."""
    from backend.pipeline import discovery as D, websearch
    from backend.schemas import Economy
    TRUNC = "[PDF] THE PERSONAL DATA PROTECTION Code of practice"
    pdfs = [
        ("https://www.pdp.gov.my/u/Communications-Sector-PDPA-COP.pdf", TRUNC, "cross-border transfer"),
        ("https://www.pdp.gov.my/u/COP_-CODE-OF-PRACTICE-FOR-PRIVATE-HOSPITALS-APHM.pdf", TRUNC, "retain records"),
        ("https://www.pdp.gov.my/u/Code_of_Practice_For_Aviation_Sector.pdf", TRUNC, "security of data"),
        ("https://www.pdp.gov.my/en/akta/code-landing-page/", TRUNC, "html wrapper"),   # dropped by pdf_only
    ]
    monkeypatch.setattr(websearch, "find_law_urls",
                        lambda economy, topic, max_results=4, log=None, site=None: pdfs)
    docs = D.discover_websearch(Economy.MY, 6, 18, site="www.pdp.gov.my",
                                queries=["code of practice filetype:pdf"], pdf_only=True)
    assert all(d.source_url.endswith(".pdf") for d in docs)        # landing page dropped
    titles = {d.title for d in docs}
    assert len(docs) >= 3 and len(titles) == len(docs)             # distinct, not collapsed to one
    assert any("Aviation" in t for t in titles)                    # filename-derived sector name
