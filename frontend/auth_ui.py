"""Landing page + sign-in gate.

Visiting the app signed-out shows the landing screen: a short, plain-language
description of what VeriTrade does, links to the source and the white paper, and the
sign-in / create-account card. Signing in reveals the tool itself. Nothing about the
deployment changes — the landing simply *is* the app's unauthenticated state.

Sessions survive a browser refresh via an opaque cookie whose SHA-256 is what the
database stores (see backend/auth/service.py).
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from backend import auth
from backend.auth import AuthError
from backend.config import settings

from . import theme

COOKIE = "vt_session"


# ── cookie helpers ───────────────────────────────────────────────────────
def _read_cookie() -> str:
    try:
        return (st.context.cookies or {}).get(COOKIE, "") or ""
    except Exception:
        return ""


def _write_cookie(token: str, days: int) -> None:
    """Set the session cookie on the PARENT document (the component runs in an iframe).
    SameSite=Lax keeps it from riding along on cross-site requests."""
    components.html(
        f"""<script>(function(){{var d=window.parent&&window.parent.document; if(!d)return;
        var s=(location.protocol==='https:')?';Secure':'';
        d.cookie="{COOKIE}={token};path=/;max-age={days*86400};SameSite=Lax"+s;}})();</script>""",
        height=0,
    )


def _clear_cookie() -> None:
    components.html(
        f"""<script>(function(){{var d=window.parent&&window.parent.document; if(!d)return;
        d.cookie="{COOKIE}=;path=/;max-age=0;SameSite=Lax";}})();</script>""",
        height=0,
    )


# ── session ──────────────────────────────────────────────────────────────
def current_user() -> auth.User | None:
    """Signed-in user for this script run: session_state first (fast), then the cookie
    (survives refresh)."""
    u = st.session_state.get("user")
    if u is not None:
        return u
    token = st.session_state.get("session_token") or _read_cookie()
    if token:
        user = auth.resolve_session(token)
        if user:
            st.session_state["user"] = user
            st.session_state["session_token"] = token
            return user
    return None


def _start_session(user: auth.User) -> None:
    token = auth.create_session(user.user_id)
    st.session_state["user"] = user
    st.session_state["session_token"] = token
    _write_cookie(token, settings.session_days)


def sign_out() -> None:
    auth.destroy_session(st.session_state.get("session_token", ""))
    for k in ("user", "session_token", "run_id"):
        st.session_state.pop(k, None)
    _clear_cookie()
    try:                      # also end Streamlit's own OIDC session if one is active
        if getattr(st.user, "is_logged_in", False):
            st.logout()
    except Exception:
        pass
    st.rerun()


# ── Google (native OIDC) ─────────────────────────────────────────────────
def _google_ready() -> bool:
    """True only when an OIDC provider is actually configured in secrets.toml — the
    button stays hidden otherwise, so it can never fail in front of a user."""
    if not settings.google_auth_enabled:
        return False
    try:
        a = st.secrets.get("auth", {})
        return bool(a) and ("google" in a or "client_id" in a)
    except Exception:
        return False


def _adopt_google_login() -> auth.User | None:
    """If Streamlit's OIDC flow has completed, turn that identity into our own account."""
    try:
        if not getattr(st.user, "is_logged_in", False):
            return None
        email = getattr(st.user, "email", "") or ""
        if not email:
            return None
        return auth.sign_in_with_google(email, getattr(st.user, "name", "") or "")
    except Exception:
        return None


