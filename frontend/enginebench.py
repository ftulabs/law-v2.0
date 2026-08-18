"""The engine bench — choosing the OCR reader and the language model on the main screen.

Provider-swappability is one of the scored requirements, and it used to be two dropdowns
inside a collapsed "Advanced settings" expander: the thing judges ask about, hidden behind
the thing most users never open. Here each engine states what it is *for*, whether it is
actually installed on this machine, whether the document leaves the building, and what it
costs — so a non-technical researcher can choose on those grounds rather than on brand
names.

Every number shown is either measured in this repo or a plain fact about the engine. Where
we have not measured something, the card says so instead of inventing a figure — an engine
comparison that quietly makes numbers up is worse than no comparison at all.

Built from ordinary Streamlit buttons rather than a custom component: a button is
keyboard-reachable and screen-reader-labelled for free, and the bench needs no state the
session cannot already hold.
"""
from __future__ import annotations

import streamlit as st

from backend.providers import registry as reg

# Bench order, which is not the registry's order: the everyday choice first, the
# specialist engines next, and the offline stand-in last — it is a demo aid, not an
# engine anyone should reach for by accident.
OCR_ORDER = ["rapidocr", "markitdown", "paddle", "tesseract", "azure", "mock"]
LLM_ORDER = ["openrouter", "anthropic", "openai", "gemini", "local", "mock"]

# ── what each engine is for, and what we can honestly say about it ──────────
# "err" is the character error rate measured by tests/test_scanned_ocr.py on the bundled
# scanned gazette. Only the engines that test actually runs get a number.
OCR: dict[str, dict] = {
    "markitdown": {
        "name": "MarkItDown",
        "role": "Reads a PDF's own text layer. Exact and fastest — but only when the "
                "document is not a scan.",
        "facts": [("Error rate", "none — not OCR", "good"), ("Speed", "~1 s / document", ""),
                  ("Cost", "free", "good"), ("Documents", "stay on this machine", "")],
    },
    "rapidocr": {
        "name": "RapidOCR",
        "role": "Recognises the words in a scanned page as an image. Installs with pip and "
                "runs without a GPU.",
        "facts": [("Error rate", "1.11 % measured", "good"), ("Speed", "~14 s / document", ""),
                  ("Cost", "free", "good"), ("Documents", "stay on this machine", "")],
    },
    "paddle": {
        "name": "PaddleOCR",
        "role": "Strongest on non-Latin script — the reader for Thai, Chinese and Mongolian "
                "law in the finals.",
        "facts": [("Error rate", "not measured here", "warn"), ("Install", "~1 GB of models", "warn"),
                  ("Cost", "free", "good"), ("Documents", "stay on this machine", "")],
    },
    "tesseract": {
        "name": "Tesseract",
        "role": "The classic open-source reader. Needs a system install, not just a pip "
                "package.",
        "facts": [("Error rate", "not measured here", "warn"), ("Install", "system package", "warn"),
                  ("Cost", "free", "good"), ("Documents", "stay on this machine", "")],
    },
    "azure": {
        "name": "Azure Document Intelligence",
        "role": "The strongest reader for damaged, skewed, real-world gazette scans.",
        "facts": [("Error rate", "not measured here", "warn"), ("Key", "required", "warn"),
                  ("Cost", "billed per page", "warn"), ("Documents", "sent to Microsoft", "warn")],
    },
    "mock": {
        "name": "Offline stand-in",
        "role": "Does not really read anything — returns a fixed sidecar so a demo is "
                "reproducible with no network.",
        "facts": [("Error rate", "not a real reader", "warn"), ("Speed", "instant", ""),
                  ("Cost", "free", "good"), ("Documents", "stay on this machine", "")],
    },
}

