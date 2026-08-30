"""Regressions for three defects found on 2026-08-27, all of which failed SILENTLY.

None of them raised, and none of them produced a short run or an error row. Each produced a
CSV that looked like a completed analysis and was wrong, which is why they are pinned here
rather than left to the end-to-end run to notice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import ROOT, Settings
from backend.pipeline.adapter_mongolia import (
    _AMENDING_TITLE, _is_principal, _matches, _query_parts, _relevance, _title_key,
    _word_variants, load_catalogue)
from backend.pipeline.extraction import _CLAUSE_RE_MN
from backend.schemas import SUBMISSION_COLUMNS, TRANSLATION_COLUMNS


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


# ─────────────────────────── 4. translations ───────────────────────────
def _mapping(economy, **kw):
    from backend.schemas import DiscoveryTag, Economy, EvidenceMapping, ReviewStatus
    base = dict(
        mapping_id="m", run_id="r", economy=Economy(economy), pillar=6, indicator_id="P6-I4",
        law_name="ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ", article_section="14 дүгээр зүйл",
        verbatim_snippet="14.1.Хүний хувийн мэдээллийг гадаад улсад дамжуулахыг хориглоно.",
        source_url="https://legalinfo.mn/mn/detail?lawId=16390288615991",
        mapping_rationale="x", confidence_score=0.9, discovery_tag=DiscoveryTag.NEW,
        review_status=ReviewStatus.AUTO_ACCEPTED, provision_id="p")
    base.update(kw)
    return EvidenceMapping(**base)


def test_translation_columns_come_after_every_mandatory_column():
    """The judges validate the template programmatically. Extra columns are permitted (the
    Q&A's own example is RDTII_Raw_Score) but only AFTER the mandatory ones."""
    from backend.export.csv_export import csv_text
    m = _mapping("MN", law_name_translated="LAW ON PROTECTION OF PERSONAL DATA",
                 snippet_translated="14.1. Transfer of personal data abroad is prohibited.",
                 translation_target="English")
    header = csv_text([m]).splitlines()[0]
    cols = [c.strip('"') for c in header.split(",")]
    assert cols[:len(SUBMISSION_COLUMNS)] == SUBMISSION_COLUMNS
    assert cols[len(SUBMISSION_COLUMNS):] == TRANSLATION_COLUMNS


def test_an_untranslated_run_keeps_the_exact_template_width():
    """Singapore legislates in English, so the translator is skipped without a call. Two
    always-blank columns would still change the width of a file the judges validate."""
    from backend.export.csv_export import csv_text
    header = csv_text([_mapping("SG")]).splitlines()[0]
    cols = [c.strip('"') for c in header.split(",")]
    assert cols == SUBMISSION_COLUMNS


def test_the_verbatim_column_is_never_the_translation():
    """`Verbatim Snippet` IS the statute's text — it is what the panel checks the citation
    against — so a translated snippet written into it would be a false citation."""
    from backend.export.csv_export import csv_text
    original = "14.1.Хүний хувийн мэдээллийг гадаад улсад дамжуулахыг хориглоно."
    m = _mapping("MN", verbatim_snippet=original,
                 snippet_translated="14.1. Transfer of personal data abroad is prohibited.",
                 law_name_translated="LAW ON PROTECTION OF PERSONAL DATA")
    body = csv_text([m]).splitlines()[1]
    assert original in body
    assert "14.1. Transfer of personal data abroad is prohibited." in body


def test_english_economies_are_skipped_without_a_call():
    """The translator must not spend a call to return its own input."""
    from backend.pipeline.translate import needs_translation
    for eco in ("SG", "AU", "MY", "IN"):
        assert not needs_translation(eco, "English")
    for eco in ("MN", "CN", "RU", "TH", "LA", "ID", "TL"):
        assert needs_translation(eco, "English")


def test_placeholder_rows_are_not_translated():
    """A "No provision found" row's snippet is a fixed English phrase we wrote ourselves."""
    from backend.pipeline import translate
    calls = []

    class _Spy:
        def complete_json(self, system, user):
            calls.append(user)
            return {"translation": "should not happen"}

    m = _mapping("MN", law_name=translate.PLACEHOLDER_LAW,
                 verbatim_snippet="No evidence found for this indicator.")
    translate.translate_mappings([m], llm=_Spy())
    assert calls == []
    assert not m.snippet_translated


def test_the_prompt_forbids_transliteration():
    """Measured on the 2026-08-27 MN pillar-6 run: one of eight rows came back ROMANISED —
    "27 duugaar zuil. Niitiin medeeleliin san" — because the earlier rule 3 invited
    transliteration for terms with no equivalent and the model applied it to the whole
    passage. A romanised snippet is the same sentence the reviewer could not read, and it is
    worse than an empty cell because it looks like an answer. This is a tripwire, not a
    quality check: the rule is cheap to delete by accident when the prompt is next edited.
    """
    from backend.pipeline.translate import TRANSLATE_SYSTEM
    body = TRANSLATE_SYSTEM.format(target="English").lower()
    assert "never transliterate" in body
    assert "romanis" in body


# ─────────────────── 5. doubly-encoded Word exports ───────────────────
def test_escaped_markup_is_not_resurrected_by_the_unescape():
    """Strip-then-unescape, once, inverts on a DOUBLY encoded export.

    lawId=16759949645981 pastes an HTML fragment into the Word document as escaped TEXT —
    11,597 `&lt;` — so it survives the tag strip untouched and the unescape then turns it back
    into live markup. The function returned 458,472 characters opening
    `<meta http-equiv="Content-Type"…`, no article pattern matched any of it, and the whole
    file became ONE provision whose 20,000-character head (MAX_SNIPPET) was markup: a garbage
    citation in the CSV and ~12,000 prompt tokens of it in every grading call it reached.
    """
    from backend.pipeline.adapter_mongolia import export_text
    body = ('<html><body><p>&lt;meta http-equiv="Content-Type"&gt;'
            '&lt;div class="x"&gt;</p><p>1 дүгээр зүйл.Нийтлэг үндэслэл</p>'
            '<p>&lt;/div&gt;</p></body></html>').encode("utf-8")
    out = export_text(body)
    assert "<meta" not in out and "<div" not in out and "</div" not in out
    assert "1 дүгээр зүйл" in out, "the statute text itself must survive both passes"


def test_a_bare_less_than_is_not_treated_as_a_tag():
    """`<[^>]+>` also matched "хугацаа < 30 хоног > бол" and ate the text between. Latent
    while this only saw the portal's own markup; not latent once the loop can run over text an
    unescape produced."""
    from backend.pipeline.adapter_mongolia import export_text
    out = export_text('<p>хугацаа &lt; 30 хоног &gt; бол устгана</p>'.encode("utf-8"))
    assert "30 хоног" in out
    assert "устгана" in out


def test_export_text_leaves_ordinary_markup_alone():
    """The single-pass case must be unchanged — this is the shape every other MN law has."""
    from backend.pipeline.adapter_mongolia import export_text
    out = export_text('<p>1 дүгээр зүйл.Зорилт</p><p>1.1.Энэ хууль</p>'.encode("utf-8"))
    assert out.splitlines() == ["1 дүгээр зүйл.Зорилт", "1.1.Энэ хууль"]


# ─────────────── 6. resolutions and rule-numbered clauses ───────────────
def test_a_resolution_splits_on_its_own_numbered_points():
    """A Mongolian тогтоол numbers its operative points at ONE level and carries nothing else.

    It has no зүйл, so _STRUCT_RE_MN found nothing; no "N.N.", so _CLAUSE_RE_MN found nothing;
    SECTION_RE is English. Every Government and CRC resolution therefore reached the grader as
    a single block — fourteen of the twenty-two documents in a Mongolia pillar-6 run. Having
    ADMITTED these documents (the panel cites resolutions for 6.3), handing over the whole file
    means the operative point can be neither quoted nor cited.
    """
    from backend.pipeline.extraction import _RESOLUTION_RE_MN
    body = (
        "МОНГОЛ УЛСЫН ЗАСГИЙН ГАЗРЫН ТОГТООЛ\n"
        "2022 оны 12 дугаар сарын 28-ны өдөр\n"
        "Дугаар 493\n"
        "Кибер аюулгүй байдлын тухай хуулийн 10.1.1-д заасныг үндэслэн ТОГТООХ нь:\n"
        '1."Кибер аюулгүй байдлын үндэсний стратеги"-ийг хавсралт ёсоор баталсугай.\n'
        "2. Хэрэгжилтийг хангаж ажиллахыг сайдад үүрэг болгосугай.\n"
        "3. Шаардагдах хөрөнгийг улсын төсөвт тусгах арга хэмжээ авахыг даалгасугай.\n")
    assert len(_RESOLUTION_RE_MN.findall(body)) == 3


def test_resolution_pattern_rejects_dates_document_numbers_and_bare_numbers():
    """A bare "N." is the weakest structural claim in the file, so its guards carry the weight."""
    from backend.pipeline.extraction import _RESOLUTION_RE_MN as R
    assert not R.match("1996 оны 4 дүгээр сарын 30-ны өдөр")   # no dot after the digits
    assert not R.match("2016.05.12 өдөр")                      # a date
    assert not R.match("Дугаар 15")                            # not at the line start
    assert not R.match("4.\n")            # a number alone on its line is not a clause head
    assert R.match("1. Харилцаа холбооны зохицуулах хороог байгуулж")
    assert R.match('1."Кибер аюулгүй байдлын үндэсний стратеги"-ийг')


def test_a_ministerial_rule_numbers_clauses_from_its_own_rule_number():
    r"""Civil Aviation Rule 191 heads its clauses "191.1.", "191.3." — three digits on the left.

    At `\d{1,2}` lawId=205434 matched nothing and arrived as one 5,244-character block; at
    `\d{1,3}` it yields 14 provisions.
    """
    from backend.pipeline.extraction import _CLAUSE_RE_MN
    assert _CLAUSE_RE_MN.match("191.1. Ерөнхий зүйл")
    assert _CLAUSE_RE_MN.match("191.3.Нууц баримт мэдээлэл")
    # …and widening the left group must not cost the date guard, which is what it protects.
    assert not _CLAUSE_RE_MN.match("2016.05.12 өдөр")
    assert not _CLAUSE_RE_MN.match("2.1.1. ил тод байх;")


def test_the_resolution_pattern_is_the_last_resort_not_the_first():
    """Inside a LAW a bare "N." is a list item. The зүйл and N.N. patterns must win outright,
    or an Act would shatter on its own enumerations."""
    from backend.pipeline.adapter_mongolia import _doc
    from backend.pipeline.extraction import extract_provisions
    from backend.schemas import Economy, OCRMetrics
    law = ("1 дүгээр зүйл.Хуулийн зорилт\n"
           "1.1.Энэ хуулийн зорилт нь дараах харилцааг зохицуулна:\n"
           "1. эхний хэсэг;\n2. хоёр дахь хэсэг;\n3. гурав дахь хэсэг;\n"
           "2 дугаар зүйл.Хууль тогтоомж\n2.1.Хууль тогтоомж дараах байна.\n"
           "3 дугаар зүйл.Нэр томьёо\n3.1.Нэр томьёог дараах утгаар ойлгоно.\n")
    ps = extract_provisions(_doc("x", "ТУХАЙ", Economy.MN, "p", 1000), law, OCRMetrics())
    assert [p.article_section for p in ps] == ["1 дүгээр зүйл", "2 дугаар зүйл", "3 дугаар зүйл"]
