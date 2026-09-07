"""Thailand: recorded as the OCR-heavy scanned-PDF lane. It is the opposite.

sources.yaml said "Thai statutes are published as PDF, frequently scanned … this is the
OCR-heavy lane". law.go.th serves clean full text as JSON, which makes Thailand one of the
two cleanest sources of the eleven alongside India.

The route came from the app's own published sourcemap (src/api/law.js, src/configs/axios.js),
not from defeating a protection. The x-api-key is a public constant compiled into the
JavaScript every visitor downloads, and www.law.go.th/robots.txt answers 4xx to every request
we tried — a WAF error page, not a published ruleset — which backend.pipeline.robots treats
as "no rules published" (an empty ruleset grants) per RFC 9309, verified live by calling
robots.allowed() directly rather than assumed from the raw HTTP status.

Fixture saved 2026-09-07 from POST apig.law.go.th/dga-user-service-phase2/law.
No test here touches the network.
"""
import json
from pathlib import Path

import pytest

from backend.pipeline import adapter_thailand
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "th_law_rows.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rows_become_documents(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert docs, "the API returned rows and the adapter produced no documents"
    assert all(d.economy == Economy.TH for d in docs)


def test_doc_ids_are_unique(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert len({d.doc_id for d in docs}) == len(docs)


def test_every_document_has_a_citable_source_url(payload):
    """The Verbatim Snippet column needs a URL a reviewer can open. An API path is not one:
    apig.law.go.th answers only with the x-api-key header, so the citation must point at the
    human page on www.law.go.th."""
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert all(d.source_url.startswith("http") for d in docs)
    assert all("apig." not in d.source_url for d in docs), (
        "an apig.law.go.th URL is not openable by a reviewer without the key header")


def test_titles_are_thai_and_not_empty(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert all(d.title.strip() for d in docs)
    thai = [d for d in docs if any("฀" <= ch <= "๿" for ch in d.title)]
    assert thai, "no document title contained a Thai character"


def test_a_row_with_no_usable_text_is_dropped_not_emitted_empty(payload):
    """A row whose content_all is empty is a landing record, not an instrument. Emitting it
    produces a document that fetches to nothing and reaches the grader as one blank block —
    the shell problem build._looks_like_a_shell exists to catch downstream."""
    empty = {"rows": [dict(payload["rows"][0], content_all="")]}
    assert adapter_thailand._rows_to_docs(empty, Economy.TH, "law.go.th") == []


def test_an_empty_payload_yields_no_documents_and_does_not_raise():
    assert adapter_thailand._rows_to_docs({}, Economy.TH, "law.go.th") == []
    assert adapter_thailand._rows_to_docs({"rows": []}, Economy.TH, "law.go.th") == []


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("th_law_api") is not None


def test_relevance_score_strictly_distinguishes_an_act_from_a_notification(payload):
    """A flat relevance_score=1.0 (portal.make_doc's own default) would make discovery._cap's
    trim to discovery_max_docs arbitrary among however many rows a page walk turns up. This
    pins that _rows_to_docs does NOT do that: an actual Act (hirachy_of_law_id=1) whose body
    carries มาตรา markers and this adapter's Thai topic vocabulary must outscore a routine
    Ministry notification (hirachy_of_law_id=2) with neither — a flat-1.0 implementation fails
    this assertion outright (both would tie), and so would one that scores the row's TITLE
    alone (both titles below are administrative boilerplate; the difference lives in the body).
    """
    act_row = dict(
        payload["rows"][0],
        law_id=999001,
        table_of_law_id=999001,
        hirachy_of_law_id=1,
        law_name_og="พระราชบัญญัติทดสอบ",
        content_all=(
            "มาตรา 1 พระราชบัญญัตินี้ให้ใช้บังคับ ... ห้ามส่งข้อมูลส่วนบุคคลไปยังต่างประเทศ "
            "เว้นแต่จะได้รับความยินยอม ให้มีเจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล ต้องจัดเก็บข้อมูล "
            "และเก็บรักษาข้อมูลไว้ในราชอาณาจักร ระบบความมั่นคงปลอดภัยไซเบอร์และคอมพิวเตอร์ "
            "มาตรา 2 ให้เป็นไปตามที่กำหนด"
        ),
    )
    notice_row = dict(
        payload["rows"][0],
        law_id=999002,
        table_of_law_id=999002,
        hirachy_of_law_id=2,
        law_name_og="ประกาศทดสอบ",
        content_all="ประกาศฉบับนี้เกี่ยวกับอัตราค่าธรรมเนียมประจำปี ให้มีผลตั้งแต่วันประกาศ",
    )
    docs = adapter_thailand._rows_to_docs(
        {"rows": [act_row, notice_row]}, Economy.TH, "law.go.th")
    by_id = {d.doc_id: d for d in docs}
    act_doc = [d for d in docs if "ทดสอบ" in d.title and d.title.startswith("พระราชบัญญัติ")][0]
    notice_doc = [d for d in docs if d.title.startswith("ประกาศ")][0]
    assert act_doc.relevance_score > notice_doc.relevance_score
