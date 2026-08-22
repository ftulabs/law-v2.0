"""Ingestion defects found by running the Round-2 lanes against the live portals.

Each one was silent: the run completed, produced a CSV, and reported far fewer provisions
than the statute contains — or one provision made of binary noise. None raised.
"""
import pytest

from backend.pipeline import fetch as fetch_mod
from backend.pipeline.extraction import _boundaries
from backend.pipeline.ocr import is_js_app_shell
from backend.providers.ocr_factory import UnavailableOCR, get_ocr_provider
from backend.schemas import DocFormat, Economy


# ── Chinese PDFs put spaces between glyphs ───────────────────────────────────────────
def test_chinese_article_heading_survives_intercharacter_spaces():
    """PDF text extraction renders 第一条 as "第 一 条". The Hainan Informatisation Regulations
    then split into 3 provisions instead of 46 — a 95% loss with nothing logged."""
    text = ("第 一 章 总 则\n"
            "第 一 条 为了规范信息化建设和管理，制定本条例。\n"
            "第 二 条 本省行政区域内的信息化规划与建设，适用本条例。\n"
            "第 十 一 条 省人民政府应当推进电信网、广播电视网和互联网的互联互通。")
    labels = [b[2] for b in _boundaries(text, Economy.CN)]
    # 条 only. This assertion used to include 第一章, and that was the bug: a chapter heading
    # carries a title and no rule, so it became a provision of its own. In the Personal
    # Information Protection Law the first ELEVEN provisions were its table of contents —
    # "第一章　总　则", nine characters — followed by the same chapter headings again from the
    # body. Reading the coverage matrix, they showed up as rows citing no article at all.
    assert labels == ["第一条", "第二条", "第十一条"], labels


def test_a_chinese_chapter_heading_is_not_a_provision():
    """章 and 节 divide a statute; they do not state a rule. `_STRUCT_RE_CN` still matches them
    because ocr.py uses it to ask a different question — does this document look structured at
    all — but provision boundaries come from 条."""
    text = ("第一章 总则\n第一条 为了保护个人信息权益，制定本法。\n"
            "第二节 一般规定\n第二条 自然人的个人信息受法律保护。")
    assert [b[2] for b in _boundaries(text, Economy.CN)] == ["第一条", "第二条"]


def test_a_notice_with_no_articles_still_splits_on_its_chapters():
    """The fallback. An administrative decision numbered only by chapter is better split than
    returned as one block."""
    text = ("第一章 总则\n内容一。\n第二章 管理\n内容二。\n"
            "第三章 附则\n内容三。")
    assert [b[2] for b in _boundaries(text, Economy.CN)] == ["第一章", "第二章", "第三章"]


def test_a_short_chinese_article_is_not_mistaken_for_a_heading_stub():
    """PIPL article 74 reads 本法自2021年11月1日起施行。 — seventeen characters, complete and
    operative. A twenty-character floor written for Latin text deleted it; twenty characters of
    Latin really is a running header, so the floor depends on the script."""
    from backend.pipeline.extraction import _min_provision_chars

    assert _min_provision_chars("本法自2021年11月1日起施行。") == 8
    assert _min_provision_chars("Privacy Act 1988 2") == 20


def test_chinese_label_is_despaced_but_snippet_is_not_touched():
    """The citation should read 第一条; the verbatim text keeps whatever the source produced."""
    labels = [b[2] for b in _boundaries("第 一 条 为了规范信息化建设。", Economy.CN)]
    assert labels == ["第一条"]


def test_chinese_heading_may_not_span_a_line_break():
    r"""The separator class is [ \t　], never \s — with \s a "第\n一\n条" straddling a line break
    would match and swallow unrelated text into one provision."""
    assert _boundaries("第\n一\n条 内容", Economy.CN) == []


# ── SPA shells ───────────────────────────────────────────────────────────────────────
VITE_SHELL = ('<!doctype html><html><head><title>国家法律法规数据库</title>'
              '<script type="module" crossorigin src="/assets/index-Y9B5oxpu.js"></script>'
              '</head><body><div id="app"></div></body></html>')


def test_vite_shell_is_recognised():
    """flk.npc.gov.cn is a Vite SPA. De-chromed it yields the 9-character site title, which
    became a "provision" whose verbatim snippet cited nothing."""
    assert is_js_app_shell(VITE_SHELL) is True


@pytest.mark.parametrize("html", [
    "<html><body><p>第一条 为了保护个人信息权益，制定本法。</p></body></html>",
    "<html><body>14 ДҮГЭЭР ЗҮЙЛ.ГАДААД УЛСАД МЭДЭЭЛЭЛ ДАМЖУУЛАХ</body></html>",
    "<html><body><p>26. Transfer of personal data outside Singapore.</p></body></html>",
])
def test_server_rendered_statutes_are_not_mistaken_for_shells(html):
    """The structure test must be asked in every drafting convention we support: SECTION_RE is
    Latin-only, so a real Chinese or Mongolian page matches none of it and would be discarded
    as an empty shell — losing the entire document."""
    assert is_js_app_shell(html) is False


# ── WORD documents ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,ct", [
    ("https://wb.flk.npc.gov.cn/dfxfg/WORD/8533be.docx", "application/octet-stream"),
    ("https://example.gov/law.doc", "application/octet-stream"),
    ("https://example.gov/law", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
])
def test_word_documents_are_not_classified_as_plain_text(url, ct):
    """A .docx is a ZIP. Read as text it produced a provision beginning "PK docProps/app.xml"
    — and China's laws database serves a large share of its statutes as WORD."""
    fmt, ext = fetch_mod._fmt_for(ct, url)
    assert ext in ("doc", "docx"), (fmt, ext)


