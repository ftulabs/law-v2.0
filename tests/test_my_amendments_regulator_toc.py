"""Malaysia, three silent losses found on the 2026-09-25 live run (all offline, no network).

1. The AGC amendment catalogue loaded as "0 acts": its records link the PDF only through
   `processFile.php?token=<base64>`, which the href parser never matched — so the PDPA
   (Amendment) Act 2024 (A1727: s.12A DPO, s.12B breach notification, s.129 rewrite) never
   reached the corpus and the run quoted the superseded 2023 reprint.
2. The regulator's guidelines and codes arrived only through a web-search lane, and every
   engine was down (Serper out of credits, DuckDuckGo challenge, Mojeek 403).
3. A guideline's page-numbered table of contents became provisions ("6. Matters Relating to
   the Appointment of Data Protection Officer 8"), and its last entry swallowed the body.
"""
import base64

import pytest

from backend.pipeline import discovery as D
from backend.pipeline import extraction as X
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, OCRMetrics


def _doc(title, url, *, current_to=None, score=1.0, economy=Economy.MY):
    return DiscoveredDoc(doc_id=url, economy=economy, title=title, source_url=url, portal="x",
                         fmt=DocFormat.PDF_TEXT, discovery_tag=DiscoveryTag.NEW,
                         relevance_score=score, text_current_to=current_to)


def _token_link(url: str, lang_icon: str = "pdf-en-printed.png") -> str:
    tok = base64.b64encode(f"{url}|{'ab' * 32}".encode()).decode().replace("=", "%3D")
    return (f'<a href="processFile.php?token={tok}" target="_blank" '
            f'class="event_kira_download_amendment"><img src="images/icons/pdf/{lang_icon}"></a>')


# The record shape json-amendment-2024.php returned on 2026-09-26 (trimmed).
_A1727 = {
    "ACTNO_LEGISLATION": "A1727",
    "LEGISLATIONTITLEBI": '<a href="act-detail.php?type=amendment&act=A1727&lang=BI">'
                          "PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024</a>",
    "COMMENCEMENTREMARKBI": "24/12/2024 [P.U. (B) 522/2024]",
    "PUBLICATIONDATE": "17/10/2024",
    "URLDOCBM": "/ilims/upload/portal/akta/outputaktap/2430673_BM/Akta A1727.pdf",
    "DOC2DOWNLOADBM": _token_link("https://lom.agc.gov.my/ilims/upload/portal/akta/outputaktap/"
                                  "2430673_BM/Akta A1727.pdf", "pdf-ms-printed.png"),
    "DOC2DOWNLOADBI": _token_link("https://lom.agc.gov.my/ilims/upload/portal/akta/outputaktap/"
                                  "2430673_BI/Act A1727.pdf"),
}
_NOT_IN_FORCE = dict(_A1727, ACTNO_LEGISLATION="A1797",
                     LEGISLATIONTITLEBI='<a href="x">WITNESS PROTECTION (AMENDMENT) ACT 2026</a>',
                     COMMENCEMENTREMARKBI="NOT YET IN FORCE")


# ───────────────────────────── 1. amendment catalogue ─────────────────────────────
def test_token_only_download_link_resolves_to_the_english_pdf():
    """The amendment catalogue's only link shape. Before the fix this returned None for all
    410 records, and the catalogue logged "0 acts"."""
    assert D._my_pdf_url(_A1727["DOC2DOWNLOADBI"]).endswith("/2430673_BI/Act A1727.pdf")
    # English is chosen over the plain-path Malay field that comes first in the record.
    assert D._my_record_pdf(_A1727).endswith("/2430673_BI/Act A1727.pdf")


def test_direct_href_shape_of_the_principal_catalogue_still_parses():
    html = ('<a href="../../../ilims/upload/portal/akta/outputaktap/1726091_BM/AKTA 709.pdf">'
            '</a><br><a href="../../../ilims/upload/portal/akta/outputaktap/1726091_BI/'
            'ACT 709-REPRINT 2023.pdf"></a>')
    assert D._my_pdf_url(html) == ("https://lom.agc.gov.my/ilims/upload/portal/akta/"
                                   "outputaktap/1726091_BI/ACT 709-REPRINT 2023.pdf")


