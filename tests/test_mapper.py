"""Indicator mapping against known examples (offline mock grader)."""
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy


def _auto(economy):
    r = run_pipeline(economy, [6, 7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    return [m for m in r.mappings if m.review_status.value == "auto_accepted"], r.mappings


def test_sg_consent_maps_to_legal_basis():
    auto, _ = _auto(Economy.SG)
    # PDPA s13 (consent) -> P7-I1 Legal basis for processing
    hits = [m for m in auto if m.indicator_id == "P7-I1" and "13" in m.article_section]
    assert hits, "SG PDPA s13 should auto-map to P7-I1"


def test_sg_breach_maps_to_breach_indicator():
    auto, _ = _auto(Economy.SG)
    assert any(m.indicator_id == "P7-I4" for m in auto), "expected a data breach notification mapping"


def test_p6_mappings_have_cross_border_context():
    _, ms = _auto(Economy.SG)
    for m in ms:
        if m.indicator_id.startswith("P6"):
            text = m.verbatim_snippet.lower()
            assert any(k in text for k in ("transfer", "outside", "overseas", "cross", "foreign")), \
                f"P6 mapping without transfer context: {m.article_section}"


def test_sectoral_notice_is_not_auto_accepted():
    auto, ms = _auto(Economy.SG)
    mas = [m for m in ms if "MAS" in m.law_name]
    assert all(m.review_status.value != "auto_accepted" for m in mas), \
        "sectoral MAS notice must never auto-accept against national indicators"
