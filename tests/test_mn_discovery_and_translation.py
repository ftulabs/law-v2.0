"""Regressions for defects that failed SILENTLY.

None of them raised, and none produced a short run or an error row. Each produced a CSV that
looked like a completed analysis and was wrong, which is why they are pinned here rather than
left to the end-to-end run to notice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import ROOT, Settings
from backend.pipeline.adapter_mongolia import (
    _AMENDING_TITLE, _is_principal, _matches, _query_parts, _relevance, _title_key,
    _word_variants, load_catalogue)
from backend.pipeline.extraction import _CLAUSE_RE_MN


# ─────────────────────────── 1. the .env path ───────────────────────────
def test_env_file_is_absolute_so_the_cwd_cannot_silence_the_key():
    """`env_file=".env"` resolved against the CURRENT WORKING DIRECTORY.

    Launch from anywhere but the repo root — `cd frontend && streamlit run app.py`, a
    scheduler, an IDE run-config — and pydantic-settings found no file at all. It did not
    complain: `llm_provider` fell back to its "mock" default and `openrouter_api_key` to "",
    so the run completed on the lexical mock grader and the only symptom was mappings that
    looked like a rejected API key.
    """
    env_file = Settings.model_config.get("env_file")
    assert env_file is not None
    assert Path(env_file).is_absolute(), (
        "env_file must be absolute; a relative path is read from the cwd and silently "
        "downgrades the run to the mock provider")
    assert Path(env_file) == ROOT / ".env"


# ─────────────────── 2. Mongolian title matching ────────────────────
def test_fleeting_vowel_reaches_the_declined_form():
    """мэдээлэл → мэдээлл-ийн DROPS the second э, so plain substring cannot reach it.

    The adapter's docstring claimed the opposite and used this exact pair as its worked
    example. The cost: "нийтийн мэдээлэл" could not match НИЙТИЙН МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДЛЫН
    ТУХАЙ — the Law on Transparency of Public Information, which is the panel's own citation
    for Mongolia's 6.3.
    """
    assert "мэдээлэл" not in "мэдээллийн", "the premise of this test has changed"
    assert "мэдээлл" in _word_variants("мэдээлэл")
    assert _matches("НИЙТИЙН МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДЛЫН ТУХАЙ", "нийтийн мэдээлэл")


def test_missing_space_in_the_portals_own_filename_still_matches():
    """legalinfo.mn's Content-Disposition omits a space: "МЭДЭЭЛЭЛХАМГААЛАХ"."""
    assert _matches("ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛХАМГААЛАХ ТУХАЙ", "хүний хувийн мэдээлэл")
    assert _matches("ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛХАМГААЛАХ ТУХАЙ", "мэдээлэл хамгаалах")


def test_quoted_group_must_be_adjacent():
    """холбоо is "communication" next to харилцаа and "federation" next to Улс.

    Mongolia has one treaty Act per recognised state, each titled "… Холбооны Улстай дипломат
    харилцаа тогтоох тухай", and each carries all three words of the unquoted telecom query as
    a principal Act. Three of twenty-two pillar-6 slots went to Comoros, Micronesia and Saint
    Kitts.
    """
    q = '"харилцаа холбоо" тухай'
    assert _query_parts(q) == [("харилцаа холбоо", True), ("тухай", False)]
    assert _matches("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ", q)
    assert not _matches("Коморосын Холбооны Улстай дипломат харилцаа тогтоох тухай", q)


def test_unquoted_query_stays_order_independent():
    """The quoting mechanism must not cost the word-order tolerance it was added beside."""
    assert _matches("ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ", "мэдээлэл хүний хувийн")


def test_amending_instruments_are_dropped():
    """An amending act's body is a DIFF, not a law — a few hundred characters naming which
    sentence of another Act changes. It cites beautifully and means nothing."""
    assert _AMENDING_TITLE.search("АРХИВЫН ТУХАЙ ХУУЛЬД НЭМЭЛТ, ӨӨРЧЛӨЛТ ОРУУЛАХ ТУХАЙ")
    assert _AMENDING_TITLE.search("КИБЕР АЮУЛГҮЙ БАЙДЛЫН ТУХАЙ ХУУЛЬД НЭМЭЛТ ОРУУЛАХ ТУХАЙ")
    assert not _AMENDING_TITLE.search("КИБЕР АЮУЛГҮЙ БАЙДЛЫН ТУХАЙ")


