"""Three silences found on 2026-09-25, pinned so they stay audible.

1. A grading call that never came back was reported as a legal finding. The grading server went
   down mid-run; India's CSV said "No provision found" for all nine indicators after 9 of 9
   calls had failed. The row must say the run could not grade, and must still be written.
2. A long document with no article marker kept only its first MAX_SNIPPET characters. A Thai
   Act from law.go.th (whose API text carries no heading for original articles) lost everything
   after its opening clauses.
3. Translations were cached without the model that made them (last test).
"""
from backend.export.csv_export import _row
from backend.pipeline.extraction import MAX_SNIPPET, _passages, extract_provisions
from backend.pipeline.orchestrator import _no_evidence_placeholders
from backend.rdtii import get_indicators
from backend.schemas import (SUBMITTABLE_STATUSES, DiscoveredDoc, DocFormat, Economy,
                             OCRMetrics)


def test_an_indicator_that_lost_calls_is_not_reported_as_absent():
    inds = get_indicators(6)
    rows = _no_evidence_placeholders("r", Economy.IN, inds, [], lambda _m: None, None,
                                     gaps={"P6-I1": (5, 5)})
    lost = next(r for r in rows if r.indicator_id == "P6-I1")
    assert lost.law_name == "Not assessed"
    assert "NOT a finding" in lost.mapping_rationale
    # still written to the CSV (a missing indicator reads as a blank), but held for a human
    assert lost.review_status.value in SUBMITTABLE_STATUSES
    assert lost.review_status.value == "pending_review"
    assert _row(lost)["Confidence"] == "N/A"
    # an indicator whose calls all came back keeps the judges' wording
    other = next(r for r in rows if r.indicator_id == "P6-I2")
    assert other.law_name == "No provision found"


def test_passages_cover_the_text_exactly_once():
    text = ("ข้อความ " * 3000) + ("a" * 9000)          # a whitespace-free tail is cut hard
    spans = _passages(text)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
    assert all(b - a <= 4000 for a, b in spans)


def test_a_long_unnumbered_document_is_not_truncated():
    body = ("พระราชบัญญัตินี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ " * 1500).strip()
    assert len(body) > MAX_SNIPPET
    doc = DiscoveredDoc(doc_id="TH:t", economy=Economy.TH, title="พระราชบัญญัติทดสอบ",
                        source_url="https://www.law.go.th/x", portal="p", fmt=DocFormat.TEXT)
    provs = extract_provisions(doc, body, OCRMetrics())
    assert len(provs) > 1
    assert provs[0].article_section.startswith("(passage 1 of ")
    kept = sum(len(p.verbatim_snippet) for p in provs)
    assert kept >= len(body) - len(provs) * 2           # only boundary whitespace is trimmed


def test_a_short_unnumbered_document_is_still_one_block():
    doc = DiscoveredDoc(doc_id="TH:s", economy=Economy.TH, title="ประกาศ",
                        source_url="https://www.law.go.th/y", portal="p", fmt=DocFormat.TEXT)
    provs = extract_provisions(doc, "ประกาศนี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ " * 40,
                               OCRMetrics())
    assert [p.article_section for p in provs] == ["(document)"]


def test_a_translation_cached_by_one_model_is_not_served_for_another(tmp_path, monkeypatch):
    """Third silence: Mongolian law names translated a month earlier by a weak model were
    served to a run on a strong one ("On the Approval of the Chemical Industry" for On
    Electronic Signature), because the cache key carried no model."""
    from backend.pipeline import translate

    monkeypatch.setattr(translate, "_cache_dir", lambda: tmp_path)

    class _LLM:
        name = "openrouter"

        def __init__(self, model, answer):
            self.model_version, self._answer = model, answer

        def complete_json(self, _sys, _user):
            return {"translation": self._answer}

    weak = _LLM("weak-4b", "ON THE APPROVAL OF THE CHEMICAL INDUSTRY")
    strong = _LLM("strong-80b", "ON ELECTRONIC SIGNATURE")
    src = "ЦАХИМ ГАРЫН ҮСГИЙН ТУХАЙ"
    assert translate._translate_one(weak, src, "English", print) == weak._answer
    assert translate._translate_one(strong, src, "English", print) == strong._answer
    assert translate._translate_one(weak, src, "English", print) == weak._answer   # each keeps its own
