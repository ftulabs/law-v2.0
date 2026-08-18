"""The engine bench — choosing how documents are read and which model judges the law.

Provider-swappability is one of the scored requirements, and it used to be two dropdowns
inside a collapsed "Advanced settings" expander: the thing judges ask about, hidden behind
the thing most users never open.

Two rules this file exists to enforce:

**No unmeasured numbers.** Every figure on an OCR card is read from
`data/benchmarks/ocr_bench.json`, which `tools/bench_ocr.py` produces by running each
installed engine over the bundled scanned sample. An engine with no row there says
"not measured here" and shows nothing else. The first version of this screen carried
per-document timings nobody had taken; they read as measurements and were guesses.

**A provider is not a model.** OpenRouter is a gateway: one key reaches many models, and
the thing a user actually chooses is the *model*. So the cards pick the route (where the
key goes, where the text travels) and a setup panel underneath picks the model and takes
the key — right there, rather than sending the user back to a sidebar to find a field.
Selecting a route is never blocked for want of a key; only running is.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from backend.config import settings
from backend.providers import registry as reg

_BENCH = Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "ocr_bench.json"

# Bench order, which is not the registry's order: the everyday choice first, the specialist
# engines next, and the offline stand-in last — it is a demo aid, not something to reach for
# by accident.
OCR_ORDER = ["rapidocr", "markitdown", "paddle", "azure", "tesseract", "mock"]
LLM_ORDER = ["openrouter", "anthropic", "openai", "gemini", "local", "mock"]

# What each engine is FOR, and whether it ships with the app. Numbers never live here.
OCR: dict[str, dict] = {
    "rapidocr": {
        "name": "RapidOCR",
        "role": "Recognises the words in a scanned page as an image. The default, and the "
                "engine the accuracy claim is based on.",
        "bundled": "Ships with the app",
    },
    "markitdown": {
        "name": "MarkItDown",
        "role": "Reads a PDF's own text layer — an exact copy, instantly. It is not an OCR "
                "engine, so it cannot read a scan at all.",
        "bundled": "Ships with the app",
    },
    "paddle": {
        "name": "PaddleOCR",
        "role": "Built for non-Latin script — the reader to switch to for Thai, Chinese and "
                "Mongolian law in the finals.",
        "bundled": "Optional · a ~1 GB extra",
    },
    "azure": {
        "name": "Azure Document Intelligence",
        "role": "A cloud reader, strongest on damaged, skewed, real-world gazette scans. "
                "Bring your own key — pages are sent to Microsoft.",
        "bundled": "Optional · bring a key",
    },
    "tesseract": {
        "name": "Tesseract",
        "role": "The classic open-source reader. Needs a system binary, so it cannot be "
                "installed from Python alone.",
        "bundled": "Optional · system install",
    },
    "mock": {
        "name": "Offline stand-in",
        "role": "Does not read anything — returns the sample's stored text so a demo runs "
                "with no network. Never use it for a submission.",
        "bundled": "Ships with the app",
    },
}

# LLM cards choose a ROUTE: whose key, and where the text goes. The model comes after.
LLM: dict[str, dict] = {
    "openrouter": {
        "name": "OpenRouter",
        "kind": "gateway",
        "role": "A gateway, not a model. One key reaches many models — choose which one "
                "below. If a model rate-limits, the run fails over to the next.",
        "facts": [("Key", "one, for every model", ""), ("Cost", "pay per token", ""),
                  ("Model", "you choose below", "good"), ("Text", "sent to the provider", "warn")],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "kind": "direct",
        "role": "Straight to Anthropic on your own account. Strong on the indicator pairs "
                "that get confused — 6.1 against 6.4, 7.1 against 7.2.",
        "facts": [("Key", "your Anthropic key", ""), ("Cost", "pay per token", ""),
                  ("Model", "you name it below", "good"), ("Text", "sent to Anthropic", "warn")],
    },
    "openai": {
        "name": "OpenAI",
        "kind": "direct",
        "role": "Straight to OpenAI on your own account — useful for cross-checking a run "
                "made with a different provider.",
        "facts": [("Key", "your OpenAI key", ""), ("Cost", "pay per token", ""),
                  ("Model", "you name it below", "good"), ("Text", "sent to OpenAI", "warn")],
    },
    "gemini": {
        "name": "Google Gemini",
        "kind": "direct",
        "role": "Straight to Google. Strong multilingual reading, which matters once the "
                "corpus stops being English.",
        "facts": [("Key", "your Google key", ""), ("Cost", "pay per token", ""),
                  ("Model", "you name it below", "good"), ("Text", "sent to Google", "warn")],
    },
    "local": {
        "name": "Self-hosted",
        "kind": "local",
        "role": "Any OpenAI-compatible server you run — Ollama, vLLM, LM Studio. No key, no "
                "network, nothing about the documents leaves the building.",
        "facts": [("Key", "none", "good"), ("Cost", "free", "good"),
                  ("Model", "whatever you serve", "good"),
                  ("Text", "never leaves your machine", "good")],
    },
    "mock": {
        "name": "Offline stand-in",
        "kind": "offline",
        "role": "Keyword rules, not a model. Reproducible with no network — but it confuses "
                "6.1 with 6.4, so never use it for a submission.",
        "facts": [("Key", "none", "good"), ("Cost", "free", "good"),
                  ("Judgement", "keywords only", "warn"),
                  ("Text", "never leaves your machine", "good")],
    },
}

CSS = """
  .eb{border:1px solid var(--rule);border-radius:13px;background:var(--panel);
    padding:.85rem .95rem .6rem;box-shadow:var(--shadow);position:relative;
    display:flex;flex-direction:column;min-height:206px;
    transition:border-color .18s ease, box-shadow .18s ease;}
  .eb:hover{border-color:color-mix(in srgb,var(--accent) 55%,transparent);}
  .eb.on{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),var(--shadow);}
  .eb .ebh{display:flex;align-items:center;gap:.45rem;}
  .eb .ebh b{font-size:.92rem;font-weight:600;color:var(--ink);line-height:1.25;}
  .eb .st{margin-left:auto;width:9px;height:9px;border-radius:50%;flex:none;}
  .eb .st.up{background:var(--good);box-shadow:0 0 0 3px var(--good-soft);}
  .eb .st.off{background:var(--ink-faint);opacity:.55;}
  .eb .role{font-size:.74rem;color:var(--ink-soft);margin:.4rem 0 .5rem;line-height:1.5;}
  .eb .ship{font-size:.63rem;color:var(--ink-faint);text-transform:uppercase;
    letter-spacing:.05em;margin-bottom:.4rem;}
  .eb .ship.in{color:var(--good);}
  .eb .facts{display:grid;grid-template-columns:1fr 1fr;gap:.35rem .7rem;margin-top:auto;
    padding-top:.55rem;border-top:1px solid var(--rule-soft);}
  .eb .fx{display:flex;flex-direction:column;min-width:0;}
  .eb .fx b{font-family:var(--mono);font-size:.72rem;font-weight:600;color:var(--ink);
    overflow-wrap:anywhere;}
  .eb .fx b.good{color:var(--good);} .eb .fx b.warn{color:var(--warn);}
  .eb .fx span{font-size:.6rem;color:var(--ink-faint);text-transform:uppercase;
    letter-spacing:.06em;}
  .eb .unmeasured{font-size:.7rem;color:var(--ink-faint);font-style:italic;margin-top:auto;
    padding-top:.55rem;border-top:1px solid var(--rule-soft);}
  .eb .tag{position:absolute;top:-.55rem;right:.8rem;font-size:.6rem;font-weight:600;
    letter-spacing:.05em;text-transform:uppercase;padding:2px 8px;border-radius:99px;
    background:var(--accent);color:var(--accent-ink);}
  .ebnote{display:flex;gap:.7rem;align-items:flex-start;margin:.9rem 0 0;padding:.75rem .9rem;
    border-radius:12px;background:var(--panel-2);border:1px solid var(--rule);
    font-size:.75rem;color:var(--ink-soft);line-height:1.55;}
  .ebnote b{color:var(--ink);}
  /* :has() on the marker span, because Streamlit gives the container no class of ours */
  [data-testid="stVerticalBlockBorderWrapper"]:has(.ebmark){
    border-color:var(--accent) !important;
    background:color-mix(in srgb,var(--accent-soft) 45%,var(--panel));}
  .ttl{font-size:.82rem;font-weight:600;color:var(--ink);margin:.2rem 0 .1rem;}
  .sub{font-size:.74rem;color:var(--ink-soft);margin-bottom:.3rem;line-height:1.5;}
