"""A candidate indicator gate must be measured against the panel's OWN rows before it ships.

Every gate in `indicators.py` carries a hand-written claim — "this gate costs the answer key
nothing". That claim was checked by reading. `tools.check_gates` checks it mechanically, so a
gate that would refuse a provision the panel itself cites cannot reach a submission.

Three populations, the same three `tools/replay_grade.py` scores against:
  CONTROL   rows the panel cites for this indicator — a gate that rejects one of these is wrong
  REFUSED   our rows an independent auditor rejected — a gate should catch these
  UPHELD    our rows the auditor accepted — a gate that rejects these is collateral damage
"""
from tools.check_gates import evaluate_gate, has_duration, is_retention_ceiling


def _rows():
    return [
        {"kind": "panel-confirmed", "satisfies": True,
         "snippet": "The company must retain the records for a period of not less than 5 years."},
        {"kind": "ours-only", "satisfies": False,
         "snippet": "The Minister may make regulations prescribing the manner of keeping records."},
        {"kind": "ours-only", "satisfies": True,
         "snippet": "Every operator shall preserve traffic data for at least 12 months."},
    ]


# ─────────────────── the report separates the three populations ───────────────────
def test_gate_that_harms_no_control_row_reports_zero_harm():
    r = evaluate_gate(_rows(), has_duration)
    assert r["control_total"] == 1
    assert r["control_harmed"] == 0


def test_gate_catches_the_refused_row_it_was_written_for():
    """The delegated-power row names no duration, so a duration gate must catch it."""
    r = evaluate_gate(_rows(), has_duration)
    assert r["refused_total"] == 1
    assert r["refused_caught"] == 1


def test_gate_reports_collateral_damage_on_upheld_rows():
    r = evaluate_gate(_rows(), has_duration)
    assert r["upheld_total"] == 1
    assert r["upheld_harmed"] == 0


def test_a_gate_that_rejects_everything_is_visible_as_harm():
    """Guard against 'fewer rows' passing for 'better rows' — the failure PROJECT_STATE
    records for the reverted P7-I1 tightening."""
    r = evaluate_gate(_rows(), lambda s: False)
    assert r["control_harmed"] == 1
    assert r["upheld_harmed"] == 1


# ─────────────────── the mechanically checkable part of each gate ───────────────────
def test_has_duration_accepts_an_explicit_period():
    assert has_duration("retain the records for a period of not less than 5 years") is True
    assert has_duration("shall be preserved for at least 12 months") is True


def test_has_duration_rejects_a_record_keeping_duty_with_no_period():
    assert has_duration("every company shall keep accounting records and books of account") is False


def test_has_duration_rejects_a_delegated_power_to_prescribe_one():
    """SG Telecommunications Act s.52 — 'regulations may be made regarding the period of
    retention' states no period itself."""
    assert has_duration("The Authority may make regulations regarding the period of retention "
                        "of records") is False


def test_retention_ceiling_detects_a_maximum_not_a_minimum():
    """IN PMLA s.20 — 'not exceeding one hundred and eighty days' is a ceiling, the opposite
    of what P7-I3 asks for."""
    assert is_retention_ceiling("records may be retained for a period not exceeding "
                                "one hundred and eighty days") is True


def test_retention_ceiling_does_not_fire_on_a_genuine_minimum():
    assert is_retention_ceiling("must retain the records for not less than 5 years") is False


def test_non_latin_snippet_is_never_gated_on_english_wording():
    """The topical guard already fails open for scripts it cannot read; a gate must too,
    or every Chinese and Mongolian row is refused for being unreadable."""
    assert has_duration("个人信息处理者应当保存该个人信息不少于三年。") is True
    assert is_retention_ceiling("个人信息处理者应当保存该个人信息不少于三年。") is False


# ─────────── refined after measurement: the panel accepts a PRESCRIBED period ───────────
def test_retention_duty_accepts_a_period_prescribed_elsewhere():
    """SG Employment Act s.95 is a CONTROL row: 'an employer must make, and keep for the
    period prescribed'. The panel scores it under 7.3 though it states no number, so a gate
    demanding a literal duration would refuse the answer key."""
    from tools.check_gates import states_retention_period
    assert states_retention_period(
        "An employer must make, and keep for the period prescribed (called in this section "
        "the record retention period), employee records containing the prescribed particulars"
    ) is True


def test_retention_duty_rejects_a_mere_power_to_make_rules():
    """SG Telecommunications Act s.52 was refused by the auditor: the Authority MAY make
    regulations. The duty lies in the regulation, not here."""
    from tools.check_gates import states_retention_period
    assert states_retention_period(
        "The Authority may make regulations regarding the period of retention of records"
    ) is False


def test_retention_duty_rejects_record_keeping_with_no_period_at_all():
    from tools.check_gates import states_retention_period
    assert states_retention_period(
        "Every company shall keep accounting records and books of account"
    ) is False


def test_retention_duty_accepts_an_explicit_minimum():
    from tools.check_gates import states_retention_period
    assert states_retention_period(
        "The company must retain the records for a period of not less than 5 years"
    ) is True


def test_retention_duty_fails_open_on_unreadable_script():
    from tools.check_gates import states_retention_period
    assert states_retention_period("个人信息处理者应当保存该个人信息不少于三年。") is True


def test_retention_period_set_by_a_table_needs_no_modal_verb():
    """AU Privacy Act s.20X sets credit-information retention periods in a table: 'The
    following table has effect ... the retention period for the information is whichever of
    the following periods ends later ... the period of 5 years'. The auditor upheld it. A
    gate requiring 'must' or 'shall' would refuse a correct row for its drafting style."""
    from tools.check_gates import states_retention_period
    assert states_retention_period(
        "20X Retention period for credit information - personal insolvency (1) The following "
        "table has effect: Item If personal insolvency the retention period for the "
        "information relates to is whichever of the following periods ends later 1 a "
        "bankruptcy of an individual (a) the period of 5 years"
    ) is True


# ─────── the ceiling detector must not read a PENALTY clause as a retention ceiling ───────
def test_ceiling_ignores_a_fine_or_imprisonment_clause():
    """SG Companies Act s.199(2) and MY PDPA s.5(1) are CONTROL rows. Both end in penalty
    boilerplate — 'a fine not exceeding $10,000 or imprisonment for a term not exceeding 12
    months'. Reading that as a retention ceiling refused two of the panel's own rows."""
    from tools.check_gates import is_retention_ceiling
    assert is_retention_ceiling(
        "Every company must retain the accounting records for not less than 5 years. A "
        "director who is in default shall be guilty of an offence and liable on conviction "
        "to a fine not exceeding $10,000 or to imprisonment for a term not exceeding 12 months"
    ) is False


def test_ceiling_still_detects_a_real_retention_maximum():
    """IN PMLA s.20 — records 'may be retained for a period not exceeding one hundred and
    eighty days' is a genuine ceiling and the auditor refused our row for it."""
    from tools.check_gates import is_retention_ceiling
    assert is_retention_ceiling(
        "The records seized may be retained for a period not exceeding one hundred and "
        "eighty days from the day on which they were seized"
    ) is True


# ═══════════ P7-I5: no gate ships — see tools/check_gates.GATES ═══════════
# The two rules reading suggested are refuted by the panel's own rows; the negative result is
# recorded there rather than encoded as a test of a rule we do not hold.
