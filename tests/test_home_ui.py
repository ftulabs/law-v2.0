"""The start screen and the coverage globe.

The guard that matters most here is the offline one. The previous globe pulled three.js,
OrbitControls, Leaflet and NASA earth textures from a CDN at render time; on a machine with no
outbound network the requests failed inside the iframe, Python saw no exception, and the
country picker was simply absent. Nothing in the test suite could have caught it, because
nothing in the test suite looked at what the component asks the network for.
"""
import json
import re
from pathlib import Path

import pytest

from backend.rdtii.indicators import get_indicators
from backend.schemas import Economy
from frontend import geo, home

COMPONENT = Path(__file__).resolve().parents[1] / "frontend" / "components" / "geo"


# ── the offline guard ────────────────────────────────────────────────────────────────
def test_the_globe_asks_the_network_for_nothing():
    """A judging machine may have no outbound network, or a proxy that blocks a CDN. Every
    asset the component needs must sit beside it."""
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    code = re.sub(r"<!--.*?-->", "", html, flags=re.S)          # the docstring may cite one
    external = re.findall(r"""["'(](https?:)?//[^"')\s]+""", code)
    assert not external, f"the globe would fetch {external} at render time"


def test_the_world_outline_ships_with_the_component():
    world = json.loads((COMPONENT / "world.json").read_text(encoding="utf-8"))
    assert world["land"], "no land outline"
    assert len(world["economies"]) >= 11


def test_the_outline_is_small_enough_to_ship():
    kb = (COMPONENT / "world.json").stat().st_size / 1024
    assert kb < 250, f"{kb:.0f} KB — simplify further in scratch/build_geo.py"


@pytest.mark.parametrize("code", [e.value for e in Economy if e.value != "SG"])
def test_every_economy_but_singapore_has_a_polygon(code):
    """Singapore is about 0.05 degrees across and is absent from the 110m outline entirely, so
    for that one economy the marker IS the country. Stated as an exception rather than left as
    a silent gap."""
    world = json.loads((COMPONENT / "world.json").read_text(encoding="utf-8"))
    assert world["economies"].get(code), code


# ── what the picker offers ───────────────────────────────────────────────────────────
def test_the_picker_offers_every_declared_economy():
    assert {e["iso"] for e in geo.economies()} == {e.value for e in Economy}


def test_every_economy_has_a_place_on_the_map():
    for row in geo.economies():
        assert -90 <= row["lat"] <= 90 and -180 <= row["lon"] <= 180, row["iso"]
        assert (row["lat"], row["lon"]) != (0.0, 0.0), f"{row['iso']} has no coordinates"


def test_readiness_is_reported_at_one_of_the_four_rungs():
    for row in geo.economies():
        assert row["level"] in home.LEVEL_WORD, (row["iso"], row["level"])


def test_the_summary_counts_every_economy_once():
    assert sum(geo.summary().values()) == len(list(Economy))


def test_the_globe_states_readiness_in_text_not_only_in_colour():
    """Chart guidance for geographic data is explicit: location meaning cannot depend on colour
    alone. The name row carries the level as a word, and each fill carries a hatch."""
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    assert 'class="lvl"' in html                      # the level, as a word, on every chip
    assert "function hatch(" in html                  # pattern as well as hue


def test_the_globe_can_be_operated_without_dragging():
    """WCAG 2.2 "dragging movements" requires a single-pointer alternative for any drag."""
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    assert "ArrowRight" in html and "ArrowLeft" in html
    assert 'id="names"' in html


# ── the pillar chips ─────────────────────────────────────────────────────────────────
def test_all_twelve_pillars_are_offered_and_named():
    assert sorted(home.PILLAR_SHORT) == list(range(1, 13))
    for pillar, label in home.PILLAR_SHORT.items():
        assert len(label) <= 26, (pillar, label)      # longer wraps the chip onto two lines
        assert get_indicators(pillar), pillar


def test_the_screen_distinguishes_measured_pillars_from_declared_ones():
    """Presenting twelve identical buttons would imply the other ten are as well-founded as 6
    and 7, and they are not — their definitions have never been scored."""
    assert home.MEASURED_PILLARS == (6, 7)


def test_the_start_screen_offers_the_live_test_before_any_run_exists():
    """It used to be a tab inside the results, so on the day — with no earlier run — it could
    not be reached at all."""
    assert "live" in home.MODES
    assert set(home.MODES) == {"run", "live", "engines", "cover"}
