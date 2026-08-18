"""VeriTrade dashboard (Streamlit).

Design direction — "clear research tool": a calm, high-contrast, sans-serif
interface built for policy researchers, not engineers. The screen leads with one
simple flow — pick a country, pick a topic, run — and keeps every technical knob
(OCR engine, LLM, model, keys) tucked inside an "Advanced settings" drawer. Plain
language throughout; a traffic-light system (green = high confidence, amber = needs
a check, red = set aside) carries certainty so the eye lands on doubt first.

Same backend the CLI/API use. Run:  streamlit run frontend/app.py
"""
from __future__ import annotations

import html as _html_mod
import queue
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import base64

import streamlit as st

# allow `import backend...` when launched via `streamlit run frontend/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings  # noqa: E402
from backend.export import export_csv, export_json, export_scored_csv  # noqa: E402
from backend.pipeline.orchestrator import run_pipeline  # noqa: E402
from backend.providers import registry as reg  # noqa: E402
from backend.rdtii import get_indicators  # noqa: E402
from backend.review import workflow  # noqa: E402
from backend.schemas import ECONOMY_UN_NAME, Economy, RunResult, SUBMISSION_COLUMNS  # noqa: E402
from backend.storage import db  # noqa: E402

from frontend import auth_ui, enginebench, geo, matrix, runview, theme  # noqa: E402
from frontend.theme import site_footer  # noqa: E402
from backend.rdtii.indicators import get_indicator  # noqa: E402

db.init_db()  # ensure schema exists on fresh mounts (no-op if tables already present)

# ── brand assets (drop files in frontend/assets/ — see ASSETS.md) ──────────
ASSETS = Path(__file__).resolve().parent / "assets"

# ── static docs: sync docs/<file> → frontend/static/ so Streamlit's static file server
#    (enableStaticServing) exposes each at /app/static/<file>. docs/ stays the single
#    source of truth; these copies are generated. The white paper opens from the app
#    header; the landing page is served here for preview (its real home is the site root). ──
_STATIC = Path(__file__).resolve().parent / "static"
_DOCS = Path(__file__).resolve().parent.parent / "docs"
WHITEPAPER_URL = "app/static/whitepaper.html"  # relative to the app origin (new-tab link)
LANDING_URL = "app/static/landing.html"


def _sync_static(filename: str) -> bool:
    src = _DOCS / filename
    if not src.exists():
        return False
    try:
        _STATIC.mkdir(exist_ok=True)
        dst = _STATIC / filename
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            dst.write_bytes(src.read_bytes())
        return True
    except Exception:
        return False


_HAS_WHITEPAPER = _sync_static("whitepaper.html")
_HAS_LANDING = _sync_static("landing.html")
_HAS_FONTS = _sync_static("fonts.html")      # typography comparison (design decision aid)


def _asset(*names: str) -> Path | None:
    for n in names:
        p = ASSETS / n
        if p.exists():
            return p
    return None


def _img_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def logo_html() -> str:
    """VeriTrade wordmark: prefer a transparent PNG, fall back to the brand SVG, then text."""
    png = _asset("veritrade_logo.png", "veritrade_logo.webp")
    if png:
        return (f'<img class="vt-logo" alt="VeriTrade" '
                f'src="data:image/{png.suffix[1:]};base64,{_img_b64(png)}"/>')
    svg = _asset("veritrade_logo.svg")
    if svg:
        return f'<div class="vt-logo">{svg.read_text(encoding="utf-8")}</div>'
    return '<h1 class="wordmark">Veri<span class="mark">Trade</span></h1>'


theme.page_config("VeriTrade")
theme.keyboard_guard()
theme.inject_css()          # tokens + typography + native-widget palette (both themes)

# ── who's signed in ───────────────────────────────────────────────────────
# Renders the landing page and stops here when nobody is; everything below this
# line therefore always has a real account to attribute runs to.
USER = auth_ui.require_user()

# The palette follows Streamlit's active theme (see theme.py) — the app no longer
# keeps a second, independent theme flag that could disagree with native widgets.
DARK = theme.is_dark()
PALETTE = (theme.DARK if DARK else theme.LIGHT) + ("--gold:#7cc4ff;" if DARK else "--gold:#2563eb;")
APP_BG = "background-color:var(--paper);"
# the blue wordmark sits close to navy in luminance — lift it and add a thin light edge
# + a soft blue halo so it separates cleanly from the dark background
LOGO_FX = (("filter:brightness(1.15) drop-shadow(0 0 1px rgba(232,240,255,.55)) "
            "drop-shadow(0 0 18px rgba(90,170,255,.28));") if DARK else "")

