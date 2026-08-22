"""The start screen and the coverage globe.

The guard that matters most is the one about failure, not about dependencies. The globe loads
three.js and earth textures from a CDN — a fair trade on a machine with a network, and the
judging machine has one. What is not acceptable is what happens when the CDN is unreachable:
the requests die inside the iframe, Python sees no exception, and the country picker is simply
absent. Nothing in the suite could have caught that, because nothing looked at what happens
when the network is not there. So the tests below assert a second renderer and a deadline,
rather than forbidding the CDN.
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
def test_the_globe_survives_a_cdn_it_cannot_reach():
    """The 3D earth loads three.js and its textures from a CDN, which is the right trade when
    the machine has a network — it looks like what it is, a globe. What is NOT acceptable is
    the failure mode: those requests die inside the iframe, Python sees no exception, and the
    country picker is silently absent. So there has to be a second renderer and a deadline
    that hands over to it."""
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    assert "function startCanvas(" in html, "no dependency-free renderer to fall back to"
    assert "setTimeout(" in html and "startCanvas(" in html, "no deadline on the CDN import"
    assert "catch (err)" in html, "an import failure must be caught, not thrown into the void"


def test_the_geometry_itself_never_depends_on_the_network():
    """Textures are decoration and can fail. The outline is the data — where each economy IS
    — and both renderers read it from disk."""
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    assert 'fetch("world.json")' in html
    externals = set(re.findall(r"https?://[a-z0-9.\-]+", html))
    allowed = {"https://esm.sh", "https://cdn.jsdelivr.net"}
    assert externals <= allowed, f"unexpected external host: {externals - allowed}"


def test_the_world_outline_ships_with_the_component():
    world = json.loads((COMPONENT / "world.json").read_text(encoding="utf-8"))
    assert world["land"], "no land outline"
    assert len(world["economies"]) >= 11


def test_the_outline_is_small_enough_to_ship():
    kb = (COMPONENT / "world.json").stat().st_size / 1024
    assert kb < 250, f"{kb:.0f} KB — simplify further in tools/build_geo_outline.py"


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


# ── the citation in a 52px cell ──────────────────────────────────────────────────────
@pytest.mark.parametrize("citation,expected", [
    ("第一条", "§1"),
    ("第十二条", "§12"),          # 十二 is 12, not 102
    ("第二十一条", "§21"),         # 二十一 is 2×10+1, not the digits 2,10,1
    ("第四十条", "§40"),
    ("第七十四条", "§74"),
    ("第一百零八条", "§108"),
    ("14 дүгээр зүйл", "§14"),
    ("Section 199(1)", "§199"),
    ("s39-40", "§39+"),
    ("(document)", "doc"),
])
def test_a_citation_is_converted_for_the_cell_never_truncated(citation, expected):
    """The matrix column is read vertically, so every jurisdiction reduces to §N.

    Han numerals are positional by MULTIPLIER. The first version of this lived in the
    component's JavaScript, shifted instead of adding, and rendered 第二十一条 as §201 — which
    is a real article of some other law, so it reads as a plausible citation rather than as a
    rendering fault. It now lives in Python precisely so this test can exist.
    """
    from frontend.matrix import short_ref

    assert short_ref(citation) == expected


def test_a_han_numeral_that_is_not_a_numeral_returns_nothing():
    from frontend.matrix import han_number

    assert han_number("abc") is None
    assert han_number("") is None
    assert han_number("40") == 40


def test_the_component_no_longer_parses_citations_itself():
    """It renders the precomputed label. A parser in a file no test can reach is how the
    §201 bug survived."""
    html = (COMPONENT.parent / "matrix" / "index.html").read_text(encoding="utf-8")
    assert "hanNumber" not in html
    assert "cell.r" in html
