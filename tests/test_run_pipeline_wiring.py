"""The wiring Phase 1 built and no test protected.

Deleting the explain_empty_discovery call from run_pipeline, or the live_discovery guard,
left the whole suite green -- so the feature that tells a judge WHY a run found nothing was
one careless edit from vanishing silently. These tests read the orchestrator's own source,
because driving a full run needs an LLM and neither grader is reachable.

Source-reading tests are weaker than behavioural ones and are chosen deliberately: they fail
on the deletion they exist to catch, and they need no network, no key and no fixture.
"""
import inspect

from backend.pipeline import discovery, orchestrator


def _run_source() -> str:
    fn = getattr(orchestrator, "run_pipeline", None) or orchestrator.run
    return inspect.getsource(fn)


def test_run_pipeline_explains_an_empty_live_discovery():
    src = _run_source()
    assert "explain_empty_discovery" in src, (
        "the orchestrator no longer explains a zero-document live run; a judged run would "
        "again export an empty CSV and exit 0")


def test_the_explanation_is_gated_on_live_discovery():
    src = _run_source()
    assert "live_discovery" in src, (
        "without the guard the explanation also fires on the reuse_documents second pass, "
        "where zero documents means the cached bodies are gone and no portal was contacted")


def test_the_second_pass_has_its_own_explanation():
    assert hasattr(orchestrator, "_explain_lost_cached_bodies")
    src = _run_source()
    assert "_explain_lost_cached_bodies" in src


def test_the_search_diagnostics_are_reset_once_per_run():
    src = _run_source()
    assert "reset_diagnostics" in src, (
        "without a per-run reset, run N reports run N-1's engine failures — the Streamlit "
        "process is long-lived and most economies no longer enter the web-search lane at all")


def test_every_explanation_line_is_an_error_pair():
    """frontend/runview.py reads these as (what happened, what to do). A last line that does
    not start with 'what to do:' leaves the Run screen showing a diagnosis with no action."""
    from backend.schemas import Economy
    from backend.pipeline import websearch
    websearch.reset_diagnostics()
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)
    assert lines and all(ln.startswith("[error] ") for ln in lines)
    assert lines[-1].startswith("[error] what to do:")
