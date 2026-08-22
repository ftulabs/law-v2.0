"""Coverage matrix — laws down the side, RDTII indicators across the top.

Replaces the vertical list of result cards. A researcher's first question is never "what
did row 14 say"; it is *which indicators are covered, by which law, and where is the gap*.
Three things fall out of the shape for free, and none of them were legible in a list:

  • a gap is an empty column — the thing judges check first
  • overlap is a row crossing several columns — the PDPA meets five indicators at once,
    which is exactly the pattern the official answer key shows
  • confidence is spatial — an amber cell is found by eye, not by working a filter

Rendered as a real bidirectional component (see `components/matrix/index.html`) because
`st.markdown` is write-only: a clicked cell has to be able to tell Python which piece of
evidence to open beside it.
"""
from __future__ import annotations

from pathlib import Path

import re

import streamlit as st
import streamlit.components.v1 as components

from backend.rdtii.indicators import get_indicators

from . import theme

_DIR = Path(__file__).resolve().parent / "components" / "matrix"
_matrix = components.declare_component("veritrade_matrix", path=str(_DIR))

# Column headers must survive a 52px column, so no single word may exceed nine characters
# — a longer one either forces the column wide (and the ninth indicator scrolls off) or
# gets broken mid-word, which reads as a rendering bug. The number is the authoritative
# label; the full official title rides along in the header tooltip, in the key printed
# under the matrix, and in the evidence panel.
SHORT: dict[str, str] = {
    "P6-I1": "Ban",
    "P6-I2": "Storage",
    "P6-I3": "Servers",
    "P6-I4": "Transfer",
    "P7-I1": "Framework",
    "P7-I2": "Cyber",
    "P7-I3": "Retention",
    "P7-I4": "DPO+DPIA",
    "P7-I5": "Gov access",
}

_TOKEN_KEYS = ("--paper", "--paper-2", "--ink", "--ink-soft", "--ink-faint", "--rule",
               "--rule-soft", "--accent", "--accent-ink", "--good", "--warn", "--bad",
               "--good-soft", "--warn-soft", "--bad-soft", "--panel", "--panel-2",
               "--shadow", "--ring")


def _tokens() -> dict[str, str]:
    """The component is an iframe and cannot inherit the page's CSS variables, so the
    active palette is passed in and re-declared on its own :root."""
    block = theme.DARK if theme.is_dark() else theme.LIGHT
    out: dict[str, str] = {}
    for part in block.replace("\n", "").split(";"):
        name, _, value = part.partition(":")
        name, value = name.strip(), value.strip()
        if name in _TOKEN_KEYS:
            out[name] = value
    return out


def num(indicator_id: str) -> str:
    """`P6-I1` -> `6.1`, the form the methodology and the judges' database both use."""
    try:
        pillar, ind = indicator_id.split("-")
        return f"{pillar[1:]}.{ind[1:]}"
    except (ValueError, IndexError):
        return indicator_id


def band(confidence: float) -> str:
    """Confidence band as a letter the component maps to a colour, matching the app's
    existing cut-offs — auto-accept at 0.85, set aside below 0.60."""
    return "g" if confidence >= 0.85 else "a" if confidence >= 0.60 else "r"


