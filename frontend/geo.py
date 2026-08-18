"""Globe + map country picker.

A real bidirectional Streamlit component (declare_component with a static path), not an
`st.components.v1.html` iframe — that one is write-only and could never tell Python which
country was clicked. The HTML implements the component postMessage handshake by hand, so
there is no npm build step to run or ship.

Interaction, in the order a researcher meets it:
  • a slowly auto-rotating 3D earth; drag to spin it
  • click a marker to pick that economy, or click anywhere else on the globe to flip to a
    flat map with every marker visible at once
  • or just press the country name in the bar underneath

That last route matters beyond convenience: a drag-only control would fail WCAG 2.2
"dragging movements", which requires a single-pointer alternative for any drag.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import theme

_DIR = Path(__file__).resolve().parent / "components" / "geo"
_geo = components.declare_component("veritrade_geo", path=str(_DIR))

# Round-1 economies the pipeline actually supports, at their real capitals/centroids.
ECONOMIES = [
    {"iso": "SG", "name": "Singapore", "lat": 1.35, "lon": 103.82},
    {"iso": "AU", "name": "Australia", "lat": -25.27, "lon": 133.78},
    {"iso": "MY", "name": "Malaysia", "lat": 4.21, "lon": 101.98},
]
# Shown greyed-out so the map tells the whole RDTII story, not just what is wired up yet.
UPCOMING = [
    {"iso": "TH", "name": "Thailand", "lat": 15.87, "lon": 100.99},
    {"iso": "CN", "name": "China", "lat": 35.86, "lon": 104.19},
    {"iso": "IN", "name": "India", "lat": 20.59, "lon": 78.96},
    {"iso": "ID", "name": "Indonesia", "lat": -0.79, "lon": 113.92},
    {"iso": "RU", "name": "Russia", "lat": 61.52, "lon": 105.32},
    {"iso": "LA", "name": "Lao PDR", "lat": 19.86, "lon": 102.50},
    {"iso": "MN", "name": "Mongolia", "lat": 46.86, "lon": 103.85},
    {"iso": "TL", "name": "Timor-Leste", "lat": -8.87, "lon": 125.73},
]

# The component lives in an iframe, so it cannot inherit the page's CSS variables — the
# active palette is passed in and re-declared on its own :root.
_TOKEN_KEYS = ("--paper", "--paper-2", "--paper-3", "--ink", "--ink-soft", "--ink-faint",
               "--rule", "--accent", "--accent-ink", "--good", "--panel", "--panel-2",
               "--shadow", "--ring")


def _tokens() -> dict[str, str]:
    block = theme.DARK if theme.is_dark() else theme.LIGHT
    out: dict[str, str] = {}
    for part in block.replace("\n", "").split(";"):
        if ":" not in part:
            continue
        name, _, value = part.partition(":")
        name, value = name.strip(), value.strip()
        if name in _TOKEN_KEYS:
            out[name] = value
    return out


def country_picker(selected: str | None = None, key: str = "geo") -> str | None:
    """Render the picker. Returns the chosen ISO code, or `selected` if nothing new was
    clicked this run."""
    try:
        chosen = _geo(
            economies=ECONOMIES,
            upcoming=UPCOMING,
            selected=selected,
            theme="dark" if theme.is_dark() else "light",
            tokens=_tokens(),
            key=key,
            default=selected,
        )
    except Exception:
        return selected                      # never let a component failure break the run
    valid = {e["iso"] for e in ECONOMIES}
    return chosen if chosen in valid else selected
