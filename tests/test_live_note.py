"""The live-test short note: the organisers' template, filled from the runs — including when a
run breaks. A note that says nothing about a failure is worse than no note: the template says
"an honest account of what broke earns credit"."""
import io
import re
from pathlib import Path

import pytest

from backend.export import live_note
from frontend import livetest

docx = pytest.importorskip("docx")


class _V:
    def __init__(self, v): self.value = v


class _Conf:
    def __init__(self, g): self.snippet_grounding = g


class _M:
    def __init__(self, ind, law, art, *, conf=0.9, status="auto_accepted", tag="NEW",
                 pid=None, quote="the quoted words", notes="", grounding=1.0):
        self.indicator_id, self.law_name, self.article_section = ind, law, art
        self.confidence_score, self.review_status, self.discovery_tag = conf, _V(status), _V(tag)
        self.provision_id = pid or f"{law}#{art}"
        self.verbatim_snippet, self.notes = quote, notes
        self.confidence = _Conf(grounding)
        self.source_url = "https://legalinfo.mn/x"


class _Doc:
    def __init__(self, url): self.source_url, self.title = url, "doc"


class _Meta:
    def __init__(self, model, fetched, docs=3, provider="openrouter", cached=None):
        self.run_id, self.model_version, self.llm_provider = "run-x", model, provider
        self.cost = {"total_usd": 0.05}
        self.processing_time_seconds = 120.0
        self.docs_discovered, self.docs_fetched, self.provisions_extracted = docs, fetched, 40
        self.documents = [_Doc(f"https://legalinfo.mn/law/{i}") for i in range(docs)]
        self.ocr_reports = []
        self.served_from_cache = cached


class _Result:
    def __init__(self, meta, rows): self.meta, self.mappings = meta, rows


def _cap(state, slot, rows, *, fetched, log=(), **kw):
    livetest.capture(state, slot, _Result(_Meta(f"m/{slot}", fetched, **kw), rows),
                     "2026-10-15T03:00:00+00:00", "2026-10-15T03:02:00+00:00",
                     log_lines=list(log))


@pytest.fixture
def state():
    s = livetest.new_state()
    s["brief"] = {"economy": "Mongolia", "code": "MN", "pillar": 6,
                  "task": "Mongolia, pillar 6"}
    return s


LAW = "Хувийн мэдээлэл хамгаалах тухай"


def _read(b: bytes):
    return docx.Document(io.BytesIO(b))


def _text(cell) -> str:
    """A cell's words including any table nested in it — sections 3 and 4 keep their writing
    box in one, and python-docx's `cell.text` does not look inside."""
    return cell.text + "".join(_text(c) for t in cell.tables for r in t.rows for c in r.cells)


# ── the template, filled ──────────────────────────────────────────────────────────────
def test_the_note_is_the_organisers_template_with_every_field_filled(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1"), _M("P6-I4", LAW, "8.2", tag="KNOWN")], fetched=3)
    _cap(state, "B", [_M("P6-I2", LAW, "7.1")], fetched=0)
    d = _read(livetest.short_note_docx(state))
    t_run, t_out, t_wb, t_caution = d.tables[:4]
    assert t_run.rows[1].cells[1].text == "FTU — VeriTrade"
    assert "Mongolia, pillar 6" in t_run.rows[2].cells[1].text
    assert t_run.rows[3].cells[1].text == "openrouter · m/A"
    assert t_run.rows[4].cells[1].text == "openrouter · m/B"
    assert "submitted" in t_run.rows[5].cells[1].text
    # section 2, per provision: A exported 2 (one of them KNOWN), B exported 1
    assert [t_out.rows[1].cells[i].text for i in (1, 2)] == ["2", "1"]
    assert [t_out.rows[2].cells[i].text for i in (1, 2)] == ["1", "1"]
    assert t_out.rows[3].cells[1].text == "3" and t_out.rows[3].cells[2].text.startswith("0")
    assert "must be 0" in t_out.rows[3].cells[2].text          # the template's own words kept
    # sections 3-5 are written, not left blank
    worked, broke = _text(t_wb.rows[0].cells[0]), _text(t_wb.rows[0].cells[2])
    assert "fetched nothing" in worked
    assert "What broke" in broke and "No step failed" in broke
    # inside the template's writing box, not under it
    assert "fetched nothing" in _text(t_wb.rows[0].cells[0].tables[0].rows[0].cells[0])
    assert t_caution.rows[0].cells[0].text.strip()
    # the signature block stays empty: it is signed on paper
    sig = d.tables[5]
    assert all(not c.text.strip() for c in sig.rows[0].cells)


def test_the_by_hand_box_ticks_exactly_one(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3)
    box = next(p.text for p in _read(livetest.short_note_docx(state)).paragraphs if "by hand." in p.text)
    assert box.count("☒") == 1 and box.index("☒") < box.index("Nothing")
    state["notes"]["by_hand"] = "retyped the task line"
    d = _read(livetest.short_note_docx(state))
    box = next(p.text for p in d.paragraphs if "by hand." in p.text)
    assert box.count("☒") == 1 and box.index("☒") > box.index("Nothing")
    assert "retyped the task line" in d.tables[4].rows[0].cells[0].text


def test_the_template_file_ships_with_the_code():
    assert live_note.TEMPLATE.exists(), "the Docker image and a fresh clone need the template"


def test_an_operators_own_words_replace_the_draft(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3)
    state["notes"]["worked"] = "The Mongolian portal lane."
    f = live_note.fields(state)
    assert f["worked"] == "The Mongolian portal lane."
    assert f["broke"].startswith("•")                             # still drafted


# ── what broke, when something did ────────────────────────────────────────────────────
def test_failures_in_the_run_log_are_quoted(state):
    log = ["[discovery] 3 documents", "[warn] 4 of 120 LLM call(s) failed and were skipped",
           "[fetch] robots refuses https://x.gov/a", "[warn] 4 of 120 LLM call(s) failed and were skipped"]
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3, log=log)
    broke = " ".join(live_note.auto_broke(state))
    assert "2 problems" in broke                                 # de-duplicated
    assert "4 of 120 LLM call(s) failed" in broke and "robots refuses" in broke
    assert "No step failed" not in broke