def test_pdf_and_html_classification_is_unchanged():
    assert fetch_mod._fmt_for("application/pdf", "https://x/a.pdf")[0] is DocFormat.PDF_TEXT
    assert fetch_mod._fmt_for("text/html", "https://x/a")[0] is DocFormat.HTML


# ── TLS ──────────────────────────────────────────────────────────────────────────────
def test_tls_relaxation_is_a_narrow_host_allowlist():
    """wb.flk.npc.gov.cn serves every Chinese statute PDF and its certificate has expired.
    The exemption must not leak to anything else."""
    assert fetch_mod._tls_relaxed("wb.flk.npc.gov.cn")
    assert fetch_mod._tls_relaxed("WB.FLK.NPC.GOV.CN:443")
    for host in ("flk.npc.gov.cn", "sso.agc.gov.sg", "legislation.gov.au",
                 "evil-wb.flk.npc.gov.cn.attacker.test", "npc.gov.cn"):
        assert not fetch_mod._tls_relaxed(host), host


# ── OCR resolution ───────────────────────────────────────────────────────────────────
def test_engine_without_a_model_for_the_script_is_never_built():
    """LangProfile records None for "no model". Building the engine anyway succeeds — it just
    loads its default (English) dictionary and can then only emit those characters, so Lao
    returns plausible-looking garbage with no error anywhere."""
    provider = get_ocr_provider("rapidocr", economy="LA")
    assert provider.name != "rapidocr"


def test_unreadable_script_fails_only_when_ocr_is_actually_needed():
    """Mongolia's statutes are HTML and never reach an OCR engine, yet resolving the provider
    up-front used to raise and kill the whole run."""
    provider = get_ocr_provider("rapidocr", economy="MN")
    if isinstance(provider, UnavailableOCR):          # depends on which engines are installed
        with pytest.raises(RuntimeError):
            provider.ocr_pdf("anything.pdf")
    else:
        assert getattr(provider, "substituted_for", None) == "rapidocr"


@pytest.mark.parametrize("economy", ["SG", "AU", "MY", "IN"])
def test_latin_economies_still_get_the_configured_engine(economy):
    from backend.config import settings
    assert get_ocr_provider(economy=economy).name == settings.ocr_provider


# ── a search engine cuts the title where the meaning lives ───────────────────────────
def test_a_truncated_search_title_is_recovered_from_the_document():
    """Web search gave us `国家互联网信息办公室关于《个人信息和重要数据出境安全 ...`. The page's
    own header ends `（征求意见稿）公开征求意见的通知` — a 2017 CONSULTATION DRAFT. Two things went
    wrong at once: the Law Name column carried a stump ending in an ellipsis, and
    rdtii/instrument.py classifies on the name, so with 征求意见稿 cut off a draft was exported
    as though it were in force. What a search engine truncates is the END of a title, which is
    exactly where a jurisdiction puts (Amendment), (Repeal) and （征求意见稿）."""
    from backend.pipeline.extraction import _law_name
    from backend.rdtii import instrument
    from backend.schemas import DiscoveredDoc, DocFormat

    full = "国家互联网信息办公室关于《个人信息和重要数据出境安全评估办法（征求意见稿）》公开征求意见的通知"
    text = full + "_中央网络安全和信息化委员会办公室\n设为首页\n加入收藏\n第一条 内容。\n"
    doc = DiscoveredDoc(doc_id="x", economy=Economy.CN,
                        title="国家互联网信息办公室关于《个人信息和重要数据出境安全 ...",
                        source_url="https://www.cac.gov.cn/x.htm", portal="p",
                        fmt=DocFormat.HTML)
    name = _law_name(doc, text)
    assert name == full
    assert instrument.classify(name) is instrument.Status.DRAFT


def test_recovery_only_accepts_a_line_that_continues_the_title():
    """The narrowness is the safety. A "find the best-looking heading" rule would happily put
    an unrelated line in the Law Name column."""
    from backend.pipeline.extraction import _recover_truncated

    text = "某个完全无关的标题\n另一个标题\n"
    assert _recover_truncated("国家互联网信息办公室关于《个人信息 ...", text) is None


def test_commentary_with_no_articles_is_not_turned_into_a_provision():
    """cac.gov.cn publishes 答记者问 and 解读 beside each measure, in the same template and with
    the measure's vocabulary. They have no articles, so they reached the whole-document
    fallback, became one "(document)" provision and were graded. Being unstructured is not
    enough to reject a document — a guidance note can be unnumbered and still be the
    instrument — and being commentary is not enough either. Both together is the signal."""
    from backend.pipeline.extraction import extract_provisions
    from backend.schemas import DiscoveredDoc, DocFormat, OCRMetrics

    ocr = OCRMetrics(provider="markitdown", confidence=1.0, pages=1)
    body = "近日，国家互联网信息办公室有关负责人就《数据出境安全评估办法》相关问题回答了记者提问。" * 3

    press = DiscoveredDoc(doc_id="a", economy=Economy.CN, title="《数据出境安全评估办法》答记者问",
                          source_url="https://www.cac.gov.cn/a.htm", portal="p",
                          fmt=DocFormat.HTML)
    assert extract_provisions(press, body, ocr) == []

    decree = DiscoveredDoc(doc_id="b", economy=Economy.CN, title="关于加强数据管理的决定",
                           source_url="https://www.cac.gov.cn/b.htm", portal="p",
                           fmt=DocFormat.HTML)
    assert len(extract_provisions(decree, body, ocr)) == 1
