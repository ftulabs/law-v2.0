"""The audit's independence must be checked against the model that GRADED the rows.

`audit_rows.py` compared the auditor to `settings.openrouter_model` — whatever is configured
right now. When the project moved to a self-hosted grader on 2026-09-06 the two stopped being
the same thing: `.env` still named an OpenRouter model while grading actually ran on
LOCAL_LLM_MODEL, so auditing with the local model would have passed a guard designed to stop
exactly that, and the system would have marked its own homework with no warning.

The rows record who graded them. That is the fact the guard has to consult.
"""
import pytest

from tools.audit_rows import graders_of, is_independent


def _rows(*models):
    return [{"model_version": m} for m in models]


def test_grader_is_read_from_the_rows_not_from_config():
    assert graders_of(_rows("mistralai/mistral-small-3.2-24b-instruct")) == {
        "mistralai/mistral-small-3.2-24b-instruct"}


def test_a_run_graded_by_two_models_reports_both():
    """The 2026-08-31 export is 2,310 mistral rows and 10 deepseek — a failover mid-run."""
    got = graders_of(_rows("mistralai/mistral-small-3.2-24b-instruct",
                           "deepseek/deepseek-v4-flash",
                           "mistralai/mistral-small-3.2-24b-instruct"))
    assert got == {"mistralai/mistral-small-3.2-24b-instruct", "deepseek/deepseek-v4-flash"}


def test_auditing_with_the_grading_model_is_not_independent():
    assert is_independent("mistralai/mistral-small-3.2-24b-instruct",
                          {"mistralai/mistral-small-3.2-24b-instruct"}) is False


def test_a_different_model_is_independent():
    """Qwen3.8-Flash-Next may audit the 2026-08-31 export: mistral graded it, not Qwen."""
    assert is_independent("Qwen3.8-Flash-Next-Uncensored",
                          {"mistralai/mistral-small-3.2-24b-instruct"}) is True


def test_a_model_that_graded_only_part_of_the_run_still_blocks():
    """Auditing with deepseek is not independent of the 10 rows deepseek graded."""
    assert is_independent("deepseek/deepseek-v4-flash",
                          {"mistralai/mistral-small-3.2-24b-instruct",
                           "deepseek/deepseek-v4-flash"}) is False


def test_unknown_graders_are_not_treated_as_independent():
    """Rows with no model_version cannot prove independence, so refuse rather than assume."""
    assert is_independent("any-model", set()) is False


@pytest.mark.parametrize("configured", ["MISTRALAI/Mistral-Small-3.2-24B-Instruct"])
def test_the_comparison_ignores_case(configured):
    assert is_independent(configured, {"mistralai/mistral-small-3.2-24b-instruct"}) is False
