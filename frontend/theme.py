"""VeriTrade design system — one palette, one type scale, shared by every screen.

Single source of truth pairing with `.streamlit/config.toml`: that file styles
Streamlit's NATIVE widgets, this module styles our own markup. The two use the same
hex values, so a light-mode screen can no longer end up with dark-mode chrome.

The app FOLLOWS Streamlit's active theme (`st.context.theme.type`); it never keeps a
theme flag of its own. The visible toggle (`theme_toggle`) sets *Streamlit's* stored
preference and reloads, so native widgets and our markup always switch together — a
second, independent switch was exactly what let the two halves disagree.

Design direction: "clear research tool" — plain language, one accent, one radius
scale, minimal motion, WCAG-AA contrast in both modes.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent / "assets"

REPO_URL = "https://github.com/ftulabs/law-v2.0"
WHITEPAPER_URL = "app/static/whitepaper.html"

# ── typography ───────────────────────────────────────────────────────────
# Combinations under evaluation — open /app/static/fonts.html to compare them
# rendered in the real UI, then set VT_FONT_SET (or FONT_SET below) to the winner.
# "display" is used for headings only; "body" for everything else; mono for
# citations/IDs/URLs. Keeping them in one place means switching is a one-word change.
FONT_SETS: dict[str, dict[str, str]] = {
    # neutral, current
    "inter":            {"display": "Inter",            "body": "Inter", "label": "Inter only"},
    # the original VeriTrade display serif, over a readable sans body
    "fraunces":         {"display": "Fraunces",         "body": "Inter", "label": "Fraunces + Inter"},
    # softer editorial serif
    "newsreader":       {"display": "Newsreader",       "body": "Inter", "label": "Newsreader + Inter"},
    # modern high-contrast editorial
    "instrument":       {"display": "Instrument Serif", "body": "Inter", "label": "Instrument Serif + Inter"},
    # geometric/technical sans display
    "space":            {"display": "Space Grotesk",    "body": "Inter", "label": "Space Grotesk + Inter"},
}
FONT_SET = os.getenv("VT_FONT_SET", "inter").lower()
_ACTIVE = FONT_SETS.get(FONT_SET, FONT_SETS["inter"])

BODY_FONT = _ACTIVE["body"]
DISPLAY_FONT = _ACTIVE["display"]
MONO_FONT = "IBM Plex Mono"
BODY_STACK = f"'{BODY_FONT}',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif"
HEAD_STACK = f"'{DISPLAY_FONT}',{BODY_STACK}"
MONO_STACK = f"'{MONO_FONT}',ui-monospace,monospace"

_GF = {
    "Inter": "Inter:wght@400;500;600;700;800",
    "Fraunces": "Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700",
    "Newsreader": "Newsreader:opsz,wght@6..72,500;6..72,600;6..72,700",
    "Instrument Serif": "Instrument+Serif:ital@0;1",
    "Space Grotesk": "Space+Grotesk:wght@500;600;700",
}


def font_import_url() -> str:
    """Google-Fonts URL loading exactly the families the active set needs."""
    fams = {BODY_FONT, DISPLAY_FONT}
    parts = [f"family={_GF[f]}" for f in fams if f in _GF]
    parts.append("family=IBM+Plex+Mono:wght@400;500;600")
    return "https://fonts.googleapis.com/css2?" + "&".join(parts) + "&display=swap"

# ── tokens (mirror .streamlit/config.toml) ────────────────────────────────
# Palette: the "accessible / public-sector" profile — grounded slate neutrals with a
# deep, serious blue rather than a bright product blue. Two deliberate changes from the
# earlier pass, both reasons the UI read as flat:
#   • the page ground is OFF-white (#f8fafc) and cards are pure white, so surfaces layer
#     instead of dissolving into one another (white-on-white had no depth);
#   • the accent is sky-700 (#0369a1) — calmer and higher-contrast on white than #2563eb.
# The confidence traffic-light and Inter/IBM Plex Mono are unchanged (CLAUDE.md §5).
LIGHT = """
  --paper:#f8fafc; --paper-2:#f1f5f9; --paper-3:#e8ecf1;
  --ink:#020617; --ink-soft:#475569; --ink-faint:#64748b;
  --rule:#e2e8f0; --rule-soft:#eef2f7;
  --accent:#0369a1; --accent-ink:#ffffff; --accent-soft:#e0f2fe;
  --good:#15803d; --warn:#a16207; --bad:#dc2626;
  --good-soft:#e7f4ec; --warn-soft:#faf1dd; --bad-soft:#fdeaea;
  --appr:#0369a1; --flag:#7e22ce;
  --panel:#ffffff; --panel-2:#f1f5f9;
  --shadow:0 1px 2px rgba(2,6,23,.05), 0 8px 24px rgba(2,6,23,.06);
  --shadow-lg:0 2px 4px rgba(2,6,23,.06), 0 16px 40px rgba(2,6,23,.10);
  --ring:rgba(3,105,161,.38);