def test_a_second_pass_that_fetched_is_reported_and_not_praised(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3)
    _cap(state, "B", [_M("P6-I2", LAW, "7.1")], fetched=22)
    assert "not engine-isolated" in " ".join(live_note.auto_broke(state))
    assert "fetched nothing" not in " ".join(live_note.auto_worked(state))


def test_a_pass_that_crashed_is_in_the_note(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3)
    livetest.capture_failure(state, "B", RuntimeError("OpenRouter 402: key limit exceeded"),
                             "2026-10-15T03:05:00+00:00", "2026-10-15T03:06:30+00:00",
                             log_lines=["[error] grading stopped after 5 failed call(s)"])
    broke = " ".join(live_note.auto_broke(state))
    assert "Engine B's pass stopped with an error" in broke and "402" in broke
    assert "grading stopped" in broke
    assert "fetched nothing" not in " ".join(live_note.auto_worked(state))
    f = live_note.fields(state)
    assert f["exported"] == ("1", "0") and f["elapsed"][1] == "1.5"
    assert livetest.short_note_docx(state)                        # still printable


def test_the_offline_stand_in_grader_is_named(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3, provider="mock")
    assert "offline stand-in grader" in " ".join(live_note.auto_broke(state))


def test_incomplete_grading_names_the_indicators(state):
    rows = [_M("P6-I2", LAW, "7.1"),
            _M("P6-I4", "No provision found", "N/A", notes="Grading incomplete — the LLM provider failed")]
    _cap(state, "A", rows, fetched=3)
    assert "grading did not finish for 1 indicator (6.4)" in " ".join(live_note.auto_broke(state))


def test_a_stored_result_is_not_passed_off_as_a_live_one(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3, cached="2026-10-14 09:00")
    assert "stored one" in " ".join(live_note.auto_broke(state))


def test_a_clean_run_says_so_in_those_words(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1")], fetched=3)
    _cap(state, "B", [_M("P6-I2", LAW, "7.1")], fetched=0)
    assert live_note.auto_broke(state)[0].startswith("No step failed")


# ── what a reviewer should look at ───────────────────────────────────────────────────
def test_caution_names_gaps_disagreements_lone_finds_and_weak_rows(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1"), _M("P6-I4", LAW, "9", conf=0.62,
                                                   status="pending_review")], fetched=3)
    _cap(state, "B", [_M("P6-I1", LAW, "7.1"), _M("P6-I4", "Other law", "3")], fetched=0)
    c = " ".join(live_note.auto_caution(state))
    assert "6.3: no provision exported by either engine" in c
    assert f"{LAW}, 7.1 (A: 6.2 · B: 6.1)" in c
    assert "Other law, 3 → 6.4 (B)" in c
    assert f"6.4 · {LAW}, 9 (0.62)" in c


# ── the counts ────────────────────────────────────────────────────────────────────────
def test_provisions_exported_is_per_provision_not_per_row(state):
    one_provision_two_indicators = [_M("P6-I2", LAW, "7.1", pid="d#p1"),
                                    _M("P6-I1", LAW, "7.1", pid="d#p1", tag="KNOWN")]
    _cap(state, "A", one_provision_two_indicators, fetched=3)
    r = state["runs"]["A"]
    assert r["rows"] == 2 and r["exported"] == 1 and r["new"] == 0
    assert r["provisions"] == 40                                 # read, a different figure


def test_set_aside_rows_are_not_exported(state):
    _cap(state, "A", [_M("P6-I2", LAW, "7.1"), _M("P6-I4", LAW, "9", status="quarantined")],
         fetched=3)
    assert state["runs"]["A"]["rows"] == 1


def test_run_issues_keeps_failures_only():
    lines = ["[fetch] retrieved 3 bodies into cache", "[fetch] retrieved 2 bodies into cache (1 duplicate/failed dropped)",
             "[error] extraction failed for X", "[map] 40 provisions", "[portal] robots refuses https://a"]
    assert live_note.run_issues(lines) == [lines[1], lines[2], lines[4]]


# ── the second pass reads engine A's documents ───────────────────────────────────────
def test_the_worker_thread_never_reads_session_state():
    """`st.session_state` read inside the background thread is an empty stand-in (no script
    context), which silently turned the second pass into a fresh crawl."""
    src = Path(__file__).resolve().parent.parent.joinpath("frontend", "app.py").read_text(
        encoding="utf-8")
    worker = re.search(r"def _worker\(\):\n(.*?)\n    thread = threading", src, re.S).group(1)
    assert "session_state" not in worker
    assert "reuse_documents=reuse_docs" in worker
