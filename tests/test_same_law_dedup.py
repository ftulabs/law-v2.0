"""Same-law dedup across URL/version variants (the SG over-extraction the user reported).

One law is served by SSO under several URLs whose BYTES differ — an as-enacted gazette
snapshot (/Acts-Supp/N-YYYY/Published/) and the current consolidated edition (/Act/{id})
both contain "Cybersecurity Act 2018" but with different provision counts. Content-SHA
dedup can't catch that; these tests pin the name-based dedup that does, and the recovery
that resolves both variants to the same name.
"""
from backend.pipeline.orchestrator import _dedup_provisions_by_law, _law_identity
from backend.pipeline.extraction import _recover_law_name
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, OCRMetrics, Provision


def _identity(name):
    return _law_identity(name)


def test_law_identity_folds_case_and_trailing_year():
    assert _identity("CYBERSECURITY ACT 2018") == _identity("Cybersecurity Act 2018")
    assert _identity("Employment Act") == _identity("Employment Act 1968")
    # the Amendment Act must stay distinct from its principal Act
    assert _identity("Cybersecurity (Amendment) Act 2024") != _identity("Cybersecurity Act 2018")
    # different instruments under one parent stay distinct (Act vs Regulations)
    assert _identity("Personal Data Protection Act 2012") \
        != _identity("Personal Data Protection Regulations 2021")


def _doc(doc_id, url):
    return DiscoveredDoc(doc_id=doc_id, economy=Economy.SG, title="t", source_url=url,
                         portal="SG", fmt=DocFormat.PDF_TEXT, discovery_tag=DiscoveryTag.NEW)


def _provs(doc_id, name, n):
    return [Provision(provision_id=f"{doc_id}#p{i}", doc_id=doc_id, economy=Economy.SG,
                      law_name=name, article_section=f"Section {i}", verbatim_snippet="x",
                      source_url="u", ocr=OCRMetrics()) for i in range(n)]


def test_dedup_keeps_consolidated_over_as_published():
    docs = [_doc("d0", "https://sso.agc.gov.sg/Act/CA2018?ViewType=Pdf"),
            _doc("d1", "https://sso.agc.gov.sg/Acts-Supp/9-2018/Published/20180312?ViewType=Pdf")]
    provs = _provs("d0", "Cybersecurity Act 2018", 149) + _provs("d1", "CYBERSECURITY ACT 2018", 121)
    out = _dedup_provisions_by_law(provs, docs, log=lambda *_: None)
    assert {p.doc_id for p in out} == {"d0"}            # consolidated kept, as-published dropped
    assert len(out) == 149


def test_dedup_tiebreaks_to_fuller_text_when_no_published_marker():
    docs = [_doc("d0", "https://sso.agc.gov.sg/Act/PDPA2012?ViewType=Pdf"),
            _doc("d1", "https://sso.agc.gov.sg/Act/PDPA2012?DocDate=2019&ViewType=Pdf")]
    provs = _provs("d0", "Personal Data Protection Act 2012", 218) \
        + _provs("d1", "Personal Data Protection Act 2012", 143)
    out = _dedup_provisions_by_law(provs, docs, log=lambda *_: None)
    assert {p.doc_id for p in out} == {"d0"} and len(out) == 218


def test_dedup_keeps_distinct_laws():
    docs = [_doc("d0", "https://sso.agc.gov.sg/Act/CA2018"),
            _doc("d1", "https://sso.agc.gov.sg/Acts-Supp/8-2024/Published/20240709"),
            _doc("d2", "https://sso.agc.gov.sg/Act/PDPA2012")]
    provs = (_provs("d0", "Cybersecurity Act 2018", 149)
             + _provs("d1", "Cybersecurity (Amendment) Act 2024", 67)
             + _provs("d2", "Personal Data Protection Act 2012", 218))
    out = _dedup_provisions_by_law(provs, docs, log=lambda *_: None)
    assert {p.doc_id for p in out} == {"d0", "d1", "d2"}    # all three are different laws


# ─────────── recovery resolves both variants to the same instrument name ───────────
def test_recover_instrument_from_consolidated_revised_edition_header():
    """Consolidated SSO PDF: a Revised-Edition cover, then the Title-Case name right before
    the table of contents. Recovery must return the name, not the LRC publisher boilerplate."""
    header = ("THE STATUTES OF THE REPUBLIC OF SINGAPORE\nCYBERSECURITY ACT 2018\n"
              "2020 REVISED EDITION\nPrepared and Published by\nTHE LAW REVISION COMMISSION\n"
              "UNDER THE AUTHORITY OF\nTHE REVISED EDITION OF THE LAWS ACT 1983\n"
              "Informal Consolidation version in force from 31/10/2025\n2020 Ed.\n"
              "Cybersecurity Act 2018\nARRANGEMENT OF SECTIONS\n1. Short title")
    assert _recover_law_name(header) == "Cybersecurity Act 2018"