"""
DARK = """
  --paper:#020617; --paper-2:#0f172a; --paper-3:#1e293b;
  --ink:#f1f5f9; --ink-soft:#94a3b8; --ink-faint:#64748b;
  --rule:#1e293b; --rule-soft:#172033;
  --accent:#38bdf8; --accent-ink:#04202e; --accent-soft:#0c2d43;
  --good:#34d399; --warn:#fbbf24; --bad:#f87171;
  --good-soft:#0d2a1d; --warn-soft:#2b2208; --bad-soft:#2e1315;
  --appr:#38bdf8; --flag:#c084fc;
  --panel:#0f172a; --panel-2:#1e293b;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  --shadow-lg:0 2px 6px rgba(0,0,0,.5), 0 18px 44px rgba(0,0,0,.45);
  --ring:rgba(56,189,248,.45);
"""


def is_dark() -> bool:
    """Follow Streamlit's active theme; default to dark when it can't be read."""
    try:
        return getattr(getattr(st.context, "theme", None), "type", "dark") != "light"
    except Exception:
        return True


# ── brand assets ─────────────────────────────────────────────────────────
def _asset(*names: str) -> Path | None:
    for n in names:
        p = ASSETS / n
        if p.exists():
            return p
    return None


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def favicon() -> str | None:
    p = _asset("veritrade_favicon.png", "veritrade_icon.png", "veritrade_logo.png", "ftu_logo.png")
    return str(p) if p else None


def logo_data_uri() -> str | None:
    p = _asset("veritrade_favicon.png", "veritrade_logo.png")
    return f"data:image/png;base64,{_b64(p)}" if p else None


def wordmark_html(height: int = 60) -> str:
    """The VeriTrade wordmark: transparent PNG → brand SVG → text fallback."""
    png = _asset("veritrade_logo.png", "veritrade_logo.webp")
    if png:
        return (f'<img class="vt-logo" alt="VeriTrade" style="height:{height}px" '
                f'src="data:image/{png.suffix[1:]};base64,{_b64(png)}"/>')
    svg = _asset("veritrade_logo.svg")
    if svg:
        return f'<div class="vt-logo" style="height:{height}px">{svg.read_text(encoding="utf-8")}</div>'
    return '<h1 class="wordmark">Veri<span class="mark">Trade</span></h1>'


# ── keyboard guard ───────────────────────────────────────────────────────
def keyboard_guard() -> None:
    """Streamlit binds BARE single keys ("C" = clear cache, "R" = rerun), so Ctrl/Cmd+C
    to copy text pops the "Clear caches?" dialog. This capture-phase listener stops any
    Ctrl/Cmd combo before Streamlit's handler sees it; it never calls preventDefault(),
    so the browser's own clipboard actions still work."""
    import streamlit.components.v1 as components
    components.html(
        """<script>(function(){var d=window.parent&&window.parent.document;
        if(!d||d.__veritradeKbdGuard)return; d.__veritradeKbdGuard=true;
        d.addEventListener('keydown',function(e){if(e.ctrlKey||e.metaKey){e.stopImmediatePropagation();}},true);})();</script>""",
        height=0,
    )


