"""The 15 October hour, as four steps that produce three files.

The live test is not another way to run the tool. It is a fixed, timed procedure with a
deliverable, and the pieces are already scored elsewhere in the app — a run, an engine switch,
an export. What is missing is the *shape*: one economy, one pillar, two indicators, announced at
the start of the hour and not before; the same work done twice, once per declared engine; and
three artefacts handed in at the end.

So this surface is a checklist, not a control panel. Every decision that can be made in advance
has been made in advance, and what remains on the day is: type what the steward announced, press
run twice, download three files.

Design notes, kept because the reasoning is easy to lose:

* **A step indicator, not tabs.** "Show progress for multi-step processes" (ui-ux-pro-max, ux /
  Feedback / Progress Indicators). Tabs invite wandering; under time pressure the operator needs
  to know what is done and what is next, at a glance.
* **Timing and cost are captured, never typed.** The Run Record asks for start, end, elapsed and
  cost per engine. Every one of those already exists — `RunMeta.cost` from `backend/metering.py`
  and the run timestamps — so asking a human to copy them under time pressure would only
  introduce errors the code cannot make.
* **The engines are read, not chosen.** They were declared on the submission and cannot change;
  offering a picker here would imply otherwise. The switch that C5b marks lives on the Engines
  screen, where a steward can watch it happen.
* **Minimal text.** Each step is one line of instruction and one control. The explanation of why
  lives in this docstring and in the README, not on a screen someone is reading against a clock.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import streamlit as st

STEPS = [
    ("Brief", "What the steward announced"),
    ("Run", "Once per declared engine"),
    ("Compare", "Same work, two engines"),
    ("Hand in", "Three files"),
]

#: The nine the sealed test draws from. Named here rather than derived from the full economy
#: list, because being READY for an economy and merely being able to name it are different
#: claims — and this screen is used at the one moment the difference matters.
LIVE_TEST_ORDER = ("TH", "VN", "ID", "CN", "IN", "KZ", "LA", "MN", "RU")


def new_state() -> dict:
    return {"step": 0, "brief": {}, "runs": {}, "started": None}


# ── step indicator ───────────────────────────────────────────────────────────────────
def _steps_html(current: int) -> str:
    cells = []
    for i, (name, hint) in enumerate(STEPS):
        state = "done" if i < current else ("now" if i == current else "todo")
        mark = "✓" if i < current else str(i + 1)
        cells.append(
            f'<li class="lt-step lt-{state}">'
            f'<span class="lt-dot" aria-hidden="true">{mark}</span>'
            f'<span class="lt-name">{name}</span>'
            f'<span class="lt-hint">{hint}</span></li>')
    return (f'<ol class="lt-steps" aria-label="Live test progress">{"".join(cells)}</ol>'
            f'<p class="lt-sr">Step {current + 1} of {len(STEPS)}: {STEPS[current][0]}</p>')


CSS = """
.lt-steps{display:flex;gap:0;list-style:none;padding:0;margin:0 0 1.5rem 0;
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
.lt-step{flex:1;display:flex;flex-direction:column;gap:.15rem;padding:.7rem .9rem;
  border-right:1px solid var(--line);min-width:0}
.lt-step:last-child{border-right:0}
.lt-dot{display:inline-flex;align-items:center;justify-content:center;
  width:1.4rem;height:1.4rem;border-radius:50%;font-size:.78rem;font-weight:600;
  font-variant-numeric:tabular-nums}
.lt-name{font-weight:600;font-size:.95rem}
.lt-hint{font-size:.8rem;color:var(--muted);overflow-wrap:anywhere}
.lt-todo .lt-dot{background:var(--surface-2);color:var(--muted)}
.lt-todo .lt-name{color:var(--muted)}
.lt-now{background:color-mix(in srgb,var(--accent) 8%,transparent)}
.lt-now .lt-dot{background:var(--accent);color:#fff}
.lt-done .lt-dot{background:var(--surface-2);color:var(--accent)}
.lt-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
  white-space:nowrap}
.lt-slot{border:1px solid var(--line);border-radius:10px;padding:.85rem 1rem;margin-bottom:.6rem}
.lt-slot h4{margin:0 0 .35rem 0;font-size:.95rem}
.lt-kv{display:grid;grid-template-columns:auto 1fr;gap:.15rem 1rem;font-size:.88rem}
.lt-kv dt{color:var(--muted)}
.lt-kv dd{margin:0;font-family:var(--mono);font-variant-numeric:tabular-nums}
.lt-empty{color:var(--muted);font-size:.88rem}
"""


# ── artefacts ────────────────────────────────────────────────────────────────────────
def run_record(state: dict) -> str:
    """The Run Record sheet, as CSV. Every field is read from the run, never typed."""
    lines = ["Engine,Provider / model,Start (UTC),End (UTC),Elapsed (min),Cost (US$),"
             "Documents,Provisions,Rows"]
    for slot in ("A", "B"):
        r = state["runs"].get(slot)
        if not r:
            lines.append(f"Engine {slot},,,,,,,,")
            continue
        lines.append(",".join([
            f"Engine {slot}", r["model"], r["start"], r["end"],
            f"{r['elapsed_s'] / 60:.1f}", f"{r['cost_usd']:.4f}",
            str(r["documents"]), str(r["provisions"]), str(r["rows"])]))
    return "\n".join(lines) + "\n"


def engine_comparison(state: dict) -> str:
    """Engine Comparison, as CSV. The same work done twice, so the differences are the finding."""
    a, b = state["runs"].get("A"), state["runs"].get("B")
    rows = [("Field", "Engine A — first pass", "Engine B — second pass"),
            ("Provider / model", a and a["model"] or "", b and b["model"] or ""),
            ("Elapsed (min)", a and f"{a['elapsed_s']/60:.1f}" or "",
             b and f"{b['elapsed_s']/60:.1f}" or ""),
            ("Cost (US$)", a and f"{a['cost_usd']:.4f}" or "",
             b and f"{b['cost_usd']:.4f}" or ""),
            ("Documents discovered", a and str(a["documents"]) or "",
             b and str(b["documents"]) or ""),
            ("Provisions extracted", a and str(a["provisions"]) or "",
             b and str(b["provisions"]) or ""),
            ("Rows exported", a and str(a["rows"]) or "", b and str(b["rows"]) or ""),
            ("Rows needing review", a and str(a["review"]) or "", b and str(b["review"]) or ""),
            ("Rows the other engine did not find", a and str(a.get("only", "")) or "",
             b and str(b.get("only", "")) or "")]
    return "\n".join(",".join(f'"{c}"' for c in r) for r in rows) + "\n"


def short_note(state: dict) -> str:
    """The short note, as Markdown — a .docx is produced from it at download time if
    python-docx is available, and the Markdown is always offered as the fallback so the hour
    never depends on an optional dependency."""
    b = state.get("brief", {})
    a, bb = state["runs"].get("A"), state["runs"].get("B")
    n_new = sum(r.get("new", 0) for r in (a, bb) if r)
    lines = [
        "# Live test — short note", "",
        f"**Economy:** {b.get('economy', '')}    **Pillar:** {b.get('pillar', '')}",
        f"**Indicators:** {b.get('indicators', '')}", "",
        "## What the tool found", "",
        f"- Documents discovered: {a['documents'] if a else '—'}",
        f"- Provisions extracted: {a['provisions'] if a else '—'}",
        f"- Rows exported: {a['rows'] if a else '—'}",
        f"- Provisions we believe absent from the 2025 baseline: **{n_new}**", "",
        "## Engines", "",
        f"- Engine A: {a['model'] if a else '—'} — "
        f"{a['elapsed_s']/60:.1f} min, ${a['cost_usd']:.4f}" if a else "- Engine A: —",
        f"- Engine B: {bb['model'] if bb else '—'} — "
        f"{bb['elapsed_s']/60:.1f} min, ${bb['cost_usd']:.4f}" if bb else "- Engine B: —", "",
        "## What we could not read", "",
        b.get("limits", "_(fill in on the day: any document the tool flagged but could not "
                        "extract, and why)_"), "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by VeriTrade._",
    ]
    return "\n".join(lines) + "\n"


def short_note_docx(md: str) -> bytes | None:
    """The note as .docx, or None when python-docx is absent — the caller then offers the
    Markdown, so a missing optional dependency costs formatting and never the deliverable."""
    try:
        from docx import Document
    except Exception:
        return None
    doc = Document()
    for line in md.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):
            doc.add_heading(s[2:], level=1)
        elif s.startswith("## "):
            doc.add_heading(s[3:], level=2)
        elif s.startswith("- "):
            doc.add_paragraph(s[2:].replace("**", ""), style="List Bullet")
        else:
            doc.add_paragraph(s.replace("**", ""))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── capture ──────────────────────────────────────────────────────────────────────────
def capture(state: dict, slot: str, result, started: str, finished: str) -> None:
    """Record one engine's pass. Reads the run; asks the operator for nothing."""
    meta = result.meta
    cost = (meta.cost or {}).get("total_usd", 0.0)
    rows = [m for m in result.mappings if m.law_name != "No provision found"]
    state["runs"][slot] = {
        "model": meta.model_version or meta.llm_provider,
        "start": started, "end": finished,
        "elapsed_s": meta.processing_time_seconds,
        "cost_usd": float(cost),
        "documents": meta.docs_discovered,
        "provisions": meta.provisions_extracted,
        "rows": len(rows),
        "review": sum(1 for m in rows if m.review_status.value == "pending_review"),
        "new": sum(1 for m in rows if m.discovery_tag.value == "NEW"),
        "keys": {f"{m.indicator_id}|{m.law_name}|{m.article_section}" for m in rows},
    }
    a, b = state["runs"].get("A"), state["runs"].get("B")
    if a and b:                      # each engine's unique finds, computed not counted by hand
        a["only"] = len(a["keys"] - b["keys"])
        b["only"] = len(b["keys"] - a["keys"])


def _slot_html(slot: str, r: dict | None) -> str:
    if not r:
        return (f'<div class="lt-slot"><h4>Engine {slot}</h4>'
                f'<p class="lt-empty">Not run yet.</p></div>')
    return (
        f'<div class="lt-slot"><h4>Engine {slot} — {r["model"]}</h4><dl class="lt-kv">'
        f'<dt>Elapsed</dt><dd>{r["elapsed_s"] / 60:.1f} min</dd>'
        f'<dt>Cost</dt><dd>${r["cost_usd"]:.4f}</dd>'
        f'<dt>Documents</dt><dd>{r["documents"]}</dd>'
        f'<dt>Provisions</dt><dd>{r["provisions"]}</dd>'
        f'<dt>Rows</dt><dd>{r["rows"]}</dd>'
        f'<dt>Needs review</dt><dd>{r["review"]}</dd>'
        f'</dl></div>')


def render(state: dict, economies: dict[str, str]) -> dict | None:
    """Draw the surface. Returns a run request when the operator presses a run button."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    step = state["step"]
    st.markdown(_steps_html(step), unsafe_allow_html=True)
    request = None

    if step == 0:
        st.caption("Type what the steward announced. Nothing here is known in advance.")
        c1, c2 = st.columns([2, 1])
        ready = [c for c in LIVE_TEST_ORDER if c in economies]
        econ = c1.selectbox("Economy", ready, format_func=lambda c: economies[c],
                            key="lt_econ")
        pillar = c2.selectbox("Pillar", list(range(1, 13)), index=5, key="lt_pillar")
        inds = st.text_input("The two indicators", placeholder="e.g. 6.2 and 6.4",
                             key="lt_inds")
        if st.button("Start the hour", type="primary", use_container_width=True):
            state["brief"] = {"economy": economies[econ], "code": econ,
                              "pillar": pillar, "indicators": inds}
            state["started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state["step"] = 1
            st.rerun()

    elif step == 1:
        b = state["brief"]
        st.caption(f"{b['economy']} · pillar {b['pillar']} · {b['indicators']}")
        c1, c2 = st.columns(2)
        for col, slot in ((c1, "A"), (c2, "B")):
            with col:
                st.markdown(_slot_html(slot, state["runs"].get(slot)), unsafe_allow_html=True)
                label = f"Run engine {slot}" + (" again" if slot in state["runs"] else "")
                if st.button(label, key=f"lt_run_{slot}", use_container_width=True,
                             type="primary" if slot not in state["runs"] else "secondary"):
                    request = {"slot": slot, "code": b["code"], "pillar": b["pillar"]}
        if len(state["runs"]) == 2 and st.button("Both engines done", type="primary",
                                                 use_container_width=True):
            state["step"] = 2
            st.rerun()

    elif step == 2:
        a, bb = state["runs"]["A"], state["runs"]["B"]
        st.caption("Same economy, same pillar, same hour — so every difference is the engine.")
        st.dataframe(
            [{"": k,
              "Engine A": va, "Engine B": vb}
             for k, va, vb in [
                 ("Model", a["model"], bb["model"]),
                 ("Elapsed (min)", f"{a['elapsed_s']/60:.1f}", f"{bb['elapsed_s']/60:.1f}"),
                 ("Cost (US$)", f"{a['cost_usd']:.4f}", f"{bb['cost_usd']:.4f}"),
                 ("Rows", a["rows"], bb["rows"]),
                 ("Needs review", a["review"], bb["review"]),
                 ("Found only by this engine", a.get("only", "—"), bb.get("only", "—"))]],
            hide_index=True, use_container_width=True)
        if st.button("Prepare the hand-in", type="primary", use_container_width=True):
            state["step"] = 3
            st.rerun()

    elif step == 3:
        st.caption("Three files. Everything in them was measured, not typed.")
        note_md = short_note(state)
        c1, c2, c3 = st.columns(3)
        c1.download_button("Run record (.csv)", run_record(state), "run_record.csv",
                           "text/csv", use_container_width=True)
        c2.download_button("Engine comparison (.csv)", engine_comparison(state),
                           "engine_comparison.csv", "text/csv", use_container_width=True)
        docx = short_note_docx(note_md)
        if docx:
            c3.download_button("Short note (.docx)", docx, "live_test_short_note.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               use_container_width=True)
        else:
            c3.download_button("Short note (.md)", note_md, "live_test_short_note.md",
                               "text/markdown", use_container_width=True)
        with st.expander("Read the note before sending it"):
            st.markdown(note_md)

    if step and st.button("← Back a step", key="lt_back"):
        state["step"] = step - 1
        st.rerun()
    return request


def brief_screen(*, economy: str, pillar: int, ocr_label: str, llm_label: str) -> None:
    """The live-test surface as a top-level screen, reached before any run exists.

    It used to be a tab inside the results, which meant it was unreachable until a run had
    already been done — and on the day there is no earlier run to open it from. Worse, the tab
    version ended with "run engine A from the sidebar", and the sidebar had been removed two
    redesigns earlier: an instruction pointing at a control that no longer exists.

    Here the run button IS the run. Pressing it hands the request to the same pipeline the Run
    screen uses, records which engine slot it belongs to, and returns to this screen with the
    result captured — so the operator never leaves the checklist.
    """
    st.markdown("#### The sealed hour")
    st.caption(f"Declared engines: {ocr_label} · {llm_label} — frozen at submission and read, "
               "not chosen. Everything in the three files is measured by the run.")
    if "livetest" not in st.session_state:
        st.session_state["livetest"] = new_state()
    econ_names = st.session_state.get("_econ_names") or {}
    request = render(st.session_state["livetest"], econ_names)
    if request:
        # Drive the ordinary pipeline. The slot is remembered so the completed run is filed
        # against the right engine without the operator copying anything.
        st.session_state["economy"] = request["code"]
        st.session_state["pillar"] = request["pillar"]
        st.session_state["use_samples"] = False
        st.session_state["fresh_run"] = True
        st.session_state["lt_pending"] = request["slot"]
        st.session_state["lt_started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st.session_state["run_requested"] = True
        st.rerun()
