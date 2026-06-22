"""Zone-3 scoring — rubric integrity, the inverted-polarity gotcha, the mock scorer,
indicator roll-up, and an end-to-end run. Validated against the official answer-key
patterns (the Database country sheets)."""
from backend.pipeline import scoring
from backend.pipeline.orchestrator import run_pipeline
from backend.providers.llm_factory import MockLLM
from backend.rdtii import RUBRICS, coerce_score, get_rubric
from backend.rdtii.indicators import INDICATORS
from backend.schemas import DiscoveryTag, EvidenceMapping, ReviewStatus, Economy


# ───────────────────────── helpers ─────────────────────────
def _mapping(indicator_id, snippet="", law="Some Act", coverage="Horizontal",
             scope_flag=None, article="Section 1") -> EvidenceMapping:
    pillar = int(indicator_id[1])
    return EvidenceMapping(
        mapping_id="m1", run_id="r1", economy=Economy.SG, pillar=pillar,
        indicator_id=indicator_id, law_name=law, article_section=article,
        verbatim_snippet=snippet, source_url="https://x", mapping_rationale="r",
        confidence_score=0.9, discovery_tag=DiscoveryTag.KNOWN,
        coverage=coverage, scope_flag=scope_flag, review_status=ReviewStatus.AUTO_ACCEPTED,
        provision_id="p1",
    )


def _score_one(m) -> EvidenceMapping:
    scoring.score_mappings([m], llm=MockLLM(), log=lambda *_: None)
    return m


# ───────────────────────── rubric integrity ─────────────────────────
def test_every_indicator_has_a_rubric():
    for ind in INDICATORS:
        assert ind.indicator_id in RUBRICS, f"no scoring rubric for {ind.indicator_id}"


def test_inverted_and_binary_flags_match_methodology():
    inverted = {k for k, v in RUBRICS.items() if v.inverted}
    binary = {k for k, v in RUBRICS.items() if v.binary}
    assert inverted == {"P7-I1", "P7-I2"}, "only the two framework indicators are inverted"
    assert binary == {"P6-I3", "P7-I3", "P7-I5"}, "only infra/retention/gov-access are binary"


def test_coerce_score_snaps_and_respects_binary():
    assert coerce_score(0.4, get_rubric("P6-I1")) == 0.5      # tiered → nearest of 0/0.5/1
    assert coerce_score(0.4, get_rubric("P6-I3")) == 0.0      # binary → only 0 or 1
    assert coerce_score(0.6, get_rubric("P7-I3")) == 1.0      # binary
    assert coerce_score("nonsense", get_rubric("P6-I1")) is None


# ───────────────────────── mock scorer behaviour ─────────────────────────
def test_inverted_horizontal_framework_scores_zero():
    # PDPA-like comprehensive horizontal framework → 7.1 = 0 (answer key: SG 7.1 = 0)
    m = _score_one(_mapping("P7-I1", snippet="general protection of personal data", coverage="Horizontal"))
    assert m.raw_score == 0.0


def test_inverted_sectoral_framework_scores_half():
    m = _score_one(_mapping("P7-I2", snippet="cybersecurity for licensed banks",
                            coverage="Sectoral", scope_flag="SECTORAL_NOT_NATIONAL"))
    assert m.raw_score == 0.5


def test_retention_needs_specified_duration():
    has = _score_one(_mapping("P7-I3", snippet="records must be retained for a period of 5 years"))
    no = _score_one(_mapping("P7-I3", snippet="shall cease to retain documents when no longer needed"))
    assert has.raw_score == 1.0          # specified minimum duration → 1
    assert no.raw_score == 0.0           # no specified period → 0


def test_binary_presence_indicator_scores_one():
    m = _score_one(_mapping("P7-I5", snippet="police may access and copy data on a computer"))
    assert m.raw_score == 1.0


