"""Triage and extraction share ONE parse of a PDF — and the verdict must not move.

Extraction is the largest cold stage of a live run (617.1s against 151.4s of LLM grading,
SG pillar-7, 2026-09-14). Profiling inside it (`tools/profile_extraction.py`) found the file
being read twice: the density fallback called `_pdf_text_layer(path)` to decide whether OCR was
needed, and `_extract_pdf` then called it again. The two cost the same — 7.17s vs 7.25s on a
121-page Act, 28.5s vs 29.7s on a 599-page one.

Sharing the parse halves it. The risk is that sharing it also changes the ROUTING, which is the
thing these tests exist to stop: a document that never needed OCR must still never reach the
OCR engine. That is not hypothetical — the first attempt fed the shared texts into the PER-PAGE
branch, and typeset Acts with a blank verso acquired `pages_needing_ocr` and invoked the engine.
"""
from __future__ import annotations

import pytest

from backend.pipeline import ocr, pdf_inspect

SAMPLES = ["data/samples/SG/mas_notice_655.pdf", "data/samples/AU/privacy_act.pdf"]


def _available(path: str) -> bool:
    from pathlib import Path
    return Path(path).exists()


@pytest.mark.parametrize("path", SAMPLES)
def test_the_shared_parse_gives_the_same_verdict_as_a_fresh_one(path):
    """`page_texts_fn` is a speed change. The classification must be bit-identical."""
    if not _available(path):
        pytest.skip(f"{path} not in this checkout")
    fresh = pdf_inspect.profile_pdf(path)
    shared = pdf_inspect.profile_pdf(path, page_texts_fn=lambda: ocr._pdf_page_texts(path))
    assert shared.doc_type == fresh.doc_type
    assert shared.pages_needing_ocr == fresh.pages_needing_ocr
    assert shared.page_count == fresh.page_count


@pytest.mark.parametrize("path", SAMPLES)
def test_the_text_layer_is_identical_whether_or_not_the_parse_is_shared(path):
    if not _available(path):
        pytest.skip(f"{path} not in this checkout")
    assert ocr._pdf_text_layer_from(ocr._pdf_page_texts(path)) == ocr._pdf_text_layer(path)


def test_the_supplier_is_lazy():
    """A fully scanned document must not pay for a text layer nobody will read, and an
    installed `pdf_inspector` must not trigger the supplier at all."""
    calls = []

    def supplier():
        calls.append(1)
        return {1: "x" * 500}

    # An explicit page_texts dict wins, so the supplier is never asked.
    prof = pdf_inspect._profile_by_density("nonexistent.pdf", {1: "y" * 500}, 1, supplier)
    assert calls == [], "an explicit page_texts must take precedence over the supplier"
    assert prof.doc_type == "text_based"


def test_a_typeset_act_with_a_thin_page_still_needs_no_ocr():
    """The regression that reverted the first attempt.

    Under the WHOLE-FILE average rule a 100-page Act averaging far above the floor is
    text_based even with a couple of near-empty pages. Under a per-page rule those pages get
    flagged and the hybrid router calls the OCR engine on a document with a perfect text layer.
    """
    pages = {i: "A" * 3000 for i in range(1, 100)}
    pages[100] = ""                      # a blank verso, as every printed Act has
    prof = pdf_inspect._profile_by_density("x.pdf", None, 100, lambda: pages)
    assert prof.doc_type == "text_based"
    assert prof.pages_needing_ocr == set(), "a blank verso must not route an Act to OCR"


def test_a_genuinely_scanned_file_is_still_caught():
    """The guard must not make everything look text-based."""
    pages = {i: "" for i in range(1, 21)}
    prof = pdf_inspect._profile_by_density("x.pdf", None, 20, lambda: pages)
    assert prof.doc_type == "scanned"
    assert prof.pages_needing_ocr == set(range(1, 21))
