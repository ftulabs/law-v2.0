"""Round-2 labels, the per-economy retrieval budget, and the grading circuit breaker.

Each test here pins a defect that was SILENT — a label set that parsed to nothing, a budget
that spent the same everywhere, a run that made 968 doomed calls and blamed the wrong thing.
"""
from __future__ import annotations

import json

import pytest

from backend.config import settings
from backend.eval import ground_truth as G
from backend.pipeline import retrieval_budget as B


# ── Round-2 labels ────────────────────────────────────────────────────────────────────────
def test_round2_economies_are_labelled():
    """The seven economies the panel scores in the Round-2 database must produce label rows."""
    rows = G.load_labels()
    got = {r.economy for r in rows}
    for econ in ("CN", "IN", "ID", "LA", "MN", "RU", "TH"):
        assert econ in got, f"{econ} has no labels — Round-2 database not being read"
    for econ in ("SG", "AU", "MY"):
        assert econ in got, f"{econ} lost its Round-1 labels"


def test_article_citations_become_provision_targets():
    """Round-2 justifications cite 'Article N', not 'Section N'. Before _ARTICLE_RE existed
    every one of those rows parsed to zero targets and measured nothing at all."""
    assert G._sections("Article 27: Ride-hailing platforms must store data locally.") == ["27"]
    assert G._sections("Article 12.7. The cross-border transfer may be prohibited.") == ["12.7"]
    assert G._sections("Article 20(2) mandates that operators…") == ["20(2)"]
    assert set(G._sections("Articles 25 and 26 of the Counter-Espionage Law")) == {"25", "26"}
    # and the Round-1 form still works
    assert G._sections("According to Section 199, every company must retain…") == ["199"]


def test_chapter_is_not_a_provision_target():
    """harness.section_key() returns None for structural headings, so a Chapter label could
    never match — counting it would depress measured recall with no pipeline at fault."""
    assert G._sections("Chapter 2 states that only a credit bureau may…") == []


def test_every_labelled_economy_covers_both_pillars():
    by_econ: dict[str, set[str]] = {}
    for r in G.load_labels():
        by_econ.setdefault(r.economy, set()).add(r.indicator_id)
    for econ, inds in by_econ.items():
        assert {i for i in inds if i.startswith("P6")}, f"{econ} has no pillar-6 labels"
        assert {i for i in inds if i.startswith("P7")}, f"{econ} has no pillar-7 labels"


def test_timor_leste_is_not_claimed_as_labelled():
    """TL is on the final-round country list and in NO database we hold. Claiming a label set
    for it would be inventing ground truth."""
    assert "TL" not in G.labelled_economies()


# ── per-economy retrieval budget ──────────────────────────────────────────────────────────
def test_unmeasured_economy_keeps_the_conservative_default():
    """The safe direction to be wrong in: unmeasured retrieval is unknown retrieval."""
    k_default, why = B.shortlist_size("ZZ", 10_000, top_k=5)
    assert k_default == settings.retrieve_max_top_k
    assert "no measured budget" in why


def test_measured_economy_spends_no_more_than_the_default():
    """A budget entry may narrow a shortlist; it must never widen one past the global cap."""
    for econ in (B._load().get("economies") or {}):
        for n in (500, 5_000, 40_000):
            k, _ = B.shortlist_size(econ, n)
            assert k <= settings.retrieve_max_top_k
            assert k <= n


def test_budget_table_is_generated_not_handwritten():
    if not B.BUDGET_JSON.exists():
        pytest.skip("no budget table measured yet")
    doc = json.loads(B.BUDGET_JSON.read_text(encoding="utf-8"))
    assert doc.get("generated_by") == "tools/measure_budget.py"
    for econ, e in doc["economies"].items():
        assert e.get("measured_on"), f"{econ} entry has no measurement date"
        assert e.get("prov_recall") is not None, f"{econ} entry records no recall"


def test_budget_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_budget_enabled", False)
    B.reload()
    k, why = B.shortlist_size("SG", 10_000)
    assert k == settings.retrieve_max_top_k
    assert "disabled" in why