def test_record_dates_read_the_reprint_currency_and_the_commencement():
    full = ("AKTA PERLINDUNGAN DATA PERIBADI 2010 Sebagaimana Pada 01-07-2023 "
            "PERSONAL DATA PROTECTION ACT 2010 As At 01-07-2023")
    assert D._my_record_date({}, full) == "2023-07-01"
    assert D._my_record_date(_A1727, "PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024") == "2024-12-24"
    assert D._my_record_date({"PUBLICATIONDATE": "17/10/2024"}, "") == "2024-10-17"


def test_amendment_catalogue_loads_and_skips_uncommenced_acts(monkeypatch):
    from backend.pipeline import portal_crypto
    monkeypatch.setattr(portal_crypto, "fetch_catalogue",
                        lambda *a, **k: [_A1727, _NOT_IN_FORCE])
    monkeypatch.setattr(D, "_my_catalogue_cache", {})
    lines = []
    recs = D._load_my_catalogue(None, {"catalogue_url": "https://x/json-amendment-2024.php"},
                                lines.append)
    assert len(recs) == 1
    act_no, name, _full, pdf, current_to = recs[0]
    assert (act_no, name, current_to) == ("A1727", "PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024",
                                          "2024-12-24")
    assert pdf.endswith("_BI/Act A1727.pdf")
    assert any("1 acts of 2 records, 1 not yet in force" in ln for ln in lines)


def test_amendment_is_found_by_the_principals_name_fragment(monkeypatch):
    url = "https://x/json-amendment-2024.php"
    monkeypatch.setattr(D, "_my_catalogue_cache", {url: [
        ("A1727", "PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024",
         "personal data protection (amendment) act 2024", "https://l/2430673_BI/Act A1727.pdf",
         "2024-12-24")]})
    docs = D._search_my_catalogue(None, {"catalogue_url": url}, "personal data protection act",
                                  Economy.MY, [], log=lambda *a: None)
    assert [d.text_current_to for d in docs] == ["2024-12-24"]
    assert docs[0].amendment_date == "2024"          # the Last Amended column is unchanged


def _family():
    principal = _doc("PERSONAL DATA PROTECTION ACT 2010", "u/ACT 709-REPRINT 2023.pdf",
                     current_to="2023-07-01")
    new = _doc("PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024", "a/Act A1727.pdf",
               current_to="2024-12-24")
    old = _doc("PERSONAL DATA PROTECTION (AMENDMENT) ACT 2016", "a/Act A1500.pdf",
               current_to="2016-03-01")
    return principal, new, old


def test_post_reprint_amendment_is_kept_level_with_its_principal_and_older_ones_dropped():
    principal, new, old = _family()
    out = D._collapse_my_amendments([principal, new, old])
    titles = [d.title for d in out]
    assert new.title in titles and old.title not in titles
    assert new.relevance_score == principal.relevance_score   # not the 0.58 tail any more


def test_companion_amendment_rides_outside_the_cap_and_never_evicts_a_guideline():
    """Measured 2026-09-26, pillar 7: four post-reprint amendments ranked level with their
    principals took four of 22 slots and pushed the DPO and breach-notification guidelines
    out. The cap is now taken without them and they follow their principal."""
    principal, new, _ = _family()
    guide = _doc("Personal Data Protection Guidelines on the Appointment of Data Protection "
                 "Officer (DPO)", "g/GP_DPO_ENG.pdf", score=0.83)
    docs = D._collapse_my_amendments([principal, new, guide])
    docs.sort(key=lambda d: d.relevance_score, reverse=True)
    kept = D._cap_with_my_companions(docs, 2, False, log=lambda *a: None)
    assert [d.title for d in kept] == [principal.title, guide.title, new.title]


def test_companion_whose_principal_was_cut_does_not_travel_alone():
    principal, new, _ = _family()
    other = _doc("CYBER SECURITY ACT 2024", "u/Act 854.pdf", current_to="2024-06-26")
    docs = D._collapse_my_amendments([other, principal, new])
    kept = D._cap_with_my_companions(docs, 1, False, log=lambda *a: None)
    assert [d.title for d in kept] == [other.title]


