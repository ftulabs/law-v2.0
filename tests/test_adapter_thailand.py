"""Thailand: law.go.th's REST API — article-level text and pillar-relevant discovery.

A live pillar run on 2026-09-25 returned 22 documents of which 20 were irrelevant, in 7-11
minutes, and cited every provision as a whole document or a "(passage k of N)" block. Both are
fixed in `backend/pipeline/adapter_thailand.py` (see its module docstring):

  * the `law/detail` endpoint carries each statute as structured items with the portal's OWN
    article numbers, which the adapter writes out one มาตรา per line, so the existing
    line-anchored splitter in extraction.py cuts one provision per article;
  * discovery SEARCHES titles/bodies with pillar vocabulary instead of dropping the 98% of Act
    rows whose `content_all` is empty.

Measured live 2026-09-26 (22 documents per pillar, no grader):
  pillar 7: 19 of 22 are Acts/Codes on topic (PDPA, Cybersecurity, Computer-Related Crime,
            Electronic Transactions, Criminal Procedure Code, Special Investigation,
            Accounting, Revenue Code, Official Information, Credit Information, National
            Intelligence, Anti-Money Laundering, Telecommunications ...); 1,286 provisions, of
            which 1,283 carry a มาตรา citation; discovery 124-129 s cold, 41 s warm.
  pillar 6: PDPA, Electronic Transactions, Payment Systems, Cybersecurity, Credit Information,
            Telecommunications, Computer-Related Crime, the Bank of Thailand IT-outsourcing
            notification, 3 National Cybersecurity Committee notifications (Gazette PDFs);
            discovery 26-35 s warm.
  PDPA มาตรา 28 (cross-border transfer) and มาตรา 41 (DPO) come out as their own provisions
  with their verbatim text; Computer-Related Crime Act มาตรา ๒๖ (traffic-data retention) too.

The detail fixtures are real `law/detail/{id}` payloads fetched 2026-09-26, trimmed to whole
items (no item text edited). No test here touches the network.
"""
import json
from pathlib import Path

import pytest

from backend.pipeline import adapter_thailand as A
from backend.pipeline import extraction
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics

FIX = Path(__file__).parent / "fixtures" / "portals"


def _detail(tid):
    return json.loads((FIX / f"th_law_detail_{tid}.json").read_text(encoding="utf-8"))


def _provisions(text, title="พระราชบัญญัติทดสอบ"):
    doc = DiscoveredDoc(doc_id="TH-test", economy=Economy.TH, title=title,
                        source_url="https://www.law.go.th/DetailLawPage?table_of_law_id=1",
                        portal="law.go.th", fmt=DocFormat.TEXT)
    return extraction.extract_provisions(doc, text, OCRMetrics())


def _digits(label):
    return label.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")).replace(" ", "")


# ── 1. one article per line, numbered by the source ─────────────────────────────────────────

def test_every_article_starts_its_own_line_with_its_heading():
    text, n = A._articles_text(_detail(382))
    lines = text.split("\n")
    assert n == 8 and len(lines) == 8
    assert all(line.startswith("มาตรา ") for line in lines)


def test_a_heading_missing_from_the_text_is_taken_from_the_items_own_number():
    """Table 382 stores the heading only in `content_number`; the line gets THAT number."""
    text, _ = A._articles_text(_detail(382))
    assert "\nมาตรา 28 ในกรณีที่ผู้ควบคุมข้อมูลส่วนบุคคลส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ" in text
    assert "\nมาตรา 41 ผู้ควบคุมข้อมูลส่วนบุคคลและผู้ประมวลผลข้อมูลส่วนบุคคลต้องจัดให้มี" in text


def test_a_heading_already_in_the_text_is_kept_verbatim_and_not_doubled():
    text, n = A._articles_text(_detail(8668))
    assert n == 4
    assert "\nมาตรา ๒๘ ในกรณีที่ผู้ควบคุมข้อมูลส่วนบุคคลส่งหรือโอน" in text
    assert "มาตรา 28" not in text and "มาตรา ๒๘ มาตรา" not in text


def test_no_article_number_is_invented():
    payload = {"rows": [{"law_id": "1", "content_list_process": [
        {"content_type": "มาตรา", "content_number": "7", "content_desc": "<p>ข้อความเจ็ด</p>",
         "seq": 1},
        {"content_type": "มาตรา", "content_number": "", "content_desc": "<p>ไม่มีเลข</p>",
         "seq": 2},
        {"content_type": "มาตรา", "content_number": "8", "content_desc": "<p>ข้อความแปด</p>",
         "seq": 3},
    ]}]}
    text, n = A._articles_text(payload)
    assert (text, n) == ("มาตรา 7 ข้อความเจ็ด\nมาตรา 8 ข้อความแปด", 2)