"""


# ── measured numbers ────────────────────────────────────────────────────────
def _bench() -> dict:
    try:
        return json.loads(_BENCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ocr_facts(name: str, bench: dict, installed: bool) -> tuple[str, str]:
    """(facts html, unmeasured note). Only what tools/bench_ocr.py actually recorded."""
    row = (bench.get("engines") or {}).get(name)
    if name == "mock":
        return "", "Not an engine — it replays stored text, so accuracy is not a question."
    if not row:
        # Two different silences, and conflating them misleads: one engine is absent, the
        # other is present but nobody has run the benchmark for it yet.
        return "", ("Installed, but not measured yet — run <code>python tools/bench_ocr.py"
                    "</code> to fill this in." if installed else
                    "Not installed here, so no figure is shown rather than one borrowed "
                    "from another machine.")

    facts: list[tuple[str, str, str]] = []
    cer = row.get("cer")
    if cer is None:
        facts.append(("On a scan", "no text at all", "warn"))
    elif cer > 0.5:
        # MarkItDown scores ~96% error on an image-only PDF because it is not an OCR engine.
        # Reporting that as an error rate invites the reader to compare it with RapidOCR's
        # 1.11% as if they were the same kind of thing.
        facts.append(("On a scan", "cannot read it", "warn"))
    else:
        facts.append(("Error rate", f"{cer:.2%}", "good" if cer < 0.05 else "warn"))

    spp = row.get("seconds_per_page")
    if spp is not None:
        facts.append(("Speed", f"{spp:g} s / page" if spp >= 0.1 else "instant", ""))
    facts.append(("Cost", "free", "good"))
    facts.append(("Documents", "stay on this machine", "good"))

    # Loading (and, for Paddle, compiling) the model is a once-per-process cost. Folding it
    # into the per-page figure would overstate every page after the first; hiding it would
    # leave someone running a single document wondering why it took eight minutes.
    cold = row.get("first_call_seconds")
    if cold and spp and cold > 3 * spp:
        facts.append(("First run", f"+{cold - spp:.0f} s to load", "warn"))

    html = "".join(f'<div class="fx"><b class="{tone}">{v}</b><span>{lab}</span></div>'
                   for lab, v, tone in facts)
    return html, ""


def _card(spec: dict, ready: bool, note: str, selected: bool,
          facts_html: str, unmeasured: str, ship: str | None = None) -> str:
    tag = '<span class="tag">In use</span>' if selected else ""
    dot = "up" if ready else "off"
    title = "ready on this machine" if ready else note
    shipline = ""
    if ship:
        bundled = ship.lower().startswith("ships")
        shipline = f'<div class="ship{" in" if bundled else ""}">{ship}</div>'
    body = (f'<div class="facts">{facts_html}</div>' if facts_html
            else f'<div class="unmeasured">{unmeasured}</div>')
    return (f'<div class="eb{" on" if selected else ""}">{tag}'
            f'<div class="ebh"><b>{spec["name"]}</b>'
            f'<span class="st {dot}" title="{title}"></span></div>'
            f'{shipline}<div class="role">{spec["role"]}</div>{body}</div>')


def short_name(kind: str, name: str) -> str:
    """The bench's own plain name, so a summary elsewhere cannot disagree with the card."""
    spec = (OCR if kind == "ocr" else LLM).get(name)
    return spec["name"] if spec else name