def test_undated_amendments_keep_the_old_tail_heuristic():
    principal = _doc("INCOME TAX ACT 1967", "u/act53.pdf")
    a1 = _doc("INCOME TAX (AMENDMENT) ACT 2017", "a/A1556.pdf")
    a2 = _doc("INCOME TAX (AMENDMENT) ACT 2024", "a/A1706.pdf")
    out = D._collapse_my_amendments([principal, a1, a2])
    assert [d.title for d in out] == [principal.title, a2.title]
    assert out[1].relevance_score < 0.6


def test_malay_consultation_paper_is_a_draft():
    from backend.rdtii import instrument
    assert instrument.classify("Kertas Konsultasi Awam Bil. 05/2024: Garis Panduan "
                               "Pemindahan Data Peribadi Rentas Sempadan") is instrument.Status.DRAFT


# ───────────────────────────── 2. regulator publication lane ─────────────────────────────
_ROOT = "https://reg.example.gov.my/site"


def _item(title, link, pdf=None, source_url=None):
    body = f'<p><a href="{pdf}">Download</a></p>' if pdf else ""
    it = {"title": {"rendered": title}, "link": link, "content": {"rendered": body}}
    if source_url:
        it["source_url"] = source_url
    return it


_UP = f"{_ROOT}/wp-content/uploads"
_DOCS = [
    _item("Personal Data Protection Guidelines on Cross-Border Transfer of Personal Data (CBPDT)",
          f"{_ROOT}/en/akta/cbpdt/", f"{_UP}/CBPDT-BI.pdf"),
    _item("Garis Panduan Pemindahan Data Peribadi Rentas Sempadan (CBPDT)",
          f"{_ROOT}/akta/cbpdt-bm/", f"{_UP}/CBPDT-BM.pdf"),
    _item("Public Consultation Paper No. 05/2024: Cross Border Personal Data Transfer Guidelines",
          f"{_ROOT}/en/akta/pcp5/", f"{_UP}/PCP-Cross-Border-ENG.pdf"),
    _item("Personal Data Protection Guidelines on the Appointment of Data Protection Officer (DPO)",
          f"{_ROOT}/en/akta/dpo/", f"{_UP}/GP_DPO_ENG.pdf"),
    _item("Data Protection Impact Assessment Guideline (DPIA)", f"{_ROOT}/en/akta/dpia/",
          f"{_UP}/DPIA.pdf"),
    _item("Personal Data Protection Code of Practice For the Utilities Sector (Water)",
          f"{_ROOT}/en/akta/water/", f"{_UP}/COP-Water.pdf"),
    # the same English PDF linked from the Malay page too, with a LONGER Malay title
    _item("Tataamalan Perlindungan Data Peribadi Untuk Sektor Utiliti (Air) Versi Penuh",
          f"{_ROOT}/akta/water-bm/", f"{_UP}/COP-Water.pdf"),
    _item("Personal Data Protection Standard 2015", f"{_ROOT}/en/akta/standard/",
          f"{_UP}/LatestStandard.pdf"),
    _item("Personal Data Protection Regulations (Compounding of Offences) 2016",
          f"{_ROOT}/en/akta/kompaun/", f"{_UP}/Peraturan-Kompaun.pdf"),
    _item("Personal Data Protection (Amendment) Act 2024", f"{_ROOT}/en/akta/a1727/",
          f"{_UP}/Act-A1727.pdf"),
    _item("Data Protection Officer Registration Guide (DPO)", f"{_ROOT}/en/dpo-guide/",
          f"{_UP}/Manual_Pengguna_Pendaftaran_DPO_EN.pdf"),
    _item("Personal Data Protection Guidelines on Data Breach Notification (DBN)",
          f"{_ROOT}/en/akta/dbn/", f"{_UP}/GP_DBN_ENG.pdf"),
    _item("Off-site document", f"{_ROOT}/en/x/", "https://elsewhere.example.com/x.pdf"),
]
_MEDIA = [_item("banner", f"{_ROOT}/banner/", source_url=f"{_UP}/banner.jpg"),
          _item("GP_DBN_ENG", f"{_ROOT}/gp_dbn_eng/", source_url=f"{_UP}/GP_DBN_ENG.pdf"),
          _item("Pekeliling_2024", f"{_ROOT}/pekeliling/", source_url=f"{_UP}/Pekeliling_2024.pdf")]