def test_chapter_headings_countersignature_and_note_are_not_glued_onto_an_article():
    payload = _detail(382)
    text, _ = A._articles_text(payload)
    headings = [A._plain(it["content_desc"])
                for it in payload["rows"][0]["content_list_process"]
                if it["content_type"] in ("หมวด", "ส่วน")]
    # Heading words ("คณะกรรมการ…") recur inside article bodies, so the test is that no
    # article line ENDS with a heading, which is what gluing would look like.
    assert headings
    assert not any(line.endswith(h) for line in text.split("\n") for h in headings)
    assert "ผู้รับสนองพระบรมราชโองการ" not in text
    assert "หมายเหตุ" not in text


def test_an_appended_amending_act_does_not_add_a_second_article_2():
    """Table 9000's row closes with its (ฉบับที่ ๒) amending act and that act's own มาตรา ๒."""
    text, n = A._articles_text(_detail(9000))
    heads = [line.split(" ")[1] for line in text.split("\n") if line.startswith("มาตรา")]
    assert heads == ["๑", "๒", "๑๘", "๒๖"] and n == 4
    assert "(ฉบับที่ ๒)" not in text


def test_a_code_is_kept_and_the_act_promulgating_it_is_not():
    """Table 9280's row is the five-article promulgating Act, then the Code from มาตรา ๑."""
    text, n = A._articles_text(_detail(9280))
    assert text.startswith("มาตรา ๑ ในประมวลกฎหมายนี้")
    assert "ให้ใช้ประมวลกฎหมายวิธีพิจารณาความอาญาตามที่ตราไว้ต่อท้าย" not in text
    assert "สารบาญ" not in text
    assert n == 9


def test_the_version_row_with_the_most_articles_wins_over_a_thin_pointed_at_one():
    def row(law_id, count):
        return {"law_id": law_id, "content_list_process": [
            {"content_type": "มาตรา", "content_number": str(i), "content_desc": f"ข้อ {i}",
             "seq": i} for i in range(1, count + 1)]}
    payload = {"rows": [row("thin", 6), row("full", 80)]}
    assert A._articles_text(payload, prefer_law_id="thin")[1] == 80
    payload = {"rows": [row("current", 75), row("older", 80)]}
    assert A._articles_text(payload, prefer_law_id="current")[1] == 75


def test_a_detail_without_article_items_yields_nothing():
    assert A._articles_text({"rows": [{"content_list_process": []}]}) == ("", 0)
    assert A._articles_text({}) == ("", 0)


# ── 2. the existing splitter now cuts one provision per article ─────────────────────────────