def test_principal_statute_outranks_what_is_made_under_it():
    """Both end in тухай; the батлах ("on approving") is what separates them."""
    assert _is_principal("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ")
    assert _is_principal("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ /Шинэчилсэн найруулга/")
    assert not _is_principal("ЖУРАМ БАТЛАХ ТУХАЙ (кибер аюулгүй байдлыг хангах)")
    assert not _is_principal("ҮНДЭСНИЙ СТРАТЕГИ БАТЛАХ ТУХАЙ (Кибер аюулгүй байдал)")


def test_size_breaks_the_tie_between_a_statute_and_its_stub():
    """Ordering by TITLE LENGTH inverted on the one case that mattered.

    lawId=100956 and lawId=523 share the title ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ. The first is 9,867
    bytes whose body opens "…ХУУЛЬД НЭМЭЛТ ОРУУЛАХ ТУХАЙ" and yields 458 characters; the
    second is the 251,215-byte Act. The tie broke on a trailing qualifier and the diff won.
    """
    assert _title_key("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ /Шинэчилсэн найруулга/") == \
        _title_key("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ")
    assert _relevance("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ", 251_215) > \
        _relevance("ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ", 9_867)
    # …and a principal statute always outranks a subordinate instrument, whatever its size.
    assert _relevance("БАНКНЫ ТУХАЙ", 1_000) > _relevance("ЖУРАМ БАТЛАХ ТУХАЙ (x)", 999_999)


@pytest.mark.parametrize("law_id,title", [
    ("16390288615991", "ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛХАМГААЛАХ ТУХАЙ"),      # 6.1 6.2 6.4 7.1 7.3 7.4
    ("16390263044601", "НИЙТИЙН МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДЛЫН ТУХАЙ"),   # 6.3
    ("16390365491061", "КИБЕР АЮУЛГҮЙ БАЙДЛЫН ТУХАЙ"),               # 7.2
    ("523", "ХАРИЛЦАА ХОЛБООНЫ ТУХАЙ"),                              # 7.3 sectoral
    ("108", "БАНКНЫ ТУХАЙ"),                                         # 7.5
])
def test_every_law_the_panel_cites_for_mongolia_is_reachable(law_id, title):
    """The catalogue is a table of contents, not an answer key — but if a law the panel cites
    is not IN it, no query can ever reach it, and the run reports an honest-looking negative."""
    cat = load_catalogue()
    if not cat:
        pytest.skip("MN catalogue not built (tools/build_mn_catalogue.py)")
    by_id = {str(r["id"]): r for r in cat}
    assert law_id in by_id, f"lawId={law_id} ({title}) is missing from the catalogue"
    assert _title_key(by_id[law_id]["title"]) == _title_key(title)


def test_catalogue_titles_carry_no_html_entities():
    """Titles come from Content-Disposition and reached the Law Name column still escaped."""
    cat = load_catalogue()
    if not cat:
        pytest.skip("MN catalogue not built")
    offenders = [r["title"] for r in cat[:5000] if "&quot;" in r.get("title", "")]
    assert not offenders, f"HTML entities survived into {len(offenders)} title(s)"


# ─────────────────── 3. Mongolian clause splitting ───────────────────
def test_clause_split_does_not_require_a_space_after_the_number():
    """legalinfo.mn's Word export runs the number into the text: "1.1.Энэхүү журмын".

    The pattern required `[ \\t]+` there, so it matched NOTHING on the Minister of Digital
    Development's order A/90 (lawId=16760452348261) — the panel's own citation for Mongolia's
    6.3. Its 3,755 characters of clean clause-numbered text produced zero provisions and
    reached the grader as a single "(document)" block.
    """
    assert _CLAUSE_RE_MN.match("1.1.Энэхүү журмын зорилго нь")
    assert _CLAUSE_RE_MN.match("3.1. Мэдээлэл боловсруулахад")


def test_clause_split_still_rejects_dates_cross_references_and_sub_clauses():
    """The guards are carried by the line anchor and the lookahead, not by the space."""
    assert not _CLAUSE_RE_MN.match("2016.05.12 өдөр")          # a date
    assert not _CLAUSE_RE_MN.match("125-131 дугаар")           # a cross-reference
    # "2.1.1." is a SUB-clause: splitting there shatters article 2.1 into fragments and
    # destroys the surrounding context the grader reads.
    assert not _CLAUSE_RE_MN.match("2.1.1. ил тод байх;")
