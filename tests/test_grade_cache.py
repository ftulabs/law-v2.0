"""The grading verdict cache — and the two cases that make it safe.

Grading was the only expensive stage with no cache: 151.4s of a 200s warm Singapore pillar-7
run, identical on every re-run, while fetch collapsed to 0.0s and extraction to 9.1s
(measured 2026-09-14). A verdict is a pure function of (model, SYSTEM, user prompt), so it
caches the same way everything else already does.

Two properties carry the risk and both are pinned here:
  * an ENGINE SWAP must miss — otherwise the panel's two-engine comparison would silently
    compare engine A with itself;
  * a FAILED call must never be stored — otherwise one truncated response becomes a permanent
    verdict for that provision.
"""
from __future__ import annotations

import pytest

from backend.config import settings
from backend.pipeline import grade_cache

SYS = "You are a legal-evidence grader. Decide whether ONE provision satisfies ONE indicator."
USER_A = "<TARGET_INDICATOR>P6-I4</TARGET_INDICATOR><SNIPPET>An organisation shall not…</SNIPPET>"
USER_B = "<TARGET_INDICATOR>P6-I1</TARGET_INDICATOR><SNIPPET>An organisation shall not…</SNIPPET>"
VERDICT = {"operative_rule": "Permits transfer on conditions", "satisfies_target": True,
           "better_sibling": None, "relevant": True, "legal_match": 1.0,
           "scope_alignment": 1.0, "scope_flag": None, "subsection": None,
           "rationale": "This Section permits cross-border transfer subject to conditions."}


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "cache_path",
                        property(lambda self: tmp_path), raising=False)
    monkeypatch.setattr(settings, "grading_cache_enabled", True, raising=False)
    grade_cache.reset_stats()
    yield


def test_a_verdict_round_trips():
    assert grade_cache.get("model-x", SYS, USER_A) is None
    grade_cache.put("model-x", SYS, USER_A, VERDICT)
    assert grade_cache.get("model-x", SYS, USER_A) == VERDICT
    assert grade_cache.stats()["hit"] == 1


def test_an_engine_swap_misses():
    """The property the 15 October two-engine comparison depends on."""
    grade_cache.put("engine-a", SYS, USER_A, VERDICT)
    assert grade_cache.get("engine-b", SYS, USER_A) is None, (
        "engine B must re-grade; serving A's verdict would compare A with itself")


def test_editing_the_system_prompt_invalidates_everything():
    """A definition change must not be answered from verdicts given under the old one."""
    grade_cache.put("model-x", SYS, USER_A, VERDICT)
    assert grade_cache.get("model-x", SYS + " WHAT IS RESTRICTED MUST BE DATA.", USER_A) is None


def test_a_different_indicator_is_a_different_question():
    """Same provision, different target — the siblings block differs, so the key must."""
    grade_cache.put("model-x", SYS, USER_A, VERDICT)
    assert grade_cache.get("model-x", SYS, USER_B) is None


def test_a_failed_call_is_never_stored():
    """An unparseable response is a FAILED CALL, which the breaker counts — not a verdict.

    Storing one would make a transient truncation permanent for that provision, which is the
    failure mode `mapping` already has a comment about (Insurance Act 49Q lost on ~2/3 of runs).
    """
    grade_cache.put("model-x", SYS, USER_A, {"_parse_error": True, "_raw": "…"})
    assert grade_cache.get("model-x", SYS, USER_A) is None
    grade_cache.put("model-x", SYS, USER_A, {})
    assert grade_cache.get("model-x", SYS, USER_A) is None


def test_a_corrupt_entry_is_a_miss_not_a_crash():
    grade_cache.put("model-x", SYS, USER_A, VERDICT)
    p = settings.cache_path / "_verdicts" / f"{grade_cache.key('model-x', SYS, USER_A)}.json"
    p.write_text("{not json", encoding="utf-8")
    assert grade_cache.get("model-x", SYS, USER_A) is None


def test_the_mock_grader_is_never_cached():
    """It is free, and the offline demo's determinism must come from the mock's code — a stale
    verdict outliving an edit to the mock would buy nothing and hide the change."""
    assert not grade_cache.cacheable("mock")
    grade_cache.put("mock-grounded-grader-0.1", SYS, USER_A, VERDICT, "mock")
    assert grade_cache.get("mock-grounded-grader-0.1", SYS, USER_A, "mock") is None
    assert grade_cache.cacheable("local") and grade_cache.cacheable("openrouter")


def test_disabling_it_makes_it_inert():
    grade_cache.put("model-x", SYS, USER_A, VERDICT)
    settings.grading_cache_enabled = False
    assert grade_cache.get("model-x", SYS, USER_A) is None


def test_the_key_is_unambiguous_across_field_boundaries():
    """Fields are length-delimited, so no two different inputs can concatenate to one key."""
    assert grade_cache.key("ab", "c", "d") != grade_cache.key("a", "bc", "d")
    assert grade_cache.key("a", "b", "cd") != grade_cache.key("a", "bc", "d")


def test_mapping_serves_a_second_run_without_calling_the_model():
    """End to end through map_provisions: the second run makes no call at all."""
    from backend.pipeline import mapping
    from backend.providers import get_ocr_provider
    from backend.pipeline import discovery, extraction
    from backend.pipeline.ocr import get_document_text
    from backend.rdtii import get_indicators
    from backend.schemas import Economy

    ocrp = get_ocr_provider("mock")
    provs, texts = [], {}
    for d in discovery.discover_from_samples(Economy.SG, pillar=7):
        raw, o = get_document_text(d, ocr_provider=ocrp)
        texts[d.doc_id] = raw
        provs += extraction.extract_provisions(d, raw, o)

    class Counting:
        # NOT "mock": the mock grader is deliberately never cached (grade_cache._NEVER_CACHE),
        # because it is free and its determinism must come from its code.
        name, model_version = "local", "counting-grader-1"
        calls = 0
        def suggested_concurrency(self): return 4
        def complete_json(self, system, user):
            Counting.calls += 1
            return dict(VERDICT)

    llm = Counting()
    inds = get_indicators(7)
    first = mapping.map_provisions("r1", provs, 7, inds, source_texts=texts, llm=llm,
                                   top_k=5, log=lambda *_: None)
    after_first = Counting.calls
    assert after_first > 0

    second = mapping.map_provisions("r2", provs, 7, inds, source_texts=texts, llm=llm,
                                    top_k=5, log=lambda *_: None)
    assert Counting.calls == after_first, "the second run must make no model call"
    assert len(second) == len(first), "and must produce the same rows"