def _order(preferred: list[str], available: list[str]) -> list[str]:
    """Preferred order first, then anything the registry gained that this file has not been
    told about — a new provider shows up rather than disappearing."""
    return [n for n in preferred if n in available] + [n for n in available if n not in preferred]


# ── the two benches ─────────────────────────────────────────────────────────
def _ocr_bench(current: str, scope: str, note: str = "") -> None:
    bench = _bench()
    names = _order(OCR_ORDER, reg.OCR_PROVIDERS)
    cols = st.columns(3, gap="small")
    for i, name in enumerate(names):
        spec = OCR.get(name)
        if not spec:
            continue
        av = reg.ocr_availability(name)
        selected = name == current
        facts, unmeasured = _ocr_facts(name, bench, av.ready)
        with cols[i % 3]:
            st.markdown(_card(spec, av.ready, av.note, selected, facts, unmeasured,
                              spec.get("bundled")), unsafe_allow_html=True)
            # An engine that is not installed stays visible but unselectable — hiding it
            # would make the app look like it has fewer options than it has. The install
            # command goes in the tooltip; as a label it truncated to "pip install azure-".
            label = "In use" if selected else ("Use this" if av.ready else "Needs installing")
            if st.button(label, key=f"{scope}_ocr_{name}", width="stretch",
                         help=None if av.ready else f"Not installed here — {av.note}",
                         type="primary" if selected else "secondary",
                         disabled=selected or not av.ready):
                st.session_state["ocr_provider"] = name
                st.rerun()

    if note:
        st.markdown(f'<div class="ebnote"><div>{note}</div></div>', unsafe_allow_html=True)

    b = _bench()
    stamp = (f'Measured {b.get("measured_on", "—")} on {b.get("machine", "this machine")}, '
             f'over <code>{b.get("sample", "the bundled scan")}</code>.' if b else
             'No measurements recorded yet — run <code>python tools/bench_ocr.py</code>.')
    st.markdown(
        '<div class="ebnote"><div><b>RapidOCR and MarkItDown ship with the app</b> — between '
        'them they cover a scanned page and a text PDF, so nothing needs installing for a '
        'normal run. PaddleOCR is a ~1 GB extra kept out of the default install because on '
        'this sample it was no more accurate than RapidOCR and far slower; it earns its place '
        'on non-Latin script, not here. Tesseract needs a system binary and Azure needs a key, '
        'so neither can be bundled.<br><br>' + stamp + '</div></div>',
        unsafe_allow_html=True)


