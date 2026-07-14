"""Extraction cache (Zone 2a): identical bytes + same OCR provider must extract to the same
text, so a repeat call should be served from cache instead of re-running the OCR/text-layer
pass — the single biggest per-run cost bucket on a live crawl.
"""
from backend.config import settings
from backend.pipeline import ocr as ocr_mod
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics


def _doc(text: str) -> DiscoveredDoc:
    return DiscoveredDoc(doc_id="d", economy=Economy.SG, title="Test Act 2020",
                         source_url="u", portal="p", fmt=DocFormat.TEXT,
                         discovery_tag="NEW", raw_text=text)


def test_cache_hit_skips_reextraction(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "extraction_cache_enabled", True)

    calls = {"n": 0}
    orig = ocr_mod._extract_document_text

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(ocr_mod, "_extract_document_text", counting)

    doc = _doc("Section 1 A real body of text long enough to matter here.")
    text1, metrics1 = ocr_mod.get_document_text(doc)
    text2, metrics2 = ocr_mod.get_document_text(doc)

    assert calls["n"] == 1, "second call must be served from cache, not re-run"
    assert text1 == text2
    assert metrics1.model_dump() == metrics2.model_dump()


def test_different_content_is_not_conflated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "extraction_cache_enabled", True)

    text_a, _ = ocr_mod.get_document_text(_doc("Section 1 First document body text here."))
    text_b, _ = ocr_mod.get_document_text(_doc("Section 1 A completely different document."))
    assert text_a != text_b


def test_cache_disabled_still_works(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "extraction_cache_enabled", False)
    doc = _doc("Section 1 Some body text for the disabled-cache path.")
    text, metrics = ocr_mod.get_document_text(doc)
    assert "Some body text" in text
    assert isinstance(metrics, OCRMetrics)
    assert not (settings.cache_path / "_extracted").exists() or \
        not list((settings.cache_path / "_extracted").glob("*.json"))