LLM: dict[str, dict] = {
    "openrouter": {
        "name": "OpenRouter",
        "role": "The default. Routes to DeepSeek V4 Flash and fails over automatically if a "
                "model is busy.",
        "facts": [("Judgement", "reasons through the legal test", "good"),
                  ("Cost", "~$0.07 per country run", ""), ("Key", "required", "warn"),
                  ("Text", "sent to the provider", "warn")],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "role": "Sharpest on the indicator pairs that get confused — 6.1 against 6.4, "
                "7.1 against 7.2.",
        "facts": [("Judgement", "reasons through the legal test", "good"),
                  ("Cost", "billed per token", ""), ("Key", "required", "warn"),
                  ("Text", "sent to the provider", "warn")],
    },
    "openai": {
        "name": "OpenAI",
        "role": "A second commercial model, for cross-checking a run made with another "
                "provider.",
        "facts": [("Judgement", "reasons through the legal test", "good"),
                  ("Cost", "billed per token", ""), ("Key", "required", "warn"),
                  ("Text", "sent to the provider", "warn")],
    },
    "gemini": {
        "name": "Google Gemini",
        "role": "Strong multilingual reading — useful once the corpus stops being English.",
        "facts": [("Judgement", "reasons through the legal test", "good"),
                  ("Cost", "billed per token", ""), ("Key", "required", "warn"),
                  ("Text", "sent to the provider", "warn")],
    },
    "local": {
        "name": "Self-hosted (Ollama)",
        "role": "Runs on the machine in the room. No key, no network — nothing about the "
                "documents leaves the building.",
        "facts": [("Judgement", "depends on the model you load", "warn"),
                  ("Cost", "free", "good"), ("Key", "none", "good"),
                  ("Text", "never leaves this machine", "good")],
    },
    "mock": {
        "name": "Offline stand-in",
        "role": "Keyword rules, not a model. Reproducible with no network — but it confuses "
                "6.1 with 6.4, so never use it for a submission.",
        "facts": [("Judgement", "keywords only", "warn"), ("Cost", "free", "good"),
                  ("Key", "none", "good"), ("Text", "never leaves this machine", "good")],
    },
}

CSS = """
  .eb{border:1px solid var(--rule);border-radius:13px;background:var(--panel);
    padding:.85rem .95rem .6rem;box-shadow:var(--shadow);position:relative;
    display:flex;flex-direction:column;min-height:214px;
    transition:border-color .18s ease, box-shadow .18s ease;}
  .eb:hover{border-color:color-mix(in srgb,var(--accent) 55%,transparent);}
  .eb.on{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),var(--shadow);}
  .eb .ebh{display:flex;align-items:center;gap:.45rem;}
  .eb .ebh b{font-size:.92rem;font-weight:600;color:var(--ink);line-height:1.25;}
  .eb .st{margin-left:auto;width:9px;height:9px;border-radius:50%;flex:none;}
  .eb .st.up{background:var(--good);box-shadow:0 0 0 3px var(--good-soft);}
  .eb .st.off{background:var(--ink-faint);opacity:.55;}
  .eb .role{font-size:.74rem;color:var(--ink-soft);margin:.4rem 0 .6rem;line-height:1.5;}
  .eb .facts{display:grid;grid-template-columns:1fr 1fr;gap:.35rem .7rem;margin-top:auto;
    padding-top:.55rem;border-top:1px solid var(--rule-soft);}
  .eb .fx{display:flex;flex-direction:column;min-width:0;}
  .eb .fx b{font-family:var(--mono);font-size:.72rem;font-weight:600;color:var(--ink);
    overflow-wrap:anywhere;}
  .eb .fx b.good{color:var(--good);} .eb .fx b.warn{color:var(--warn);}
  .eb .fx span{font-size:.6rem;color:var(--ink-faint);text-transform:uppercase;
    letter-spacing:.06em;}
  .eb .tag{position:absolute;top:-.55rem;right:.8rem;font-size:.6rem;font-weight:600;
    letter-spacing:.05em;text-transform:uppercase;padding:2px 8px;border-radius:99px;
    background:var(--accent);color:var(--accent-ink);}
  .ebnote{display:flex;gap:.7rem;align-items:flex-start;margin:.9rem 0 0;padding:.75rem .9rem;
    border-radius:12px;background:var(--panel-2);border:1px solid var(--rule);
    font-size:.75rem;color:var(--ink-soft);}
  .ebnote b{color:var(--ink);}
"""