def _llm_bench(current: str, scope: str) -> None:
    names = _order(LLM_ORDER, reg.LLM_PROVIDERS)
    cols = st.columns(3, gap="small")
    for i, name in enumerate(names):
        spec = LLM.get(name)
        if not spec:
            continue
        av = reg.llm_availability(name, api_key=st.session_state.get("llm_key"))
        selected = name == current
        facts = "".join(f'<div class="fx"><b class="{tone}">{v}</b><span>{lab}</span></div>'
                        for lab, v, tone in spec["facts"])
        with cols[i % 3]:
            st.markdown(_card(spec, av.ready, av.note, selected, facts, ""),
                        unsafe_allow_html=True)
            # Never blocked for want of a key. Choosing the route is how you GET to the field
            # that takes the key — refusing the click was a dead end with no way forward.
            lib_missing = av.note.startswith("pip install")
            if st.button("In use" if selected else "Use this",
                         key=f"{scope}_llm_{name}", width="stretch",
                         help=av.note if lib_missing else None,
                         type="primary" if selected else "secondary",
                         disabled=selected or lib_missing):
                st.session_state["llm_provider"] = name
                st.rerun()

    _llm_setup(current, scope)


def _llm_setup(provider: str, scope: str) -> None:
    """Key and model for the chosen route, in place.

    The model belongs here rather than on the cards because for a gateway the two are
    different questions: OpenRouter is where the key goes, DeepSeek V4 Flash is what reads
    the law. Values land in plain session_state keys that the run reads.
    """
    # A model id is only meaningful for the route it came from — leaving OpenRouter's
    # "deepseek/deepseek-v4-flash" sitting in the Anthropic box is a config that cannot work.
    if st.session_state.get("llm_model_for") != provider:
        st.session_state["llm_model"] = None
        st.session_state["llm_model_for"] = provider

    if provider == "mock":
        st.markdown('<div class="ebnote">The offline stand-in needs no key and no model. '
                    'It is here so a demo runs with the network unplugged — it is not good '
                    'enough to submit.</div>', unsafe_allow_html=True)
        st.session_state["llm_model"] = None
        st.session_state["llm_key"] = None
        return

    box = st.container(border=True)
    with box:
        st.markdown('<span class="ebmark"></span>', unsafe_allow_html=True)
        _llm_setup_body(provider, scope)