# ── UI ───────────────────────────────────────────────────────────────────
# Content and section order mirror the standalone marketing page (docs/landing.html):
# hero → stats → how it works → coverage → footer. Rebuilding it here rather than
# iframing that file keeps the sign-in form native (an iframe can't drive Streamlit).
_LANDING_CSS = """
  /* the hero row and the sign-in card share one height: Streamlit columns are flex
     children, so stretching the row and letting the card fill it keeps the two sides
     level instead of leaving a ragged gap under the shorter one. */
  /* Grow the card down to the hero's height with flex only — never height:100%.
     A percentage height on the column resolves against a parent whose height is
     content-driven, which pins the column to its OWN content and cancels the row's
     align-items:stretch (measured: hero 607px, card column stuck at 407px). */
  [data-testid="stHorizontalBlock"]:has(.vt-authcol){align-items:stretch;}
  [data-testid="stColumn"]:has(.vt-authcol){display:flex;flex-direction:column;}
  [data-testid="stColumn"]:has(.vt-authcol) > [data-testid="stVerticalBlock"]{
    flex:1;display:flex;flex-direction:column;gap:0;}
  /* st.container(border=True) renders as stLayoutWrapper */
  [data-testid="stColumn"]:has(.vt-authcol) [data-testid="stLayoutWrapper"]{
    flex:1;display:flex;flex-direction:column;justify-content:center;}
  /* the markers are layout hooks only — collapse the wrappers Streamlit gives them */
  .vt-authcol,.vt-herocol{display:none;}
  [data-testid="stElementContainer"]:has(> .vt-authcol),
  [data-testid="stElementContainer"]:has(> .vt-herocol){display:none;}

  .land-hero{padding:.2rem 0 0;}
  .land-eyebrow{display:inline-flex;align-items:center;gap:.5rem;font-size:.78rem;font-weight:600;
    color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent-soft);
    padding:.28rem .7rem;border-radius:99px;margin-bottom:1rem;}
  .land-eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--accent);}
  .land-title{font-size:clamp(2rem,3.8vw,2.9rem);font-weight:800;letter-spacing:-.03em;
    line-height:1.08;margin:.2rem 0 .8rem;}
  .land-title .accent{color:var(--accent);}
  .land-lede{font-size:1.05rem;color:var(--ink-soft);max-width:56ch;margin:0 0 1.3rem;line-height:1.6;}
  .land-steps{display:grid;gap:.75rem;margin:1.2rem 0 0;}
  .land-step{display:grid;grid-template-columns:30px 1fr;gap:.8rem;align-items:start;}
  .land-step .n{width:30px;height:30px;border-radius:50%;background:var(--accent);color:var(--accent-ink);
    font-weight:700;font-size:.85rem;display:flex;align-items:center;justify-content:center;flex:none;}
  .land-step .t{font-weight:600;}
  .land-step .d{color:var(--ink-soft);font-size:.9rem;line-height:1.5;}

  /* stats band — the four measured numbers from the marketing page */
  .land-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;margin:2rem 0 .4rem;}
  @media(max-width:820px){.land-stats{grid-template-columns:repeat(2,1fr);}}
  .land-stat{border:1px solid var(--rule);border-radius:12px;background:var(--panel);
    padding:.9rem 1rem;position:relative;overflow:hidden;}
  .land-stat::before{content:"";position:absolute;top:0;left:0;width:26px;height:2px;background:var(--accent);}
  .land-stat .n{font-size:1.55rem;font-weight:800;letter-spacing:-.02em;line-height:1;}
  .land-stat .k{font-size:.76rem;color:var(--ink-faint);margin-top:.3rem;}

  .land-sec{margin-top:2.2rem;}
  .land-kicker{font-size:.72rem;text-transform:uppercase;letter-spacing:.12em;color:var(--ink-faint);
    font-weight:700;margin-bottom:.5rem;}
  .land-kicker b{color:var(--accent);}
  .land-h2{font-size:1.3rem;font-weight:700;letter-spacing:-.02em;margin:0 0 1rem;}
  .land-h2 .dim{color:var(--ink-faint);font-weight:600;}

  .land-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;}
  @media(max-width:900px){.land-cards{grid-template-columns:repeat(2,1fr);}}
  @media(max-width:560px){.land-cards{grid-template-columns:1fr;}}
  .land-card{border:1px solid var(--rule);border-radius:12px;background:var(--panel);padding:1.1rem 1.1rem;
    transition:transform .16s ease,border-color .16s ease;}
  .land-card:hover{transform:translateY(-2px);border-color:var(--accent);}
  .land-card .num{font-size:.72rem;letter-spacing:.1em;color:var(--accent);font-weight:700;margin-bottom:.6rem;}
  .land-card .t{font-weight:600;margin-bottom:.25rem;}
  .land-card .d{color:var(--ink-soft);font-size:.88rem;line-height:1.5;}

  .land-pillars{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;}
  @media(max-width:820px){.land-pillars{grid-template-columns:1fr;}}
  .land-pillar{border:1px solid var(--rule);border-radius:13px;background:var(--panel);padding:1.1rem 1.2rem;}
  .land-pillar .ph{display:flex;align-items:baseline;gap:.6rem;margin-bottom:.7rem;}
  .land-pillar .pn{font-family:var(--mono,'IBM Plex Mono',monospace);font-weight:700;color:var(--accent);font-size:.9rem;}
  .land-pillar .pt{font-weight:700;}
  .land-ind{display:grid;grid-template-columns:62px 1fr;gap:.7rem;padding:.42rem 0;
    border-top:1px solid var(--rule-soft);font-size:.88rem;}
  .land-ind:first-of-type{border-top:0;}
  .land-ind .iid{font-family:'IBM Plex Mono',monospace;font-weight:600;color:var(--ink-soft);font-size:.8rem;}
  .land-ind .idesc{color:var(--ink-soft);} .land-ind .idesc b{color:var(--ink);font-weight:600;}
  .land-econ{display:flex;gap:.45rem;flex-wrap:wrap;margin-bottom:1rem;}
  .land-econ span{font-family:'IBM Plex Mono',monospace;font-size:.76rem;border:1px solid var(--rule);
    border-radius:99px;padding:.25rem .7rem;color:var(--ink-soft);background:var(--panel);}
  .land-econ b{color:var(--ink);}

  .auth-or{display:flex;align-items:center;gap:.7rem;color:var(--ink-faint);font-size:.78rem;margin:.8rem 0 .4rem;}
  .auth-or::before,.auth-or::after{content:"";flex:1;height:1px;background:var(--rule);}
  .land-foot{color:var(--ink-faint);font-size:.82rem;margin-top:2.2rem;
    border-top:1px solid var(--rule-soft);padding-top:1.1rem;display:flex;
    justify-content:space-between;gap:1rem;flex-wrap:wrap;}
"""