def test_pdpa_sections_28_and_41_are_their_own_provisions_with_verbatim_text():
    text, _ = A._articles_text(_detail(382))
    provs = _provisions(text, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒")
    by = {_digits(p.article_section): p for p in provs}
    assert {"มาตรา28", "มาตรา41"} <= set(by)
    s28 = by["มาตรา28"].verbatim_snippet
    assert "ส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ" in s28
    assert "เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล" not in s28      # s.41 did not bleed in
    assert "จัดให้มี เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล" in by["มาตรา41"].verbatim_snippet
    assert not any(p.article_section == "(document)" for p in provs)


def test_a_cross_reference_inside_an_article_is_not_split_on():
    """s.28 says "ตามมาตรา ๑๖ (๕)" mid-line; that must not become a provision."""
    text, n = A._articles_text(_detail(382))
    assert len(_provisions(text)) == n


def test_computer_crime_retention_section_26_is_its_own_provision():
    text, _ = A._articles_text(_detail(9000))
    provs = _provisions(text)
    s26 = [p for p in provs if _digits(p.article_section) == "มาตรา26"]
    assert s26 and "เก็บรักษาข้อมูลจราจรทางคอมพิวเตอร์ไว้ไม่น้อยกว่าเก้าสิบวัน" in s26[0].verbatim_snippet


# ── 3. ranking ──────────────────────────────────────────────────────────────────────────────

def _row(tid, title, hirachy=1, content="", law_id=None, announce=None):
    return {"table_of_law_id": tid, "law_id": law_id or tid, "law_name_og": title,
            "hirachy_of_law_id": hirachy, "content_all": content, "announce_url": announce}


P7 = A._TITLE_TERMS[7]


def _order(rows, terms=P7, body=None):
    return [A._title(A._principal(f)) for _s, f in A.rank_families(rows, terms, body)]


def test_a_law_family_is_named_by_its_principal_title_not_an_amendment():
    rows = [_row(9280, "พระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายวิธีพิจารณาความอาญา (ฉบับที่ 4) พ.ศ. 2493", 893),
            _row(9280, "ประมวลกฎหมายวิธีพิจารณาความอาญา", 893)]
    assert _order(rows) == ["ประมวลกฎหมายวิธีพิจารณาความอาญา"]


def test_the_law_about_the_topic_outranks_one_that_mentions_it():
    rows = [_row(9138, "พระราชบัญญัติจัดตั้งศาลแขวงและวิธีพิจารณาความอาญาในศาลแขวง พ.ศ. 2499"),
            _row(9280, "ประมวลกฎหมายวิธีพิจารณาความอาญา", 893)]
    assert _order(rows)[0] == "ประมวลกฎหมายวิธีพิจารณาความอาญา"


def test_an_instrument_issued_under_a_topical_act_is_not_about_the_topic():
    rows = [_row(12053, "พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร (ฉบับที่ 765) พ.ศ. 2566", 884),
            _row(8726, "ประมวลรัษฎากร", 893),
            _row(1, "พระราชบัญญัติจัดตั้งศาลปกครองนครสวรรค์ พ.ศ. 2555")]
    ranked = A.rank_families(rows, P7)
    names = [A._title(A._principal(f)) for _s, f in ranked]
    scores = dict(zip(names, (s for s, _f in ranked)))
    assert names[0] == "ประมวลรัษฎากร"
    assert scores["ประมวลรัษฎากร"] > 2 * scores[names[1]]


def test_a_repealed_law_is_dropped():
    rows = [_row(12080, "พระราชบัญญัติวิธีดำเนินการคุมความประพฤติตามประมวลกฎหมายอาญา พ.ศ. 2522 (ยกเลิก)")]
    assert _order(rows) == []


def test_a_body_hit_lifts_a_notification_whose_title_says_nothing():
    notice = _row(5887, "ประกาศธนาคารแห่งประเทศไทย ที่ สนส. 29/2551 เรื่อง การใช้บริการด้านงานเทคโนโลยีสารสนเทศ", 2)
    other = _row(4960, "ประกาศธนาคารแห่งประเทศไทย ที่ สนช. 2/2561 เรื่อง หลักเกณฑ์การกำกับดูแลระบบการชำระเงิน", 2)
    order = _order([other, notice], A._TITLE_TERMS[6], body={5887: 1})
    assert order[0].startswith("ประกาศธนาคารแห่งประเทศไทย ที่ สนส. 29/2551")


def test_no_law_name_is_hardcoded_as_vocabulary():
    """The vocabulary is subject matter, never a whole title."""
    for terms in (*A._TITLE_TERMS.values(), *A._BODY_TERMS.values()):
        for t in terms:
            assert not t.startswith(("พระราชบัญญัติ", "พระราชกำหนด", "ประกาศ")), t
            assert "พ.ศ." not in t, t


# ── 4. the entry point, against a fake client ───────────────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    """Answers searchResult from `search`, law/detail from `details`, the browse feed from
    `tiers`; records every call."""

    def __init__(self, search=None, details=None, tiers=None, search_status=200):
        self.search, self.details, self.tiers = search or {}, details or {}, tiers or {}
        self.search_status = search_status
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/law/searchResult"):
            if self.search_status != 200:
                return _Resp({}, self.search_status)
            rows = self.search.get((json["searchType"], json["searchText"]), [])
            return _Resp({"rows": rows, "total": len(rows)})
        rows = self.tiers.get(json.get("hirachy"), [])
        return _Resp({"rows": rows[: json.get("size") or 1], "total": str(len(rows))})

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        tid = url.rsplit("/", 1)[-1]
        return _Resp(self.details.get(tid, {"rows": []}))


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(A.robots, "allowed", lambda *a, **k: (True, ""))
    monkeypatch.setattr(A.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(A.settings, "cache_dir", str(tmp_path))
    seeded = {}
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache",
                        lambda url, data, *a, **k: seeded.__setitem__(url, data.decode("utf-8")))
    return seeded


SRC = {"api_base": "https://apig.law.go.th", "api_key": "test-key", "name": "law.go.th"}


def _indicators(pillar):
    from backend.rdtii.indicators import get_indicators
    return get_indicators(pillar)


def test_search_uses_the_bundles_payload_shape_for_titles_and_bodies(offline):
    client = _Client()
    A.search_th_law(client, SRC, "", Economy.TH, _indicators(6), lambda m: None)
    bodies = [c[2] for c in client.calls if c[1].endswith("/law/searchResult")]
    assert {b["searchType"] for b in bodies} == {1, 2}
    assert all(set(b) == {"type", "agency", "hirachy", "searchType", "searchText", "size",
                          "page"} for b in bodies)
    assert {b["searchText"] for b in bodies if b["searchType"] == 1} == set(A._TITLE_TERMS[6])


def test_the_seeded_text_is_one_article_per_line_under_the_citable_url(offline):
    pdpa = _row(382, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒", law_id="966")
    client = _Client(search={(1, "ข้อมูลส่วนบุคคล"): [pdpa]}, details={"382": _detail(382)})
    docs = A.search_th_law(client, SRC, "", Economy.TH, _indicators(7), lambda m: None)
    assert [d.source_url for d in docs] == [
        "https://www.law.go.th/DetailLawPage?table_of_law_id=382"]
    assert "apig." not in docs[0].source_url
    seeded = offline[docs[0].source_url]
    assert seeded.split("\n")[3].startswith("มาตรา 28 ในกรณีที่ผู้ควบคุม")


def test_details_are_fetched_only_for_the_documents_discovery_keeps(offline, monkeypatch):
    monkeypatch.setattr(A.settings, "discovery_max_docs", 2)
    rows = [_row(i, f"พระราชบัญญัติข้อมูลเครดิตฉบับทดสอบ{i}", content="ข้อความ") for i in range(10)]
    client = _Client(search={(1, "ข้อมูลเครดิต"): rows})
    docs = A.search_th_law(client, SRC, "", Economy.TH, _indicators(7), lambda m: None)
    assert len(docs) == 2
    assert len([c for c in client.calls if c[0] == "GET"]) == 2


def test_a_second_run_reads_rebuilt_articles_from_cache_not_the_network(offline):
    pdpa = _row(382, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒")
    client = _Client(search={(1, "ข้อมูลส่วนบุคคล"): [pdpa]}, details={"382": _detail(382)})
    A.search_th_law(client, SRC, "", Economy.TH, _indicators(6), lambda m: None)
    A.search_th_law(client, SRC, "", Economy.TH, _indicators(7), lambda m: None)
    assert len([c for c in client.calls if c[0] == "GET"]) == 1


def test_the_same_law_under_two_ids_is_one_document_using_the_id_with_articles(offline):
    a = _row(8668, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562\n")
    b = _row(382, "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒", content="ข้อความทั้งฉบับ")
    client = _Client(search={(1, "ข้อมูลส่วนบุคคล"): [a, b]},
                     details={"8668": {"rows": []}, "382": _detail(382)})
    docs = A.search_th_law(client, SRC, "", Economy.TH, _indicators(7), lambda m: None)
    assert len(docs) == 1
    assert offline[docs[0].source_url].startswith("มาตรา 1 ")


def test_no_articles_falls_back_to_content_all_then_to_the_gazette_pdf(offline):
    notice = _row(5887, "ประกาศธนาคารแห่งประเทศไทย เรื่อง ทดสอบ", 2, content="ข้อ ๑ ข้อความจริง")
    cyber = _row(11618, "ประกาศคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ เรื่อง ทดสอบ", 2,
                 announce="https://ratchakitcha.soc.go.th/documents/17190586.pdf")
    empty = _row(1, "ประกาศคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์ เรื่อง ไม่มีข้อความ", 2)
    client = _Client(search={(1, "ความมั่นคงปลอดภัยไซเบอร์"): [cyber, empty],
                             (2, "ไว้ในประเทศไทย"): [notice]})
    docs = A.search_th_law(client, SRC, "", Economy.TH, _indicators(6), lambda m: None)
    urls = {d.source_url for d in docs}
    assert "https://ratchakitcha.soc.go.th/documents/17190586.pdf" in urls
    assert offline["https://www.law.go.th/DetailLawPage?table_of_law_id=5887"] == "ข้อ ๑ ข้อความจริง"
    assert len(docs) == 2                             # the one with no text anywhere is dropped


def test_when_search_is_down_the_act_tier_walk_supplies_candidates(offline):
    act = _row(9000, "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550",
               law_id="19250")
    client = _Client(search_status=400, tiers={1: [act]}, details={"9000": _detail(9000)})
    docs = A.search_th_law(client, SRC, "", Economy.TH, _indicators(7), lambda m: None)
    assert [d.title for d in docs] == [act["law_name_og"]]
    assert any(c[2] and c[2].get("hirachy") == 1 for c in client.calls)


def test_missing_config_returns_nothing_and_says_so(offline):
    said = []
    assert A.search_th_law(_Client(), {}, "", Economy.TH, [], said.append) == []
    assert said and said[0].startswith("[error]")


def test_the_adapter_is_registered_as_a_portal_enumerator():
    from backend.pipeline import portal
    assert portal.get_adapter("th_law_api") is not None
    assert portal.enumerates_portal("th_law_api")
