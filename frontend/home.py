"""The start screen: one decision surface, one screen, almost no prose.

What it replaced was six stacked sections — a welcome paragraph, a three-step explainer, the
globe, two large pillar cards, a row of engine cards, a run bar — each with its own heading
and subtitle. Every section was individually defensible and the sum was a wall of text you
scrolled past to reach the button. The feedback was blunt and correct.

The rebuild rests on four decisions.

**The map does the explaining.** The globe is not decoration and not merely a picker: every
economy is filled by how far it has actually been taken — declared, reachable, extracted,
measured. That is the first question anyone asks about a tool like this, and answering it
inside the picker removes both the explanatory paragraph and a separate status table. It is
also the answer that cannot be over-claimed, because `tools/readiness.py` derives it from the
registries the pipeline reads rather than from anything typed here.

**Twelve pillars, not two.** The final-round brief warns the sealed test may name a pillar we
have not worked on, so all twelve are on screen and each says whether its definitions are
measured or merely declared. Two large cards for pillars 6 and 7 could not have shown that,
and implied the other ten did not exist.

**Screens, not tabs.** Run · Live test · Engines · Coverage are modes. On 15 October there is
no completed run to open a results tab from, so a live-test tab that only appears after a run
is a feature that exists and is not reachable when it is needed. Engines get a screen for the
opposite reason: provider-swappability is scored, and a screen states it more plainly than a
drawer does.

**Prose is spent only where a first-time researcher would otherwise be stuck.** Everything
else is a number, a state, or a name.
"""
from __future__ import annotations

import streamlit as st

from backend.rdtii.indicators import get_indicators
from backend.rdtii.indicators_wide import PILLAR_NAMES
from backend.schemas import ECONOMY_UN_NAME

from . import geo, theme

#: Pillars whose indicator definitions were tuned against the panel's own answer key and whose
#: retrieval parameters were swept against them. The other ten are coded from the Methodology's
#: scoring criteria and have never been scored — the screen says which is which rather than
#: presenting twelve equal buttons.
MEASURED_PILLARS = (6, 7)

#: Short enough to sit on a chip without wrapping. The official names are longer and are kept
#: as the tooltip, so nothing is lost.
PILLAR_SHORT = {
    1: "Tariffs & trade defence", 2: "Public procurement", 3: "Foreign investment",
    4: "Intellectual property", 5: "Telecom & competition", 6: "Cross-border data",
    7: "Data protection", 8: "Intermediary liability", 9: "Content access",
    10: "Non-technical NTMs", 11: "Standards", 12: "Online sales",
}

LEVEL_WORD = {"measured": "measured end to end", "extracted": "provisions extracted",
              "reachable": "portal answers", "declared": "declared only"}

MODES = {"run": "Run", "live": "Live test", "engines": "Engines", "cover": "Coverage"}