def _llm_setup_body(provider: str, scope: str) -> None:
    if provider == "openrouter":
        st.markdown('<div class="ttl">Which model should judge the law?</div>'
                    '<div class="sub">One OpenRouter key reaches all of these. If the one you '
                    'pick is rate-limited, the run fails over to the next in this list.</div>',
                    unsafe_allow_html=True)
        models = list(reg.OPENROUTER_MODELS)
        cur = st.session_state.get("llm_model")
        idx = models.index(cur) if cur in models else (
            models.index(settings.openrouter_model) if settings.openrouter_model in models else 0)
        st.session_state["llm_model"] = st.selectbox(
            "Model", models, index=idx, key=f"{scope}_or_model",
            label_visibility="collapsed")
        _key_field("OpenRouter API key", "OPENROUTER_API_KEY", settings.openrouter_api_key,
                   "openrouter.ai/keys", scope)

    elif provider == "local":
        st.markdown('<div class="ttl">Your own server</div>'
                    '<div class="sub">Any OpenAI-compatible endpoint. Nothing leaves the '
                    'machine you point this at.</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        url = c1.text_input("Base URL", value=st.session_state.get("local_base_url")
                            or settings.local_llm_base_url, key=f"{scope}_local_url",
                            help="Ollama: http://localhost:11434/v1")
        model = c2.text_input("Model name", value=st.session_state.get("llm_model")
                              or settings.local_llm_model, key=f"{scope}_local_model",
                              help="a model your server actually serves, e.g. qwen2.5:14b")
        st.session_state["local_base_url"] = url.strip()
        settings.local_llm_base_url = url.strip()
        st.session_state["llm_model"] = model.strip() or None
        st.session_state["llm_key"] = None

    else:
        vendor = {"anthropic": ("Anthropic", "ANTHROPIC_API_KEY", settings.anthropic_api_key,
                                settings.anthropic_model, "console.anthropic.com"),
                  "openai": ("OpenAI", "OPENAI_API_KEY", settings.openai_api_key,
                             settings.openai_model, "platform.openai.com/api-keys"),
                  "gemini": ("Google", "GEMINI_API_KEY", settings.gemini_api_key,
                             getattr(settings, "gemini_model", "gemini-2.5-flash"),
                             "aistudio.google.com/apikey")}[provider]
        label, env, configured, default_model, where = vendor
        st.markdown(f'<div class="ttl">Which {label} model should judge the law?</div>'
                    '<div class="sub">Type the model id exactly as your account names it.</div>',
                    unsafe_allow_html=True)
        model = st.text_input("Model", value=st.session_state.get("llm_model") or default_model,
                              key=f"{scope}_{provider}_model", label_visibility="collapsed")
        st.session_state["llm_model"] = model.strip() or None
        _key_field(f"{label} API key", env, configured, where, scope)


def _key_field(label: str, env: str, configured: str | None, where: str, scope: str) -> None:
    """One key field, saying plainly where a key comes from and whether one is already set."""
    if configured:
        st.session_state["llm_key"] = configured
        st.markdown(f'<div class="sub" style="padding-bottom:.7rem">A key is already '
                    f'configured in <code>{env}</code> — nothing to paste.</div>',
                    unsafe_allow_html=True)
        return
    typed = st.text_input(label, type="password", key=f"{scope}_key_{env}",
                          placeholder=f"paste a key, or set {env} in the environment",
                          help=f"Get one at {where}. It is held for this session only and is "
                               f"never written to disk or to the exported files.")
    st.session_state["llm_key"] = typed.strip() or None
    if not typed:
        st.markdown(f'<div class="sub" style="padding-bottom:.7rem">No key yet — get one at '
                    f'<b>{where}</b>, or set <code>{env}</code> in the environment. Without a '
                    f'key the run falls back to the offline stand-in.</div>',
                    unsafe_allow_html=True)


def render(ocr_current: str, llm_current: str, scope: str = "eb",
           ocr_note: str = "") -> None:
    """Draw both benches.

    `scope` keeps widget keys distinct when the bench appears twice (welcome screen and the
    Engines tab) in one session. `ocr_note` is the caller's per-country advisory about which
    recognition model will actually load — it belongs beside the OCR cards, not in a
    settings drawer, because it can contradict the card the user just pressed.
    """
    from . import theme

    theme.inject_style(CSS)

    st.markdown('<div class="kicker" style="margin:.2rem 0 .1rem">Reading the documents '
                '<span class="muted">— how a PDF becomes text</span></div>',
                unsafe_allow_html=True)
    _ocr_bench(ocr_current, scope, ocr_note)

    st.markdown('<div class="kicker" style="margin:1.4rem 0 .1rem">Judging the law '
                '<span class="muted">— which model decides that a provision meets an '
                'indicator</span></div>', unsafe_allow_html=True)
    _llm_bench(llm_current, scope)
