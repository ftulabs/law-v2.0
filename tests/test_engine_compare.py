"""The provision-by-provision engine comparison — Section 5 of the final submission form.

"A comparison covering every provision either engine produced ... which engine found it; for
shared provisions, how the indicator, the article citation or the quoted words differed."
Code is frozen on 30 September and this file is handed in at 11:00 on 15 October, so each of
those clauses is pinned by a test here, plus one end-to-end pass through the real pipeline.
"""
import csv
import io

import pytest

from backend.export import engine_compare as ec
from frontend import livetest


class _S:
    def __init__(self, v): self.value = v


class _M:
    """An EvidenceMapping stand-in carrying only what the comparison reads."""
    def __init__(self, ind, law, art, quote="", conf=0.9, status="auto_accepted",
                 url="https://example.gov/law"):
        self.indicator_id, self.law_name, self.article_section = ind, law, art
        self.verbatim_snippet, self.confidence_score = quote, conf
        self.review_status, self.discovery_tag = _S(status), _S("NEW")
        self.source_url = url


PDPA = "Personal Data Protection Act 2012"


def _one(rows, found_by=None):
    hit = [r for r in rows if found_by is None or r.found_by == found_by]
    assert len(hit) == 1, [(r.found_by, (r.a or r.b).article) for r in rows]
    return hit[0]


# ── which engine found it ────────────────────────────────────────────────────────────
def test_identical_passes_are_all_shared_and_identical():
    a = [_M("P6-I4", PDPA, "Section 26", "shall not transfer"), _M("P7-I4", PDPA, "s. 11(3)", "dpo")]
    rows = ec.compare(a, list(a))
    s = ec.summary(rows)
    assert s == {"provisions": 2, "both": 2, "a_only": 0, "b_only": 0, "indicator_differs": 0,
                 "citation_differs": 0, "quote_differs": 0, "identical": 2}


def test_each_engine_is_credited_with_what_only_it_found():
    a = [_M("6.4", PDPA, "Section 26", "x"), _M("6.2", PDPA, "Section 9", "y")]
    b = [_M("6.4", PDPA, "Section 26", "x"), _M("7.3", PDPA, "Section 8", "z")]
    rows = ec.compare(a, b)
    assert _one(rows, ec.A_ONLY).a.article == "Section 9"
    assert _one(rows, ec.B_ONLY).b.article == "Section 8"
    assert ec.summary(rows)["both"] == 1


def test_one_engine_finding_nothing_leaves_every_row_to_the_other():
    rows = ec.compare([_M("6.4", PDPA, "Section 26", "x")], [])
    assert [r.found_by for r in rows] == [ec.A_ONLY]
    assert rows[0].differs == "Only engine A mapped this provision"


# ── for shared provisions: how the INDICATOR differed ────────────────────────────────
def test_a_different_indicator_is_one_disagreement_not_two_finds():
    """The defect this module replaces: keyed on (indicator, law, article), this was two
    'only this engine' rows and no disagreement at all."""
    rows = ec.compare([_M("6.4", PDPA, "Section 26", "q")], [_M("6.1", PDPA, "Section 26", "q")])
    r = _one(rows)
    assert r.found_by == ec.BOTH and r.indicator == ec.DIFFERS
    assert "A adds 6.4" in r.differs and "B adds 6.1" in r.differs


def test_a_provision_mapped_to_several_indicators_is_one_row():
    a = [_M("6.1", PDPA, "Section 26", "q"), _M("6.2", PDPA, "Section 26", "q")]
    b = [_M("6.2", PDPA, "Section 26", "q")]
    r = _one(ec.compare(a, b))
    assert r.a.indicators == ["6.1", "6.2"] and r.indicator == ec.DIFFERS
    assert r.differs == "indicator: A adds 6.1"


def test_indicator_ids_are_written_as_rdtii_codes():
    r = _one(ec.compare([_M("P7-I5", PDPA, "s.40", "q")], [_M("7.5", PDPA, "s.40", "q")]))
    assert r.indicator == ec.SAME and r.a.indicators == ["7.5"]