# ── the stylesheet ───────────────────────────────────────────────────────
def inject_style(css: str) -> None:
    """Inject a stylesheet safely.

    Two traps, both hit in practice:
      • st.markdown ends a raw-HTML block at the first BLANK LINE, then parses the
        indented remainder as a markdown code block — so every rule after the first
        blank line was silently dropped (or printed on the page as text).
      • st.html discards a payload whose only top-level node is a <style> tag.
    Flattening to a single line sidesteps both: no blank lines, no indentation.
    """
    flat = " ".join(line.strip() for line in css.splitlines() if line.strip())
    st.markdown(f"<style>{flat}</style>", unsafe_allow_html=True)


def inject_css() -> None:
    """Base design system: tokens, typography, and the native-widget overrides that
    keep Streamlit's own components on-palette in both themes."""
    tokens = DARK if is_dark() else LIGHT
    inject_style(
        f"""
          @import url('{font_import_url()}');
          :root {{ {tokens} }}

          /* ── typography: one family everywhere ({BODY_FONT}), mono only for IDs/citations/URLs.
                config.toml already points Streamlit's native widgets at the same family; this
                keeps our own markup in step so headings and labels match.
                NOTE: do NOT use a catch-all like [class*="st-"] here. Streamlit draws its icons
                as Material Symbols LIGATURES (<span data-testid="stIconMaterial">expand_more</span>);
                forcing a text font on them stops the ligature resolving and the raw icon name
                renders as words ("light_mode", "arrow_drop_down", "keyboard_double_arrow_left"). ── */
          html, body, .stApp, button, input, optgroup, select, textarea {{
              font-family:{BODY_STACK};
          }}
          [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
          .stTabs [data-baseweb="tab"], [data-baseweb="select"] {{ font-family:{BODY_STACK}; }}
          /* restore the icon font, whatever else we set above */
          [data-testid="stIconMaterial"], span[data-testid="stIconMaterial"],
          .material-symbols-rounded, [class*="material-symbols"] {{
              font-family:'Material Symbols Rounded' !important; font-weight:normal !important;
              font-style:normal !important; letter-spacing:normal !important;
              text-transform:none !important; white-space:nowrap; word-wrap:normal;
              direction:ltr; -webkit-font-feature-settings:'liga'; font-feature-settings:'liga';
              -webkit-font-smoothing:antialiased;
          }}
          h1,h2,h3,h4,h5 {{ font-family:{HEAD_STACK}; }}
          .stApp {{ background:var(--paper); color:var(--ink); }}
          .block-container {{ padding-top:1.2rem; max-width:1240px; }}
          [data-testid="stHeader"] {{ background:transparent; }}
          h1,h2,h3,h4 {{ color:var(--ink); letter-spacing:-.015em; }}
          a {{ color:var(--accent); text-decoration:none; }}
          a:hover {{ text-decoration:underline; }}
          .mono {{ font-family:{MONO_STACK}; }}
          .muted {{ color:var(--ink-faint); font-size:.85rem; }}
          .soft {{ color:var(--ink-soft); }}
          /* section label — sentence case, never a shouty all-caps eyebrow */
          .kicker {{ font-size:.8rem; font-weight:600; color:var(--ink-soft); }}
          .vt-logo {{ line-height:0; margin:.1rem 0; }}
          img.vt-logo, .vt-logo img, .vt-logo svg {{ width:auto !important; max-width:420px; display:block; }}
          .wordmark {{ font-size:2rem; font-weight:800; letter-spacing:-.02em; margin:0; }}
          .wordmark .mark {{ color:var(--accent); }}

          /* ── native widgets: keep labels/captions/inputs on-palette in BOTH themes ── */
          [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * {{ color:var(--ink) !important; }}
          [data-testid="stMarkdownContainer"] {{ color:var(--ink); }}
          [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color:var(--ink-faint) !important; }}
          [data-testid="stMetricValue"] {{ color:var(--ink) !important; }}
          [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{ color:var(--ink-soft) !important; }}
          [data-testid="stSidebar"] {{ background:var(--paper-2); border-right:1px solid var(--rule); }}
          [data-testid="stExpander"] {{ border:1px solid var(--rule) !important; border-radius:10px !important;
                  background:var(--panel) !important; }}
          [data-testid="stExpander"] details, [data-testid="stExpander"] summary,
          [data-testid="stExpanderDetails"] {{ background:var(--panel) !important; }}
          [data-testid="stExpander"] summary:hover {{ background:var(--panel-2) !important; }}
          [data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{
                  color:var(--ink) !important; font-weight:600; }}
          .stTextInput input, .stNumberInput input, .stTextArea textarea {{
                  color:var(--ink) !important; background:var(--paper) !important; border-radius:8px !important; }}
          .stTextInput input::placeholder, .stTextArea textarea::placeholder {{ color:var(--ink-faint) !important; }}
          div[data-baseweb="select"] > div {{ background:var(--paper) !important;
                  border-color:var(--rule) !important; border-radius:8px !important; }}
          div[data-baseweb="select"] * {{ color:var(--ink) !important; }}
          [data-baseweb="popover"] > div, [data-baseweb="popover"] div, [data-baseweb="popover"] ul,
          [data-baseweb="menu"], ul[role="listbox"], div[role="listbox"] {{ background-color:var(--paper-2) !important; }}
          [role="option"], [role="option"] *, [data-baseweb="menu"] li {{
                  background-color:transparent !important; color:var(--ink) !important; }}
          [role="option"]:hover, li[role="option"][aria-selected="true"] {{ background-color:var(--paper-3) !important; }}
          [data-baseweb="popover"]:has([role="menuitem"]), [data-baseweb="popover"]:has([role="menuitem"]) * {{
                  color:var(--ink) !important; }}
          [data-baseweb="tag"] {{ background:var(--accent) !important; border-color:var(--accent) !important;
                  border-radius:6px !important; }}
          [data-baseweb="tag"], [data-baseweb="tag"] * {{ color:var(--accent-ink) !important; fill:var(--accent-ink) !important; }}
          pre, code, .stCode, [data-testid="stJson"], [data-testid="stJson"] * {{
                  background:var(--paper-3) !important; color:var(--ink) !important; border-radius:8px; }}

          /* ── buttons: the label sits in a child element that the global ink rule would
                otherwise darken, so pin colour on the button AND its descendants ── */
          .stButton button, .stLinkButton a, .stDownloadButton button, .stFormSubmitButton button {{
                  font-weight:600; border-radius:9px; text-decoration:none !important; }}
          .stButton button:not([kind="primary"]), .stLinkButton a, .stDownloadButton button {{
                  background:var(--panel) !important; border:1px solid var(--rule) !important; }}
          .stButton button:not([kind="primary"]), .stButton button:not([kind="primary"]) *,
          .stLinkButton a, .stLinkButton a *,
          .stDownloadButton button, .stDownloadButton button * {{ color:var(--ink) !important; }}
          .stButton button:not([kind="primary"]):hover, .stLinkButton a:hover,
          .stDownloadButton button:hover {{ background:var(--panel-2) !important; border-color:var(--accent) !important; }}
          .stButton button:not([kind="primary"]):hover *, .stLinkButton a:hover,
          .stLinkButton a:hover *, .stDownloadButton button:hover * {{ color:var(--accent) !important; }}
          .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
          .stButton button[data-testid="stBaseButton-primary"] {{
                  background:var(--accent) !important; border-color:var(--accent) !important; font-weight:700; }}
          .stButton button[kind="primary"], .stButton button[kind="primary"] *,
          .stFormSubmitButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] *,
          .stButton button[data-testid="stBaseButton-primary"],
          .stButton button[data-testid="stBaseButton-primary"] * {{
                  color:var(--accent-ink) !important; fill:var(--accent-ink) !important; }}
          .stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {{
                  filter:brightness(1.06); }}

          /* ── shared components ── */
          .seal {{ display:inline-block; font-size:.72rem; font-weight:600; padding:.14rem .55rem;
                  border-radius:99px; border:1px solid; }}
          .s-auto {{ color:var(--good); border-color:var(--good); background:var(--good-soft); }}
          .s-review {{ color:var(--warn); border-color:var(--warn); background:var(--warn-soft); }}
          .s-quar {{ color:var(--bad); border-color:var(--bad); background:var(--bad-soft); }}
          .s-appr {{ color:var(--appr); border-color:var(--appr); background:var(--accent-soft); }}
          .s-rej {{ color:var(--ink-soft); border-color:var(--rule); }}
          .s-flag {{ color:var(--flag); border-color:var(--flag); background:color-mix(in srgb,var(--flag) 12%,transparent); }}
          .s-none {{ color:var(--ink-faint); border-color:var(--rule); background:transparent; }}
          .hr-thin {{ border:none; border-top:1px solid var(--rule-soft); margin:.7rem 0; }}
          /* ── Hide Streamlit's own toolbar (Deploy + the ⋮ menu). It carried a SECOND
                light/dark switch that duplicated ours, and its other entries — Rerun,
                Clear cache, Print, Deploy — are developer actions, not something a policy
                researcher should be offered. Everything a user needs now lives in the one
                account menu (frontend/auth_ui.account_control). ── */
          [data-testid="stToolbar"], [data-testid="stMainMenu"],
          [data-testid="stStatusWidget"] {{ display:none !important; }}
          [data-testid="stHeader"] {{ height:0; min-height:0; }}
          /* ── accessibility: a visible keyboard focus ring. There was none before, so a
                keyboard user had no idea where they were. 3px + offset, on the accent. ── */
          *:focus-visible {{ outline:3px solid var(--ring) !important; outline-offset:2px !important;
                  border-radius:6px; }}
          .stButton button:focus-visible, .stLinkButton a:focus-visible,
          .stFormSubmitButton button:focus-visible, [data-baseweb="tab"]:focus-visible {{
                  outline:3px solid var(--ring) !important; outline-offset:2px !important; }}
          .stTextInput input:focus, .stTextArea textarea:focus {{
                  border-color:var(--accent) !important;
                  box-shadow:0 0 0 3px var(--ring) !important; }}
          /* ── surface depth: cards sit on the off-white ground, not flush with it.
                Scoped to wrappers that actually draw a border — stLayoutWrapper is also
                used for column and row wrappers, and styling those painted a white slab
                across the header and hero. ── */
          [data-testid="stLayoutWrapper"][style*="border"],
          [data-testid="stVerticalBlockBorderWrapper"] {{
                  background:var(--panel); box-shadow:var(--shadow); }}
          /* comfortable hit areas (skill: 44px minimum) + a consistent motion token */
          .stButton button, .stLinkButton a, .stDownloadButton button,
          .stFormSubmitButton button {{ min-height:42px; cursor:pointer;
                  transition:background .18s ease, border-color .18s ease, color .18s ease; }}
          @media (prefers-reduced-motion: reduce) {{
              * {{ transition:none !important; animation:none !important; }}
          }}
        """
    )


