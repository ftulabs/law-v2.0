"""The 15 October hand-in, generated rather than typed.

The live-test items cannot be fixed on the day: code is frozen at submission, and the hour has
a deadline. So every artefact is pinned here — a format discovered to be wrong at 10:15 on
15 October is a format that stays wrong.
"""
import pytest

from frontend import livetest


class _Meta:
    def __init__(self, **kw):
        self.run_id = kw.get("run_id", "run-abc12345")
        self.model_version = kw.get("model", "m/one")
        self.llm_provider = "openrouter"
        self.cost = {"total_usd": kw.get("cost", 0.0289)}
        self.processing_time_seconds = kw.get("elapsed", 138.2)
        self.docs_discovered = kw.get("docs", 18)
        # The cell the organisers' template marks "must be 0" for the second pass.
        self.docs_fetched = kw.get("fetched", 18)
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
    s["brief"] = {"economy": "India", "code": "IN", "pillar": 6,
                  "task": "India, pillar 6, indicators 6.2 and 6.4"}
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
    lines = [ln for ln in csv.strip().splitlines() if ln.startswith(("Engine", '"'))]
    header = next(ln for ln in lines if ln.startswith("Engine,Provider"))
    assert "Documents fetched" in header
    assert any(ln.startswith("Engine B,,") for ln in lines)


def test_the_short_note_reports_the_count_the_template_asks_for(state):
    """It asks for provisions "you believe absent from the 2025 baseline" — the NEW tag, which
    baseline.py now decides per provision rather than per law."""
    _run("A", state, rows=[_Row("6.4", "L", "s.16", tag="NEW"),
                           _Row("6.2", "L", "s.9", tag="KNOWN")])
    note = livetest.short_note(state)
    assert "India" in note and "6.2 and 6.4" in note
    # The organisers' own section order, so a steward does not have to hunt for an answer.
    for heading in ("1 · The run", "2 · What came out", "3 · What worked", "4 · What broke",
                    "5 · What a reviewer should be cautious about",
                    "6 · Anything done by hand", "7 · Declaration"):
        assert heading in note, heading


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


def test_the_picker_offers_exactly_what_the_assignment_can_name():
    """Being able to NAME an economy and being ready for it are different claims, and this is
    the one screen where the difference is decided against a clock.

    Eleven, not nine: the panel publishes eight countries and the assignment "draws from the
    listed economies", which includes the mandatory three. Timor-Leste is on the list and
    carries the bonus; nothing that is NOT on it may be offered here."""
    from backend.schemas import FINAL_ROUND_LIST, LIVE_TEST_POOL, ROUND1_ECONOMIES
    assert set(livetest.LIVE_TEST_ORDER) == set(LIVE_TEST_POOL)
    assert "TL" in FINAL_ROUND_LIST, "Timor-Leste is on the list and carries a bonus"
    assert set(LIVE_TEST_POOL) == set(FINAL_ROUND_LIST) | set(ROUND1_ECONOMIES)


# ── what the organisers' own template requires, and this file used to get wrong ──────
def test_the_second_pass_must_fetch_nothing(state):
    """The template's comparison table has one cell with an instruction printed in it:
    "Documents fetched during this pass — must be 0" for engine B. Two live crawls minutes
    apart differ in what the portal served, so a second pass that re-fetches measures the
    weather rather than the engine."""
    _run("A", state, model="a/one", fetched=18)
    _run("B", state, model="b/two", fetched=0)
    assert state["runs"]["B"]["fetched"] == 0
    csv = livetest.engine_comparison(state)
    assert "Documents fetched during this pass" in csv
    note = livetest.short_note(state)
    assert "fetched nothing" in note


def test_a_second_pass_that_did_fetch_is_called_out(state):
    """Silence here would let a broken comparison be handed in as a good one."""
    _run("A", state, model="a/one", fetched=18)
    _run("B", state, model="b/two", fetched=7)
    assert "not engine-isolated" in livetest.short_note(state)


def test_the_comparison_states_the_difference_not_just_two_columns(state):
    """"Show cost per run and cost difference between engines" — orientation notes. A column
    each leaves the reader doing the arithmetic the tool already did."""
    _run("A", state, model="a/one", cost=0.0400, fetched=18)
    _run("B", state, model="b/two", cost=0.0250, fetched=0)
    csv = livetest.engine_comparison(state)
    assert "Difference (B \u2212 A)" in csv or "Difference" in csv
    assert "-0.0150" in csv
    html = livetest._delta_html(state["runs"]["A"], state["runs"]["B"])
    assert "0.0150" in html and "engine B" in html


def test_the_better_value_is_marked_in_each_row(state):
    """Two columns of numbers make a reader compare by eye under a clock."""
    _run("A", state, model="a/one", cost=0.0400, provs=10, fetched=18)
    _run("B", state, model="b/two", cost=0.0250, provs=14, fetched=0)
    html = livetest._comparison_html(state["runs"]["A"], state["runs"]["B"])
    assert html.count("class='win'") >= 2


def test_both_engines_are_switchable_from_the_interface(state):
    """"Engine swap should be UI-driven, not code-level." A declaration that can only be read
    back fails the criterion it was written for — on the day a declared model can be
    rate-limited and the steward has to watch the switch happen."""
    assert set(state["engines"]) == {"A", "B"}
    for slot in ("A", "B"):
        assert state["engines"][slot]["provider"] and state["engines"][slot]["model"]


def test_the_declared_pair_comes_from_configuration_not_from_this_screen():
    """So the README, the run record and the interface cannot disagree about what was
    declared on 30 September."""
    from backend.config import settings

    s = livetest.new_state()
    assert s["engines"]["A"]["model"] == settings.declared_engine_a_model
    assert s["engines"]["B"]["model"] == settings.declared_engine_b_model


def test_any_economy_and_any_pillar_can_be_named(state):
    """"Assignment will draw from any listed country, any pillar." The nine come first because
    the brief says so, but nothing is excluded."""
    order = livetest.economy_order(["SG", "MN", "AU", "CN"])
    assert order[0] in livetest.LIVE_TEST_ORDER
    assert set(order) == {"SG", "MN", "AU", "CN"}


def test_the_run_record_carries_the_task_as_read_out(state):
    """Section 1 of the note asks for the steward's words, and the run record heads with them."""
    _run("A", state)
    assert "India, pillar 6" in livetest.run_record(state)