# ── circuit breaker ───────────────────────────────────────────────────────────────────────
def test_terminal_error_stops_the_run_after_one_call(monkeypatch):
    """An exhausted key used to produce one doomed call per pairing — 968 of them on a live
    Singapore pillar-6 run — and report the spend cap as a bad key.

    Retrieval is stubbed out. The subject here is the breaker, and letting the real retriever
    run would pull ~500 MB of sentence-transformer weights from HuggingFace on a cold CI
    runner — which is exactly how this test wedged a deploy for two hours.
    """
    from backend.pipeline import mapping
    from backend.pipeline.retrieval import Retrieved
    from backend.providers.llm_base import LLMProvider, LLMTerminalError
    from backend.rdtii import get_indicators
    from backend.schemas import Economy, Provision

    monkeypatch.setattr(mapping, "retrieve",
                        lambda _ind, provs, top_k=5: [
                            Retrieved(provision=p, score=0.5,
                                      raw_context=p.verbatim_snippet, log=[])
                            for p in provs[:top_k]])

    calls = {"n": 0}

    class DeadKey(LLMProvider):
        name, model_version = "dead", "dead-1"

        def complete_json(self, system, user):
            calls["n"] += 1
            raise LLMTerminalError("spend limit reached", kind="quota",
                                   hint="check the cap at openrouter.ai")

    provisions = [
        Provision(provision_id=f"p{i}", doc_id="d1", economy=Economy.SG,
                  law_name="Test Act", article_section=f"Section {i}",
                  verbatim_snippet="Personal data shall be stored within Singapore.",
                  source_url="https://example.gov")
        for i in range(60)
    ]
    lines: list[str] = []
    out = mapping.map_provisions("run-x", provisions, 6, get_indicators(6),
                                 llm=DeadKey(), log=lines.append)

    assert out == []
    assert calls["n"] <= settings.mapping_concurrency, (
        f"breaker did not stop the run: {calls['n']} calls made")
    joined = "\n".join(lines)
    assert "quota" in joined, "the failure was not reported as a spend cap"
    assert "not attempted" in joined, "an incomplete run must say its coverage is incomplete"


# ── the run screen must show a blocked run as blocked ─────────────────────────────────────
def test_run_screen_shows_a_blocked_run_instead_of_an_empty_one():
    """A run that failed for a knowable reason used to render identically to one that found
    nothing: five stages, four zeroes, and the reason buried in the collapsed raw log."""
    from frontend import runview

    st = runview.new_state()
    runview.absorb(st, "[extract] PDPA -> 42 provisions")
    runview.absorb(st, "[error] grading stopped after 1 failed call(s) - quota: spend limit")
    runview.absorb(st, "[error] what to do: the key is VALID - its spend cap is used up")
    html = runview.track_html(st)

    assert 'role="alert"' in html, "a stop must be announced, not left to a status region"
    assert "What to do" in html, "an error with no recovery path is a dead end"
    assert "spend cap is used up" in html
    assert "rvnow" not in html, "the live sentence must yield to the problem"


def test_a_healthy_run_is_unchanged():
    from frontend import runview

    st = runview.new_state()
    runview.absorb(st, "[done] 5 mappings")
    html = runview.track_html(st)
    assert "rvnow" in html and "rvbad" not in html


def test_a_silent_mock_substitution_is_impossible():
    """A deployment with no key completed every run on the offline lexical stand-in and said
    so only in a `[warn]` inside a collapsed expander. On screen it looked like real work."""
    from backend.pipeline.orchestrator import _resolve_llm

    lines: list[str] = []
    llm = _resolve_llm("openrouter", None, None, lines.append)

    if llm.name == "mock":          # only asserts when the fallback actually fired
        joined = "\n".join(lines)
        assert any(m.startswith("[error]") for m in lines), "the substitution must be an error"
        assert "OFFLINE STAND-IN" in joined and "NOT evidence" in joined


