"""Robust input handling — the rubric requires the engine to cope with unanticipated
input such as a mis-spelt country name instead of rejecting the run."""
import pytest

from backend.schemas import Economy, resolve_economy


@pytest.mark.parametrize("value,expected", [
    ("Singapore", Economy.SG),
    ("singapore", Economy.SG),
    ("SG", Economy.SG),
    ("Singapor", Economy.SG),        # mis-spelling (rubric: mis-spelt country)
    ("austrlia", Economy.AU),        # mis-spelling
    ("  MALAYSIA  ", Economy.MY),    # whitespace + case
    ("Republic of Singapore", Economy.SG),
])
def test_resolve_tolerates_codes_names_and_typos(value, expected):
    assert resolve_economy(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "xyzland", "France"])
def test_resolve_rejects_unknown_with_clear_message(value):
    with pytest.raises(ValueError) as ei:
        resolve_economy(value)
    assert "Singapore" in str(ei.value)   # message lists supported economies
