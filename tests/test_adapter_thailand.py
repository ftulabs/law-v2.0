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


# ─────────────────────────────────────────────────────────────────────────────────────────
# Fix round 1: the page-order-drift finding. Round-1 review found that 2 of the 3 panel-cited
# Thai Acts (PDPA, Cybersecurity Act) were present in Step 1's recon and absent from a timed
# `search_th_law` run, because `POST …/law`'s browse-all feed reorders between calls minutes
# apart. The fix (see adapter_thailand.py's module docstring, "DETERMINISM" section) is a
# second, PRIMARY pass that fetches every legislative-grade `hirachy` tier (Act, Organic Act,
# Emergency Decree, Code, Revenue Code, Constitution) in ONE atomic request per tier — probe
# the tier's own `total` (size=1), then fetch `size=total` — so there is no multi-request
# window left for the feed's reordering to act in. These two tests pin that mechanism so a
# future edit cannot silently fold it back into a small, bounded, order-dependent page walk.
# Both mock `robots.allowed` and `time.sleep` (no network, no real delay) and drive
# `search_th_law` through a fake client — still no test here touches the network.
# ─────────────────────────────────────────────────────────────────────────────────────────

class _FakeTierResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def _th_row(law_id, table_of_law_id, title, hirachy=1,
            content="มาตรา 1 เนื้อหาจริงของกฎหมาย"):
    return {"law_id": law_id, "table_of_law_id": table_of_law_id, "hirachy_of_law_id": hirachy,
            "law_name_og": title, "content_all": content}


def test_the_tier_walk_probes_total_then_fetches_a_size_covering_the_whole_tier(monkeypatch):
    """Pins the fix's request shape: a probe call (size=1) to learn the tier's own total, then
    a full fetch whose size covers that total — not a small, fixed page size. A future edit
    that reverts to a bounded per-page walk here restores the exact bug round 1's review
    caught: a panel-cited Act missing from a run because of where the feed happened to sort it.
    """
    monkeypatch.setattr(adapter_thailand.robots, "allowed", lambda *a, **k: (True, ""))
    monkeypatch.setattr(adapter_thailand.time, "sleep", lambda *_a, **_k: None)
    # seed_cache writes real files under settings.cache_path; a test row is not a real
    # document body, so this must not leave fake cache entries behind (the same reason
    # adapter_india.py's own test mocks it).
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache", lambda *a, **k: None)

    tier_rows = {1: [_th_row(1, 1, "พระราชบัญญัติทดสอบหนึ่ง"),
                      _th_row(2, 2, "พระราชบัญญัติทดสอบสอง")]}
    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        hirachy = json.get("hirachy")
        if hirachy is not None:
            rows = tier_rows.get(hirachy, [])
            if json.get("size") == 1:
                return _FakeTierResponse({"rows": rows[:1], "total": str(len(rows))})
            return _FakeTierResponse({"rows": rows, "total": str(len(rows))})
        return _FakeTierResponse({"rows": [], "total": "0"})   # secondary browse walk: nothing

    class _FakeClient:
        post = staticmethod(fake_post)

    src = {"api_base": "https://apig.law.go.th", "api_key": "test-key", "name": "test"}
    docs = adapter_thailand.search_th_law(_FakeClient(), src, "", Economy.TH, [],
                                          lambda m: None)

    tier1_calls = [c for c in calls if c.get("hirachy") == 1]
    assert any(c.get("size") == 1 for c in tier1_calls), (
        "no probe call (size=1) was sent for hirachy=1")
    assert any(c.get("size", 0) >= 2 for c in tier1_calls), (
        "the full fetch must ask for size covering the tier's own total (2 rows here), not a "
        "small fixed page size -- this is what makes the tier fetch atomic and immune to the "
        "feed's own page-order drift")
    assert len(docs) == 2


def test_tier_walk_documents_survive_the_browse_walk_reordering(monkeypatch):
    """Models the exact failure round 1's review caught: the SECONDARY browse walk's
    underlying feed reorders between the two top-level calls (a different row on the second
    call, standing in for the measured "content moving between requests" behaviour), while the
    PRIMARY tier walk's view of the SAME target law does not change, because it is one atomic
    per-tier request rather than a paged walk subject to that reordering. A future edit that
    folds the tier walk back into the paged browse mechanism would fail this test the same way
    the live run failed in round 1.
    """
    monkeypatch.setattr(adapter_thailand.robots, "allowed", lambda *a, **k: (True, ""))
    monkeypatch.setattr(adapter_thailand.time, "sleep", lambda *_a, **_k: None)
    # seed_cache writes real files under settings.cache_path; a test row is not a real
    # document body, so this must not leave fake cache entries behind (the same reason
    # adapter_india.py's own test mocks it).
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache", lambda *a, **k: None)

    pdpa = _th_row(11029, 8668, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562")
    tier_rows = {1: [pdpa]}
    browse_call_count = {"n": 0}

    def make_fake_post():
        def fake_post(url, headers=None, json=None, timeout=None):
            hirachy = json.get("hirachy")
            if hirachy is not None:
                rows = tier_rows.get(hirachy, [])
                if json.get("size") == 1:
                    return _FakeTierResponse({"rows": rows[:1], "total": str(len(rows))})
                return _FakeTierResponse({"rows": rows, "total": str(len(rows))})
            # Secondary browse walk: a DIFFERENT irrelevant row each call, standing in for the
            # feed's own measured reordering between separate search_th_law calls.
            browse_call_count["n"] += 1
            if json.get("page") != 1:
                return _FakeTierResponse({"rows": [], "total": "1"})
            other = _th_row(900 + browse_call_count["n"], 900 + browse_call_count["n"],
                            f"ประกาศฉบับที่ {browse_call_count['n']}", hirachy=2)
            return _FakeTierResponse({"rows": [other], "total": "1"})
        return fake_post

    class _FakeClient:
        def __init__(self):
            self.post = make_fake_post()

    src = {"api_base": "https://apig.law.go.th", "api_key": "test-key", "name": "test"}
    docs1 = adapter_thailand.search_th_law(_FakeClient(), src, "", Economy.TH, [],
                                           lambda m: None)
    docs2 = adapter_thailand.search_th_law(_FakeClient(), src, "", Economy.TH, [],
                                           lambda m: None)

    pdpa1 = [d for d in docs1 if "คุ้มครองข้อมูลส่วนบุคคล" in d.title]
    pdpa2 = [d for d in docs2 if "คุ้มครองข้อมูลส่วนบุคคล" in d.title]
    assert pdpa1 and pdpa2, "PDPA must be found by the deterministic tier walk on every call"
    assert pdpa1[0].doc_id == pdpa2[0].doc_id