def page_config(title: str = "VeriTrade") -> None:
    ico = favicon()
    st.set_page_config(page_title=title, page_icon=ico or "⚖", layout="wide")


# ── light / dark switch ──────────────────────────────────────────────────
# This drives Streamlit's REAL theme, not a private flag of our own. Streamlit keeps
# the user's choice in localStorage under `stActiveTheme-<pathname>-v2`, whose value is
# a JSON string: "Light" | "Dark" | "System". Writing that key and reloading is exactly
# what its own Settings dialog does, so native widgets AND our CSS switch together —
# the previous app-level toggle only ever repainted our own markup.
_THEME_KEY_JS = "'stActiveTheme-' + w.location.pathname + '-v2'"


def _apply_streamlit_theme(name: str) -> None:
    """Persist the choice the way Streamlit does, then reload so it takes effect."""
    import streamlit.components.v1 as components
    components.html(
        f"""<script>(function(){{
          var w = window.parent; if (!w) return;
          try {{
            w.localStorage.setItem({_THEME_KEY_JS}, JSON.stringify("{name}"));
            w.location.reload();
          }} catch (e) {{}}
        }})();</script>""",
        height=0,
    )


def theme_toggle(key: str = "theme_toggle") -> None:
    """Visible light/dark button, labelled with the mode it switches TO. Uses Streamlit's
    own Material icons rather than an emoji, so it matches the rest of the chrome instead
    of rendering in whatever the OS emoji font happens to be."""
    dark = is_dark()
    target = "Light" if dark else "Dark"
    if st.button(target, key=key, icon=":material/light_mode:" if dark else ":material/dark_mode:",
                 help=f"Switch to {target.lower()} mode", width="stretch"):
        _apply_streamlit_theme(target)
