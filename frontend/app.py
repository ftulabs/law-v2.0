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

import sys
from pathlib import Path

import pandas as pd
import base64

import streamlit as st

# allow `import backend...` when launched via `streamlit run frontend/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings  # noqa: E402
from backend.export import export_csv, export_json, export_scored_csv  # noqa: E402
from backend.pipeline.orchestrator import run_pipeline  # noqa: E402
from backend.providers import registry as reg  # noqa: E402
from backend.review import workflow  # noqa: E402
from backend.schemas import Economy, RunResult, SUBMISSION_COLUMNS  # noqa: E402
from backend.storage import db  # noqa: E402

db.init_db()  # ensure schema exists on fresh mounts (no-op if tables already present)

# ── brand assets (drop files in frontend/assets/ — see ASSETS.md) ──────────
ASSETS = Path(__file__).resolve().parent / "assets"


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


_favicon = _asset("ftu_logo.png", "ftu_logo.webp", "ftu_logo.jpg")
st.set_page_config(page_title="VeriTrade", page_icon=str(_favicon) if _favicon else "⚖", layout="wide")

# ── keyboard guard ─────────────────────────────────────────────────────────
# Streamlit binds BARE single keys on the page — notably "C" = Clear cache and "R" = Rerun.
# When you press Ctrl/Cmd+C to COPY selected text, the "C" keydown also fires Streamlit's
# shortcut, so a "Clear caches?" dialog pops up. This invisible (0-height) component installs a
# capture-phase keydown listener on the PARENT document that stops any Ctrl/Cmd combo from
# reaching Streamlit's global handler — so copy/paste/cut/select-all behave natively again.
# It never calls preventDefault(), so the browser's own clipboard actions still work.
import streamlit.components.v1 as _components  # noqa: E402

_components.html(
    """
    <script>
    (function () {
      var doc = window.parent && window.parent.document;
      if (!doc || doc.__veritradeKbdGuard) return;
      doc.__veritradeKbdGuard = true;
      doc.addEventListener('keydown', function (e) {
        if (e.ctrlKey || e.metaKey) { e.stopImmediatePropagation(); }
      }, true);  // capture phase → runs before Streamlit's listener
    })();
    </script>
    """,
    height=0,
)

# ── theme: the app owns it. A visible toggle (top-right) drives the palette via
#    session_state. Dark (slate) is the default; Light is a clean white sheet. ──
if "dark" not in st.session_state:
    _t0 = getattr(getattr(st.context, "theme", None), "type", None)
    st.session_state["dark"] = (_t0 != "light")
DARK = st.session_state["dark"]

if DARK:
    PALETTE = (
        "--paper:#0b1120; --paper-2:#111a2b; --paper-3:#1a2740;"
        "--ink:#e9eef8; --ink-soft:#a3b0c9; --ink-faint:#6f7d99;"
        "--rule:#26334d; --rule-soft:#1b2740;"
        "--accent:#4f9cff; --accent-ink:#04122b;"
        "--good:#34d399; --warn:#fbbf24; --bad:#f87171;"
        "--appr:#60a5fa; --flag:#c084fc; --gold:#7cc4ff;"
        "--panel:#111a2b; --panel-2:#16233a;"
    )
    APP_BG = "background-color:var(--paper);"