def test_the_breaker_does_not_deadlock_when_it_trips_under_the_lock():
    """The counting paths hold the breaker's lock and then call _trip(), which takes it again.
    With a non-reentrant Lock the 25th consecutive failure froze the worker holding it and
    every worker queued behind — a silent hang, which is a worse failure than the one the
    breaker exists to report. Fails by timing out if the lock stops being reentrant."""
    import threading

    from backend.pipeline import mapping
    from backend.pipeline.retrieval import Retrieved
    from backend.providers.llm_base import LLMProvider
    from backend.rdtii import get_indicators
    from backend.schemas import Economy, Provision

    class AlwaysBroken(LLMProvider):
        name, model_version = "broken", "broken-1"

        def complete_json(self, system, user):
            raise RuntimeError("upstream is having a bad day")

    provisions = [
        Provision(provision_id=f"p{i}", doc_id="d1", economy=Economy.SG,
                  law_name="Test Act", article_section=f"Section {i}",
                  verbatim_snippet="Personal data shall be stored within Singapore.",
                  source_url="https://example.gov")
        for i in range(70)
    ]
    orig = mapping.retrieve
    mapping.retrieve = lambda _i, provs, top_k=5: [
        Retrieved(provision=p, score=0.5, raw_context=p.verbatim_snippet, log=[])
        for p in provs[:top_k]]
    done = threading.Event()
    result: list = []
    try:
        t = threading.Thread(
            target=lambda: (result.append(mapping.map_provisions(
                "run-d", provisions, 6, get_indicators(6), llm=AlwaysBroken(),
                log=lambda *_: None)), done.set()),
            daemon=True)
        t.start()
        assert done.wait(90), "map_provisions deadlocked when the breaker tripped"
        assert result[0] == []
    finally:
        mapping.retrieve = orig


# ── the Database-seeded evaluation corpus ─────────────────────────────────────────────────
def test_the_seeded_corpus_can_never_reach_a_scored_run():
    """The corpus for the Round-2 economies is seeded from the panel's own citations, which
    would be a "baked corpus" if the scored path could read it. It cannot, and that is checked
    here rather than promised in a comment: nothing under backend/pipeline imports the store."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent / "backend" / "pipeline"
    offenders = []
    for f in root.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        if re.search(r"^\s*from\s+\.\.corpus|^\s*from\s+backend\.corpus|^\s*import\s+.*\bcorpus\b",
                     src, re.M):
            offenders.append(f.name)
    assert not offenders, f"the live pipeline now reads the corpus store: {offenders}"


def test_a_seeded_economy_is_refused_when_it_has_a_real_enumerator():
    """Seeding an economy we can already discover from would make its measured numbers
    meaningless — recall against the answer key, measured on a corpus built from the answer
    key, is not a measurement of anything."""
    from backend.corpus.catalogue_database import sweep_database

    for econ in ("SG", "AU", "MY"):
        with pytest.raises(ValueError, match="portal enumerator"):
            sweep_database(econ, log=lambda _m: None)


def test_every_seeded_row_says_where_it_came_from():
    """A row a reader cannot tell apart from discovery output is the whole risk here."""
    import json

    from backend.corpus.catalogue_database import enumerate_from_database

    rows = enumerate_from_database("MN", log=lambda _m: None)
    assert rows, "Mongolia has cited instruments with URLs in the Round-2 database"
    for r in rows:
        meta = json.loads(r["catalogue_json"])
        assert meta["seed"] == "rdtii_database"
        assert "official_publisher" in meta and meta["indicators"]


def test_a_url_is_not_attached_to_a_law_it_does_not_name():
    """A Database row lists several instruments and several references with no correspondence
    between them; pairing them positionally is how linkage.py once matched the Privacy Act to
    the Security of Critical Infrastructure Act."""
    from backend.corpus.catalogue_database import _url_names_this_law

    assert _url_names_this_law("https://x.gov/acts/personal-data-protection-act-2012.pdf",
                               "Personal Data Protection Act 2012")
    assert not _url_names_this_law("https://x.gov/documents/12148567",
                                   "Federal Law No. 152-FZ On Personal Data")
    assert not _url_names_this_law("https://x.gov/acts/companies-act.pdf",
                                   "Cybersecurity Act 2018")
