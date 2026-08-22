"""The 15 October live stress test: any economy, any pillar, named on the day.

The instruction for the day is deliberately open — a steward names ONE economy and ONE pillar,
with no notice, and the tool has to go and find the law. So this is not a rehearsal surface for
the ground we happen to have covered: both pickers offer everything the tool declares, and the
screen says plainly what to expect from that particular combination before the clock starts.

What it adds over the ordinary Run screen is the *shape* of the hour: a brief that is typed in
rather than prepared, one run against the live portals, an optional second run on the other
declared engine (which is what C5b marks), and three artefacts at the end.

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
* **The second engine is optional.** Running the brief twice is worth doing when the clock
  allows. Making it mandatory would strand the operator mid-flow, with nothing to hand in, on
  exactly the day a first run turns out to be slow.
* **The screen states the risk before the run, not after.** Being able to NAME an economy and
  being ready for it are different claims, and the one moment that difference matters is this
  one. Step 1 says which it is.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import streamlit as st

STEPS = [
    ("Brief", "Any economy, any pillar"),
    ("Run", "Live, against the real portals"),
    ("Result", "What came back, and what it cost"),
    ("Hand in", "Three files"),
]

#: The nine the panel's 2025 database covers, listed FIRST in the picker because those are the
#: ones the brief says the test draws from. They are an ordering, not a restriction: the
#: instruction on the day is "any economy, any pillar", and a picker that could not accept
#: Singapore — or a pillar nobody expected — would fail at the only moment it exists for.
LIVE_TEST_ORDER = ("TH", "VN", "ID", "CN", "IN", "KZ", "LA", "MN", "RU")


def new_state() -> dict:
    return {"step": 0, "brief": {}, "runs": {}, "started": None}


def economy_order(codes) -> list[str]:
    """Every declared economy, the live-test nine first, then the rest."""
    nine = [c for c in LIVE_TEST_ORDER if c in codes]
    return nine + [c for c in codes if c not in nine]


#: Pillar labels, borrowed from the start screen so the two surfaces name a pillar the same
#: way. home.py does not import this module, so there is no cycle.
from .home import MEASURED_PILLARS, PILLAR_SHORT      # noqa: E402


#: What each rung means for someone about to press Run under a clock — the READINESS ladder
#: read as a forecast rather than as a status.
_EXPECT = {
    "measured": ("Measured end to end", "scored against the panel's own database"),
    "extracted": ("Provisions extracted", "runs live; accuracy not yet scored"),
    "reachable": ("Portal answers", "no adapter yet — discovery may return little or nothing"),
    "declared": ("Declared only", "the portal has not answered us; expect an empty run"),
}


def _expect_html(code: str, pillar: int, readiness: dict) -> str:
    """What this exact (economy, pillar) pair is likely to do.

    Written before the run rather than explained after it. An empty result from an economy at
    the "declared" rung and an empty result from a measured one look identical in the output
    and mean completely different things, and the person watching has sixty minutes.
    """
    row = (readiness or {}).get(code, {})
    level = row.get("level", "declared")
    head, why = _EXPECT.get(level, _EXPECT["declared"])
    measured = pillar in MEASURED_PILLARS
    pill = (f"pillar {pillar} definitions are scored against the answer key" if measured
            else f"pillar {pillar} definitions are coded from the Methodology, never scored")
    return (f'<div class="lt-slot"><h4>What to expect</h4>'
            f'<dl class="lt-kv">'
            f'<dt>Economy</dt><dd>{head} &mdash; {why}</dd>'
            f'<dt>Portal</dt><dd>{row.get("portal", "—")}</dd>'
            f'<dt>Pillar</dt><dd>{pill}</dd>'
            f'<dt>Blocker</dt><dd>{row.get("blocker", "—")}</dd>'
            f'</dl></div>')


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
/* !important on the layout properties, and only those. Streamlit styles `ol`/`li` inside its
   markdown container with a more specific selector than a bare class, so `display:flex` lost
   and the four steps stacked into a narrow vertical column — the border and the numbered dots
   applied, which made it look designed rather than broken. */
.lt-steps{display:flex !important;width:100%;gap:0;list-style:none !important;
  padding:0 !important;margin:0 0 1.5rem 0;
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
.lt-step{flex:1 1 0;display:flex !important;flex-direction:column;gap:.15rem;
  padding:.7rem .9rem;border-right:1px solid var(--line);min-width:0;
  margin:0 !important;list-style:none !important}
.lt-step::marker{content:none}
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


def render(state: dict, economies: dict[str, str], readiness: dict | None = None,
           engines: str = "") -> dict | None:
    """Draw the surface. Returns a run request when the operator presses a run button.

    The shape follows what actually happens on 15 October: a steward names ONE economy and ONE
    pillar — any of them, with no notice — and the tool has to go and find the law. So step 1
    is a pair of pickers over everything we declare, not a menu of what we prepared, and step 2
    is a single button that runs live against the real portals.

    The second engine is offered but not required. Running the same brief twice is what C5b
    marks, and it is worth doing when the clock allows; making it a mandatory step would mean a
    slow first run leaves the operator stranded mid-flow with nothing to hand in.
    """
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    step = state["step"]
    st.markdown(_steps_html(step), unsafe_allow_html=True)
    request = None
    readiness = readiness or {}

    if step == 0:
        st.caption("Type in whatever the steward names. Every economy and every pillar is "
                   "selectable — nothing here is prepared in advance.")
        order = economy_order(list(economies))
        c1, c2 = st.columns([2, 1])
        econ = c1.selectbox(
            "Economy", order, key="lt_econ",
            format_func=lambda c: economies.get(c, c)
                                  + ("" if c in LIVE_TEST_ORDER else "  (outside the nine)"))
        pillar = c2.selectbox("Pillar", list(range(1, 13)), index=5, key="lt_pillar",
                              format_func=lambda n: f"{n} · {PILLAR_SHORT.get(n, '')}")
        inds = st.text_input("Indicators they named, if any",
                             placeholder="e.g. 6.2 and 6.4 — leave blank to search the "
                                         "whole pillar", key="lt_inds")
        st.markdown(_expect_html(econ, pillar, readiness), unsafe_allow_html=True)
        if st.button("Start the clock", type="primary", width="stretch"):
            state["brief"] = {"economy": economies.get(econ, econ), "code": econ,
                              "pillar": pillar, "indicators": inds}
            state["started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state["step"] = 1
            st.rerun()

    elif step == 1:
        b = state["brief"]
        st.caption(f"{b['economy']} · pillar {b['pillar']}"
                   + (f" · {b['indicators']}" if b.get("indicators") else "")
                   + (f" · {engines}" if engines else ""))
        c1, c2 = st.columns(2)
        for col, slot in ((c1, "A"), (c2, "B")):
            with col:
                st.markdown(_slot_html(slot, state["runs"].get(slot)), unsafe_allow_html=True)
                done = slot in state["runs"]
                label = ("Run again" if done else
                         ("Run — engine A" if slot == "A" else "Run — engine B (optional)"))
                if st.button(label, key=f"lt_run_{slot}", width="stretch",
                             disabled=(slot == "B" and "A" not in state["runs"]),
                             type="primary" if (slot == "A" and not done) else "secondary"):
                    request = {"slot": slot, "code": b["code"], "pillar": b["pillar"]}
        if state["runs"] and st.button("See the result", type="primary", width="stretch"):
            state["step"] = 2
            st.rerun()

    elif step == 2:
        a, bb = state["runs"].get("A"), state["runs"].get("B")
        b = state["brief"]
        if bb:
            st.caption("Same economy, same pillar, same hour — so every difference is the "
                       "engine, which is exactly what C5b asks to see.")
            st.dataframe(
                [{"": k, "Engine A": va, "Engine B": vb} for k, va, vb in [
                    ("Model", a["model"], bb["model"]),
                    ("Elapsed (min)", f"{a['elapsed_s']/60:.1f}", f"{bb['elapsed_s']/60:.1f}"),
                    ("Cost (US$)", f"{a['cost_usd']:.4f}", f"{bb['cost_usd']:.4f}"),
                    ("Documents", a["documents"], bb["documents"]),
                    ("Provisions", a["provisions"], bb["provisions"]),
                    ("Rows", a["rows"], bb["rows"]),
                    ("Needs review", a["review"], bb["review"]),
                    ("Found only by this engine", a.get("only", "—"), bb.get("only", "—"))]],
                hide_index=True, width="stretch")
        elif a:
            st.caption(f"{b['economy']} · pillar {b['pillar']} — one engine. Running the "
                       "second is optional and can be done from the previous step.")
            m = st.columns(4)
            m[0].metric("Rows", a["rows"])
            m[1].metric("Provisions read", a["provisions"])
            m[2].metric("Minutes", f"{a['elapsed_s']/60:.1f}")
            m[3].metric("Cost (US$)", f"{a['cost_usd']:.4f}")
            st.caption(f"Engine: {a['model']} · {a['documents']} documents · "
                       f"{a['review']} rows flagged for review")
        else:
            st.info("No run has been captured yet — go back a step and press Run.")
        if st.button("Prepare the hand-in", type="primary", width="stretch"):
            state["step"] = 3
            st.rerun()

    elif step == 3:
        st.caption("Three files. Everything in them was measured by the run, not typed.")
        note_md = short_note(state)
        c1, c2, c3 = st.columns(3)
        c1.download_button("Run record (.csv)", run_record(state), "run_record.csv",
                           "text/csv", width="stretch")
        c2.download_button("Engine comparison (.csv)", engine_comparison(state),
                           "engine_comparison.csv", "text/csv", width="stretch")
        docx = short_note_docx(note_md)
        if docx:
            c3.download_button("Short note (.docx)", docx, "live_test_short_note.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               width="stretch")
        else:
            c3.download_button("Short note (.md)", note_md, "live_test_short_note.md",
                               "text/markdown", width="stretch")
        st.caption("The submission CSV itself is on the Download tab of the run that produced "
                   "it — these three are the live-test paperwork, not the evidence.")
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
    from . import geo                                   # noqa: PLC0415 — avoids an import cycle

    st.markdown("#### Live stress test")
    st.caption("One economy and one pillar, named by the steward on the day. Both pickers "
               "cover everything the tool declares — there is no prepared shortlist.")
    if "livetest" not in st.session_state:
        st.session_state["livetest"] = new_state()
    econ_names = st.session_state.get("_econ_names") or {}
    request = render(st.session_state["livetest"], econ_names,
                     readiness=geo.readiness(),
                     engines=f"{ocr_label} · {llm_label} (declared, frozen)")
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