class _Resp:
    def __init__(self, payload, pages=1):
        self.status_code = 200
        self._p = payload
        self.headers = {"X-WP-TotalPages": str(pages)}

    def json(self):
        return self._p


class _Client:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(url)
        if url.endswith("/wp-json/wp/v2/types"):
            return _Resp({"docs": {"rest_base": "docs"}, "attachment": {"rest_base": "media"},
                          "nav_menu_item": {"rest_base": "menu-items"}})
        if url.endswith("/docs"):
            return _Resp(_DOCS)
        if url.endswith("/media"):
            return _Resp(_MEDIA)
        raise AssertionError(f"unexpected fetch {url}")


@pytest.fixture
def wp(monkeypatch):
    from backend.pipeline import adapter_wp_regulator as W, portal
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(W, "_site_cache", {})
    return W


def test_enumeration_reads_the_rest_index_and_keeps_every_page_linking_a_file(wp):
    client = _Client()
    cands = wp.enumerate_site(client, _ROOT, lambda *a: None)
    urls = {u for u, _, _ in cands}
    assert f"{_UP}/Pekeliling_2024.pdf" in urls                # attachment-only file
    # a file with a publication page is named by that page, not by its attachment record
    assert [t for u, t, _ in cands if u.endswith("GP_DBN_ENG.pdf")] == [
        "Personal Data Protection Guidelines on Data Breach Notification (DBN)"]
    assert f"{_UP}/banner.jpg" not in urls                     # not a document
    assert "https://elsewhere.example.com/x.pdf" not in urls   # not this site's
    assert not any("menu-items" in c for c in client.calls)    # site machinery is skipped
    # both language pages that link the water code are kept for `rank` to choose between
    assert sum(1 for u, _, _ in cands if u.endswith("COP-Water.pdf")) == 2


def test_rank_drops_drafts_and_acts_and_prefers_the_english_page(wp):
    from backend.rdtii.indicators import get_indicators
    cands = wp.enumerate_site(_Client(), _ROOT, lambda *a: None)
    ranked = wp.rank(cands, get_indicators(6))
    titles = [t for _, _, t in ranked]
    assert not any("Consultation" in t for t in titles)          # draft
    assert not any(t.endswith("(Amendment) Act 2024") for t in titles)   # the AGC lane's
    water = next(t for _, u, t in ranked if u.endswith("COP-Water.pdf"))
    assert water.startswith("Personal Data Protection Code of Practice")   # not the Malay name
    cb_en = next(s for s, u, _ in ranked if u.endswith("CBPDT-BI.pdf"))
    cb_bm = next(s for s, u, _ in ranked if u.endswith("CBPDT-BM.pdf"))
    assert cb_en > cb_bm


def test_rank_orders_by_the_pillar(wp):
    from backend.rdtii.indicators import get_indicators
    cands = wp.enumerate_site(_Client(), _ROOT, lambda *a: None)
    p6 = [u.rsplit("/", 1)[-1] for _, u, _ in wp.rank(cands, get_indicators(6))]
    p7 = [u.rsplit("/", 1)[-1] for _, u, _ in wp.rank(cands, get_indicators(7))]
    assert p6[0] == "CBPDT-BI.pdf"
    assert set(p7[:3]) == {"DPIA.pdf", "GP_DPO_ENG.pdf", "GP_DBN_ENG.pdf"}
    # a binding code/standard outranks procedure and help material on either pillar
    for order in (p6, p7):
        assert order.index("LatestStandard.pdf") < order.index("Peraturan-Kompaun.pdf")
        assert order.index("COP-Water.pdf") < order.index("Manual_Pengguna_Pendaftaran_DPO_EN.pdf")