CSS = """
  /* ── the selection column ─────────────────────────────────────────────── */
  .pick-h{display:flex;align-items:baseline;gap:.55rem;flex-wrap:wrap;margin:0 0 .1rem;}
  .pick-h .nm{font-size:1.6rem;font-weight:700;letter-spacing:-.025em;line-height:1.1;}
  .pick-h .lv{font-size:.68rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    padding:.16rem .5rem;border-radius:99px;border:1px solid var(--rule);color:var(--ink-soft);
    background:var(--paper-2);white-space:nowrap;}
  .pick-h .lv.measured{border-color:var(--accent);color:var(--accent);}
  .pick-sub{font-family:var(--mono);font-size:.72rem;color:var(--ink-faint);
    overflow-wrap:anywhere;margin:0 0 .1rem;}

  /* ── section labels: one line, no subtitle ────────────────────────────── */
  .sec{font-size:.68rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
    color:var(--ink-faint);margin:1.1rem 0 .45rem;display:flex;gap:.5rem;align-items:baseline;}
  .sec .hint{font-weight:500;letter-spacing:0;text-transform:none;font-size:.75rem;
    color:var(--ink-faint);opacity:.85;}

  /* ── pillar chips ─────────────────────────────────────────────────────── */
  /* Streamlit's own button IS the chip. A markdown card with an invisible button beside it
     was the old approach and it left a dead zone wherever the two disagreed about their
     bounds — the card looked pressable in places that did nothing. */
  /* Targeted by widget KEY (Streamlit stamps `st-key-<key>` on the container), not by
     position. A sibling or nth-child selector here broke every time a wrapper div moved. */
  [class*="st-key-pill_"] button{
    width:100%;justify-content:flex-start;text-align:left;padding:.45rem .6rem;
    border-radius:10px;font-weight:600;font-size:.8rem;line-height:1.2;min-height:50px;}
  .pnote{font-size:.7rem;color:var(--ink-faint);margin:.4rem 0 0;line-height:1.5;}

  /* ── engines + run ────────────────────────────────────────────────────── */
  .eng{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;font-size:.8rem;
    color:var(--ink-soft);margin-bottom:.2rem;}
  .eng code{font-family:var(--mono);font-size:.74rem;background:var(--paper-2);
    border:1px solid var(--rule);border-radius:6px;padding:.1rem .38rem;color:var(--ink);}
  .runsum{font-size:.75rem;color:var(--ink-faint);margin:.45rem 0 0;text-align:center;
    font-family:var(--mono);overflow-wrap:anywhere;}
"""


def mode_bar(current: str) -> str:
    picked = st.segmented_control(
        "Screen", list(MODES), format_func=MODES.get, key="home_mode",
        default=current, label_visibility="collapsed")
    return picked or current


def _pillar_grid(current: int) -> int:
    st.markdown('<div class="sec">Topic'
                '<span class="hint">which RDTII pillar to search for</span></div>'
                '<div class="pgrid"></div>', unsafe_allow_html=True)
    chosen = current
    for row_start in (1, 4, 7, 10):
        for offset, col in enumerate(st.columns(3, gap="small")):
            pillar = row_start + offset
            measured = pillar in MEASURED_PILLARS
            with col:
                if st.button(f"{pillar} · {PILLAR_SHORT[pillar]}",
                             key=f"pill_{pillar}", width="stretch",
                             type="primary" if pillar == current else "secondary",
                             help=f"{PILLAR_NAMES[pillar]} · {len(get_indicators(pillar))} "
                                  f"indicators — "
                                  + ("definitions scored against the panel's answer key"
                                     if measured else
                                     "definitions coded from the Methodology, not yet scored")):
                    chosen = pillar
    st.markdown(
        '<p class="pnote">6 and 7 are the mandatory pair, and the only two whose indicator '
        'definitions have been scored against the panel&rsquo;s answer key. The other ten are '
        'coded from the same Methodology and have not been measured.</p>',
        unsafe_allow_html=True)
    return chosen


def _economy_head(code: str) -> None:
    row = geo.readiness().get(code, {})
    level = row.get("level", "declared")
    st.markdown(
        f'<div class="pick-h"><span class="nm">{ECONOMY_UN_NAME.get(code, code)}</span>'
        f'<span class="lv {level}">{LEVEL_WORD.get(level, level)}</span></div>'
        f'<p class="pick-sub">{row.get("portal", "—")}</p>',
        unsafe_allow_html=True)


def translate_needed(economy: str) -> bool:
    """Whether a run on this economy would produce any translation at all.

    Asks the translator itself rather than keeping a second list of English-speaking
    economies here — two lists is how the control ends up offering a translation the
    pipeline then skips.
    """
    try:
        from backend.pipeline.translate import needs_translation
        return needs_translation(economy)
    except Exception:                       # noqa: BLE001 — a control must not break the screen
        return True