def _landing_intro() -> None:
    theme.inject_style(_LANDING_CSS)     # flattened — see theme.inject_style for why
    st.html('<div class="vt-herocol"></div>')
    st.markdown(
        f'<div class="land-hero">{theme.wordmark_html(74)}'
        '<div class="land-eyebrow" style="margin-top:1rem">UN ESCAP · RDTII 2.1 · Team FTU</div>'
        '<div class="land-title">Find the law, <span class="accent">prove the clause</span></div>'
        '<p class="land-lede">VeriTrade searches official government websites, reads the documents '
        '(including scanned PDFs), and matches each provision to the right RDTII indicator — with the '
        'exact quote, a link to the source, and a confidence score you can check.</p>'
        '<div class="land-steps">'
        '<div class="land-step"><div class="n">1</div><div><div class="t">Choose a country and a pillar</div>'
        '<div class="d">Singapore, Australia or Malaysia · cross-border data, or data protection &amp; cybersecurity.</div></div></div>'
        '<div class="land-step"><div class="n">2</div><div><div class="t">VeriTrade finds and reads the law</div>'
        '<div class="d">No seed links, no hand-picked corpus — it searches the official portals live.</div></div></div>'
        '<div class="land-step"><div class="n">3</div><div><div class="t">Get citable evidence</div>'
        '<div class="d">A verbatim quote, article-level citation and source URL for every result, ready to export.</div></div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _landing_below() -> None:
    """Everything under the fold — same sections, same order as docs/landing.html."""
    st.markdown(
        '<div class="land-stats">'
        '<div class="land-stat"><div class="n">3</div><div class="k">economies · Singapore, Australia, Malaysia</div></div>'
        '<div class="land-stat"><div class="n">9</div><div class="k">RDTII indicators · Pillars 6 &amp; 7</div></div>'
        '<div class="land-stat"><div class="n">1.11%</div><div class="k">OCR error rate · bar is 5%</div></div>'
        '<div class="land-stat"><div class="n">100%</div><div class="k">verbatim citations, never generated</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="land-sec"><div class="land-kicker"><b>01</b> · How it works</div>'
        '<div class="land-h2">Four passes <span class="dim">from a blank query to cited evidence.</span></div>'
        '<div class="land-cards">'
        '<div class="land-card"><div class="num">01 · DISCOVER</div><div class="t">Find the law</div>'
        '<div class="d">Autonomous search of official portals — no seed URLs, no hardcoded law names. '
        'Bot-resistant fetching clears blocks that stop a plain crawler.</div></div>'
        '<div class="land-card"><div class="num">02 · EXTRACT</div><div class="t">Read every format</div>'
        '<div class="d">HTML, text PDFs and scanned image PDFs. Real OCR with a measured error rate; '
        'text split into verbatim article chunks.</div></div>'
        '<div class="land-card"><div class="num">03 · MAP</div><div class="t">Match the indicator</div>'
        '<div class="d">Hybrid retrieval shortlists provisions; the model maps each to the right '
        'indicator while seeing every sibling, so look-alikes stay apart.</div></div>'
        '<div class="land-card"><div class="num">04 · VERIFY</div><div class="t">Cite or refuse</div>'
        '<div class="d">A verbatim snippet, article-level citation, source URL and confidence score. '
        'Low-confidence rows go to human review.</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="land-sec"><div class="land-kicker"><b>02</b> · Coverage</div>'
        '<div class="land-h2">Two mandatory pillars, <span class="dim">nine indicators, three economies.</span></div>'
        '<div class="land-econ">'
        '<span><b>Singapore</b> · sso.agc.gov.sg</span>'
        '<span><b>Australia</b> · legislation.gov.au</span>'
        '<span><b>Malaysia</b> · lom.agc.gov.my</span></div>'
        '<div class="land-pillars">'
        '<div class="land-pillar"><div class="ph"><span class="pn">Pillar 6</span>'
        '<span class="pt">Cross-border data policies</span></div>'
        '<div class="land-ind"><span class="iid">P6-I1</span><span class="idesc"><b>Ban &amp; local processing</b> — bans transfer or mandates local processing</span></div>'
        '<div class="land-ind"><span class="iid">P6-I2</span><span class="idesc"><b>Local storage</b> — data must be stored in-country</span></div>'
        '<div class="land-ind"><span class="iid">P6-I3</span><span class="idesc"><b>Infrastructure</b> — local servers as a condition of service</span></div>'
        '<div class="land-ind"><span class="iid">P6-I4</span><span class="idesc"><b>Conditional flow</b> — transfer allowed only if conditions are met</span></div>'
        '</div>'
        '<div class="land-pillar"><div class="ph"><span class="pn">Pillar 7</span>'
        '<span class="pt">Domestic data protection</span></div>'
        '<div class="land-ind"><span class="iid">P7-I1</span><span class="idesc"><b>Comprehensive framework</b> — a general, horizontal data-protection law</span></div>'
        '<div class="land-ind"><span class="iid">P7-I2</span><span class="idesc"><b>Dedicated cybersecurity</b> — a standalone cybersecurity law</span></div>'
        '<div class="land-ind"><span class="iid">P7-I3</span><span class="idesc"><b>Minimum retention</b> — a minimum data-retention duration</span></div>'
        '<div class="land-ind"><span class="iid">P7-I4</span><span class="idesc"><b>DPO / DPIA</b> — an officer or impact assessment is required</span></div>'
        '<div class="land-ind"><span class="iid">P7-I5</span><span class="idesc"><b>Government access</b> — state access to personal data</span></div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )


def _auth_card() -> None:
    # A real bordered container — a raw <div> can't wrap Streamlit widgets (each element
    # gets its own container), so an opening tag just renders as an empty box.
    # The marker div is what the equal-height CSS keys off (see _LANDING_CSS).
    st.html('<div class="vt-authcol"></div>')
    card = st.container(border=True)
    with card:
        _auth_card_body()


def _auth_card_body() -> None:
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])

    with tab_in:
        with st.form("sign_in", clear_on_submit=False):
            email = st.text_input("Email", key="in_email", placeholder="you@organisation.org")
            pw = st.text_input("Password", type="password", key="in_pw", placeholder="Your password")
            ok = st.form_submit_button("Sign in", type="primary", width="stretch")
        if ok:
            try:
                with st.spinner("Signing you in…"):
                    user = auth.sign_in(email, pw)
                _start_session(user)
                st.success(f"Welcome back, {user.display_name}.")
                st.rerun()
            except AuthError as e:
                st.error(str(e))
            except Exception:
                st.error("Sorry — sign-in is unavailable right now. Please try again.")

    with tab_up:
        with st.form("sign_up", clear_on_submit=False):
            name = st.text_input("Your name", key="up_name", placeholder="Jane Researcher")
            org = st.text_input("Organisation (optional)", key="up_org", placeholder="Ministry / university / firm")
            email2 = st.text_input("Email", key="up_email", placeholder="you@organisation.org")
            pw2 = st.text_input("Password", type="password", key="up_pw",
                                placeholder="At least 8 characters",
                                help="At least 8 characters. Stored only as a secure hash.")
            ok2 = st.form_submit_button("Create account", type="primary", width="stretch")
        if ok2:
            try:
                with st.spinner("Creating your account…"):
                    user = auth.sign_up(email2, pw2, name, org)
                _start_session(user)
                st.success("Account created — welcome to VeriTrade.")
                st.rerun()
            except AuthError as e:
                st.error(str(e))
            except Exception:
                st.error("Sorry — we couldn't create the account right now. Please try again.")

    if _google_ready():
        st.markdown('<div class="auth-or">or</div>', unsafe_allow_html=True)
        if st.button("Continue with Google", width="stretch", key="google_btn"):
            try:
                st.login("google")
            except Exception:
                st.error("Google sign-in isn't configured on this deployment.")
    st.caption("Your email is used only to save your analysis history. "
               "Passwords are stored hashed, never in plain text.")