def test_recover_instrument_from_as_enacted_gazette_header():
    """As-enacted gazette: the enactment formula ends '…on 2 March 2018:' (a colon-clause,
    not a title), then the ALL-CAPS name, then a '(No. 9 of 2018)' citation."""
    header = ("REPUBLIC OF SINGAPORE\nGOVERNMENT GAZETTE\nACTS SUPPLEMENT\n"
              "The following Act was passed by Parliament and assented to by\n"
              "the President on 2 March 2018:\nCYBERSECURITY ACT 2018\n(No. 9 of 2018)\n"
              "ARRANGEMENT OF SECTIONS\n1. Short title")
    assert _recover_law_name(header) == "CYBERSECURITY ACT 2018"


def test_recover_does_not_pull_jurisdiction_header():
    """MY-style header: name line is complete, must not absorb 'LAWS OF MALAYSIA' / 'Act 709'."""
    header = "LAWS OF MALAYSIA\nAct 709\nPERSONAL DATA PROTECTION ACT 2010\nARRANGEMENT OF SECTIONS\n1. Short"
    assert _recover_law_name(header) == "PERSONAL DATA PROTECTION ACT 2010"


def test_recover_my_amendment_below_act_number_no_toc():
    """A short MY amendment Act has no 'ARRANGEMENT OF' table — the wrapped name sits below
    the 'Act A1727' number header. The 'ACT 2024' year line must not be read as the number."""
    header = ("Personal Data Protection (Amendment) 1\nLAWS OF MALAYSIA\nAct A1727\n"
              "PERSONAL DATA PROTECTION (AMENDMENT)\nACT 2024\n\n"
              "An Act to amend the Personal Data Protection Act 2010.")
    assert _recover_law_name(header) == "PERSONAL DATA PROTECTION (AMENDMENT) ACT 2024"


# ─────────── non-Latin titles (China P6, 2026-09-29: the same Measures kept twice) ───────────
def test_law_identity_keeps_non_latin_titles():
    """`[^a-z0-9]` turned every Chinese/Russian/Mongolian title into "" — nothing ever grouped."""
    assert _identity("个人信息出境认证办法") == "个人信息出境认证办法"
    assert _identity("个人信息出境认证办法") != _identity("个人信息出境标准合同办法")
    assert _identity("Федеральный закон О персональных данных")
    assert _identity("ТУХАЙ ХУУЛЬ")
    # Thai titles end in a Buddhist-era year; it is stripped like a Gregorian one
    assert _identity("พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562") \
        == _identity("พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล")


def test_dedup_merges_a_chinese_law_served_by_two_portals():
    docs = [_doc("gov", "https://www.gov.cn/gongbao/2025/issue_12426/202511/content_7049740.html"),
            _doc("cac", "https://www.cac.gov.cn/2025-10/17/c_1762449728720008.htm")]
    mk = lambda d, n: [Provision(provision_id=f"{d}#p{i}", doc_id=d, economy=Economy.CN,
                                 law_name="个人信息出境认证办法", article_section=f"第{i}条",
                                 verbatim_snippet="x", source_url="u", ocr=OCRMetrics())
                       for i in range(1, n + 1)]
    out = _dedup_provisions_by_law(mk("gov", 20) + mk("cac", 20), docs, log=lambda *_: None)
    assert len({p.doc_id for p in out}) == 1 and len(out) == 20


def _row(url, conf, ind="P6-I4", snippet="个人信息处理者……应当同时符合下列情形：\n（一）非关键信息基础设施运营者；"):
    from backend.schemas import EvidenceMapping, ReviewStatus
    return EvidenceMapping(mapping_id=url + ind, run_id="r", economy=Economy.CN, pillar=6,
                           indicator_id=ind, provision_id=url + "#p5", law_name="个人信息出境认证办法", article_section="第五条",
                           verbatim_snippet=snippet, source_url=url, mapping_rationale="x",
                           confidence_score=conf, discovery_tag=DiscoveryTag.NEW,
                           review_status=ReviewStatus.AUTO_ACCEPTED)


def test_duplicate_rows_collapse_to_the_most_confident():
    from backend.pipeline.orchestrator import _drop_duplicate_rows
    a = _row("https://www.gov.cn/a", 0.80)
    b = _row("https://www.cac.gov.cn/b", 0.86,
             snippet="个人信息处理者……应当同时符合下列情形： （一）非关键信息基础设施运营者；")  # other line breaks
    other_indicator = _row("https://www.gov.cn/a", 0.70, ind="P6-I2")
    out = _drop_duplicate_rows([a, b, other_indicator], log=lambda *_: None)
    assert [m.source_url for m in out] == ["https://www.cac.gov.cn/b", "https://www.gov.cn/a"]
    assert {m.indicator_id for m in out} == {"P6-I4", "P6-I2"}