def build_rows(mappings, is_no_evidence, host) -> list[dict]:
    """Group mappings into one row per law, keyed by indicator.

    A "no provision found" placeholder is not evidence — it is a stated negative, so it
    gets its own neutral band ("n") rather than being coloured by its 0.0 confidence,
    which would paint an honest finding red.
    """
    rows: dict[str, dict] = {}
    for m in mappings:
        key = m.law_name
        row = rows.setdefault(key, {
            "law": m.law_name,
            "ref": getattr(m, "law_number", "") or "",
            "host": host(m.source_url),
            "cells": {},
        })
        no_ev = is_no_evidence(m)
        cell = {
            "s": "n" if no_ev else band(m.confidence_score),
            "t": "none" if no_ev else (m.article_section or "—"),
            # The short form is computed HERE, not in the component: it has to parse Han
            # numerals, and a citation converter that nothing can unit-test is how §21
            # became §201.
            "r": short_ref("none" if no_ev else (m.article_section or "—")),
            "band": "no provision found" if no_ev else f"confidence {m.confidence_score:.2f}",
        }
        # Where one law maps to the same indicator twice, keep the stronger reading —
        # the weaker one is still reachable from the Details tab.
        prev = row["cells"].get(m.indicator_id)
        if prev is None or (not no_ev and prev["s"] in ("n", "r")):
            row["cells"][m.indicator_id] = cell

    # Laws first by how many indicators they carry, then alphabetically: the workhorse
    # statute (usually the data-protection act) lands at the top where it belongs.
    ordered = sorted(rows.values(),
                     key=lambda r: (-sum(1 for c in r["cells"].values() if c["s"] != "n"),
                                    r["law"].lower()))
    return ordered


def indicator_columns(pillars) -> list[dict]:
    return [
        {"id": i.indicator_id, "num": num(i.indicator_id),
         "title": i.title, "short": SHORT.get(i.indicator_id, i.title)}
        for i in get_indicators() if i.pillar in pillars
    ]


_HAN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_HAN_UNIT = {"十": 10, "百": 100, "千": 1000}
_CN_ARTICLE = re.compile(r"^第\s*([零〇一二三四五六七八九十百千两\d\s]+)\s*[条章节]")
_MN_ARTICLE = re.compile(r"^(\d{1,3})\s*(?:д[үу]г[эа]{0,2}р|дэх|дахь)", re.I)
_LATIN_SEC = re.compile(r"^(?:section|sec\.?|s)\s*", re.I)
_LATIN_ART = re.compile(r"^(?:article|art\.?)\s*", re.I)


def han_number(text: str) -> int | None:
    """Read a Chinese numeral. 二十一 → 21, 一百零八 → 108, 四十 → 40.

    Positional by multiplier, not by digit. Treating the characters as a digit string turns
    article 21 into 201 — which is a real article of some other law, so the mistake reads as
    a plausible citation rather than as a rendering fault.
    """
    text = re.sub(r"\s+", "", text or "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = section = digit = 0
    for ch in text:
        if ch in _HAN_DIGIT:
            digit = _HAN_DIGIT[ch]
        elif ch in _HAN_UNIT:
            section += (digit or 1) * _HAN_UNIT[ch]
            digit = 0
        else:
            return None
    return (total + section + digit) or None


def short_ref(text: str) -> str:
    """The citation as it appears in a 52px matrix cell.

    Every jurisdiction is reduced to the same shape, §N, because the column is read
    vertically and a mix of "§199", "第二十一条" and "14 дүгээр зүйл" cannot be compared at a
    glance. Numerals are converted, never truncated: "第二十" is not a shorter way of writing
    article 21, it is article 20.
    """
    t = (text or "").strip()
    if not t or t == "—":
        return "·"
    if t == "(document)":
        return "doc"
    if t == "none":
        return "none"
    m = _CN_ARTICLE.match(t)
    if m:
        n = han_number(m.group(1))
        if n:
            return f"§{n}"
    m = _MN_ARTICLE.match(t)
    if m:
        return f"§{int(m.group(1))}"
    out = _LATIN_ART.sub("Art ", _LATIN_SEC.sub("§", t))
    out = re.sub(r"[–—-]\s*\d+.*$", "+", out)
    out = re.sub(r"\(.*$", "", out).strip()
    return out[:6] if len(out) > 6 else out


def coverage_matrix(rows: list[dict], indicators: list[dict],
                    selected: str | None = None, key: str = "matrix") -> str | None:
    """Render the matrix. Returns `"<law name>|<indicator id>"` for the chosen cell, or
    `selected` when nothing new was clicked this run."""
    try:
        chosen = _matrix(rows=rows, indicators=indicators, selected=selected,
                         tokens=_tokens(), key=key, default=selected)
    except Exception:
        return selected              # never let a component failure break a finished run
    return chosen or selected