st.markdown(
    f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

      :root {{ {PALETTE} }}

      .stApp {{
        {APP_BG}
        color: var(--ink);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 16px;
      }}
      .vt-logo {{ line-height:0; margin:.1rem 0; }}
      img.vt-logo, .vt-logo img, .vt-logo svg {{ height:68px !important; width:auto !important;
              max-width:420px; display:block; {LOGO_FX} }}
      .wordmark {{ font-size:2rem; font-weight:700; letter-spacing:-.02em; margin:0; }}
      .wordmark .mark {{ color:var(--accent); }}
      .block-container {{padding-top: 1.2rem; max-width: 1240px;}}
      [data-testid="stHeader"] {{background: transparent;}}

      h1,h2,h3,h4 {{font-family:'Inter',sans-serif; color:var(--ink); letter-spacing:-.015em; font-weight:600;}}
      a {{color:var(--accent); text-decoration:none;}}
      a:hover {{text-decoration:underline;}}

      .mono {{font-family:'IBM Plex Mono',ui-monospace,monospace;}}
      /* section label — calm, sentence-case, NOT a shouty all-caps eyebrow */
      .kicker {{font-family:'Inter',sans-serif; font-size:.8rem; font-weight:600;
                letter-spacing:.01em; text-transform:none; color:var(--ink-soft);}}
      .muted {{color:var(--ink-faint); font-size:.85rem;}}

      /* ── header ── */
      .vt-brand {{display:flex; align-items:center;}}
      .masthead {{border-bottom:1px solid var(--rule); padding-bottom:.8rem; margin-bottom:.6rem;}}
      .masthead .subrow {{display:flex; align-items:baseline; justify-content:space-between;
                          gap:1.2rem; flex-wrap:wrap;}}
      .masthead .strap {{color:var(--ink-soft); font-size:.95rem;}}
      /* the confidence bands sit opposite the logo; they must not wrap mid-band or get
         clipped by the flex row, so give the block room and keep each band intact */
      .masthead .edition {{text-align:right; font-family:'IBM Plex Mono',monospace; font-size:.72rem;
                           color:var(--ink-faint); line-height:1.7; flex:none;}}
      .masthead .edition .tip {{flex-wrap:wrap; justify-content:flex-end;}}
      .masthead .edition span {{white-space:nowrap;}}

      /* ── summary strip ── */
      .ledger {{display:flex; flex-wrap:wrap; gap:.6rem; margin:1rem 0 .4rem;}}
      .ledger .cell {{flex:1; min-width:120px; padding:.7rem .9rem; border:1px solid var(--rule);
                      border-radius:10px; background:var(--panel);}}
      .ledger .cap {{font-size:.72rem; font-weight:500; color:var(--ink-faint);}}
      .ledger .num {{font-size:1.55rem; font-weight:700; line-height:1.15; margin-top:.15rem; white-space:nowrap;}}
      .ledger .num.ox {{color:var(--bad);}} .ledger .num.fo {{color:var(--good);}}
      .ledger .num.oc {{color:var(--warn);}}

      /* ── confidence bar ── */
      .verdict {{display:flex; align-items:center; gap:.5rem;}}
      .vbar {{flex:1; height:8px; background:var(--paper-3); border-radius:99px; overflow:hidden;}}
      .vbar > i {{display:block; height:100%; background:var(--c); border-radius:99px;}}
      .vnum {{font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:.82rem; color:var(--c);}}
      .vtag {{font-size:.68rem; font-weight:500; color:var(--ink-faint);}}

      /* ── status pill ── */
      .seal {{display:inline-block; font-size:.72rem; font-weight:600;
              padding:.14rem .55rem; border-radius:99px; border:1px solid; }}
      .s-auto {{color:var(--good); border-color:var(--good); background:color-mix(in srgb, var(--good) 12%, transparent);}}
      .s-review {{color:var(--warn); border-color:var(--warn); background:color-mix(in srgb, var(--warn) 12%, transparent);}}
      .s-quar {{color:var(--bad); border-color:var(--bad); background:color-mix(in srgb, var(--bad) 12%, transparent);}}
      .s-appr {{color:var(--appr); border-color:var(--appr); background:color-mix(in srgb, var(--appr) 12%, transparent);}}
      .s-rej {{color:var(--ink-soft); border-color:var(--rule);}}
      .s-flag {{color:var(--flag); border-color:var(--flag); background:color-mix(in srgb, var(--flag) 12%, transparent);}}

      /* ── confidence legend ── */
      .legend {{display:flex; flex-wrap:wrap; gap:1.2rem; align-items:center; padding:.7rem .95rem;
                border:1px solid var(--rule); border-radius:10px; background:var(--panel);
                margin:.2rem 0 1rem; font-size:.86rem;}}
      .legend .item {{display:flex; align-items:center; gap:.45rem; color:var(--ink-soft);}}
      .legend .dot {{width:11px; height:11px; border-radius:50%; flex:none;}}
      .legend .dot.g {{background:var(--good);}} .legend .dot.a {{background:var(--warn);}}
      .legend .dot.r {{background:var(--bad);}}
      .legend b {{color:var(--ink); font-weight:600;}}

      /* ── result card ── */
      .vt-card {{border:1px solid var(--rule); border-left:4px solid var(--c,var(--rule));
                 background:var(--panel); padding:1rem 1.1rem; margin-bottom:.7rem; border-radius:10px;
                 display:grid; grid-template-columns: 96px 1fr 176px; gap:1.1rem; align-items:start;}}
      .vt-card .docket b {{font-size:1.1rem; color:var(--ink); font-weight:700;}}
      .vt-card .docket span {{display:block; font-size:.72rem; color:var(--ink-faint); margin-top:.2rem;}}
      .vt-card .law {{font-weight:600; font-size:1.02rem; line-height:1.3;}}
      .vt-card .cite {{font-family:'IBM Plex Mono',monospace; font-size:.74rem; color:var(--ink-soft);}}
      .quote {{color:var(--ink-soft); border-left:3px solid var(--rule); background:var(--paper-2);
               padding:.5rem .8rem; margin:.5rem 0 .4rem; font-size:.92rem; line-height:1.55; border-radius:0 6px 6px 0;}}
      .cite {{font-family:'IBM Plex Mono',monospace; font-size:.78rem; color:var(--ink-soft);}}
      .law {{font-weight:600;}}
      .srcurl {{font-family:'IBM Plex Mono',monospace; font-size:.7rem;}}
      /* "nothing found" card — deliberately muted, no traffic-light, no link-as-evidence */
      .vt-card.empty {{border-left-color:var(--rule); grid-template-columns:96px 1fr auto; align-items:center;}}
      .vt-card.empty .docket b {{color:var(--ink-soft);}}
      .vt-card.empty .empty-ttl {{font-weight:600; color:var(--ink-soft); font-size:1rem;}}
      .vt-card.empty .empty-sub {{color:var(--ink-faint); font-size:.9rem; margin-top:.15rem; line-height:1.5;}}
      .vt-card.empty .searched {{font-family:'IBM Plex Mono',monospace; font-size:.7rem;
              color:var(--ink-faint); margin-top:.45rem;}}
      .seal.s-none {{color:var(--ink-faint); border-color:var(--rule); background:transparent;}}

      /* ── tabs ── */
      .stTabs [data-baseweb="tab-list"] {{gap:1.4rem; border-bottom:1px solid var(--rule);}}
      .stTabs [data-baseweb="tab"] {{font-family:'Inter',sans-serif; font-size:.95rem; font-weight:600;
              letter-spacing:0; text-transform:none; color:var(--ink-faint); padding:.5rem 0;}}
      .stTabs [aria-selected="true"] {{color:var(--accent) !important;}}
      .stTabs [data-baseweb="tab-highlight"] {{background:var(--accent);}}

      /* ── sidebar ── */
      [data-testid="stSidebar"] {{background:var(--paper-2); border-right:1px solid var(--rule);}}
      [data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 {{font-family:'Inter',sans-serif;}}
      [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg,
      [data-testid="stSidebarCollapsedControl"] svg, [data-testid="stExpandSidebarButton"] svg,
      [data-testid="stSidebarCollapseButton"] button, [data-testid="collapsedControl"] button {{
              color:var(--accent) !important; fill:var(--accent) !important; opacity:1 !important;}}
      [data-testid="collapsedControl"] {{background:var(--paper-2) !important; border-radius:8px;}}

      /* buttons — clear, rounded, readable in EVERY state and theme. The label sits in a child
         (stMarkdownContainer/<p>) the global ink rule would darken, and Streamlit's baked dark
         secondaryBackground bleeds into hover/active — so pin bg + label colour on all states.
         Scoped :not([kind="primary"]) so the filled primary button keeps its own styling. */
      /* the white-paper link is a real st.link_button, so it shares these rules with the
         secondary theme-toggle button — identical font, weight, and format. */
      .stButton button, .stLinkButton a {{font-family:'Inter',sans-serif; font-size:.9rem; font-weight:600;
              border-radius:9px; text-decoration:none !important;}}
      .stButton button:not([kind="primary"]), .stLinkButton a {{ background:var(--panel) !important;
              border:1px solid var(--rule) !important; }}
      .stButton button:not([kind="primary"]), .stButton button:not([kind="primary"]) *,
      .stLinkButton a, .stLinkButton a * {{ color:var(--ink) !important; }}
      .stButton button:not([kind="primary"]):hover, .stButton button:not([kind="primary"]):active,
      .stButton button:not([kind="primary"]):focus, .stLinkButton a:hover, .stLinkButton a:focus {{
              background:var(--panel-2) !important; border-color:var(--accent) !important; }}
      .stButton button:not([kind="primary"]):hover *, .stButton button:not([kind="primary"]):active *,
      .stButton button:not([kind="primary"]):focus *, .stLinkButton a:hover, .stLinkButton a:hover * {{
              color:var(--accent) !important; }}
      /* primary action = filled accent, high contrast. The label lives in a child
         (stMarkdownContainer / <p>) that the global ink rule would otherwise darken, so
         paint the button AND all its descendants the accent-ink colour. */
      .stButton button[kind="primary"], .stButton button[data-testid="baseButton-primary"],
      .stButton button[data-testid="stBaseButton-primary"] {{
              background:var(--accent) !important; border-color:var(--accent) !important; font-weight:700;}}
      .stButton button[kind="primary"], .stButton button[kind="primary"] *,
      .stButton button[data-testid="baseButton-primary"], .stButton button[data-testid="baseButton-primary"] *,
      .stButton button[data-testid="stBaseButton-primary"], .stButton button[data-testid="stBaseButton-primary"] * {{
              color:var(--accent-ink) !important; fill:var(--accent-ink) !important; }}
      .stButton button[kind="primary"]:hover {{filter:brightness(1.06);}}
      .stDownloadButton button {{font-family:'Inter',sans-serif; font-weight:600; border-radius:9px;}}

      /* ── confidence breakdown bars (details) ── */
      .bd {{display:grid; grid-template-columns:150px 1fr 48px; align-items:center; gap:.6rem; margin:.35rem 0;}}
      .bd .lab {{font-size:.8rem; color:var(--ink-soft);}}
      .bd .track {{height:7px; background:var(--paper-3); border-radius:99px; overflow:hidden;}}
      .bd .track > i {{display:block; height:100%; background:var(--accent); border-radius:99px;}}
      .bd .track > i.final {{background:var(--good);}}
      .bd .val {{font-family:'IBM Plex Mono',monospace; font-size:.76rem; text-align:right;}}

      .prov-note {{font-size:.78rem; color:var(--ink-faint); margin:.15rem 0 .4rem; line-height:1.4;}}
      .prov-note.ready {{color:var(--good);}}

      /* ── text-extraction (OCR) quality panel ── */
      .ocr-forensics {{border:1px solid var(--rule); border-radius:12px; overflow:hidden;
                       background:var(--panel); margin:1rem 0 .2rem;}}
      .ocr-head {{display:flex; justify-content:space-between; align-items:center;
                  padding:.8rem 1.1rem; border-bottom:1px solid var(--rule-soft); background:var(--panel-2);}}
      .ocr-headline {{text-align:right; line-height:1.15;}}
      .ocr-headline .hv {{display:block; font-weight:700; font-size:1.25rem; color:var(--c);}}
      .ocr-headline .hk {{font-size:.72rem; font-weight:500; color:var(--c); opacity:.9;}}
      .ocr-row {{display:grid; grid-template-columns:1.5fr 1.3fr .9fr; gap:1.3rem; align-items:center;
                 padding:.75rem 1.1rem; border-bottom:1px solid var(--rule-soft);}}
      .ocr-row:last-child {{border-bottom:none;}}
      .ocr-doc .ttl {{font-weight:600; font-size:1rem; line-height:1.25;}}
      .ocr-doc .meta {{font-family:'IBM Plex Mono',monospace; font-size:.7rem;
                       color:var(--ink-faint); margin-top:.2rem;}}
      .ocr-row .cap {{font-size:.72rem; font-weight:500; color:var(--ink-faint); margin-bottom:.28rem;}}
      .ocr-conf .track {{height:8px; background:var(--paper-3); border-radius:99px; overflow:hidden;}}
      .ocr-conf .track > i {{display:block; height:100%; background:var(--accent); border-radius:99px;}}
      .ocr-conf .cval {{font-family:'IBM Plex Mono',monospace; font-size:.74rem; color:var(--ink-soft);
                        margin-top:.24rem;}}
      .ocr-verdict {{text-align:right;}}
      .ocr-cer {{font-weight:700; font-size:1.7rem; line-height:1; color:var(--c); display:block;}}
      .ocr-cer small {{font-size:.9rem; opacity:.7; font-weight:500;}}
      .ocr-stamp {{display:inline-block; margin-top:.34rem; font-size:.7rem; font-weight:600;
                   padding:.14rem .55rem; border-radius:99px; border:1px solid currentColor;}}
      .ocr-stamp.pass {{color:var(--good); background:color-mix(in srgb, var(--good) 12%, transparent);}}
      .ocr-stamp.fail {{color:var(--bad); background:color-mix(in srgb, var(--bad) 12%, transparent);}}
      .ocr-stamp.none {{color:var(--ink-faint); border-color:var(--rule);}}

      /* ── native Streamlit elements follow the palette (var(--ink) flips light/dark) ── */
      [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * {{ color:var(--ink) !important; }}
      [data-testid="stMarkdownContainer"] {{ color:var(--ink); }}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color:var(--ink-faint) !important; }}
      [data-testid="stMetricValue"] {{ color:var(--ink) !important; }}
      [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{ color:var(--ink-soft) !important; }}
      [data-testid="stExpander"] {{ border:1px solid var(--rule) !important; border-radius:10px !important;
              background:var(--panel) !important; }}
      /* the summary bar + opened body must follow the theme too — otherwise Streamlit's baked
         dark secondaryBackground shows through in light mode until you hover it */
      [data-testid="stExpander"] details, [data-testid="stExpander"] summary,
      [data-testid="stExpanderDetails"] {{ background:var(--panel) !important; }}
      [data-testid="stExpander"] summary:hover {{ background:var(--panel-2) !important; }}
      [data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{ color:var(--ink) !important; font-weight:600; }}
      [data-testid="stNotificationContentInfo"], [data-testid="stStatusWidget"] * {{ color:var(--ink) !important; }}
      .stTextInput input, .stNumberInput input, .stTextArea textarea {{
              color:var(--ink) !important; background:var(--paper) !important;
              border-radius:8px !important; }}
      div[data-baseweb="select"] > div {{ background:var(--paper) !important;
              border-color:var(--rule) !important; border-radius:8px !important; }}
      div[data-baseweb="select"] * {{ color:var(--ink) !important; }}
      /* Dropdown surfaces ONLY — scoped to popovers that actually contain a listbox/menu.
         The old blanket `[data-baseweb="popover"] div … !important` painted every div in
         every popover, which flattened the account menu's avatar and stat tiles. */
      [data-baseweb="popover"]:has([role="listbox"]) > div,
      [data-baseweb="popover"]:has([data-baseweb="menu"]) > div,
      [data-baseweb="popover"] ul, [data-baseweb="menu"],
      ul[role="listbox"], div[role="listbox"] {{
              background-color:var(--paper-2) !important; }}
      [role="option"], [role="option"] *, [data-baseweb="menu"] li {{
              background-color:transparent !important; color:var(--ink) !important; }}
      [role="option"]:hover, li[role="option"][aria-selected="true"] {{ background-color:var(--paper-3) !important; }}
      [data-baseweb="popover"]:has([role="menuitem"]), [data-baseweb="popover"]:has([role="menuitem"]) * {{
              color:var(--ink) !important; }}
      /* multiselect chips */
      [data-baseweb="tag"] {{ background:var(--accent) !important; border-color:var(--accent) !important; border-radius:6px !important; }}
      [data-baseweb="tag"], [data-baseweb="tag"] *,
      [data-testid="stMultiSelect"] [data-baseweb="tag"], [data-testid="stMultiSelect"] [data-baseweb="tag"] * {{
              color:var(--accent-ink) !important; fill:var(--accent-ink) !important; }}
      [data-testid="stSliderThumbValue"], [data-testid="stTickBarMin"], [data-testid="stTickBarMax"] {{
              color:var(--ink-soft) !important; }}
      pre, code, .stCode, [data-testid="stJson"], [data-testid="stJson"] * {{
              background:var(--paper-3) !important; color:var(--ink) !important; border-radius:8px; }}

      /* top-right toggle button + overflow menu */
      [data-testid="stPopover"] {{ display:flex; justify-content:flex-end; }}
      [data-testid="stPopover"] button {{background:var(--panel) !important; border:1px solid var(--rule) !important;
              color:var(--ink-soft) !important; border-radius:8px; padding:.1rem .55rem;}}
      [data-testid="stPopover"] button:hover {{color:var(--accent) !important; border-color:var(--accent) !important;}}
      .hr-thin {{border:none; border-top:1px solid var(--rule-soft); margin:.7rem 0;}}

      /* ── RDTII score chip — a neutral GREY chip (not the traffic-light colours) so it
            reads as a different axis: restrictiveness / compliance cost, not confidence. ── */
      .stamp {{display:inline-flex; align-items:center; gap:.5rem; font-family:'IBM Plex Mono', monospace;
              border:1px solid var(--rule); border-radius:9px; padding:.32rem .6rem;
              background:var(--paper-2); color:var(--ink);}}
      .stamp .pie {{width:18px; height:18px; border-radius:50%; flex:none;
              border:1.5px solid var(--ink-faint);
              background:conic-gradient(var(--ink-soft) var(--p,0%), transparent 0);}}
      .stamp .sc-cap {{font-size:.6rem; text-transform:uppercase; letter-spacing:.08em;
              color:var(--ink-faint); line-height:1.05; display:block;}}
      .stamp .sc-num {{font-weight:600; font-size:1.02rem; line-height:1;}}
      .stamp .sc-tier {{font-size:.62rem; color:var(--ink-soft);}}
      .stamp.mini {{padding:.18rem .45rem; gap:.35rem;}}
      .stamp.mini .pie {{width:13px; height:13px;}}
      .stamp.mini .sc-num {{font-size:.82rem;}}

      /* ── indicator scorecard (RDTII roll-up: one score per indicator) ── */
      .scorecard {{display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 1.1rem;}}
      .sc-tile {{display:flex; flex-direction:column; gap:.3rem; border:1px solid var(--rule);
              background:var(--panel); padding:.55rem .8rem; border-radius:10px; min-width:104px;}}
      .sc-tile .ind {{font-size:.72rem; font-weight:600; color:var(--ink-faint);}}
      .sc-tile .scrow {{display:flex; align-items:center; gap:.4rem;}}
      .sc-tile .pie {{width:15px; height:15px; border-radius:50%; flex:none;
              border:1.5px solid var(--ink-faint);
              background:conic-gradient(var(--ink-soft) var(--p,0%), transparent 0);}}
      .sc-tile .scv {{font-family:'IBM Plex Mono', monospace; font-weight:700; font-size:1.35rem;
              line-height:1; color:var(--ink);}}
      .sc-tile .meta {{font-size:.68rem; color:var(--ink-faint);}}

      /* ── guided empty state ── */
      .welcome {{border:1px solid var(--rule); border-radius:14px; background:var(--panel);
                 padding:1.6rem 1.8rem; margin-top:1.2rem;}}
      .welcome h3 {{margin:0 0 .3rem; font-size:1.3rem;}}
      .welcome p {{color:var(--ink-soft); margin:.2rem 0 1.1rem; font-size:.98rem;}}
      .steps {{display:grid; grid-template-columns:repeat(3,1fr); gap:1rem;}}
      @media (max-width:760px) {{ .steps {{grid-template-columns:1fr;}} }}
      .step {{border:1px solid var(--rule); border-radius:12px; padding:1rem 1.1rem; background:var(--paper-2);}}
      .step .n {{display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px;
                 border-radius:50%; background:var(--accent); color:var(--accent-ink); font-weight:700;
                 font-size:.9rem; margin-bottom:.5rem;}}
      .step .t {{font-weight:600; margin-bottom:.2rem;}}
      .step .d {{color:var(--ink-soft); font-size:.9rem; line-height:1.5;}}

      /* ── "while you wait" panels: indicator glossary, live discovery feed, results-so-far ── */
      .waitpanel {{border:1px solid var(--rule); border-radius:12px; background:var(--panel);
              padding:.9rem 1.05rem; margin:.6rem 0 1rem;}}
      .waitpanel .wp-head {{font-weight:600; font-size:.92rem; margin-bottom:.5rem;}}
      .glossary-item {{padding:.55rem 0; border-bottom:1px solid var(--rule-soft);}}
      .glossary-item:last-child {{border-bottom:none;}}
      .glossary-item .gi-id {{font-family:'IBM Plex Mono',monospace; font-size:.72rem; font-weight:600;
              color:var(--accent); margin-right:.4rem;}}
      .glossary-item .gi-title {{font-weight:600; font-size:.92rem;}}
      .glossary-item .gi-desc {{color:var(--ink-soft); font-size:.85rem; margin-top:.15rem; line-height:1.45;}}

      /* ── hover tooltip (explains the confidence formula + cut-offs) ── */
      /* let tooltips escape their Streamlit containers instead of being clipped */
      [data-testid="stMarkdownContainer"], .stTabs [data-baseweb="tab-panel"],
      [data-testid="stColumn"], [data-testid="column"] {{ overflow: visible; }}
      .tip {{ position:relative; display:inline-flex; align-items:center; gap:.3rem; cursor:help; }}
      .tip .tq {{ display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
              border-radius:50%; border:1px solid var(--ink-faint); color:var(--ink-faint);
              font-size:.62rem; font-weight:700; flex:none; }}
      .tip:hover .tq {{ border-color:var(--accent); color:var(--accent); }}
      .tip .tipbox {{ position:absolute; z-index:9999; top:calc(100% + 8px); left:0; width:340px; max-width:80vw;
              padding:.8rem .9rem; border-radius:11px; border:1px solid var(--rule); background:var(--paper-2);
              color:var(--ink); box-shadow:0 14px 40px rgba(0,0,0,.30); font-size:.82rem; line-height:1.5;
              text-align:left; white-space:normal; font-weight:400;
              opacity:0; visibility:hidden; transform:translateY(-4px); transition:opacity .12s, transform .12s; }}
      .tip.right .tipbox {{ left:auto; right:0; }}
      .tip:hover .tipbox, .tip:focus-within .tipbox {{ opacity:1; visibility:visible; transform:none; }}
      .tipbox b {{ color:var(--ink); font-weight:600; }}
      .tipbox .thead {{ font-size:.92rem; margin-bottom:.35rem; }}
      .tipbox .row {{ display:flex; justify-content:space-between; gap:.9rem; margin:.18rem 0; align-items:baseline; }}
      .tipbox .k {{ color:var(--ink-soft); }}
      .tipbox .w {{ font-family:'IBM Plex Mono',monospace; color:var(--ink); font-weight:600; flex:none; }}
      .tipbox .d {{ display:inline-block; width:8px; height:8px; border-radius:50%; vertical-align:middle; margin-right:.4rem; }}
      .tipbox .frm {{ font-family:'IBM Plex Mono',monospace; font-size:.74rem; color:var(--ink-soft);
              background:var(--paper-3); border-radius:7px; padding:.4rem .55rem; margin:.45rem 0; display:block; }}
      .tipbox .note {{ color:var(--ink-faint); margin-top:.4rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)

_EVIDENCE_CSS = """
  /* Panel that opens beside the coverage matrix. Its job is to let a researcher judge the
     mapping themselves, so the indicator's legal test sits directly above the quote —
     without it the reader can only take the confidence score on trust. */
  .evp{border:1px solid var(--rule);border-radius:14px;background:var(--panel);
    padding:1.05rem 1.15rem 1.15rem;box-shadow:var(--shadow-lg);}
  .evp .evhead{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;}
  .evp .evid{font-family:var(--mono);font-size:.82rem;font-weight:600;color:var(--accent);
    background:var(--accent-soft);padding:2px 8px;border-radius:6px;}
  .evp h4{font-size:1.02rem;line-height:1.3;margin:.5rem 0 .1rem;font-weight:600;}
  .evp .evcite{font-family:var(--mono);font-size:.72rem;color:var(--ink-faint);}
  .evp .test{background:var(--paper-2);border-left:3px solid var(--accent);
    border-radius:0 8px 8px 0;padding:.6rem .75rem;margin:.85rem 0;font-size:.78rem;
    color:var(--ink-soft);}
  .evp .test b{display:block;font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;
    color:var(--ink-faint);margin-bottom:.15rem;font-weight:600;}
  .evp blockquote{margin:0;padding:.85rem .95rem;border-radius:10px;background:var(--panel-2);
    border:1px solid var(--rule);font-size:.87rem;line-height:1.62;color:var(--ink);}
  .evp blockquote::before{content:"C";font-size:1.6rem;color:var(--accent);line-height:0;
    vertical-align:-.35rem;margin-right:2px;}
  .evp .why{font-size:.78rem;color:var(--ink-soft);margin:.75rem 0 0;}
  .evp .why b{color:var(--ink);}
  .evp .bars{margin:.95rem 0 0;display:flex;flex-direction:column;gap:.35rem;}
  .evp .bd{display:grid;grid-template-columns:88px 1fr 34px;align-items:center;gap:.55rem;
    font-size:.72rem;}
  .evp .bd .lab{color:var(--ink-faint);}
  .evp .bd .track{height:6px;border-radius:99px;background:var(--paper-2);overflow:hidden;}
  .evp .bd .track i{display:block;height:100%;border-radius:99px;background:var(--accent);}
  .evp .bd .val{font-family:var(--mono);text-align:right;color:var(--ink-soft);}
  .evp .bd.tot{font-weight:600;font-size:.78rem;margin-top:.15rem;}
  .evp .bd.tot .lab{color:var(--ink);} .evp .bd.tot .track{height:9px;}
  .evp .evlink{display:block;margin-top:.85rem;font-family:var(--mono);font-size:.72rem;
    word-break:break-all;}
  .evp.empty{box-shadow:var(--shadow);}
  .evp .nofind{font-size:.85rem;color:var(--ink-soft);line-height:1.6;}
  .mxhint{font-size:.75rem;color:var(--ink-faint);margin:.5rem 0 .75rem;}
  .mxkey{display:flex;flex-wrap:wrap;gap:.25rem 1.1rem;margin:.7rem 0 0;
    font-size:.72rem;color:var(--ink-faint);}
  .mxkey b{font-family:var(--mono);color:var(--ink-soft);font-weight:600;}
"""

_RUNBAR_CSS = """
  .rbttl{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
    color:var(--ink-faint);margin-bottom:.3rem;}
  .rbsum{font-size:.95rem;font-weight:600;color:var(--ink);line-height:1.4;}
  .rbsum span{display:block;font-family:var(--mono);font-size:.72rem;font-weight:400;
    color:var(--ink-faint);margin-top:.15rem;overflow-wrap:anywhere;}
  .rbsum.big{font-size:1.15rem;}
"""

_PILLAR_CARD_CSS = """
  .pcard{border:1px solid var(--rule);border-radius:14px;background:var(--panel);
    padding:1.1rem 1.2rem .9rem;box-shadow:var(--shadow);position:relative;overflow:hidden;
    transition:border-color .18s ease, transform .18s ease, box-shadow .18s ease;}
  .pcard:hover{transform:translateY(-2px);border-color:var(--accent);box-shadow:var(--shadow-lg);}
  .pcard.on{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),var(--shadow-lg);}
  .pcard::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent);
    opacity:0;transition:opacity .18s;}
  .pcard.on::before{opacity:1;}
  .pcard .pnum{font-family:'IBM Plex Mono',monospace;font-size:.72rem;font-weight:700;
    letter-spacing:.1em;text-transform:uppercase;color:var(--accent);}
  .pcard .ptitle{font-size:1.18rem;font-weight:700;letter-spacing:-.02em;margin:.25rem 0 .3rem;}
  .pcard .psub{color:var(--ink-soft);font-size:.9rem;line-height:1.5;margin-bottom:.8rem;}
  .pcard .plist{display:flex;flex-wrap:wrap;gap:.32rem;margin-bottom:.7rem;}
  .pcard .plist span{font-size:.74rem;color:var(--ink-soft);background:var(--paper-2);
    border:1px solid var(--rule);border-radius:99px;padding:.16rem .55rem;}
  .pcard .pfoot{font-size:.72rem;color:var(--ink-faint);margin-top:auto;}
  /* both cards share one height so their buttons line up, however many indicator chips
     each pillar wraps onto. Flex only — a percentage height would resolve against a
     content-height parent and pin each column to its own content. */
  [data-testid="stHorizontalBlock"]:has(.pcard){align-items:stretch;}
  [data-testid="stColumn"]:has(.pcard){display:flex;flex-direction:column;}
  [data-testid="stColumn"]:has(.pcard) > [data-testid="stVerticalBlock"]{
    flex:1;display:flex;flex-direction:column;}
  [data-testid="stElementContainer"]:has(.pcard){flex:1;display:flex;}
  /* stretch the wrappers Streamlit puts between the container and our markup, or the
     card sits at its own content height and leaves a gap above the button */
  [data-testid="stElementContainer"]:has(.pcard) > div,
  [data-testid="stElementContainer"]:has(.pcard) [data-testid="stMarkdownContainer"]{
    flex:1;display:flex;flex-direction:column;}
  /* Streamlit nests our markup several wrappers deep and flex:1 does not survive the
     chain, so pin a shared min-height instead: predictable, and both cards hold the same
     shape whichever pillar wraps an extra row of chips. */
  .pcard{flex:1;display:flex;flex-direction:column;min-height:215px;}
"""

SEAL = {"auto_accepted": "s-auto", "pending_review": "s-review", "quarantined": "s-quar",
        "approved": "s-appr", "rejected": "s-rej", "corrected": "s-appr"}
# plain-language status names (shown to users instead of raw codes)
STATUS_LABEL = {"auto_accepted": "high confidence", "pending_review": "needs review",
                "quarantined": "set aside", "approved": "approved", "rejected": "rejected",
                "corrected": "corrected"}
ECON_NAME = dict(ECONOMY_UN_NAME)          # never hardcode: the enum is the source of truth
# "Singapore, Australia and Malaysia" for prose, derived so the copy cannot go stale
_ECON_PROSE = ", ".join(list(ECON_NAME.values())[:-1]) + " and " + list(ECON_NAME.values())[-1]


def vcolor(c: float) -> str:
    if c >= settings.conf_auto_accept:
        return "var(--good)"
    if c >= settings.conf_review_floor:
        return "var(--warn)"
    return "var(--bad)"


def vband(c: float) -> str:
    if c >= settings.conf_auto_accept:
        return "high confidence"
    if c >= settings.conf_review_floor:
        return "needs a check"
    return "low confidence"


def verdict_html(c: float) -> str:
    return (f'<div class="verdict" style="--c:{vcolor(c)}"><div class="vbar"><i style="width:{int(c*100)}%"></i></div>'
            f'<span class="vnum">{c:.2f}</span></div>'
            f'<div class="vtag" style="text-align:right">{vband(c)}</div>')


def seal_html(s: str) -> str:
    return f'<span class="seal {SEAL.get(s, "s-review")}">{STATUS_LABEL.get(s, s.replace("_", " "))}</span>'


def tip_html(trigger: str, inner: str, right: bool = False, plain: str = "") -> str:
    """A hover tooltip: `trigger` text + a small ? badge that reveals `inner` on hover.
    `plain` is a text-only fallback set as the native title attribute (never clipped)."""
    cls = "tip right" if right else "tip"
    t = f' title="{plain}"' if plain else ""
    return (f'<span class="{cls}"{t}>{trigger}<span class="tq">?</span>'
            f'<span class="tipbox">{inner}</span></span>')


def _cutoff_tip_inner() -> str:
    """Explains the 0.60 / 0.85 confidence cut-offs and why results are banded."""
    a, r = settings.conf_auto_accept, settings.conf_review_floor
    return (
        '<div class="thead"><b>How results are sorted by confidence</b></div>'
        'Every result gets a 0&ndash;1 confidence score, then falls into one band:'
        f'<div class="row"><span class="k"><span class="d" style="background:var(--good)"></span>'
        f'<b>Accept</b> &mdash; signals agree, no human check needed</span><span class="w">&ge; {a:.2f}</span></div>'
        f'<div class="row"><span class="k"><span class="d" style="background:var(--warn)"></span>'
        f'<b>Review</b> &mdash; a real but imperfect match; a person should glance</span>'
        f'<span class="w">{r:.2f}&ndash;{a:.2f}</span></div>'
        f'<div class="row"><span class="k"><span class="d" style="background:var(--bad)"></span>'
        f'<b>Set aside</b> &mdash; too weak to trust; kept out of the submission</span>'
        f'<span class="w">&lt; {r:.2f}</span></div>'
        '<div class="note">The score is a weighted blend of four signals (open any result&rsquo;s '
        '<b>Details</b> to see the breakdown). The cut-offs are deliberately conservative, so only '
        'strong, well-grounded matches auto-accept &mdash; both are tunable in <span class="mono">.env</span>.</div>'
    )


def _formula_tip_inner() -> str:
    """Explains how the confidence score is built and why the weights are set as they are."""
    return (
        '<div class="thead"><b>How the confidence score is built</b></div>'
        'A transparent, weighted blend of four auditable signals &mdash; each stored on the result:'
        '<div class="row"><span class="k"><b>Legal fit</b> &mdash; does the text actually satisfy the '
        'indicator&rsquo;s legal test?</span><span class="w">0.40</span></div>'
        '<div class="row"><span class="k"><b>Search match</b> &mdash; how strongly search surfaced this '
        'provision</span><span class="w">0.25</span></div>'
        '<div class="row"><span class="k"><b>Quote grounding</b> &mdash; is the quoted snippet really in the '
        'source text?</span><span class="w">0.20</span></div>'
        '<div class="row"><span class="k"><b>Scope fit</b> &mdash; national vs sector-specific</span>'
        '<span class="w">0.15</span></div>'
        '<span class="frm">final = 0.40&middot;legal + 0.25&middot;search + 0.20&middot;quote + 0.15&middot;scope</span>'
        '<div><b>Why these weights:</b> legal fit weighs most because whether the provision meets the legal '
        'test is the core question; quote grounding is a strong anti-hallucination guard (the snippet must '
        'appear verbatim in the source).</div>'
        '<div class="note"><b>Safety caps:</b> a scope mismatch caps the score at 0.55 (it can never '
        'auto-accept); a snippet with no on-topic vocabulary caps at 0.45 (likely off-topic).</div>'
    )


def is_no_evidence(m) -> bool:
    """Placeholder rows the pipeline writes for an indicator with no submittable finding.
    These carry confidence 0.0 but review_status=auto_accepted (a *confident negative*),
    so the normal traffic-light card renders a contradiction — render them differently."""
    return (m.verbatim_snippet or "").strip().startswith("No evidence") or m.law_name == "No provision found"


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def no_evidence_card_html(m) -> str:
    """A muted 'we searched, found nothing' card — no confidence bar, no NEW tag, no
    law link presented as evidence. Just: which indicator, and where we looked."""
    searched = (f'<div class="searched">Searched · '
                f'<a href="{m.source_url}" target="_blank">{_host(m.source_url)}</a></div>'
                if m.source_url else "")
    return (
        '<div class="vt-card empty">'
        f'<div class="docket"><b>{m.indicator_id}</b><span>Pillar {m.pillar}</span></div>'
        f'<div><div class="empty-ttl">No relevant law found</div>'
        f'<div class="empty-sub">The official portal was searched for {m.economy.value}; '
        f'no active provision matched this indicator.</div>{searched}</div>'
        '<div><span class="seal s-none">none found</span></div>'
        '</div>'
    )


# RDTII Raw Score → a plain tier word describing the 0=simplified … 1=heavily-regulated scale.
def _score_tier(s: float) -> str:
    return "heavy" if s >= 1.0 else ("partial" if s >= 0.5 else "light")


def _score_num(s: float) -> str:
    return str(int(s)) if float(s).is_integer() else f"{s:g}"


def score_stamp_html(s: float | None, mini: bool = False) -> str:
    """The RDTII raw-score chip (neutral grey, not the confidence traffic-light)."""
    if s is None:
        return ""
    pct = int(float(s) * 100)
    cls = "stamp mini" if mini else "stamp"
    if mini:
        return (f'<span class="{cls}"><span class="pie" style="--p:{pct}%"></span>'
                f'<span class="sc-num">{_score_num(s)}</span></span>')
    return (f'<div class="{cls}"><span class="pie" style="--p:{pct}%"></span>'
            f'<span><span class="sc-cap">RDTII score</span>'
            f'<span class="sc-num">{_score_num(s)}</span> '
            f'<span class="sc-tier">{_score_tier(s)}</span></span></div>')


def scorecard_html(mappings) -> str:
    """The indicator-level roll-up: one score per indicator. Empty when scoring did not run."""
    from backend.pipeline.scoring import aggregate_indicator_scores
    agg = aggregate_indicator_scores(mappings)
    if not agg:
        return ""

    def _num(ind):  # "P6-I1" -> "6.1" for display
        try:
            p, i = ind.replace("P", "").split("-I"); return f"{p}.{i}"
        except ValueError:
            return ind

    tiles = []
    for ind in sorted(agg, key=_num):
        info = agg[ind]
        sc = info["score"]
        pct = int(float(sc) * 100)
        tiles.append(
            f'<div class="sc-tile" title="{info["n_measures"]} measure(s) — {info["basis"]}">'
            f'<span class="ind">Indicator {_num(ind)}</span>'
            f'<span class="scrow"><span class="pie" style="--p:{pct}%"></span>'
            f'<span class="scv">{_score_num(sc)}</span></span>'
            f'<span class="meta">{info["n_measures"]} measure{"s" if info["n_measures"] != 1 else ""}</span></div>'
        )
    return ('<div class="kicker" style="margin:.2rem 0 .5rem">RDTII score by indicator '
            '<span class="muted">(one score per indicator, 0–1)</span></div>'
            '<div class="scorecard">' + "".join(tiles) + "</div>")


def ocr_forensics_html(reports) -> str:
    """Text-extraction quality panel — shows how well scanned PDFs were read. Each scanned
    document shows its engine, mean confidence, and the measured character-error-rate (CER),
    stamped PASS (< 5%) or OVER 5%. Empty when no scanned document was processed."""
    used = [r for r in (reports or []) if r.ocr_used]
    if not used:
        return ""
    measured = [r for r in used if r.cer is not None]
    worst = max((r.cer for r in measured), default=None)
    if worst is None:
        hk, hv, hc = "read from the text layer", "no scans to correct", "var(--ink-faint)"
    elif worst < 0.05:
        hk, hv, hc = "error rate under 5% — good", f"worst {worst*100:.2f}%", "var(--good)"
    else:
        hk, hv, hc = "error rate over 5% — check", f"worst {worst*100:.2f}%", "var(--bad)"

    rows = ""
    for r in used:
        conf = r.mean_confidence
        conf_pct = int(conf * 100) if conf is not None else 0
        conf_lbl = f"{conf*100:.1f}%" if conf is not None else "—"
        if r.cer is None:
            cer_num = '<span class="ocr-cer" style="--c:var(--ink-faint)">—</span>'
            stamp = '<span class="ocr-stamp none">no scan measured</span>'
        else:
            ok = bool(r.cer_under_5pct)
            c = "var(--good)" if ok else "var(--bad)"
            cer_num = f'<span class="ocr-cer" style="--c:{c}">{r.cer*100:.2f}<small>%</small></span>'
            stamp = (f'<span class="ocr-stamp {"pass" if ok else "fail"}">'
                     f'{"under 5% — pass" if ok else "over 5%"}</span>')
        rows += (
            '<div class="ocr-row">'
            f'<div class="ocr-doc"><div class="ttl">{r.title}</div>'
            f'<div class="meta">{r.provider} · {r.fmt} · {r.pages} pages</div></div>'
            f'<div class="ocr-conf"><div class="cap">Reading confidence</div>'
            f'<div class="track"><i style="width:{conf_pct}%"></i></div>'
            f'<div class="cval">{conf_lbl}</div></div>'
            f'<div class="ocr-verdict"><div class="cap">Character error rate</div>'
            f'{cer_num}{stamp}</div>'
            '</div>'
        )
    return (
        '<div class="ocr-forensics">'
        '<div class="ocr-head"><div class="kicker">Text-extraction quality '
        '<span class="muted">(how well scanned PDFs were read)</span></div>'
        f'<div class="ocr-headline" style="--c:{hc}"><span class="hv">{hv}</span>'
        f'<span class="hk">{hk}</span></div></div>'
        f'{rows}</div>'
    )


def _esc(s: str) -> str:
    return _html_mod.escape(str(s), quote=True)


_SIGNAL_LABEL = {"retrieval_score": "search match", "legal_match": "legal fit",
                 "snippet_grounding": "quote grounding", "scope_alignment": "scope fit"}


def _ocr_language_note(economy_code, ocr_name: str) -> str:
    """What the pipeline will ACTUALLY load for this country.

    The engine alone does not determine the result — the per-script recognition model does,
    so a card that named only the engine would claim a choice the run may not honour.
    """
    try:
        from backend.providers.ocr_languages import is_validated, ocr_code, profile_for
        code = economy_code.value if hasattr(economy_code, "value") else str(economy_code)
        prof, model = profile_for(code), ocr_code(ocr_name, code)
        if model:
            msg = (f"For {ECON_NAME.get(code, code)} this reads <b>{prof.script}</b> using the "
                   f"<code>{model}</code> recognition model.")
            if not is_validated(code):
                msg += " Accuracy for that script is <b>not yet validated</b> by our tests."
            return msg
        best = prof.preferred[0] if prof.preferred else "another engine"
        return (f"This engine has <b>no model</b> for {prof.script}, which "
                f"{ECON_NAME.get(code, code)} is written in. Recommended: <b>{best}</b>.")
    except Exception:  # noqa: BLE001 — an advisory line must never break the screen
        return ""



def evidence_panel_html(cell_key: str | None, mappings) -> str:
    """The evidence for one matrix cell, rendered beside the matrix.

    Deliberately leads with the indicator's own legal test and then the verbatim quote:
    that ordering lets a policy researcher judge the mapping themselves instead of
    taking the confidence number on trust. The number comes last, broken into the four
    signals that produced it.
    """
    m = None
    if cell_key and "|" in cell_key:
        law, _, ind = cell_key.partition("|")
        m = next((x for x in mappings if x.law_name == law and x.indicator_id == ind), None)
    if m is None:
        return ('<div class="evp empty"><div class="nofind">Press a cell in the matrix to read '
                'the law behind it — the exact quote, why it was mapped there, and how '
                'confident the system is.</div></div>')

    ind = get_indicator(m.indicator_id)
    head = (f'<div class="evhead"><span class="evid">{matrix.num(m.indicator_id)}</span>'
            f'{seal_html(m.review_status.value)}</div>')

    if is_no_evidence(m):
        where = (f'<a class="evlink" href="{m.source_url}" target="_blank">'
                 f'Searched · {_host(m.source_url)}</a>') if m.source_url else ""
        return (f'<div class="evp empty">{head}'
                f'<h4>No relevant law found</h4>'
                f'<div class="evcite">{m.economy.value} · Pillar {m.pillar}</div>'
                f'<div class="test"><b>{matrix.num(m.indicator_id)} '
                f'{_esc(ind.title) if ind else ""} — the legal test</b>'
                f'{_esc(ind.legal_test) if ind else ""}</div>'
                f'<div class="nofind">The official portal was searched and no active provision '
                f'matched this test. It ships in the submission file as an explicit '
                f'“no evidence” row, so the indicator is never left blank.</div>{where}</div>')

    cb = m.confidence.model_dump()
    bars = "".join(
        f'<div class="bd"><div class="lab">{_SIGNAL_LABEL[k]}</div>'
        f'<div class="track"><i style="width:{int(float(cb[k]) * 100)}%"></i></div>'
        f'<div class="val">{float(cb[k]):.2f}</div></div>'
        for k in ("legal_match", "retrieval_score", "snippet_grounding", "scope_alignment")
        if k in cb)
    tone = vcolor(m.confidence_score)
    bars += (f'<div class="bd tot"><div class="lab">Confidence</div>'
             f'<div class="track"><i style="width:{int(m.confidence_score * 100)}%;'
             f'background:{tone}"></i></div>'
             f'<div class="val">{m.confidence_score:.2f}</div></div>')

    score = (score_stamp_html(m.raw_score, mini=True) + " ") if m.raw_score is not None else ""
    flag = (f'<div class="why" style="color:var(--flag)">Sector-flagged · {_esc(m.scope_flag)} '
            f'— capped so a sector-specific rule is not auto-accepted.</div>'
            if m.scope_flag else "")
    return (
        f'<div class="evp">{head}'
        f'<h4>{_esc(m.law_name)}</h4>'
        f'<div class="evcite">{_esc(m.article_section)} · {_esc(m.law_number or m.economy.value)}'
        f' · {_host(m.source_url)}</div>'
        f'<div class="test"><b>{matrix.num(m.indicator_id)} {_esc(ind.title) if ind else ""}'
        f' — the legal test</b>{_esc(ind.legal_test) if ind else ""}</div>'
        f'<blockquote>{_esc(m.verbatim_snippet)}</blockquote>'
        f'<p class="why"><b>Why this mapping.</b> {_esc(m.mapping_rationale)}</p>{flag}'
        f'<div class="bars">{bars}</div>'
        f'<div style="margin-top:.7rem">{score}</div>'
        f'<a class="evlink" href="{m.source_url}" target="_blank">{m.source_url}</a>'
        f'</div>')


def indicator_glossary_html(pillar: int) -> str:
    """'What we're looking for' — the legal test for every indicator in the chosen pillar,
    so a researcher can read this WHILE a run is in progress instead of only after. Useful,
    not filler: by the time results appear, the reader already knows how to judge them."""
    items = ""
    for ind in get_indicators(pillar):
        num = ind.indicator_id.replace("P", "").replace("-I", ".")
        items += (
            '<div class="glossary-item">'
            f'<div><span class="gi-id">{num}</span><span class="gi-title">{_esc(ind.title)}</span></div>'
            f'<div class="gi-desc">{_esc(ind.description)}</div>'
            '</div>'
        )
    return (
        '<div class="waitpanel"><div class="wp-head">While you wait — what this pillar looks for</div>'
        f'<div class="muted" style="margin-bottom:.4rem">The legal test behind each indicator in '
        f'Pillar {pillar}, so you can judge results as soon as they appear.</div>'
        f'{items}</div>'
    )


def _secret(name: str, fallback: str = "") -> str:
    """Read a secret from st.secrets (deployed app) → falling back to env/.env."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return fallback


# ── header ─────────────────────────────────────────────────────────────────
# ONE aligned bar: brand on the left, actions on the right, vertically centred — then a
# single quiet line underneath carrying the strapline and the confidence bands. The old
# layout stacked three separate strips (a floating button row, then a logo row, then the
# strapline), which is what made the top of the app look cluttered.
_a, _r = settings.conf_auto_accept, settings.conf_review_floor
_bands = (f'<span style="color:var(--good)">&ge;{_a:.2f} accept</span> &middot; '
          f'<span style="color:var(--warn)">{_r:.2f}&ndash;{_a:.2f} review</span> &middot; '
          f'<span style="color:var(--bad)">&lt;{_r:.2f} set aside</span>')
_bands_plain = (f"Accept ≥{_a:.2f} · Review {_r:.2f}–{_a:.2f} · Set aside <{_r:.2f}. "
                "Confidence = weighted blend of 4 signals. Hover for details.")

# Brand left, ONE menu right. The white-paper link, the theme switch and sign-out all
# live inside that menu now — three separate top-right buttons plus Streamlit's own ⋮
# (which held a duplicate theme switch) was four competing controls for the same corner.
_brand_col, _act_col = st.columns([3.4, 1.0], vertical_alignment="center")
with _brand_col:
    st.markdown(f'<div class="vt-brand">{logo_html()}</div>', unsafe_allow_html=True)
with _act_col:
    auth_ui.account_control(USER)

st.markdown(
    '<div class="masthead"><div class="subrow">'
    '<div class="strap">Find and map data-regulation laws for UN ESCAP RDTII 2.1 &middot; '
    f'{_ECON_PROSE}</div>'
    f'<div class="edition">{tip_html(_bands, _cutoff_tip_inner(), right=True, plain=_bands_plain)}</div>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── run settings ───────────────────────────────────────────────────────────
# There is no sidebar. Every control a researcher touches lives on the main screen, where
# it can be as large and as self-explanatory as it needs to be; this block only READS what
# those controls left in the session. A widget here as well as there would be two widgets
# writing one choice, which is exactly how the theme toggle used to drift out of step.
_ECON_CODES = [e.value for e in Economy]
if st.session_state.get("economy") not in _ECON_CODES:
    st.session_state["economy"] = _ECON_CODES[0]
economy = st.session_state["economy"]

if st.session_state.get("pillar") not in (6, 7):
    st.session_state["pillar"] = 6
pillar = st.session_state["pillar"]
pillars = [pillar]

ocr_choice = st.session_state.setdefault("ocr_provider", settings.ocr_provider)
if ocr_choice not in reg.OCR_PROVIDERS:
    ocr_choice = st.session_state["ocr_provider"] = settings.ocr_provider
_llm_default = (settings.llm_provider if settings.llm_provider in reg.LLM_PROVIDERS
                else reg.LLM_PROVIDERS[0])
llm_choice = st.session_state.setdefault("llm_provider", _llm_default)
if llm_choice not in reg.LLM_PROVIDERS:
    llm_choice = st.session_state["llm_provider"] = _llm_default
llm_model = st.session_state.get("llm_model")
llm_key = st.session_state.get("llm_key")

use_samples = st.session_state.get("use_samples", False)
fresh_run = st.session_state.get("fresh_run", False)
scoring_on = st.session_state.get("scoring_on", settings.scoring_enabled)
top_k = 5   # grade-all ignores top_k on small corpora; large crawls scale it internally

# The Run button sets a flag and reruns rather than running inline: the controls must have
# been drawn (and their values committed to the session) before the pipeline reads them.
run_clicked = st.session_state.pop("run_requested", False)

# scoped to the signed-in account, so one researcher never sees another's history
prev = db.list_runs(user_id=USER.user_id, limit=200)


def _run_label(rid: str) -> str:
    if rid == "—":
        return "—"
    r = next((x for x in prev if x["run_id"] == rid), None)
    if not r:
        return rid
    econ = ECON_NAME.get(r["economy"], r["economy"] or "?")
    when = (r["started_at"] or "")[:16].replace("T", " ")
    return f"{econ} · {when}"


def past_run_picker(key: str, label: str = "Open a past analysis") -> None:
    """One control, usable from either screen; selecting a run opens it immediately."""
    if not prev:
        st.caption("No past analyses yet — the ones you run are saved here.")
        return
    chosen = st.selectbox(label, ["—"] + [r["run_id"] for r in prev],
                          format_func=_run_label, key=key, label_visibility="collapsed")
    if chosen and chosen != "—" and chosen != st.session_state.get("run_id"):
        st.session_state["run_id"] = chosen
        st.rerun()


# ── run / load state ─────────────────────────────────────────────────────
if run_clicked and pillars:
    # Run the pipeline in a background thread so the main script thread stays free to keep
    # redrawing "while you wait" panels every ~0.25s — the log callback only ever pushes onto a
    # thread-safe queue (never calls into Streamlit directly, including from the pipeline's own
    # internal thread pools for extraction/mapping), so nothing here needs a lock.
    log_q: "queue.Queue[str]" = queue.Queue()
    outcome: dict = {}

    def log(m):
        log_q.put(m)

    def _worker():
        try:
            outcome["result"] = run_pipeline(
                Economy(economy), pillars, use_samples=use_samples, top_k=top_k, log=log,
                ocr_provider=ocr_choice, llm_provider=llm_choice,
                llm_model=llm_model or None, llm_api_key=llm_key or None,
                scoring_enabled=scoring_on, use_result_cache=not fresh_run)
        except Exception as e:  # noqa: BLE001 — surfaced in the main thread below
            outcome["error"] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    # The run is shown as work, not as a log: five stages, four counters, and one plain
    # sentence about what is happening right now. The pipeline's own log still runs, into
    # the collapsed expander below, because a technical reviewer does need it.
    theme.inject_style(runview.CSS)
    rv = runview.new_state()
    track_box = st.empty()
    stream_box = st.empty()
    track_box.markdown(runview.track_html(rv), unsafe_allow_html=True)
    stream_box.markdown(runview.streams_html(rv), unsafe_allow_html=True)
    st.markdown(indicator_glossary_html(pillar), unsafe_allow_html=True)

    with st.status("Technical log — the pipeline's own output", expanded=False) as status:
        import time as _time
        while True:
            drained = False
            while True:
                try:
                    m = log_q.get_nowait()
                except queue.Empty:
                    break
                drained = True
                status.write(m)
                runview.absorb(rv, m)
            if drained:
                track_box.markdown(runview.track_html(rv), unsafe_allow_html=True)
                stream_box.markdown(runview.streams_html(rv), unsafe_allow_html=True)
            if not thread.is_alive() and log_q.empty():
                break
            _time.sleep(0.25)
        thread.join()

        if "error" in outcome:
            rv["now"] = "The run stopped early"
            rv["sub"] = "the error is shown below; the technical log has the detail"
            track_box.markdown(runview.track_html(rv), unsafe_allow_html=True)
            status.update(label="Technical log — the run failed here", state="error")
            raise outcome["error"]

        result = outcome["result"]
        # attribute the run to this account so it shows up in their history
        db.claim_run(result.meta.run_id, USER.user_id)
        export_csv(result.mappings, result.meta.run_id)
        export_json(result)
        if any(m.raw_score is not None for m in result.mappings):
            export_scored_csv(result.mappings, result.meta.run_id)
        status.update(label=f"Technical log · {result.meta.run_id}", state="complete")
    track_box.empty()
    stream_box.empty()
    st.session_state["run_id"] = result.meta.run_id
run_id = st.session_state.get("run_id")
if not run_id:
    st.markdown(
        '<div class="welcome">'
        '<h3>Welcome — let\'s find the law</h3>'
        '<p>VeriTrade searches official government websites, reads the documents (including scanned '
        'PDFs), and maps each relevant law to the RDTII indicators — with the exact quote and a link '
        'to the source. Follow three steps in the panel on the left.</p>'
        '<div class="steps">'
        '<div class="step"><div class="n">1</div><div class="t">Choose a country</div>'
        f'<div class="d">{_ECON_PROSE}.</div></div>'
        '<div class="step"><div class="n">2</div><div class="t">Choose a pillar</div>'
        '<div class="d">Pillar 6 — cross-border data rules, or Pillar 7 — data protection &amp; cybersecurity.</div></div>'
        '<div class="step"><div class="n">3</div><div class="t">Press “Run analysis”</div>'
        '<div class="d">Results appear here in a few minutes. You can also reopen a past analysis.</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    # The globe is the headline way in: spin it, click a marker (or a name) to choose the
    # economy. It writes the same session_state the sidebar select reads, so the two stay
    # in step whichever one you touch.
    st.markdown('<div class="kicker" style="margin:1.4rem 0 .5rem">Choose an economy '
                '<span class="muted">— spin the globe, or pick a name</span></div>',
                unsafe_allow_html=True)
    _picked = geo.country_picker(selected=st.session_state.get("economy"), key="geo_home")
    if _picked and _picked != st.session_state.get("economy"):
        st.session_state["economy"] = _picked
        st.rerun()

    # ── pillar as two large choice cards, not a radio ────────────────────────
    # The two pillars are the second real decision, so they get real estate and the
    # indicators they cover shown up front — a dropdown label could never carry that.
    st.markdown('<div class="kicker" style="margin:1.6rem 0 .5rem">Choose a pillar '
                '<span class="muted">— what kind of rule are you looking for?</span></div>',
                unsafe_allow_html=True)
    theme.inject_style(_PILLAR_CARD_CSS)
    _pc = st.columns(2, gap="medium")
    for _i, (_pn, _title, _sub, _inds) in enumerate([
        (6, "Cross-border data rules",
         "Can data leave the country, and on what conditions?",
         ["Ban &amp; local processing", "Local storage", "Infrastructure", "Conditional flow"]),
        (7, "Data protection &amp; cybersecurity",
         "How personal data must be protected at home.",
         ["Comprehensive framework", "Dedicated cybersecurity", "Minimum retention",
          "DPO / DPIA", "Government access"]),
    ]):
        with _pc[_i]:
            _on = st.session_state.get("pillar") == _pn
            st.markdown(
                f'<div class="pcard {"on" if _on else ""}">'
                f'<div class="pnum">Pillar {_pn}</div>'
                f'<div class="ptitle">{_title}</div>'
                f'<div class="psub">{_sub}</div>'
                f'<div class="plist">' +
                "".join(f'<span>{x}</span>' for x in _inds) +
                f'</div><div class="pfoot">{len(_inds)} indicators</div></div>',
                unsafe_allow_html=True)
            if st.button(("Selected" if _on else f"Choose Pillar {_pn}"),
                         key=f"pick_pillar_{_pn}", width="stretch",
                         type=("primary" if _on else "secondary"), disabled=_on):
                st.session_state["pillar"] = _pn
                st.rerun()

    # Step 3 on the main surface, not buried in a sidebar expander: swapping the reader or
    # the model is a scored requirement, so it gets real estate and every option explains
    # itself.
    st.markdown('<div class="kicker" style="margin:1.8rem 0 .5rem">Choose the engines '
                '<span class="muted">— or leave the defaults, they are already sensible'
                '</span></div>', unsafe_allow_html=True)
    enginebench.render(st.session_state.get("ocr_provider", settings.ocr_provider),
                       st.session_state.get("llm_provider", settings.llm_provider),
                       scope="home", ocr_note=_ocr_language_note(economy, ocr_choice))

    # ── run ────────────────────────────────────────────────────────────────
    # The last thing on the page, after the three choices, because that is the order the
    # work happens in. Everything here has a working default, so a first-time user can
    # ignore all of it and press the button.
    st.markdown('<div class="kicker" style="margin:1.8rem 0 .5rem">Run the analysis '
                '<span class="muted">— this takes a few minutes on a live search</span>'
                '</div>', unsafe_allow_html=True)
    theme.inject_style(_RUNBAR_CSS)
    _rc = st.columns([1.15, 1, 1], gap="medium")
    with _rc[0]:
        st.markdown('<div class="rbttl">Where to look</div>', unsafe_allow_html=True)
        _LIVE = "Live search of the official portals"
        _SAMPLE = "Bundled offline examples (fast, no internet)"
        _mode = st.radio("Where to look", [_LIVE, _SAMPLE],
                         index=1 if st.session_state.get("use_samples") else 0,
                         label_visibility="collapsed",
                         help="The live search crawls the government portals — this is the "
                              "scored path. The offline examples are a reproducible fallback "
                              "for when a portal is down.")
        st.session_state["use_samples"] = _mode == _SAMPLE
    with _rc[1]:
        st.markdown('<div class="rbttl">Options</div>', unsafe_allow_html=True)
        st.session_state["fresh_run"] = st.checkbox(
            "Search again, ignore the saved result", value=st.session_state.get("fresh_run", False),
            help="Identical inputs normally return the saved result instantly.")
        st.session_state["scoring_on"] = st.checkbox(
            "Also rate how restrictive each law is",
            value=st.session_state.get("scoring_on", settings.scoring_enabled),
            help="Adds an RDTII restrictiveness score (0 / 0.5 / 1) per law. One extra AI call "
                 "each. Never written to the submission file.")
    with _rc[2]:
        st.markdown(f'<div class="rbttl">Ready</div>'
                    f'<div class="rbsum">{ECON_NAME.get(economy, economy)} · Pillar {pillar}<br>'
                    f'<span>{enginebench.short_name("ocr", ocr_choice)} · '
                    f'{enginebench.short_name("llm", llm_choice)}'
                    f'{" · " + llm_model if llm_model else ""}</span></div>',
                    unsafe_allow_html=True)
        if st.button("Run analysis", type="primary", width="stretch", key="run_home"):
            st.session_state["run_requested"] = True
            st.rerun()

    if prev:
        st.markdown('<div class="kicker" style="margin:1.6rem 0 .4rem">Or reopen a past '
                    'analysis</div>', unsafe_allow_html=True)
        _pc = st.columns([1, 2])
        with _pc[0]:
            past_run_picker("prev_home")

    site_footer()
    st.stop()

meta = db.get_run(run_id)
mappings = db.list_mappings(run_id=run_id)
if not mappings:
    st.warning("No results were recorded for this analysis.")
    st.stop()

# ── summary strip ─────────────────────────────────────────────────────────
# Count "no provision found" placeholders on their own axis — they are confident
# negatives, not high-confidence evidence, so they get a neutral "Not found" cell
# and are kept OUT of the High-confidence count.
real = [m for m in mappings if not is_no_evidence(m)]


def _status_count(*statuses) -> int:
    return sum(1 for m in real if m.review_status.value in statuses)


high_conf = _status_count("auto_accepted", "approved", "corrected")
review_n = _status_count("pending_review")
quar_n = _status_count("quarantined")
not_found_n = sum(1 for m in mappings if is_no_evidence(m))
cells = [
    ("Country", ECON_NAME.get(meta.economy.value, "—") if meta else "—", ""),
    ("Documents found", meta.docs_discovered if meta else "—", ""),
    ("Provisions read", meta.provisions_extracted if meta else "—", ""),
    ("High confidence", high_conf, "fo"),
    ("Needs review", review_n, "oc"),
]
if not_found_n:
    cells.append(("Not found", not_found_n, ""))   # neutral — searched, nothing matched
if quar_n:                                          # only show when something is actually set aside
    cells.append(("Set aside", quar_n, "ox"))
st.markdown(
    '<div class="ledger">' + "".join(
        f'<div class="cell"><div class="cap">{c}</div><div class="num {cls}">{v}</div></div>'
        for c, v, cls in cells
    ) + "</div>",
    unsafe_allow_html=True,
)

# confidence legend — plain language, so a non-technical reader knows what the colours mean
st.markdown(
    '<div class="legend">'
    '<span class="muted" style="font-weight:600;color:var(--ink)">What the colours mean:</span>'
    '<span class="item"><span class="dot g"></span><b>Green</b>&nbsp;= high confidence, accepted automatically</span>'
    '<span class="item"><span class="dot a"></span><b>Amber</b>&nbsp;= worth a human check</span>'
    '<span class="item"><span class="dot r"></span><b>Red</b>&nbsp;= low confidence, set aside</span>'
    '</div>',
    unsafe_allow_html=True,
)

# text-extraction quality — only when a scanned/OCR document was processed
_ocr_panel = ocr_forensics_html(meta.ocr_reports if meta else [])
if _ocr_panel:
    st.markdown(_ocr_panel, unsafe_allow_html=True)

# RDTII indicator scorecard — only when the scoring layer ran
_scorecard = scorecard_html(mappings)
if _scorecard:
    st.markdown(_scorecard, unsafe_allow_html=True)

# The run header carries what the sidebar used to: which run this is, and the way out of it.
theme.inject_style(_RUNBAR_CSS)
_hb = st.columns([2.2, 1.4, 1], gap="medium")
with _hb[0]:
    _when = (meta.started_at or "")[:16].replace("T", " ") if meta else ""
    st.markdown(f'<div class="rbsum big">{ECON_NAME.get(meta.economy.value, "—") if meta else "—"}'
                f' · Pillar {", ".join(str(p) for p in sorted({m.pillar for m in mappings}))}'
                f'<br><span>{_when} · {len(mappings)} results · run {run_id}</span></div>',
                unsafe_allow_html=True)
with _hb[1]:
    past_run_picker("prev_results", "Open another analysis")
with _hb[2]:
    if st.button("New analysis", width="stretch", key="new_run"):
        st.session_state.pop("run_id", None)
        st.rerun()

tab_ev, tab_review, tab_audit, tab_export, tab_eng = st.tabs(
    ["Results", f"Needs review · {len(workflow.queue(run_id))}", "Details", "Download", "Engines"]
)

# ── results ────────────────────────────────────────────────────────────────
with tab_ev:
    # ── filters ───────────────────────────────────────────────────────────
    # Kept, but demoted: the matrix answers most questions the filters used to,
    # so they sit on one quiet row above it rather than heading the screen.
    f1, f2, f3 = st.columns([1, 1, 1])
    pillar_f = f1.multiselect("Pillar", sorted({m.pillar for m in mappings}),
                              default=sorted({m.pillar for m in mappings}),
                              format_func=lambda p: f"Pillar {p}")
    status_f = f2.multiselect("Status", sorted({m.review_status.value for m in mappings}),
                              default=sorted({m.review_status.value for m in mappings}),
                              format_func=lambda s: STATUS_LABEL.get(s, s.replace("_", " ")))
    only_flag = f3.toggle("Sector-flagged only", value=False,
                          help="Show only results flagged as a sector-specific (not general) rule.")
    view = [m for m in mappings if m.pillar in pillar_f and m.review_status.value in status_f
            and (not only_flag or m.scope_flag)]

    theme.inject_style(_EVIDENCE_CSS)
    rows = matrix.build_rows(view, is_no_evidence, _host)
    inds = matrix.indicator_columns(sorted({m.pillar for m in mappings}))
    _covered = sum(1 for i in inds
                   if any(r["cells"].get(i["id"], {}).get("s", "n") != "n" for r in rows))
    st.markdown(
        f'<div class="kicker" style="margin:.6rem 0 .1rem">Coverage matrix '
        f'<span class="muted">— {len(rows)} laws · {_covered} of {len(inds)} indicators covered'
        f'</span></div>'
        '<div class="mxhint">Each row is a law found on the official portal; each column is an '
        'RDTII indicator. A filled cell means a provision in that law meets that indicator’s '
        'legal test — press one to read the evidence. An empty column is a gap.</div>',
        unsafe_allow_html=True)

    # Open on the strongest real finding, so the panel is never empty on arrival.
    _real = [m for m in view if not is_no_evidence(m)]
    _default = (f"{max(_real, key=lambda m: m.confidence_score).law_name}|"
                f"{max(_real, key=lambda m: m.confidence_score).indicator_id}") if _real else None

    # Measured, not guessed: the Results column runs ~1050px at a normal window,
    # so this split hands the matrix ~660px — clear of its 624px minimum — and
    # still leaves the evidence panel enough width for a readable quote.
    mcol, ecol = st.columns([2, 1.18], gap="medium")
    with mcol:
        picked = matrix.coverage_matrix(
            rows, inds, selected=st.session_state.get("cell") or _default,
            key=f"mx_{run_id}")
    st.session_state["cell"] = picked or _default

    with ecol:
        st.markdown(evidence_panel_html(picked, view), unsafe_allow_html=True)

    # The column headers are abbreviated to fit; the full official titles go here so the
    # abbreviation never has to carry meaning on its own.
    st.markdown(
        '<div class="mxkey">' + " ".join(
            f'<span><b>{i["num"]}</b> {_esc(i["title"])}</span>' for i in inds) + '</div>',
        unsafe_allow_html=True)

# ── needs review ───────────────────────────────────────────────────────────
with tab_review:
    queue = workflow.queue(run_id)
    if not queue:
        st.markdown('<div class="quote">Nothing to review — no results fell in the amber '
                    '“needs a check” band. You’re all set.</div>', unsafe_allow_html=True)
    for m in queue:
        with st.container(border=True):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1rem">'
                f'<div class="law">{m.indicator_id} &middot; {m.law_name}'
                f'<span class="cite"> — {m.article_section}</span></div></div>'
                f'<div style="display:flex;gap:1rem;align-items:center;margin:.4rem 0 .2rem">'
                f'<div style="max-width:300px;flex:1">{verdict_html(m.confidence_score)}</div>'
                f'{score_stamp_html(m.raw_score, mini=True)}</div>'
                f'<div class="quote">{m.verbatim_snippet}</div>'
                f'<div class="cite">Why this mapping · {m.mapping_rationale}</div>'
                + (f'<div class="cite">Impact · {m.impact}</div>' if m.impact else ""),
                unsafe_allow_html=True,
            )
            note = st.text_input("Note (optional)", key=f"note_{m.mapping_id}",
                                 placeholder="optional — saved to the audit log")
            b = st.columns([1, 1, 1.4, 1])
            if b[0].button("Approve", key=f"ap_{m.mapping_id}", width="stretch"):
                workflow.approve(m.mapping_id, "dashboard", note); st.rerun()
            if b[1].button("Reject", key=f"rj_{m.mapping_id}", width="stretch"):
                workflow.reject(m.mapping_id, "dashboard", note); st.rerun()
            new_ind = b[2].text_input("indicator", value=m.indicator_id, key=f"ci_{m.mapping_id}",
                                      label_visibility="collapsed")
            if b[3].button("Fix indicator", key=f"co_{m.mapping_id}", width="stretch"):
                workflow.correct(m.mapping_id, {"indicator_id": new_ind}, "dashboard", note); st.rerun()

# ── details ────────────────────────────────────────────────────────────────
with tab_audit:
    ids = [f"{m.indicator_id} · {m.law_name[:30]} {m.article_section}" for m in mappings]
    idx = st.selectbox("Pick a result to inspect", range(len(mappings)), format_func=lambda i: ids[i])
    m = mappings[idx]
    if is_no_evidence(m):
        # A no-evidence row has nothing to score or quote — show a clean explanation instead
        # of an all-zero confidence breakdown that reads as a broken result.
        st.markdown(f"### {m.indicator_id} — No relevant law found")
        st.markdown(f'<div class="cite">{m.economy.value} &middot; Pillar {m.pillar}</div>', unsafe_allow_html=True)
        st.markdown('<div class="quote">The official portal was searched for this indicator and no active '
                    'provision matched its legal test. It appears in the submission file as an explicit '
                    '“No evidence” row, so the indicator is never left blank.</div>', unsafe_allow_html=True)
        if m.source_url:
            st.markdown(f'<div class="srcurl">Searched · <a href="{m.source_url}">{_host(m.source_url)}</a></div>',
                        unsafe_allow_html=True)
    else:
        left, right = st.columns([1.3, 1])
        with left:
            st.markdown(f"### {m.indicator_id} — {m.law_name}")
            st.markdown(f'<div class="cite">{m.article_section} &middot; {m.economy.value} &middot; Pillar {m.pillar} '
                        f'&middot; {m.discovery_tag.value}</div>', unsafe_allow_html=True)
            st.markdown('<div class="kicker" style="margin-top:.8rem">Exact quote</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="quote">{m.verbatim_snippet}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="srcurl">Source · <a href="{m.source_url}">{m.source_url}</a></div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="cite" style="margin-top:.6rem">Why this mapping · {m.mapping_rationale}</div>',
                        unsafe_allow_html=True)
            if m.raw_score is not None:
                st.markdown('<div class="kicker" style="margin-top:.9rem">Restrictiveness score</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="display:flex;gap:.8rem;align-items:center">{score_stamp_html(m.raw_score)}'
                            f'<span class="cite">Coverage · {m.coverage or "—"}</span></div>', unsafe_allow_html=True)
                if m.impact:
                    st.markdown(f'<div class="cite" style="margin-top:.5rem">Impact · {m.impact}</div>',
                                unsafe_allow_html=True)
            if m.scope_flag:
                st.markdown(f'<div style="margin-top:.7rem">{seal_html("scope").replace("s-review","s-flag")} '
                            f'<span class="cite">{m.scope_flag} — capped so a sector-specific rule is not auto-accepted.</span></div>',
                            unsafe_allow_html=True)
        with right:
            cb = m.confidence.model_dump()
            _formula_plain = ("Weighted blend: 0.40 legal fit + 0.25 search + 0.20 quote grounding "
                              "+ 0.15 scope. Caps: scope mismatch 0.55, off-topic 0.45.")
            st.markdown('<div class="kicker">' + tip_html("How the confidence was scored",
                        _formula_tip_inner(), right=True, plain=_formula_plain) + '</div>',
                        unsafe_allow_html=True)
            _LAB = {"retrieval_score": "search match", "legal_match": "legal fit",
                    "snippet_grounding": "quote grounding", "scope_alignment": "scope fit"}
            rows = [(k, cb[k]) for k in ("retrieval_score", "legal_match", "snippet_grounding", "scope_alignment")]
            html = ""
            for lab, v in rows:
                html += (f'<div class="bd"><div class="lab">{_LAB.get(lab, lab.replace("_"," "))}</div>'
                         f'<div class="track"><i style="width:{int(float(v)*100)}%"></i></div>'
                         f'<div class="val">{float(v):.2f}</div></div>')
            html += (f'<div class="bd"><div class="lab" style="color:var(--good);font-weight:600">overall</div>'
                     f'<div class="track"><i class="final" style="width:{int(cb["final"]*100)}%"></i></div>'
                     f'<div class="val">{cb["final"]:.2f}</div></div>')
            st.markdown(html, unsafe_allow_html=True)
            st.markdown(f'<div class="muted">{cb["explanation"]}</div>', unsafe_allow_html=True)
            st.markdown('<div class="kicker" style="margin-top:.9rem">Text-reading metrics</div>', unsafe_allow_html=True)
            st.json(m.ocr.model_dump(), expanded=False)
            st.markdown('<div class="kicker">Search log</div>', unsafe_allow_html=True)
            st.code("\n".join(m.retrieval_log) or "—")
            st.markdown(f'<div class="muted">model · {m.model_version}</div>', unsafe_allow_html=True)

# ── download ───────────────────────────────────────────────────────────────
with tab_export:
    result = RunResult(meta=meta, mappings=mappings)
    st.markdown('<div class="quote">The <b>Submission CSV</b> is the official RDTII file (exact template '
                'columns) for the policy reviewer. The <b>Evidence JSON</b> carries the full trace for the '
                'technical reviewer. The <b>Scored CSV</b> adds restrictiveness scores per law (optional).</div>',
                unsafe_allow_html=True)
    sub_only = st.toggle("Submission set only — leave out rejected & set-aside rows", value=True,
                         help="Keeps sector-flagged and low-confidence rows out of the official submission.")
    csv_path = export_csv(mappings, run_id, submission_only=sub_only)
    json_path = export_json(result)
    has_scores = any(m.raw_score is not None for m in mappings)
    scored_path = export_scored_csv(mappings, run_id, submission_only=sub_only) if has_scores else None
    n_rows = sum(1 for ln in Path(csv_path).read_text(encoding="utf-8-sig").splitlines()) - 1
    st.markdown(f'<div class="kicker">{n_rows} rows · {len(SUBMISSION_COLUMNS)} columns</div>', unsafe_allow_html=True)
    cols = st.columns(3 if scored_path else 2)
    cols[0].download_button("⬇  Submission CSV", Path(csv_path).read_bytes(),
                            file_name=Path(csv_path).name, mime="text/csv", width="stretch")
    cols[1].download_button("⬇  Evidence JSON", Path(json_path).read_bytes(),
                            file_name=Path(json_path).name, mime="application/json", width="stretch")
    if scored_path:
        cols[2].download_button("⬇  Scored CSV", Path(scored_path).read_bytes(),
                                file_name=Path(scored_path).name, mime="text/csv", width="stretch")
    st.dataframe(pd.read_csv(csv_path, dtype=str).fillna(""), width="stretch", height=380)

# ── engines ────────────────────────────────────────────────────────────────
with tab_eng:
    st.markdown('<div class="quote">Changing an engine here applies to your <b>next</b> run — '
                'this analysis keeps the engines it was made with, so the two stay comparable '
                'side by side in your history.</div>', unsafe_allow_html=True)
    enginebench.render(st.session_state.get("ocr_provider", settings.ocr_provider),
                       st.session_state.get("llm_provider", settings.llm_provider),
                       scope="tab")

# every screen ends with the site footer, not mid-content
site_footer()