def test_tiered_horizontal_scores_one_sectoral_scores_half():
    horiz = _score_one(_mapping("P6-I4", snippet="transfer only with consent", coverage="Horizontal"))
    sect = _score_one(_mapping("P6-I4", snippet="transfer only with consent for insurers",
                               coverage="Sectoral", scope_flag="SECTORAL_NOT_NATIONAL"))
    assert horiz.raw_score == 1.0
    assert sect.raw_score == 0.5


def test_scoring_always_sets_a_valid_score_and_impact():
    m = _score_one(_mapping("P6-I1", snippet="shall not transfer personal data abroad"))
    assert m.raw_score in (0.0, 0.5, 1.0)
    assert m.impact and isinstance(m.impact, str)


# ───────────────────────── indicator roll-up ─────────────────────────
def test_restrictive_indicator_takes_most_restrictive():
    ms = [_mapping("P7-I3"), _mapping("P7-I3")]
    ms[0].raw_score, ms[1].raw_score = 0.0, 1.0
    agg = scoring.aggregate_indicator_scores(ms)
    assert agg["P7-I3"]["score"] == 1.0      # max wins (SG 7.3: PDPA 0 + Telecom 1 → 1)


def test_inverted_indicator_takes_best_framework():
    # SG 7.2: Cybersecurity Act (horizontal, 0) + MAS notice (sectoral, 0.5) → indicator 0
    ms = [_mapping("P7-I2"), _mapping("P7-I2")]
    ms[0].raw_score, ms[1].raw_score = 0.5, 0.0
    agg = scoring.aggregate_indicator_scores(ms)
    assert agg["P7-I2"]["score"] == 0.0      # min wins for inverted


def test_two_sectoral_measures_roll_up_to_one():
    ms = [_mapping("P6-I2"), _mapping("P6-I2")]
    ms[0].raw_score = ms[1].raw_score = 0.5
    agg = scoring.aggregate_indicator_scores(ms)
    assert agg["P6-I2"]["score"] == 1.0      # >1 measure in the 0.5 category → 1


# ───────────────────────── end-to-end (offline mock) ─────────────────────────
def test_pipeline_produces_scores_offline():
    r = run_pipeline(Economy.SG, [7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    scored = [m for m in r.mappings if m.raw_score is not None]
    assert scored, "scoring layer should populate raw_score on the offline run"
    assert all(m.raw_score in (0.0, 0.5, 1.0) for m in scored)
    assert all(m.impact for m in scored)


def test_score_embedded_in_csv_notes(tmp_path):
    """Zone-3 score appears in the CSV Notes column, 13-col structure is unchanged."""
    import csv as csv_mod
    from backend.export import export_csv
    from backend.schemas import SUBMISSION_COLUMNS
    r = run_pipeline(Economy.SG, [7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    path = export_csv(r.mappings, r.meta.run_id, out_dir=tmp_path)
    rows = list(csv_mod.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert list(rows[0].keys()) == SUBMISSION_COLUMNS, "must stay 13 columns"
    scored = [m for m in r.mappings if m.raw_score is not None
              and m.review_status.value in ("auto_accepted", "pending_review")]
    if scored:
        notes_col = [r["Notes"] for r in rows]
        assert any("RDTII score" in n for n in notes_col), "Notes must carry RDTII score"


def test_scored_csv_has_no_rollup_footer(tmp_path):
    """scored_export writes only measure rows — no INDICATOR SCORES footer block."""
    from backend.export.scored_export import export_scored_csv
    r = run_pipeline(Economy.SG, [7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    path = export_scored_csv(r.mappings, r.meta.run_id, out_dir=tmp_path)
    content = path.read_text(encoding="utf-8-sig")
    assert "INDICATOR SCORES" not in content


def test_json_has_analytical_index(tmp_path):
    """JSON export places roll-up under analytical_index, not in summary."""
    from backend.export.json_export import build_payload
    r = run_pipeline(Economy.SG, [7], use_samples=True,
                     ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    payload = build_payload(r)
    assert "indicator_scores" not in payload["summary"], "roll-up must leave summary"
    assert "analytical_index" in payload, "roll-up must be in analytical_index"
    assert "_note" in payload["analytical_index"]