def render(*, economy: str, pillar: int, ocr_label: str, llm_label: str,
           use_samples: bool, fresh: bool, scoring: bool, translate: bool = True) -> dict:
    """Draw the Run screen. Returns what the user changed, for app.py to commit.

    Nothing is written to `st.session_state` here: the caller owns that, so a control can
    never be written from two places — which is exactly how the theme toggle drifted out of
    step with Streamlit's own preference.
    """
    theme.inject_style(CSS)
    out: dict = {}
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        # The shell is 1720px wide now, and a 380px globe in a 950px column looked stranded.
        out["economy"] = geo.country_picker(selected=economy, key="geo_home", height=470)
    with right:
        _economy_head(out.get("economy") or economy)
        out["pillar"] = _pillar_grid(pillar)

        st.markdown('<div class="sec">Run</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="eng"><code>{ocr_label}</code> reads &middot; '
                    f'<code>{llm_label}</code> maps '
                    f'<span style="opacity:.7">&mdash; change them on the Engines screen'
                    f'</span></div>', unsafe_allow_html=True)

        _LIVE, _SAMPLE = "Live portals", "Offline samples"
        where = st.segmented_control(
            "Where to look", [_LIVE, _SAMPLE], key="where_to_look",
            default=_SAMPLE if use_samples else _LIVE, label_visibility="collapsed",
            help="Live crawls the government portals — the scored path. The offline samples "
                 "are a reproducible fallback for when a portal is down.")
        out["use_samples"] = (where == _SAMPLE)

        opt = st.columns(3, gap="small")
        with opt[0]:
            out["fresh"] = st.checkbox("Search again", value=fresh,
                                       help="Identical inputs normally return the saved "
                                            "result instantly.")
        with opt[1]:
            out["scoring"] = st.checkbox("Rate restrictiveness", value=scoring,
                                         help="Adds the RDTII raw score (0 / 0.5 / 1) per "
                                              "law. One extra AI call each. Never written to "
                                              "the submission file.")
        with opt[2]:
            # Shown DISABLED rather than hidden when the country already legislates in the
            # target language. A control that silently vanishes reads as a missing feature;
            # one that is present and explains itself answers the question instead.
            _needs = translate_needed(out.get("economy") or economy)
            out["translate"] = st.checkbox(
                "Translate results", value=(translate and _needs), disabled=not _needs,
                help=("Adds an English translation of each law name and quote, beside the "
                      "original. The original text is never replaced — it is the citation."
                      if _needs else
                      "This country's laws are already published in English, so there is "
                      "nothing to translate."))

        out["run"] = st.button("Run analysis", type="primary", width="stretch", key="run_home")
        st.markdown(f'<p class="runsum">{out.get("economy") or economy} · pillar '
                    f'{out["pillar"]} · {"samples" if out["use_samples"] else "live"}</p>',
                    unsafe_allow_html=True)
    return out


def coverage_screen() -> None:
    """The readiness table, generated — the long form of what the globe shows.

    It exists because a map answers "roughly where are we" and a submission needs "exactly
    what, and what is the next blocker". Both read the same rows, so they cannot disagree.
    """
    import pandas as pd

    rows = list(geo.readiness().values())
    if not rows:
        st.info("Readiness could not be computed — tools/readiness.py did not load.")
        return
    order = {"measured": 0, "extracted": 1, "reachable": 2, "declared": 3}
    rows.sort(key=lambda r: (order.get(r["level"], 9), r["economy"]))
    st.dataframe(
        pd.DataFrame([{
            "Economy": r["economy"],
            "Live-test nine": "yes" if r["nine"] else "—",
            "Reached": LEVEL_WORD.get(r["level"], r["level"]),
            "Language of source": r["language"],
            "Portal": r["portal"],
            "OCR": r["ocr"],
            "Next blocker": r["blocker"],
        } for r in rows]),
        width="stretch", hide_index=True)
    st.caption("Generated from data/sources.yaml, the language profiles and the OCR registry — "
               "not typed. Only *measured* is a claim about quality; the rungs below it are "
               "claims about plumbing.")