def test_lane_returns_its_best_max_docs_below_the_statute_score(wp):
    from backend.rdtii.indicators import get_indicators
    src = {"name": "PDP", "base_url": _ROOT, "max_docs": 3}
    docs = wp.search_wp_regulator(_Client(), src, "", Economy.MY, get_indicators(7),
                                  lambda *a: None)
    assert len(docs) == 3
    assert all(0.6 <= d.relevance_score < 1.0 for d in docs)
    assert docs[0].title == "Data Protection Impact Assessment Guideline (DPIA)"
    assert all(d.fmt == DocFormat.PDF_TEXT for d in docs)


def test_regulator_lane_is_registered_as_a_portal_enumerator():
    from backend.pipeline import adapter_wp_regulator  # noqa: F401 — runs the registration
    from backend.pipeline import portal
    assert portal.get_adapter("wp_regulator") is not None
    assert portal.enumerates_portal("wp_regulator")
    assert any(s.get("adapter") == "wp_regulator" and s.get("economy") == "MY"
               for s in D.load_sources())


# ───────────────────────────── 3. table of contents ─────────────────────────────
# The DPO guideline as it extracted on 2026-09-25 (abridged, same shape): cover, a TOC whose
# entries end in page numbers and wrap, then a body headed "PART A" / "1 Background" / "1.1".
_DPO = (
    "\x0c1\x0c\nPERSONAL DATA PROTECTION\nGUIDELINE\nAPPOINTMENT\nOF DATA PROTECTION OFFICER\n"
    "\x0c2\x0c\nTABLE OF CONTENTS\nNO. DISCRIPTION PAGE\nPART A: INTRODUCTION 3\n"
    "1. Background 3\n2. Legal Provisions 3\n3. Interpretations 4\n"
    "PART B: REQUIREMENTS FOR THE APPOINTMENT OF DATA 4\nPROTECTION OFFICER\n"
    "4. Conditions for the Appointment of Data Protection Officer 4\n"
    "5. Expertise and Qualifications of Data Protection Officer 6\n"
    "6. Matters Relating to the Appointment of Data Protection Officer 8\n"
    "\x0c3\x0c\nPART A: INTRODUCTION\n1 Background\n"
    "1.1 Section 12A of the Personal Data Protection Act 2010 sets the requirement for both\n"
    "data controller and data processor to appoint one or more data protection officer.\n"
    "2 Legal Provisions\n2.1 This Guideline is issued by the Commissioner under the Act.\n"
    "3 Interpretations\n3.1 Unless otherwise defined, the terms have the meanings in the Act.\n"
    "\x0c4\x0c\nPART B: REQUIREMENTS FOR THE APPOINTMENT OF DATA\nPROTECTION OFFICER\n"
    "4 Conditions for the Appointment of Data Protection Officer\n"
    "4.1 The requirement for the appointment of data protection officer is subject to the\n"
    "conditions determined by the Commissioner.\n"
    "5 Expertise and Qualifications of Data Protection Officer\n"
    "5.1 A data protection officer shall have sound knowledge of data protection law.\n"
    "6 Matters Relating to the Appointment of Data Protection Officer\n"
    "6.1 The data controller shall appoint the data protection officer in writing.\n")

# The water-sector code: TOC with sub-entries that carry no page number, split over two pages
# under two headings, then a body whose first heading adds a gloss the entry does not have.
_WATER = (
    "CODE OF PRACTICE\n\x0c5\x0c\nTABLE OF CONTENTS\nNO. SUBJECT MATTER Pages\n"
    "1. PURPOSE AND SCOPE OF THIS CODE OF PRACTICE 45.\n2. DEFINITION 45.\n"
    "3. GENERAL PRINCIPLE 46.\n3.1 General Principle\n3.2 Requirement Under General Principle\n"
    "\x0c6\x0c\nISI KANDUNGAN\n10. RIGHTS OF DATA SUBJECT 53.\n10.1 Right Of Access To Personal Data\n"
    "11. TRANSFER OF PERSONAL DATA TO PLACES OUTSIDE MALAYSIA 57.\n"
    "\x0c7\x0c\n1. PURPOSE AND SCOPE OF THIS CODE OF PRACTICE (“Code”)\n"
    "1.1 This Code is developed by Data Users under Section 23 of the Act and is applicable to\n"
    "the Utilities Sector (Water) only.\n"
    "2. DEFINITION\n(i) Data User means a person who processes personal data.\n"
    "3. GENERAL PRINCIPLE\n3.1 General Principle\nThis principle requires Data Users to adhere\n"
    "to the restrictions imposed on processing.\n"
    "\x0c9\x0c\n10. RIGHTS OF DATA SUBJECT\n10.1 A data subject may make a data access request in\n"
    "writing to the data user.\n"
    "11. TRANSFER OF PERSONAL DATA TO PLACES OUTSIDE MALAYSIA\n"
    "Transfer of Personal Data to places outside Malaysia is not permissible unless it is\n"
    "done in the manner prescribed in Section 129 of the Act.\n")