# ── for shared provisions: how the ARTICLE CITATION differed ─────────────────────────
def test_the_same_words_cited_to_a_different_article_are_paired():
    quote = "Personal data shall not be transferred outside Singapore except in accordance"
    rows = ec.compare([_M("6.4", PDPA, "Section 26", quote)],
                      [_M("6.4", PDPA, "Section 26(1)", quote)])
    r = _one(rows)
    assert r.found_by == ec.BOTH and r.citation == ec.DIFFERS
    assert "Section 26(1)" in r.differs


def test_citation_formatting_alone_is_not_a_difference():
    r = _one(ec.compare([_M("6.4", PDPA, "Section 26", "q")],
                        [_M("6.4", PDPA, "section  26", "q")]))
    assert r.citation == ec.SAME


def test_different_articles_with_different_words_stay_separate():
    rows = ec.compare([_M("6.4", PDPA, "Section 26", "transfer abroad")],
                      [_M("6.4", PDPA, "Section 24", "protection obligation")])
    assert sorted(r.found_by for r in rows) == [ec.A_ONLY, ec.B_ONLY]


# ── for shared provisions: how the QUOTED WORDS differed ─────────────────────────────
def test_a_different_quote_is_reported():
    r = _one(ec.compare([_M("6.4", PDPA, "Section 26", "shall not transfer")],
                        [_M("6.4", PDPA, "Section 26", "may transfer if")]))
    assert r.quote == ec.DIFFERS and "quoted words differ" in r.differs


def test_a_longer_extract_of_the_same_words_is_an_overlap():
    r = _one(ec.compare([_M("6.4", PDPA, "Section 26", "shall not transfer")],
                        [_M("6.4", PDPA, "Section 26", "An organisation shall not transfer any")]))
    assert r.quote == ec.OVERLAP


def test_whitespace_and_punctuation_are_not_a_different_quote():
    r = _one(ec.compare([_M("6.4", PDPA, "Section 26", "shall  not\ntransfer.")],
                        [_M("6.4", PDPA, "Section 26", "shall not transfer")]))
    assert r.quote == ec.SAME


def test_full_width_chinese_punctuation_matches_ascii():
    law = "中华人民共和国个人信息保护法"
    r = _one(ec.compare([_M("6.4", law, "第三十八条", "向境外提供个人信息（一）")],
                        [_M("6.4", law, "第三十八条", "向境外提供个人信息(一)")]))
    assert r.found_by == ec.BOTH and r.quote == ec.SAME


# ── provision identity ───────────────────────────────────────────────────────────────
def _P(ind, art, pid, quote="q"):
    m = _M(ind, PDPA, art, quote)
    m.provision_id = pid
    return m


def test_the_extraction_id_is_the_identity_when_both_passes_carry_it():
    """Two different provisions whose article strings happen to read alike (a schedule's
    'Section 1' and the Act's 'Section 1') stay two provisions."""
    a = [_P("6.4", "Section 1", "SG-x#p1"), _P("6.4", "Section 1", "SG-x#p90", "other")]
    rows = ec.compare(a, [_P("6.4", "Section 1", "SG-x#p1")])
    assert sorted(r.found_by for r in rows) == [ec.BOTH, ec.A_ONLY]


def test_the_same_quote_on_another_provision_id_is_a_citation_difference():
    quote = "shall not transfer personal data outside the country"
    rows = ec.compare([_P("6.4", "Section 26", "SG-x#p26", quote)],
                      [_P("6.4", "Section 27", "SG-x#p27", quote)])
    r = _one(rows)
    assert r.found_by == ec.BOTH and r.citation == ec.DIFFERS


# ── what counts as a provision ───────────────────────────────────────────────────────
def test_placeholders_and_rows_set_aside_are_not_provisions():
    """The comparison covers what each engine handed in — the same rows as its evidence file."""
    a = [_M("6.1", "No provision found", "N/A"), _M("6.4", PDPA, "s.26", "q", status="rejected"),
         _M("6.2", PDPA, "s.9", "q", status="quarantined"), _M("7.4", PDPA, "s.11", "d")]
    rows = ec.compare(a, [])
    assert [(r.a.article) for r in rows] == ["s.11"]


def test_rows_without_an_article_are_kept_apart_by_their_words():
    rows = ec.compare([_M("7.1", PDPA, "", "first whole document"),
                       _M("7.2", PDPA, "", "second whole document")], [])
    assert len(rows) == 2