def _card(key: str, spec: dict, ready: bool, note: str, selected: bool) -> str:
    facts = "".join(
        f'<div class="fx"><b class="{tone}">{value}</b><span>{label}</span></div>'
        for label, value, tone in spec["facts"])
    tag = '<span class="tag">In use</span>' if selected else ""
    dot = "up" if ready else "off"
    title = note if not ready else "ready on this machine"
    return (f'<div class="eb{" on" if selected else ""}">{tag}'
            f'<div class="ebh"><b>{spec["name"]}</b>'
            f'<span class="st {dot}" title="{title}"></span></div>'
            f'<div class="role">{spec["role"]}</div>'
            f'<div class="facts">{facts}</div></div>')


def _group(kind: str, specs: dict, providers: list[str], current: str,
           availability, state_key: str, keyprefix: str) -> None:
    cols = st.columns(3, gap="small")
    for i, name in enumerate(providers):
        spec = specs.get(name)
        if not spec:
            continue
        av = availability(name)
        selected = name == current
        with cols[i % 3]:
            st.markdown(_card(name, spec, av.ready, av.note, selected),
                        unsafe_allow_html=True)
            # An engine that is not installed stays visible but unselectable — hiding it
            # would make the app look like it has fewer options than it does. The button
            # says only that it needs setup; the install command goes in the tooltip,
            # because a truncated "pip install azure-ai-vision-" is not a usable label.
            label = "In use" if selected else ("Use this" if av.ready else "Needs setup")
            if st.button(label, key=f"{keyprefix}_{name}", width="stretch",
                         help=None if av.ready else f"Not available yet — {av.note}",
                         type="primary" if selected else "secondary",
                         disabled=selected or not av.ready):
                st.session_state[state_key] = name
                st.rerun()


def _order(preferred: list[str], available: list[str]) -> list[str]:
    """Preferred order first, then anything the registry gained that this file has not
    been told about — a new provider shows up rather than disappearing."""
    return [n for n in preferred if n in available] + [n for n in available if n not in preferred]


def render(ocr_current: str, llm_current: str) -> None:
    """Draw both benches. Selection is written to session_state and picked up by the run."""
    from . import theme

    theme.inject_style(CSS)

    st.markdown('<div class="kicker" style="margin:.2rem 0 .1rem">Reading the documents '
                '<span class="muted">— how a PDF becomes text</span></div>',
                unsafe_allow_html=True)
    _group("ocr", OCR, _order(OCR_ORDER, reg.OCR_PROVIDERS), ocr_current,
           reg.ocr_availability, "ocr_provider", "ebocr")

    st.markdown('<div class="kicker" style="margin:1.3rem 0 .1rem">Judging the law '
                '<span class="muted">— what decides that a provision meets an indicator'
                '</span></div>', unsafe_allow_html=True)
    _group("llm", LLM, _order(LLM_ORDER, reg.LLM_PROVIDERS), llm_current,
           reg.llm_availability, "llm_provider", "ebllm")

    st.markdown(
        '<div class="ebnote"><b>These are facts, not marketing.</b> The 1.11 % error rate is '
        'measured by the test suite on the bundled scanned gazette; where an engine has not '
        'been measured here the card says so rather than showing a number we did not take. '
        'A greyed-out engine is one this machine cannot run yet — the button says what it '
        'needs. Swapping an engine and running again keeps both runs in your history, so the '
        'two can be compared.</div>', unsafe_allow_html=True)