def _extract(text, title="Code of Practice"):
    doc = DiscoveredDoc(doc_id="MY-t", economy=Economy.MY, title=title, source_url="u.pdf",
                        portal="x", fmt=DocFormat.PDF_TEXT)
    return X.extract_provisions(doc, text, OCRMetrics(used=False, pages=9))


def test_toc_entries_are_not_provisions_and_the_body_sections_are():
    provs = _extract(_WATER)
    labels = [p.article_section for p in provs]
    assert labels == ["Section 1", "Section 2", "Section 3", "Section 10", "Section 11"]
    assert not any(p.verbatim_snippet.rstrip().endswith(("45.", "53.", "57.")) for p in provs)
    s11 = provs[-1]
    assert "Section 129 of the Act" in s11.verbatim_snippet
    assert s11.location_ref == "p. 9"            # page sentinels inside the cut were kept


def test_toc_strip_cuts_exactly_from_heading_to_body():
    out = X._strip_contents_toc(_WATER)
    assert "TABLE OF CONTENTS" not in out and "ISI KANDUNGAN" not in out
    assert out.startswith("CODE OF PRACTICE\n")
    # every page sentinel survives, in order, so later page citations still count right
    assert [m.group(1) for m in X.PAGE_MARK_RE.finditer(out)] == ["5", "6", "7", "9"]
    assert "(“Code”)" in out


def test_guideline_without_dotted_headings_splits_on_its_own_numbering():
    """Once the TOC is gone the DPO guideline has no statute-style boundary; its 'N Title' +
    'N.1' headings carry it. Before: 15 TOC stubs and one 20,000-character 'Section 16'."""
    provs = _extract(_DPO, "Personal Data Protection Guidelines on the Appointment of Data "
                           "Protection Officer (DPO)")
    assert [p.article_section for p in provs] == [f"Section {n}" for n in range(1, 7)]
    s6 = provs[-1]
    assert s6.verbatim_snippet.startswith("6 Matters Relating")
    assert "appoint the data protection officer in writing" in s6.verbatim_snippet


def test_a_numbered_line_before_the_first_page_number_leaves_the_text_alone():
    """An entry whose page number wrapped: anchoring on the next entry would cut section 1."""
    text = ("CONTENTS\n1. PURPOSE AND SCOPE OF THIS\nCODE 3\n2. DEFINITION 4\n3. GENERAL 5\n"
            "4. RETENTION 6\n1. PURPOSE AND SCOPE OF THIS CODE\n1.1 Body.\n2. DEFINITION\n")
    assert X._strip_contents_toc(text) == text


def test_statute_arrangement_and_a_numbered_list_ending_in_numbers_are_untouched():
    statute = ("LAWS OF MALAYSIA\nARRANGEMENT OF SECTIONS\n1. Short title\n2. Interpretation\n"
               "ENACTED by the Parliament of Malaysia as follows:\n"
               "1. (1) This Act may be cited as the Example Act 2010.\n"
               "2. (1) In this Act, unless the context otherwise requires, section 12\n")
    assert X._strip_contents_toc(statute) == statute
    no_heading = ("1. Retention period of 7\n2. Records kept for 5\n3. Data held for 3\n"
                  "1. Retention period of 7 years applies.\n")
    assert X._strip_contents_toc(no_heading) == no_heading
