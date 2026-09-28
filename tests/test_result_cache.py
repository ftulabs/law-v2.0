"""The full-result cache must say when it answered, and must not outlive the code that made it.

Two defects, found 2026-09-29. A repeat Run returned the stored result with the original run's
time and cost and nothing on screen said so; and the key held inputs only, with no expiry, so a
result computed before a fix was still served after it.
"""
import os
import time

import pytest

from backend.config import settings
from backend.pipeline import orchestrator
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "result_cache_enabled", True)
    monkeypatch.setattr(settings, "result_cache_ttl_hours", 24.0)
    monkeypatch.setattr(orchestrator, "_CODE_FINGERPRINT", "code-a")
    return tmp_path


def _run(**kw):
    return run_pipeline(Economy.SG, [6], use_samples=True, ocr_provider="mock",
                        llm_provider="mock", log=lambda *_: None,
                        translation_enabled=False, **kw)


def test_a_live_run_is_not_marked_and_a_repeat_is(isolated_cache):
    first = _run()
    assert first.meta.served_from_cache is None
    again = _run()
    assert again.meta.run_id == first.meta.run_id
    assert again.meta.served_from_cache == first.meta.finished_at


def test_a_code_change_misses_the_cache(isolated_cache, monkeypatch):
    first = _run()
    monkeypatch.setattr(orchestrator, "_CODE_FINGERPRINT", "code-b")
    after_fix = _run()
    assert after_fix.meta.served_from_cache is None
    assert after_fix.meta.run_id != first.meta.run_id


def test_translation_is_part_of_the_key(isolated_cache):
    from backend.providers import get_llm_provider, get_ocr_provider
    ocr, llm = get_ocr_provider("mock"), get_llm_provider("mock")
    args = (Economy.MN, [6], False, ocr, llm, 5, False, None)
    assert (orchestrator._result_cache_file(*args, do_translate=False)
            != orchestrator._result_cache_file(*args, do_translate=True))


def test_an_expired_result_is_not_served(isolated_cache):
    _run()
    for f in (isolated_cache / "_results").glob("*.json"):
        old = time.time() - 25 * 3600
        os.utime(f, (old, old))
    assert _run().meta.served_from_cache is None


def test_a_code_change_deletes_the_old_results(isolated_cache, monkeypatch):
    results = isolated_cache / "_results"
    _run()
    (results / "SG_P6_0123456789abcdef.json").write_text("{}")   # pre-fingerprint name
    monkeypatch.setattr(orchestrator, "_CODE_FINGERPRINT", "code-b")
    _run()
    names = [f.name for f in results.glob("*.json")]
    assert len(names) == 1 and "_code-b_" in names[0]


def test_a_new_live_run_replaces_the_stored_one(isolated_cache):
    first = _run()
    fresh = _run(use_result_cache=False)
    assert fresh.meta.run_id != first.meta.run_id
    assert len(list((isolated_cache / "_results").glob("*.json"))) == 1
    served = _run()
    assert served.meta.run_id == fresh.meta.run_id
    assert served.meta.served_from_cache == fresh.meta.finished_at


def test_a_second_pass_never_reads_the_cache(isolated_cache):
    first = _run()
    second = _run(reuse_documents=list(first.meta.documents))
    assert second.meta.served_from_cache is None
    assert second.meta.run_id != first.meta.run_id