# ── the file handed in ───────────────────────────────────────────────────────────────
def test_csv_has_every_column_a_bom_and_survives_non_latin_text():
    rows = ec.compare([_M("6.4", "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล", "มาตรา 28", "ข้อมูล")],
                      [_M("6.2", "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล", "มาตรา 28", "ข้อมูล")])
    raw = ec.to_csv(rows)
    assert raw.startswith(b"\xef\xbb\xbf")
    parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert list(parsed[0]) == ec.COLUMNS
    assert parsed[0]["Law name"].startswith("พระราชบัญญัติ")
    assert parsed[0]["Indicator"] == ec.DIFFERS


def test_every_provision_is_numbered_once_shared_first():
    a = [_M("6.4", "B Act", "s.1", "a1"), _M("6.4", "A Act", "s.2", "a2")]
    b = [_M("6.4", "A Act", "s.2", "a2"), _M("7.3", "C Act", "s.3", "c3")]
    t = ec.table(ec.compare(a, b))
    assert [r["Provision #"] for r in t] == [1, 2, 3]
    assert [r["Found by"] for r in t] == [ec.BOTH, ec.A_ONLY, ec.B_ONLY]


# ── the live-test screen ─────────────────────────────────────────────────────────────
class _Meta:
    def __init__(self, model, fetched):
        self.run_id, self.model_version, self.llm_provider = "run-x", model, "openrouter"
        self.cost, self.processing_time_seconds = {"total_usd": 0.01}, 60.0
        self.docs_discovered, self.docs_fetched, self.provisions_extracted = 3, fetched, 30


class _Result:
    def __init__(self, meta, rows): self.meta, self.mappings = meta, rows


@pytest.fixture
def state():
    s = livetest.new_state()
    s["brief"] = {"economy": "Singapore", "code": "SG", "pillar": 6, "task": "SG p6"}
    return s


def _capture(state, slot, rows, fetched):
    livetest.capture(state, slot, _Result(_Meta(f"m/{slot}", fetched), rows),
                     "2026-10-15T10:00:00", "2026-10-15T10:20:00")


def test_the_screen_hands_in_a_provision_comparison_once_both_have_run(state):
    _capture(state, "A", [_M("6.4", PDPA, "s.26", "q"), _M("6.2", PDPA, "s.9", "y")], 3)
    assert livetest.provision_comparison(state) is None          # B has not run
    _capture(state, "B", [_M("6.1", PDPA, "s.26", "q")], 0)
    raw = livetest.provision_comparison(state)
    parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert {r["Found by"] for r in parsed} == {ec.BOTH, ec.A_ONLY}
    # the old key counted the indicator swap on s.26 as a find for each engine
    assert state["runs"]["A"]["only"] == 1 and state["runs"]["B"]["only"] == 0


def test_the_summary_sheet_and_the_note_carry_the_same_totals(state):
    _capture(state, "A", [_M("6.4", PDPA, "s.26", "q")], 3)
    _capture(state, "B", [_M("6.1", PDPA, "s.26", "q")], 0)
    summary_csv = livetest.engine_comparison(state)
    assert '"  of which: indicator differs","1","1",""' in summary_csv
    note = livetest.short_note(state)
    assert "1 found by both" in note and "1 differ in indicator" in note


def test_rerunning_engine_a_alone_drops_a_stale_comparison(state):
    _capture(state, "A", [_M("6.4", PDPA, "s.26", "q")], 3)
    _capture(state, "B", [_M("6.4", PDPA, "s.26", "q")], 0)
    assert livetest.provision_comparison(state) is not None
    del state["runs"]["B"]
    _capture(state, "A", [_M("6.4", PDPA, "s.26", "q")], 3)
    assert livetest.provision_comparison(state) is None


