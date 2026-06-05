"""Indicator mapping against known examples (offline mock grader)."""
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy


def _auto(economy):
    r = run_pipeline(economy, [6, 7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    return [m for m in r.mappings if m.review_status.value == "auto_accepted"], r.mappings


def test_sg_pdpa_maps_to_data_protection_framework():
    auto, _ = _auto(Economy.SG)
    # PDPA s13 (consent to collect/use) is evidence of the data-protection framework -> P7-I1
    hits = [m for m in auto if m.indicator_id == "P7-I1" and "13" in m.article_section]
    assert hits, "SG PDPA s13 should auto-map to P7-I1 (data-protection framework)"


def test_sg_cybersecurity_act_maps_to_P7I2():
    auto, _ = _auto(Economy.SG)
    # the Cybersecurity Act establishes a dedicated cybersecurity framework -> P7-I2
    hits = [m for m in auto if m.indicator_id == "P7-I2" and "Cybersecurity" in m.law_name]
    assert hits, "SG Cybersecurity Act should auto-map to P7-I2"


def test_p6_mappings_have_localisation_context():
    _, ms = _auto(Economy.SG)
    # Pillar 6 (localisation) provisions must concern cross-border movement OR a localisation
    # requirement (store/process/host in-country), not a generic domestic clause.
    for m in ms:
        if m.indicator_id.startswith("P6"):
            text = m.verbatim_snippet.lower()
            assert any(k in text for k in ("transfer", "outside", "overseas", "cross", "foreign",
                                           "stored", "store", "storage", "located in", "territory",
                                           "locally", "server", "data centre", "infrastructure")), \
                f"P6 mapping without localisation context: {m.article_section}"


def test_sectoral_notice_is_not_auto_accepted():
    auto, ms = _auto(Economy.SG)
    mas = [m for m in ms if "MAS" in m.law_name]
    assert all(m.review_status.value != "auto_accepted" for m in mas), \
        "sectoral MAS notice must never auto-accept against national indicators"