else:
    PALETTE = (
        "--paper:#ffffff; --paper-2:#f5f8fc; --paper-3:#eaeff6;"
        "--ink:#0f172a; --ink-soft:#48566b; --ink-faint:#7a879c;"
        "--rule:#dbe2ec; --rule-soft:#eaeff5;"
        "--accent:#2563eb; --accent-ink:#ffffff;"
        "--good:#15803d; --warn:#b45309; --bad:#dc2626;"
        "--appr:#1d4ed8; --flag:#9333ea; --gold:#2563eb;"
        "--panel:#f7f9fc; --panel-2:#eef3f9;"
    )
    APP_BG = "background-color:var(--paper);"

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
      img.vt-logo, .vt-logo img, .vt-logo svg {{ height:52px !important; width:auto !important;
              max-width:320px; display:block; }}
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
      .masthead {{border-bottom:1px solid var(--rule); padding-bottom:.9rem; margin-bottom:.4rem;}}
      .masthead .row {{display:flex; align-items:center; justify-content:space-between; gap:1rem;}}
      .masthead .strap {{color:var(--ink-soft); font-size:.95rem; margin-top:.35rem;}}
      .masthead .edition {{text-align:right; font-family:'IBM Plex Mono',monospace; font-size:.72rem;
                           color:var(--ink-faint); line-height:1.5; white-space:nowrap;}}

      /* ── summary strip ── */
      .ledger {{display:flex; flex-wrap:wrap; gap:.6rem; margin:1rem 0 .4rem;}}
      .ledger .cell {{flex:1; min-width:120px; padding:.7rem .9rem; border:1px solid var(--rule);
                      border-radius:10px; background:var(--panel);}}
      .ledger .cap {{font-size:.72rem; font-weight:500; color:var(--ink-faint);}}
      .ledger .num {{font-size:1.55rem; font-weight:700; line-height:1.15; margin-top:.15rem;}}
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

      /* buttons — clear, rounded, readable */
      .stButton button {{font-family:'Inter',sans-serif; font-size:.9rem; font-weight:600;
              border-radius:9px; border:1px solid var(--rule); background:var(--panel); color:var(--ink);}}
      .stButton button:hover {{border-color:var(--accent); color:var(--accent);}}
      /* primary action = filled accent, high contrast */
      .stButton button[kind="primary"], .stButton button[data-testid="baseButton-primary"] {{
              background:var(--accent) !important; border-color:var(--accent) !important;
              color:var(--accent-ink) !important; font-weight:700;}}
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
      [data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{ color:var(--ink) !important; font-weight:600; }}
      [data-testid="stNotificationContentInfo"], [data-testid="stStatusWidget"] * {{ color:var(--ink) !important; }}
      .stTextInput input, .stNumberInput input, .stTextArea textarea {{
              color:var(--ink) !important; background:var(--paper) !important;
              border-radius:8px !important; }}
      div[data-baseweb="select"] > div {{ background:var(--paper) !important;
              border-color:var(--rule) !important; border-radius:8px !important; }}
      div[data-baseweb="select"] * {{ color:var(--ink) !important; }}
      [data-baseweb="popover"] > div, [data-baseweb="popover"] div, [data-baseweb="popover"] ul,
      [data-baseweb="menu"], ul[role="listbox"], div[role="listbox"] {{
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
    </style>
    """,
    unsafe_allow_html=True,
)

SEAL = {"auto_accepted": "s-auto", "pending_review": "s-review", "quarantined": "s-quar",
        "approved": "s-appr", "rejected": "s-rej", "corrected": "s-appr"}
# plain-language status names (shown to users instead of raw codes)
STATUS_LABEL = {"auto_accepted": "high confidence", "pending_review": "needs review",
                "quarantined": "set aside", "approved": "approved", "rejected": "rejected",
                "corrected": "corrected"}
ECON_NAME = {"SG": "Singapore", "AU": "Australia", "MY": "Malaysia"}


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


def _secret(name: str, fallback: str = "") -> str:
    """Read a secret from st.secrets (deployed app) → falling back to env/.env."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return fallback


# ── theme toggle (top-right) ───────────────────────────────────────────────
_, _theme_col = st.columns([9, 1])
with _theme_col:
    if st.button("☀ Light" if DARK else "☾ Dark", key="theme_toggle",
                 help="Switch between light and dark", width="stretch"):
        st.session_state["dark"] = not DARK
        st.rerun()

# ── header ─────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="masthead"><div class="row">'
    f'<div>{logo_html()}'
    '<div class="strap">Find and map data-regulation laws for UN ESCAP RDTII 2.1 &middot; '
    'Singapore, Australia, Malaysia</div></div>'
    f'<div class="edition">RDTII 2.1<br>'
    f'auto-accept ≥ {settings.conf_auto_accept:.2f}</div>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── sidebar: simple flow first, advanced settings hidden ───────────────────
with st.sidebar:
    st.markdown('### Run an analysis')

    # Step 1 — country
    st.markdown('<div class="kicker" style="margin:.4rem 0 .1rem">1. Choose a country</div>',
                unsafe_allow_html=True)
    economy = st.selectbox("Country", [e.value for e in Economy], format_func=lambda v: ECON_NAME[v],
                           label_visibility="collapsed")

    # Step 2 — pillar (RDTII's term), with a plain-language explanation
    st.markdown('<div class="kicker" style="margin:.7rem 0 .1rem">2. Choose a pillar (topic)</div>',
                unsafe_allow_html=True)
    _PILLAR_OPT = {
        6: "Pillar 6 — Cross-border data rules (can data leave the country?)",
        7: "Pillar 7 — Data protection & cybersecurity (privacy, DPO, retention, gov access)",
    }
    pillar = st.radio("Pillar", [6, 7], index=0, format_func=lambda p: _PILLAR_OPT[p],
                      label_visibility="collapsed",
                      help="Pick one pillar per run. Pillar 6 covers cross-border data flows and "
                           "localisation; Pillar 7 covers domestic data-protection and cybersecurity.")
    pillars = [pillar]

    # Step 3 — run
    st.markdown('<div class="kicker" style="margin:.7rem 0 .3rem">3. Run</div>', unsafe_allow_html=True)
    run_clicked = st.button("Run analysis", type="primary", width="stretch")
    st.markdown('<div class="prov-note">Uses smart defaults — a live search of the official '
                'government portals. No setup needed.</div>', unsafe_allow_html=True)

    # ── advanced settings (hidden by default; smart defaults handle everything) ──
    with st.expander("Advanced settings", expanded=False):
        # Data source
        st.markdown('<div class="kicker">Where to look</div>', unsafe_allow_html=True)
        _LIVE = "Live search of official portals (recommended)"
        _SAMPLE = "Bundled offline examples (fast, no internet)"
        run_mode = st.radio("Data source", [_LIVE, _SAMPLE], index=0, label_visibility="collapsed",
                            help="Live search crawls the official government portals (the scored path). "
                                 "The offline examples are a fast, reproducible fallback when a portal is down.")
        use_samples = run_mode == _SAMPLE
        fresh_run = st.checkbox("Ignore the saved result and search again", value=False,
                                help="Identical inputs normally return the saved result instantly. "
                                     "Tick this to force a fresh live search.")
        top_k = 5  # grade-all ignores top_k on small corpora; large crawls scale it internally

        st.markdown('<hr class="hr-thin">', unsafe_allow_html=True)
        st.markdown('<div class="kicker">Engines</div>', unsafe_allow_html=True)
        st.markdown('<div class="prov-note">Leave these on the defaults unless you know you need to '
                    'change them.</div>', unsafe_allow_html=True)

        def _ocr_fmt(n):
            return f"{reg.OCR_LABELS[n]}  {'✓' if reg.ocr_availability(n).ready else '⚙'}"

        ocr_choice = st.selectbox("Text reader (OCR)", reg.OCR_PROVIDERS, format_func=_ocr_fmt,
                                  index=reg.OCR_PROVIDERS.index(settings.ocr_provider))
        _oa = reg.ocr_availability(ocr_choice)
        st.markdown(f'<div class="prov-note {"ready" if _oa.ready else ""}">'
                    f'{"✓ ready" if _oa.ready else "⚙ " + _oa.note}</div>', unsafe_allow_html=True)

        def _llm_fmt(n):
            return f"{reg.LLM_LABELS[n]}  {'✓' if reg.llm_availability(n).ready else '⚙'}"

        _llm_index = reg.LLM_PROVIDERS.index(settings.llm_provider) if settings.llm_provider in reg.LLM_PROVIDERS else 0
        llm_choice = st.selectbox("AI model provider", reg.LLM_PROVIDERS, format_func=_llm_fmt, index=_llm_index)
        llm_model, llm_key = None, None
        if llm_choice == "openrouter":
            llm_key = _secret("OPENROUTER_API_KEY", settings.openrouter_api_key)
            _models = reg.OPENROUTER_MODELS
            _idx = _models.index(settings.openrouter_model) if settings.openrouter_model in _models else 0
            llm_model = st.selectbox("Model", _models, index=_idx,
                                     help="Paid models only — DeepSeek V4 Flash (default) is fast and about "
                                          "$0.07 for a full country run. A model that rate-limits fails over "
                                          "to the next paid one.")
            if not llm_key:
                llm_key = st.text_input("OpenRouter API key", type="password",
                                        placeholder="set OPENROUTER_API_KEY in Secrets, or paste here") or None
        elif llm_choice == "local":
            base_url = st.text_input("Base URL", value=settings.local_llm_base_url, key="local_url_in",
                                     help="OpenAI-compatible /v1 — Ollama: http://<lab-host>:11434/v1")
            settings.local_llm_base_url = base_url.strip()
            llm_model = st.text_input("Model name", value=settings.local_llm_model, key="local_model_in",
                                      help="a model your server serves, e.g. llama3.1, qwen2.5:14b")
            llm_key = st.text_input("API key (optional)", type="password", key="local_key_in",
                                    placeholder="leave blank for Ollama") or None
        elif llm_choice != "mock":
            _default_model = settings.anthropic_model if llm_choice == "anthropic" else settings.openai_model
            llm_model = st.text_input("Model name", value=_default_model, key="llm_model_in")
            llm_key = st.text_input("API key", type="password", key="llm_key_in",
                                    placeholder="paste to enable live calls") or None
        _la = reg.llm_availability(llm_choice, api_key=llm_key or None)
        if llm_choice != "mock":
            st.markdown(f'<div class="prov-note {"ready" if _la.ready else ""}">'
                        f'{"✓ ready — live calls enabled" if _la.ready else "⚙ " + _la.note}</div>',
                        unsafe_allow_html=True)
        if (ocr_choice != "mock" and not _oa.ready) or (llm_choice != "mock" and not _la.ready):
            st.markdown('<div class="prov-note">Unavailable engines fall back automatically — '
                        'the run never breaks.</div>', unsafe_allow_html=True)

        st.markdown('<hr class="hr-thin">', unsafe_allow_html=True)
        st.markdown('<div class="kicker">Restrictiveness scoring (optional)</div>', unsafe_allow_html=True)
        scoring_on = st.toggle("Rate each law's restrictiveness (0 / 0.5 / 1)", value=settings.scoring_enabled,
                               help="Adds an RDTII restrictiveness score to each mapped law. One extra AI call "
                                    "per result — off by default keeps the run lean. Never written to the "
                                    "submission file.")

    st.markdown('<hr class="hr-thin">', unsafe_allow_html=True)
    st.markdown('<div class="kicker">Past analyses</div>', unsafe_allow_html=True)
    prev = db.list_runs()
    chosen_prev = st.selectbox("Open a past analysis", ["—"] + [r["run_id"] for r in prev],
                               label_visibility="collapsed")

# defaults when the Advanced expander was never opened this run
ocr_choice = locals().get("ocr_choice", settings.ocr_provider)
llm_choice = locals().get("llm_choice", settings.llm_provider)
llm_model = locals().get("llm_model", None)
llm_key = locals().get("llm_key", None)
use_samples = locals().get("use_samples", False)
fresh_run = locals().get("fresh_run", False)
top_k = locals().get("top_k", 5)
scoring_on = locals().get("scoring_on", settings.scoring_enabled)

# ── run / load state ─────────────────────────────────────────────────────
if run_clicked and pillars:
    with st.status("Working on it — searching, reading, and mapping…", expanded=True) as status:
        def log(m):
            status.write(m)
        result = run_pipeline(Economy(economy), pillars, use_samples=use_samples, top_k=top_k, log=log,
                              ocr_provider=ocr_choice, llm_provider=llm_choice,
                              llm_model=llm_model or None, llm_api_key=llm_key or None,
                              scoring_enabled=scoring_on, use_result_cache=not fresh_run)
        export_csv(result.mappings, result.meta.run_id)
        export_json(result)
        if any(m.raw_score is not None for m in result.mappings):
            export_scored_csv(result.mappings, result.meta.run_id)
        status.update(label=f"Done — {result.meta.run_id}", state="complete")
    st.session_state["run_id"] = result.meta.run_id
elif chosen_prev and chosen_prev != "—":
    st.session_state["run_id"] = chosen_prev

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
        '<div class="d">Singapore, Australia, or Malaysia.</div></div>'
        '<div class="step"><div class="n">2</div><div class="t">Choose a pillar</div>'
        '<div class="d">Pillar 6 — cross-border data rules, or Pillar 7 — data protection &amp; cybersecurity.</div></div>'
        '<div class="step"><div class="n">3</div><div class="t">Press “Run analysis”</div>'
        '<div class="d">Results appear here in a few minutes. You can also reopen a past analysis.</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

meta = db.get_run(run_id)
mappings = db.list_mappings(run_id=run_id)
if not mappings:
    st.warning("No results were recorded for this analysis.")
    st.stop()

# ── summary strip ─────────────────────────────────────────────────────────
summ = workflow.summary(run_id)
bs = summ["by_status"]
auto = bs.get("auto_accepted", 0) + bs.get("approved", 0)
cells = [
    ("Country", ECON_NAME.get(meta.economy.value, "—") if meta else "—", ""),
    ("Documents found", meta.docs_discovered if meta else "—", ""),
    ("Provisions read", meta.provisions_extracted if meta else "—", ""),
    ("High confidence", auto, "fo"), ("Needs review", bs.get("pending_review", 0), "oc"),
    ("Set aside", bs.get("quarantined", 0), "ox"),
]
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

tab_ev, tab_review, tab_audit, tab_export = st.tabs(
    ["Results", f"Needs review · {len(workflow.queue(run_id))}", "Details", "Download"]
)

# ── results ────────────────────────────────────────────────────────────────
with tab_ev:
    f1, f2, f3 = st.columns(3)
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
    st.markdown(f'<div class="kicker" style="margin:.5rem 0 .8rem">{len(view)} laws mapped</div>',
                unsafe_allow_html=True)
    for m in view:
        snip = m.verbatim_snippet[:260] + ("…" if len(m.verbatim_snippet) > 260 else "")
        flag = f' {seal_html("scope")}'.replace("s-review", "s-flag") if m.scope_flag else ""
        st.markdown(
            f'<div class="vt-card" style="--c:{vcolor(m.confidence_score)}">'
            f'<div class="docket"><b>{m.indicator_id}</b><span>Pillar {m.pillar}</span>'
            f'<span>{m.discovery_tag.value}</span></div>'
            f'<div><div class="law">{m.law_name}</div>'
            f'<div class="cite">{m.article_section} &middot; {m.economy.value}{flag}</div>'
            f'<div class="quote">{snip}</div>'
            f'<a class="srcurl" href="{m.source_url}" target="_blank">{m.source_url}</a></div>'
            f'<div>{(score_stamp_html(m.raw_score) + "<div style=margin-top:.5rem></div>") if m.raw_score is not None else ""}'
            f'{verdict_html(m.confidence_score)}<div style="margin-top:.5rem">{seal_html(m.review_status.value)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

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
        st.markdown('<div class="kicker">How the confidence was scored</div>', unsafe_allow_html=True)
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