# ── end to end: two real passes of the pipeline ──────────────────────────────────────
def test_two_real_passes_over_the_same_documents_compare_cleanly(tmp_path, monkeypatch):
    """Engine A runs; engine B re-reads A's documents (fetching nothing); the comparison
    covers every exported row of both. Mock engine on both sides, so the passes agree and
    every shared provision must come out identical — any difference is a comparison bug."""
    from backend.config import settings
    from backend.export import csv_text
    from backend.pipeline.orchestrator import run_pipeline
    from backend.schemas import Economy

    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    kw = dict(use_samples=True, ocr_provider="mock", llm_provider="mock",
              log=lambda *_: None, use_result_cache=False, translation_enabled=False)
    first = run_pipeline(Economy.SG, [6], **kw)
    second = run_pipeline(Economy.SG, [6], reuse_documents=list(first.meta.documents), **kw)
    assert second.meta.docs_fetched == 0

    rows = ec.compare(first.mappings, second.mappings)
    s = ec.summary(rows)
    exported_a = list(csv.DictReader(io.StringIO(csv_text(first.mappings))))
    real_a = [r for r in exported_a if r.get("Law Name") not in ("No provision found",
                                                                 "Not assessed")]
    assert real_a, "the sample run exported no provisions — the test proves nothing"
    assert s["a_only"] == s["b_only"] == 0
    assert s["identical"] == s["both"] == s["provisions"] > 0


# ── the screen itself renders the comparison and the download ───────────────────────
def _screen_script():
    import streamlit as st

    from backend.export import engine_compare as ec  # noqa: F401
    from frontend import livetest
    from backend.schemas import (DiscoveryTag, Economy, EvidenceMapping, ReviewStatus,
                                 RunMeta, RunResult)
    from tests.test_engine_compare import PDPA

    def _Meta(model, fetched):
        return RunMeta(run_id=f"run-{model[-1]}", economy=Economy.SG, pillars=[6],
                       started_at="2026-10-15T10:00:00", model_version=model,
                       llm_provider="openrouter", cost={"total_usd": 0.01},
                       processing_time_seconds=60.0, docs_discovered=3,
                       docs_fetched=fetched, provisions_extracted=30)

    def _Result(meta, rows):
        return RunResult(meta=meta, mappings=rows)

    def _M(ind, law, art, quote):
        # Real EvidenceMapping objects: the hand-in step writes the evidence CSV from them.
        return EvidenceMapping(
            mapping_id=f"m-{ind}-{art}", run_id="run-x", provision_id=f"SG-abc#{art}",
            economy=Economy.SG, pillar=6,
            indicator_id=ind, law_name=law, article_section=art, verbatim_snippet=quote,
            source_url="https://sso.agc.gov.sg/Act/PDPA2012", mapping_rationale="r",
            confidence_score=0.9, discovery_tag=DiscoveryTag("NEW"),
            review_status=ReviewStatus("auto_accepted"))

    if "lt" not in st.session_state:
        s = livetest.new_state()
        s["brief"] = {"economy": "Singapore", "code": "SG", "pillar": 6, "task": "SG p6"}
        for slot, rows, fetched in (("A", [_M("6.4", PDPA, "s.26", "q"),
                                           _M("6.2", PDPA, "s.9", "y")], 3),
                                    ("B", [_M("6.1", PDPA, "s.26", "q")], 0)):
            livetest.capture(s, slot, _Result(_Meta(f"m/{slot}", fetched), rows),
                             "2026-10-15T10:00:00", "2026-10-15T10:20:00")
        s["step"] = st.session_state.get("_want_step", 2)
        st.session_state["lt"] = s
    livetest.render(st.session_state["lt"], {"SG": "Singapore"})


@pytest.fixture
def _restore_main():
    """AppTest replaces sys.modules["__main__"] with its temporary script and never puts it
    back. Every later test that starts a `spawn` process then re-runs THAT script in the
    child (NameError: __args) — which is how this test broke test_fetch_index_concurrency in
    CI on 2026-09-29, while each passed alone."""
    import sys
    saved = sys.modules["__main__"]
    yield
    sys.modules["__main__"] = saved


@pytest.mark.parametrize("step", [2, 3])
def test_compare_and_hand_in_steps_render(step, _restore_main):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_screen_script)
    at.session_state["_want_step"] = step
    at.run(timeout=60)
    assert not at.exception, at.exception
    if step == 2:
        assert len(at.dataframe) == 1
        assert any("distinct provisions" in c.value for c in at.caption)
    else:
        labels = [b.label for b in at.get("download_button")]
        assert "Provision comparison (.csv)" in labels, labels