def require_user() -> auth.User:
    """Gate the app. Returns the signed-in user, or renders the landing page and stops."""
    if not settings.auth_enabled:                      # escape hatch for CLI-style demos
        return auth.User(user_id="local", email="local@veritrade", name="Local user")

    user = current_user()
    if user is None:                                   # a completed Google flow counts as signed in
        g = _adopt_google_login()
        if g:
            _start_session(g)
            user = g
    if user is not None:
        return user

    # top bar: white paper / source / theme — available before signing in
    _sp, c_wp, c_src, c_th = st.columns([5.3, 1.5, 1.5, 1.1])
    with c_wp:
        st.link_button("White paper", theme.WHITEPAPER_URL, icon=":material/description:",
                       help="Open the technical white paper", width="stretch")
    with c_src:
        st.link_button("Source", theme.REPO_URL, icon=":material/code:",
                       help="View the code on GitHub", width="stretch")
    with c_th:
        theme.theme_toggle(key="theme_toggle_landing")

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        _landing_intro()
    with right:
        _auth_card()
    _landing_below()
    st.markdown(
        '<div class="land-foot">'
        '<span>Team FTU · Foreign Trade University · UN ESCAP / KMITL Global Hackathon 2026</span>'
        f'<span>Apache-2.0 · <a href="{theme.REPO_URL}" target="_blank">github.com/ftulabs/law-v2.0</a></span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()


def account_control(user: auth.User) -> None:
    """Signed-in identity + sign-out, rendered in the app's top-right."""
    with st.popover(user.display_name, icon=":material/account_circle:", width="stretch"):
        st.markdown(f"**{user.display_name}**")
        st.caption(user.email + (f" · {user.organisation}" if user.organisation else ""))
        if user.auth_provider == "google":
            st.caption("Signed in with Google")
        st.markdown('<hr class="hr-thin">', unsafe_allow_html=True)
        if st.button("Sign out", key="sign_out_btn", width="stretch"):
            sign_out()
