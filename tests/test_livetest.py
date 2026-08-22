"""The 15 October hand-in, generated rather than typed.

The live-test items cannot be fixed on the day: code is frozen at submission, and the hour has
a deadline. So every artefact is pinned here — a format discovered to be wrong at 10:15 on
15 October is a format that stays wrong.
"""
import pytest

from frontend import livetest


class _Meta:
    def __init__(self, **kw):
        self.model_version = kw.get("model", "m/one")
        self.llm_provider = "openrouter"
        self.cost = {"total_usd": kw.get("cost", 0.0289)}
        self.processing_time_seconds = kw.get("elapsed", 138.2)
        self.docs_discovered = kw.get("docs", 18)
        self.provisions_extracted = kw.get("provs", 18)


class _Status:
    def __init__(self, v): self.value = v


class _Row:
    def __init__(self, ind, law, art, status="auto_accepted", tag="NEW"):
        self.indicator_id, self.law_name, self.article_section = ind, law, art
        self.review_status, self.discovery_tag = _Status(status), _Status(tag)


class _Result:
    def __init__(self, meta, rows): self.meta, self.mappings = meta, rows


def _run(slot, state, model="m/one", rows=None, **kw):
    rows = rows if rows is not None else [_Row("6.4", "DPDP Act 2023", "Section 16(1)")]
    livetest.capture(state, slot, _Result(_Meta(model=model, **kw), rows),
                     "2026-10-15T09:00:00", "2026-10-15T09:02:18")


@pytest.fixture
def state():
    s = livetest.new_state()
    s["brief"] = {"economy": "India", "code": "IN", "pillar": 6, "indicators": "6.2 and 6.4"}
    return s


def test_capture_reads_the_run_and_asks_the_operator_for_nothing(state):
    """Start, end, elapsed and cost are all in the run already. Asking a human to copy them
    under time pressure only adds errors the code cannot make."""
    _run("A", state)
    r = state["runs"]["A"]
    assert r["elapsed_s"] == 138.2 and r["cost_usd"] == 0.0289
    assert r["documents"] == 18 and r["rows"] == 1


def test_placeholder_rows_are_not_counted_as_findings(state):
    """"No provision found" is an honest output and not a row we found."""
    _run("A", state, rows=[_Row("6.4", "DPDP Act 2023", "s.16"),
                           _Row("6.1", "No provision found", "N/A")])
    assert state["runs"]["A"]["rows"] == 1


def test_each_engine_gets_credit_for_what_only_it_found(state):
    """The comparison sheet's most interesting cell. Counting it by eye across two exports at
    speed is exactly the arithmetic the template says logging should remove."""
    _run("A", state, model="a/one", rows=[_Row("6.4", "L", "s.16"), _Row("6.2", "L", "s.9")])
    _run("B", state, model="b/two", rows=[_Row("6.4", "L", "s.16"), _Row("7.3", "L", "s.8")])
    assert state["runs"]["A"]["only"] == 1 and state["runs"]["B"]["only"] == 1


def test_run_record_has_a_row_per_engine_even_before_both_have_run(state):
    """A half-finished hour must still produce a well-formed file."""
    _run("A", state)
    csv = livetest.run_record(state)
    lines = csv.strip().splitlines()
    assert lines[0].startswith("Engine,Provider / model,Start")
    assert len(lines) == 3 and lines[2].startswith("Engine B,")


def test_the_short_note_reports_the_count_the_template_asks_for(state):
    """It asks for provisions "you believe absent from the 2025 baseline" — the NEW tag, which
    baseline.py now decides per provision rather than per law."""
    _run("A", state, rows=[_Row("6.4", "L", "s.16", tag="NEW"),
                           _Row("6.2", "L", "s.9", tag="KNOWN")])
    note = livetest.short_note(state)
    assert "absent from the 2025 baseline: **1**" in note
    assert "India" in note and "6.2 and 6.4" in note


def test_the_note_survives_python_docx_being_absent(monkeypatch, state):
    """An optional dependency may cost formatting on the day. It must not cost the deliverable."""
    _run("A", state)
    md = livetest.short_note(state)
    monkeypatch.setattr(livetest, "short_note_docx", lambda _m: None)
    assert livetest.short_note_docx(md) is None
    assert md.startswith("# Live test — short note")


def test_docx_is_produced_when_the_library_is_there(state):
    _run("A", state)
    out = livetest.short_note_docx(livetest.short_note(state))
    if out is None:
        pytest.skip("python-docx not installed")
    assert out[:2] == b"PK" and len(out) > 5000        # a .docx is a zip


def test_engine_comparison_is_quoted_csv(state):
    """Model ids contain slashes and the note contains commas; unquoted CSV would split them."""
    _run("A", state); _run("B", state, model="b/two")
    first = livetest.engine_comparison(state).splitlines()[0]
    assert first.startswith('"Field","Engine A')


def test_the_step_indicator_says_which_step_of_how_many():
    """ui-ux-pro-max, ux/Feedback/Progress Indicators: show progress for multi-step processes.
    Announced to screen readers too, since the visual dots carry it only by colour."""
    html = livetest._steps_html(1)
    assert "Step 2 of 4" in html
    assert 'aria-label="Live test progress"' in html


def test_the_current_step_is_not_signalled_by_colour_alone():
    """WCAG: colour is never the only indicator. Completed steps show a tick, pending show a
    number — legible without colour vision and in a screenshot."""
    html = livetest._steps_html(2)
    assert "✓" in html and "lt-now" in html and "lt-todo" in html


def test_only_the_nine_live_test_economies_are_offered():
    """Being able to NAME an economy and being ready for it are different claims, and this is
    the one screen where the difference is decided against a clock."""
    from backend.schemas import LIVE_TEST_NINE
    assert set(livetest.LIVE_TEST_ORDER) == set(LIVE_TEST_NINE)
