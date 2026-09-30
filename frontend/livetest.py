"""The 15 October live stress test — built against the organisers' own template, not a guess.

An earlier version of this file was written from inference and got three things wrong. The
sources that settle it are in the repo: `Finalist Orientation/Live_Test_Short_Note_TEMPLATE.docx`
and `Finalist Orientation/Meeting notes.docx`. What they actually require:

  * **Any listed country, any pillar**, revealed at 10:00, about sixty minutes to finish.
    "Prepare all economies and languages in advance."
  * **Two engines**, exporting comparable results in the same format.
  * **"Engine swap should be UI-driven, not code-level."** So the switch lives on this screen.
    Reading the declaration back and calling it read-only — which is what this file used to do
    — fails the criterion it was written to satisfy.
  * **The second pass must not fetch.** The template's comparison table has a cell reading
    *"Documents fetched during this pass — must be 0"* for engine B, and the notes say it twice
    more: "the tool must be able to reprocess already-downloaded documents without re-fetching".
    Two live crawls minutes apart differ in what the portal served, so without this an engine
    comparison measures the weather.
  * **"Show cost per run and cost difference between engines."** A number each is not enough;
    the difference is the thing being asked for.
  * **Observers watch, and most actions are expected to be performed through the interface.**
    So the evidence files are downloaded here, from the run in front of you — not found later
    in an output directory.

Design notes worth keeping:

* **A step indicator, not tabs.** "Show progress for multi-step processes" (ui-ux-pro-max, ux /
  Feedback / Progress Indicators). Under a clock the operator needs to know what is done and
  what is next at a glance; tabs invite wandering.
* **Timing, cost and counts are captured, never typed.** All of them already exist on
  `RunMeta` — asking a human to copy them under time pressure only adds errors the code cannot
  make. Section 6 of the note ("anything done by hand") can then honestly say *nothing was*.
* **The comparison marks the winner per row.** Two columns of numbers make the reader do the
  arithmetic; the template asks for a difference, so the screen states one.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import streamlit as st

from backend.config import settings
from backend.export import engine_compare, live_note
from backend.providers import registry as reg
from backend.schemas import LIVE_TEST_POOL, PLACEHOLDER_LAW_NAMES

from .home import MEASURED_PILLARS, PILLAR_SHORT

STEPS = [
    ("Brief", "Any economy, any pillar"),
    ("Run", "Engine A live · engine B on the same documents"),
    ("Compare", "Same work, two engines"),
    ("Hand in", "Evidence, comparison, note"),
]

#: What the assignment can name, listed FIRST in the picker: the panel's eight published
#: countries and the three mandatory ones — eleven, because the instruction on the day is
#: "draw from the listed economies (any pillar)" and the mandatory three are listed too.
#: An ordering, not a restriction; a picker that could not accept an economy would fail at
#: the only moment it exists for.
#:
#: See backend/schemas.LIVE_TEST_POOL.
LIVE_TEST_ORDER = LIVE_TEST_POOL

#: Which way is better, per comparison row. Used to mark the winner rather than leaving the
#: reader to work out whether more minutes is good news.
BETTER = {"Provisions exported": "high", "Rows exported": "high",
          "Absent from the 2025 baseline": "high", "Rows needing review": "low",
          "Elapsed (minutes)": "low", "Cost of this pass (US$)": "low",
          "Found only by this engine": "high",
          "Documents fetched during this pass": None}


def new_state() -> dict:
    return {
        "step": 0,
        "brief": {},
        "runs": {},
        "engines": {
            "A": {"provider": settings.declared_engine_a_provider,
                  "model": settings.declared_engine_a_model},
            "B": {"provider": settings.declared_engine_b_provider,
                  "model": settings.declared_engine_b_model},
        },
        "notes": {"worked": "", "broke": "", "caution": "", "by_hand": ""},
        "started": None,
    }


def economy_order(codes) -> list[str]:
    """Every declared economy, the ones the live test can name first, then the rest."""
    listed = [c for c in LIVE_TEST_ORDER if c in codes]
    return listed + [c for c in codes if c not in listed]


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
  padding:0 !important;margin:0 0 1.4rem 0;
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
.lt-step{flex:1 1 0;display:flex !important;flex-direction:column;gap:.15rem;
  padding:.65rem .85rem;border-right:1px solid var(--line);min-width:0;
  margin:0 !important;list-style:none !important}
.lt-step::marker{content:none}
.lt-step:last-child{border-right:0}
.lt-dot{display:inline-flex;align-items:center;justify-content:center;
  width:1.35rem;height:1.35rem;border-radius:50%;font-size:.76rem;font-weight:600;
  font-variant-numeric:tabular-nums}
.lt-name{font-weight:600;font-size:.92rem}
.lt-hint{font-size:.76rem;color:var(--muted);overflow-wrap:anywhere}
.lt-todo .lt-dot{background:var(--surface-2);color:var(--muted)}
.lt-todo .lt-name{color:var(--muted)}
.lt-now{background:color-mix(in srgb,var(--accent) 8%,transparent)}
.lt-now .lt-dot{background:var(--accent);color:#fff}
.lt-done .lt-dot{background:var(--surface-2);color:var(--accent)}
.lt-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
  white-space:nowrap}

.lt-slot{border:1px solid var(--line);border-radius:10px;padding:.8rem .95rem;
  margin-bottom:.55rem}
.lt-slot h4{margin:0 0 .3rem 0;font-size:.92rem;display:flex;align-items:baseline;gap:.45rem;
  flex-wrap:wrap}
.lt-slot h4 .eng{font-family:var(--mono);font-size:.72rem;font-weight:500;color:var(--muted);
  overflow-wrap:anywhere}
.lt-kv{display:grid;grid-template-columns:auto 1fr;gap:.12rem .9rem;font-size:.86rem;margin:0}
.lt-kv dt{color:var(--muted)}
.lt-kv dd{margin:0;font-family:var(--mono);font-variant-numeric:tabular-nums}
.lt-empty{color:var(--muted);font-size:.86rem}

/* the comparison: the winner per row is marked, because the template asks for a DIFFERENCE */
.lt-cmp{width:100%;border-collapse:collapse;font-size:.88rem}
.lt-cmp th,.lt-cmp td{padding:.42rem .6rem;border-bottom:1px solid var(--line);text-align:right}
.lt-cmp th:first-child,.lt-cmp td:first-child{text-align:left;color:var(--muted)}
.lt-cmp thead th{color:var(--ink);font-weight:600;border-bottom:2px solid var(--line)}
.lt-cmp td{font-family:var(--mono);font-variant-numeric:tabular-nums}
.lt-cmp td.win{color:var(--good);font-weight:700}
.lt-cmp td.win::after{content:" \\25C2";letter-spacing:-.1em}
.lt-delta{font-size:.88rem;color:var(--ink);margin:.8rem 0 0;padding:.65rem .85rem;
  border-radius:9px;background:var(--surface-2);border:1px solid var(--line);line-height:1.6}
.lt-delta b{font-family:var(--mono)}

/* the short-note preview: the template's own layout, one value per line */
.ln{border:1px solid var(--line);border-radius:10px;padding:1rem 1.2rem;line-height:1.55}
.ln h3{margin:0;font-size:1.15rem}
.ln h4{margin:1.1rem 0 .4rem;font-size:.95rem}
.ln-sub{color:var(--muted);font-size:.84rem}
.ln table{width:100%;border-collapse:collapse;font-size:.87rem}
.ln th,.ln td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left;vertical-align:top}
.ln-kv th{width:38%;font-weight:500;color:var(--muted)}
.ln-fig thead th{font-weight:600}
.ln-fig tbody th{font-weight:500;color:var(--muted);width:46%}
.ln-fig td{font-family:var(--mono);font-variant-numeric:tabular-nums}
.ln-must{font-family:inherit;font-size:.75rem;color:var(--muted);margin-left:.4rem}
.ln-two{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media (max-width:720px){.ln-two{grid-template-columns:1fr}}
.ln-list{margin:.2rem 0;padding-left:1.1rem;font-size:.87rem}
.ln-list li{margin:.25rem 0}
.ln p{margin:.2rem 0;font-size:.87rem}
"""


# ── what to expect, before the clock starts ──────────────────────────────────────────
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


# ── artefacts ────────────────────────────────────────────────────────────────────────
def _q(text: str) -> str:
    return str(text or "").replace('"', "'")


def run_record(state: dict) -> str:
    """The Run Record sheet, as CSV. Every field is read from the run, never typed."""
    b = state.get("brief", {})
    lines = ['"Team","Team VeriTrade"',
             f'"Task as read out","{_q(b.get("task"))}"',
             f'"Economy","{_q(b.get("economy"))}"',
             f'"Pillar","{_q(b.get("pillar"))}"',
             "",
             "Engine,Provider / model,Start (UTC),End (UTC),Elapsed (min),Cost (US$),"
             "Documents discovered,Documents fetched,Provisions,Rows exported"]
    for slot in ("A", "B"):
        r = state["runs"].get(slot)
        if not r:
            lines.append(f"Engine {slot},,,,,,,,,")
            continue
        lines.append(",".join([
            f"Engine {slot}", r["model"], r["start"], r["end"],
            f"{r['elapsed_min']:.1f}", f"{r['cost_usd']:.4f}",
            str(r["documents"]), str(r["fetched"]), str(r["provisions"]), str(r["rows"])]))
    return "\n".join(lines) + "\n"


def _diff(a: dict | None, b: dict | None, key: str, fmt: str) -> str:
    if not a or not b:
        return ""
    try:
        return fmt.format(b[key] - a[key])
    except (KeyError, TypeError):
        return ""


def engine_comparison(state: dict) -> str:
    """Engine Comparison, as CSV — the template's own rows, plus the difference it asks for."""
    a, b = state["runs"].get("A"), state["runs"].get("B")

    def cell(r, key, fmt="{}"):
        return fmt.format(r[key]) if r else ""

    rows = [("Field", "Engine A — first pass", "Engine B — second pass", "Difference (B − A)"),
            ("Provider / model", cell(a, "model"), cell(b, "model"), ""),
            ("Provisions read", cell(a, "provisions"), cell(b, "provisions"),
             _diff(a, b, "provisions", "{:+d}")),
            ("Provisions exported", cell(a, "exported"), cell(b, "exported"),
             _diff(a, b, "exported", "{:+d}")),
            ("Absent from the 2025 baseline", cell(a, "new"), cell(b, "new"),
             _diff(a, b, "new", "{:+d}")),
            ("Documents fetched during this pass", cell(a, "fetched"), cell(b, "fetched"),
             "second pass must be 0"),
            ("Elapsed (minutes)", cell(a, "elapsed_min", "{:.1f}"),
             cell(b, "elapsed_min", "{:.1f}"), _diff(a, b, "elapsed_min", "{:+.1f}")),
            ("Cost of this pass (US$)", cell(a, "cost_usd", "{:.4f}"),
             cell(b, "cost_usd", "{:.4f}"), _diff(a, b, "cost_usd", "{:+.4f}")),
            ("Rows exported", cell(a, "rows"), cell(b, "rows"), _diff(a, b, "rows", "{:+d}")),
            ("Rows needing review", cell(a, "review"), cell(b, "review"),
             _diff(a, b, "review", "{:+d}")),
            ("Provisions only this engine found",
             str(a.get("only", "")) if a else "", str(b.get("only", "")) if b else "", "")]
    s = (state.get("compare") or {}).get("summary")
    if s:
        # Provision-level agreement. The full provision-by-provision sheet is its own file
        # (`provision_comparison`); these are its totals, so the two can be checked together.
        rows += [
            ("Provisions found by both engines", s["both"], s["both"], ""),
            ("  of which: indicator differs", s["indicator_differs"], s["indicator_differs"], ""),
            ("  of which: article citation differs", s["citation_differs"],
             s["citation_differs"], ""),
            ("  of which: quoted words differ", s["quote_differs"], s["quote_differs"], ""),
            ("  of which: identical", s["identical"], s["identical"], ""),
        ]
    return "\n".join(",".join(f'"{_q(c)}"' for c in r) for r in rows) + "\n"


def provision_comparison(state: dict) -> bytes | None:
    """Every provision either engine exported, one row each — the comparison note's body."""
    cmp = (state.get("compare") or {}).get("rows")
    return None if cmp is None else engine_compare.to_csv(cmp)


def _provision_sentence(s: dict) -> str:
    return (f"{s['provisions']} distinct provisions across both engines: {s['both']} found by "
            f"both, {s['a_only']} by engine A only, {s['b_only']} by engine B only. Of the "
            f"shared ones, {s['indicator_differs']} differ in indicator, "
            f"{s['citation_differs']} in article citation and {s['quote_differs']} in the "
            f"quoted words; {s['identical']} are identical.")


def short_note(state: dict) -> str:
    """The short note as Markdown, in the organisers' own sections and table rows. The .docx is
    the same content written into their template (`backend/export/live_note.py`)."""
    return live_note.to_markdown(live_note.fields(state))


def short_note_docx(state: dict) -> bytes | None:
    """The organisers' own template, every field filled, ready to print and sign — or None
    when python-docx is absent, so the caller offers the Markdown and the deliverable
    survives a missing optional dependency."""
    try:
        return live_note.to_docx(live_note.fields(state))
    except ImportError:
        return None


# ── capture ──────────────────────────────────────────────────────────────────────────
def capture(state: dict, slot: str, result, started: str, finished: str,
            log_lines: list[str] | None = None) -> None:
    """Record one engine's pass. Reads the run; asks the operator for nothing.

    The whole RunResult is kept, not just its numbers: the evidence files are generated from it
    on the hand-in step, so what the operator downloads is the run in front of them rather than
    whatever a shared output directory happens to hold.
    """
    meta = result.meta
    # The rows this engine hands in (submittable, not placeholders) — the same set as its
    # evidence file. "Provisions exported" is counted per provision over these, which is the
    # template's unit; `provisions` stays the number READ, a different figure.
    rows = [m for m in engine_compare.exported(result.mappings)
            if m.law_name not in PLACEHOLDER_LAW_NAMES]
    n_exported, n_new = engine_compare.provision_counts(rows)
    state["runs"][slot] = {
        "model": meta.model_version or meta.llm_provider,
        "provider": meta.llm_provider,
        "run_id": meta.run_id,
        "start": started, "end": finished,
        "elapsed_s": meta.processing_time_seconds,
        "elapsed_min": meta.processing_time_seconds / 60.0,
        "cost_usd": float((meta.cost or {}).get("total_usd", 0.0)),
        "documents": meta.docs_discovered,
        "fetched": meta.docs_fetched,
        "provisions": meta.provisions_extracted,
        "rows": len(rows),
        "exported": n_exported,
        "review": sum(1 for m in rows if m.review_status.value == "pending_review"),
        "new": n_new,
        # what the run's own log reported as going wrong — section 4 of the note quotes it
        "issues": live_note.run_issues(log_lines),
        "result": result,
    }
    a, b = state["runs"].get("A"), state["runs"].get("B")
    if a and b:                      # each engine's unique finds, computed not counted by hand
        # Per PROVISION, not per (indicator, law, article): a provision both engines found but
        # mapped to different indicators is a disagreement, not two independent finds.
        cmp = engine_compare.compare(a["result"].mappings, b["result"].mappings)
        s = engine_compare.summary(cmp)
        state["compare"] = {"rows": cmp, "summary": s}
        a["only"], b["only"] = s["a_only"], s["b_only"]
    else:
        state.pop("compare", None)


def capture_failure(state: dict, slot: str, error: BaseException, started: str, finished: str,
                    log_lines: list[str] | None = None) -> None:
    """Record a pass that stopped with an error. Zero rows, the error itself and the log's own
    failure lines are kept, so the note reports the break instead of an engine that never ran."""
    try:
        elapsed = (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except (TypeError, ValueError):
        elapsed = 0.0
    eng = state["engines"][slot]
    state["runs"][slot] = {
        "model": eng.get("model", ""), "provider": eng.get("provider", ""), "run_id": "",
        "start": started, "end": finished, "elapsed_s": elapsed, "elapsed_min": elapsed / 60.0,
        "cost_usd": 0.0, "documents": 0, "fetched": 0, "provisions": 0, "rows": 0,
        "exported": 0, "review": 0, "new": 0,
        "failed": f"{type(error).__name__}: {error}",
        "issues": live_note.run_issues(log_lines), "result": None,
    }
    state.pop("compare", None)


def _slot_html(slot: str, engine: dict, r: dict | None) -> str:
    head = (f'<h4>Engine {slot}<span class="eng">{engine.get("provider", "—")} · '
            f'{engine.get("model", "—")}</span></h4>')
    if not r:
        note = ("live — discovers and fetches" if slot == "A"
                else "second pass — re-reads engine A's documents, fetches nothing")
        return (f'<div class="lt-slot">{head}'
                f'<div class="lt-empty">Not run yet · {note}</div></div>')
    if r.get("failed"):
        return (f'<div class="lt-slot">{head}<div class="lt-empty" style="color:var(--bad)">'
                f'Stopped with an error after {r["elapsed_min"]:.1f} min — '
                f'{_esc(r["failed"][:220])}</div></div>')
    return (f'<div class="lt-slot">{head}<dl class="lt-kv">'
            f'<dt>Provisions read</dt><dd>{r["provisions"]}</dd>'
            f'<dt>Provisions exported</dt><dd>{r.get("exported", "—")}</dd>'
            f'<dt>Rows exported</dt><dd>{r["rows"]}</dd>'
            f'<dt>Documents fetched</dt><dd>{r["fetched"]}</dd>'
            f'<dt>Elapsed</dt><dd>{r["elapsed_min"]:.1f} min</dd>'
            f'<dt>Cost</dt><dd>${r["cost_usd"]:.4f}</dd>'
            f'</dl></div>')


def _comparison_html(a: dict, b: dict) -> str:
    rows = [
        ("Provisions read", a["provisions"], b["provisions"], "{}"),
        ("Provisions exported", a.get("exported", 0), b.get("exported", 0), "{}"),
        ("Absent from the 2025 baseline", a["new"], b["new"], "{}"),
        ("Documents fetched during this pass", a["fetched"], b["fetched"], "{}"),
        ("Elapsed (minutes)", a["elapsed_min"], b["elapsed_min"], "{:.1f}"),
        ("Cost of this pass (US$)", a["cost_usd"], b["cost_usd"], "{:.4f}"),
        ("Rows exported", a["rows"], b["rows"], "{}"),
        ("Rows needing review", a["review"], b["review"], "{}"),
        ("Found only by this engine", a.get("only", 0), b.get("only", 0), "{}"),
    ]
    body = [f'<tr><td>Provider / model</td><td>{a["model"]}</td><td>{b["model"]}</td></tr>']
    for label, va, vb, fmt in rows:
        want = BETTER.get(label)
        cls_a = cls_b = ""
        if want and va != vb:
            better_is_a = (va > vb) if want == "high" else (va < vb)
            cls_a, cls_b = (" class='win'", "") if better_is_a else ("", " class='win'")
        body.append(f'<tr><td>{label}</td><td{cls_a}>{fmt.format(va)}</td>'
                    f'<td{cls_b}>{fmt.format(vb)}</td></tr>')
    return ('<table class="lt-cmp"><thead><tr><th></th>'
            '<th>Engine A · first pass</th><th>Engine B · second pass</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def _delta_html(a: dict, b: dict) -> str:
    """The sentence the organisers asked for by name: the cost difference between the engines."""
    d = b["cost_usd"] - a["cost_usd"]
    rel = (f" ({abs(d) / a['cost_usd'] * 100:.0f}% {'more' if d > 0 else 'less'})"
           if a["cost_usd"] > 0 and d else "")
    speed = b["elapsed_min"] - a["elapsed_min"]
    cheaper = "engine B" if d < 0 else ("engine A" if d > 0 else "neither — identical")
    warn = ("" if b["fetched"] == 0 else
            f' <b style="color:var(--bad)">Engine B fetched {b["fetched"]} documents, so this '
            f'pass was not engine-isolated — the template requires 0.</b>')
    return (f'<p class="lt-delta">Engine B cost <b>${abs(d):.4f}</b> '
            f'{"less" if d < 0 else "more"} than engine A{rel} and took '
            f'<b>{abs(speed):.1f} min</b> {"less" if speed < 0 else "more"}. '
            f'Cheaper: <b>{cheaper}</b>.{warn}</p>')


# ── the surface ──────────────────────────────────────────────────────────────────────
def _engine_picker(state: dict, slot: str) -> None:
    """The UI-driven engine swap the criteria require.

    Defaults come from the declaration in `backend/config.py`, the same pair the README prints.
    Editable, because "engine swap should be UI-driven, not code-level" — and because on the
    day a declared model can be rate-limited and the steward needs to watch the switch happen
    rather than watch someone edit a file.
    """
    eng = state["engines"][slot]
    cols = st.columns([1, 1.5, 1.5])
    with cols[0]:
        providers = list(reg.LLM_PROVIDERS)
        idx = providers.index(eng["provider"]) if eng["provider"] in providers else 0
        eng["provider"] = st.selectbox(f"Engine {slot} — provider", providers, index=idx,
                                       key=f"lt_prov_{slot}")
    with cols[1]:
        eng["model"] = st.text_input(f"Engine {slot} — model", value=eng["model"],
                                     key=f"lt_model_{slot}")
    with cols[2]:
        _key_input(slot, eng["provider"])


#: provider → (environment variable, where a key is issued). mock and local take no key.
_KEY_SOURCES = {
    "openrouter": ("OPENROUTER_API_KEY", "openrouter.ai/keys"),
    "anthropic": ("ANTHROPIC_API_KEY", "console.anthropic.com"),
    "openai": ("OPENAI_API_KEY", "platform.openai.com/api-keys"),
    "gemini": ("GEMINI_API_KEY", "aistudio.google.com/apikey"),
}


def _key_input(slot: str, provider: str) -> None:
    """The engine's API key. Held in the widget's own session slot and handed to the run as it
    starts — never copied into `state`, which feeds the run record and the exported note."""
    src = _KEY_SOURCES.get(provider)
    if not src:
        st.text_input(f"Engine {slot} — API key", value="", disabled=True,
                      key=f"lt_keyoff_{slot}", placeholder="not needed for this provider")
        return
    env, where = src
    configured = bool(getattr(settings, env.lower(), ""))
    st.text_input(
        f"Engine {slot} — API key", type="password", key=f"lt_key_{slot}_{provider}",
        placeholder=(f"leave empty to use {env}" if configured else "paste a key"),
        help=(f"Get one at {where}. Held for this session only — never written to disk, the "
              f"run record or the exported note."))
    if configured:
        st.caption(f"A key is set in `{env}`; one pasted here overrides it for this engine.")
    else:
        st.caption(f"No `{env}` set — paste a key, or this engine cannot run.")


def engine_key(slot: str, provider: str) -> str | None:
    """The key typed for this engine, if any (None → the run falls back to the environment)."""
    return (st.session_state.get(f"lt_key_{slot}_{provider}") or "").strip() or None


def render(state: dict, economies: dict[str, str],
           readiness: dict | None = None) -> dict | None:
    """Draw the surface. Returns a run request when the operator presses a run button."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    state.setdefault("engines", new_state()["engines"])
    state.setdefault("notes", new_state()["notes"])
    step = state["step"]
    st.markdown(_steps_html(step), unsafe_allow_html=True)
    request = None
    readiness = readiness or {}

    if step == 0:
        st.caption("Type in whatever the steward reads out. Every economy and every pillar is "
                   "selectable — nothing here is prepared in advance.")
        order = economy_order(list(economies))
        c1, c2 = st.columns([2, 1])
        econ = c1.selectbox(
            "Economy", order, key="lt_econ",
            format_func=lambda c: economies.get(c, c)
            + ("" if c in LIVE_TEST_ORDER else "  (outside the nine)"))
        pillar = c2.selectbox("Pillar", list(range(1, 13)), index=5, key="lt_pillar",
                              format_func=lambda n: f"{n} · {PILLAR_SHORT.get(n, '')}")
        task = st.text_input("The task as read out", key="lt_task",
                             placeholder="the steward's words — this goes into the short note")
        st.markdown(_expect_html(econ, pillar, readiness), unsafe_allow_html=True)

        st.markdown("**The two declared engines** — fixed at submission on 30 September. Swap "
                    "them here if one is unreachable on the day; the run record and the note "
                    "report whatever was actually used.")
        _engine_picker(state, "A")
        _engine_picker(state, "B")

        if st.button("Start the clock", type="primary", width="stretch"):
            state["brief"] = {"economy": economies.get(econ, econ), "code": econ,
                              "pillar": pillar, "task": task}
            state["started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state["step"] = 1
            st.rerun()

    elif step == 1:
        b = state["brief"]
        st.caption(f"{b['economy']} · pillar {b['pillar']}"
                   + (f" · “{b['task']}”" if b.get("task") else ""))
        c1, c2 = st.columns(2)
        for col, slot in ((c1, "A"), (c2, "B")):
            with col:
                st.markdown(_slot_html(slot, state["engines"][slot], state["runs"].get(slot)),
                            unsafe_allow_html=True)
                done = slot in state["runs"]
                # Engine B re-reads engine A's documents, so it needs a pass of A that
                # finished. Without one there is nothing to re-read, and letting it run
                # would crawl the portals instead — the one thing a second pass must not do.
                blocked = slot == "B" and not (state["runs"].get("A") or {}).get("result")
                if st.button("Run again" if done else f"Run engine {slot}",
                             key=f"lt_run_{slot}", width="stretch", disabled=blocked,
                             help=("Engine A has to finish a pass first — engine B "
                                   "re-reads its documents" if blocked else None),
                             type="primary" if (slot == "A" and not done) else "secondary"):
                    request = {"slot": slot, "code": b["code"], "pillar": b["pillar"],
                               **state["engines"][slot]}
        if state["runs"] and st.button("See the comparison", type="primary", width="stretch"):
            state["step"] = 2
            st.rerun()

    elif step == 2:
        a, bb = state["runs"].get("A"), state["runs"].get("B")
        if a and bb:
            st.markdown(_comparison_html(a, bb), unsafe_allow_html=True)
            st.markdown(_delta_html(a, bb), unsafe_allow_html=True)
            cmp = state.get("compare") or {}
            if cmp.get("summary"):
                st.markdown("**Provision by provision** — every provision either engine "
                            "exported, and what differs between them.")
                st.caption(_provision_sentence(cmp["summary"]))
                st.dataframe(
                    engine_compare.table(cmp["rows"]), hide_index=True, width="stretch",
                    column_order=["Provision #", "Law name", "Article (engine A)",
                                  "Article (engine B)", "Found by", "Indicators (engine A)",
                                  "Indicators (engine B)", "What differs"])
        elif a:
            st.info("Only engine A has run. The comparison — and criterion C5b — needs both.")
            m = st.columns(4)
            m[0].metric("Rows", a["rows"])
            m[1].metric("Provisions", a["provisions"])
            m[2].metric("Minutes", f"{a['elapsed_min']:.1f}")
            m[3].metric("Cost (US$)", f"{a['cost_usd']:.4f}")
        else:
            st.info("No run has been captured yet — go back a step and press Run.")
        if st.button("Prepare the hand-in", type="primary", width="stretch"):
            state["step"] = 3
            st.rerun()

    elif step == 3:
        _hand_in(state)

    if step and st.button("← Back a step", key="lt_back"):
        state["step"] = step - 1
        st.rerun()
    return request


def _hand_in(state: dict) -> None:
    """Everything that leaves the building, generated from the runs in front of the operator."""
    import json                                               # noqa: PLC0415

    from backend.export import csv_text                       # noqa: PLC0415
    from backend.export.json_export import build_payload      # noqa: PLC0415

    b = state.get("brief", {})
    stem = f"VeriTrade_{b.get('code', 'XX')}_P{b.get('pillar', '')}"

    st.markdown("**The evidence** — the mapped provisions themselves, in the official "
                "14-column format, one file per engine, plus the full JSON trace.")
    for slot in ("A", "B"):
        r = state["runs"].get(slot)
        if not r:
            continue
        res = r.get("result")
        cols = st.columns([1.6, 1, 1])
        cols[0].markdown(
            f'<div class="lt-slot" style="margin:0"><h4>Engine {slot}'
            f'<span class="eng">{r["model"]} · {r["rows"]} rows</span></h4></div>',
            unsafe_allow_html=True)
        if res is None:
            cols[1].caption("this run is not held in the session any more")
            continue
        cols[1].download_button(f"Evidence {slot} (.csv)", csv_text(res.mappings),
                                f"{stem}_engine{slot}.csv", "text/csv", width="stretch",
                                key=f"lt_csv_{slot}")
        cols[2].download_button(f"Trace {slot} (.json)",
                                json.dumps(build_payload(res), indent=2, ensure_ascii=False),
                                f"{stem}_engine{slot}.json", "application/json",
                                width="stretch", key=f"lt_json_{slot}")

    st.markdown("**The paperwork** — sections 3 to 5 are drafted from the two runs: what "
                "their logs reported, whether the second pass stayed off the network, where the "
                "engines disagreed and which rows sit lowest. Read them, and edit if the team "
                "knows more; every number elsewhere in the note comes off the runs.")
    n = state["notes"]
    drafts = {"worked": live_note.auto_worked(state), "broke": live_note.auto_broke(state),
              "caution": live_note.auto_caution(state)}

    def _area(col, key, label, height):
        draft = "\n".join(f"• {x}" for x in drafts[key])
        text = col.text_area(label, value=n.get(key) or draft, height=height)
        # Kept only when the operator actually changed it; otherwise the note follows the
        # runs, so re-running an engine refreshes the draft instead of freezing an old one.
        n[key] = "" if text.strip() == draft.strip() else text

    c1, c2 = st.columns(2)
    _area(c1, "worked", "3 · What worked — the part you would fully trust", 200)
    _area(c2, "broke", "4 · What broke — the part you would not fully trust", 200)
    _area(st, "caution", "5 · What a reviewer should be cautious about — rows or indicators", 150)
    n["by_hand"] = st.text_input("6 · Anything done by hand (leave blank if nothing was)",
                                 value=n.get("by_hand", ""))

    fields = live_note.fields(state)
    note_md = live_note.to_markdown(fields)
    d1, d2, d4, d3 = st.columns(4)
    d1.download_button("Run record (.csv)", run_record(state), f"{stem}_run_record.csv",
                       "text/csv", width="stretch")
    d2.download_button("Engine comparison (.csv)", engine_comparison(state),
                       f"{stem}_engine_comparison.csv", "text/csv", width="stretch")
    per_provision = provision_comparison(state)
    if per_provision is not None:
        d4.download_button("Provision comparison (.csv)", per_provision,
                           f"{stem}_provision_comparison.csv", "text/csv", width="stretch")
    else:
        d4.caption("Provision comparison appears once both engines have run.")
    docx = short_note_docx(state)
    if docx:
        d3.download_button(
            "Short note (.docx) — print and sign", docx, f"{stem}_short_note.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch", type="primary")
    else:
        d3.download_button("Short note (.md)", note_md, f"{stem}_short_note.md",
                           "text/markdown", width="stretch")
    with st.expander("Read the note before sending it", expanded=True):
        st.markdown(note_preview_html(fields), unsafe_allow_html=True)


def _esc(t) -> str:
    import html                                              # noqa: PLC0415
    return html.escape(str(t if t is not None else ""))


def _lines_html(text: str) -> str:
    items = [ln.strip() for ln in str(text or "").split("\n") if ln.strip()]
    if all(i.startswith("• ") for i in items) and items:
        return "<ul class='ln-list'>" + "".join(f"<li>{_esc(i[2:])}</li>" for i in items) + "</ul>"
    return "".join(f"<p>{_esc(i)}</p>" for i in items) or "<p>—</p>"


def note_preview_html(f: dict) -> str:
    """The note as it will print: the template's sections, its label/value rows and its
    two-column figures table — one value per line, not a run-on paragraph."""
    run_rows = [("Team name", f["team"]), ("The task as read out", f["task"]),
                ("Engine A, first pass — provider and model", f["engine_a"]),
                ("Engine B, second pass — provider and model", f["engine_b"]),
                ("Machine used, and time submitted", f["machine_time"])]
    out_rows = [("Provisions exported", "exported"),
                ("Of those, absent from the 2025 baseline", "new"),
                ("Documents fetched during this pass", "fetched"),
                ("Elapsed (minutes)", "elapsed"), ("Cost of this pass (US$)", "cost")]
    kv = "".join(f"<tr><th scope='row'>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in run_rows)
    fig = "".join(
        f"<tr><th scope='row'>{_esc(label)}</th><td>{_esc(f[k][0])}</td><td>{_esc(f[k][1])}"
        + (" <span class='ln-must'>must be 0</span>" if k == "fetched" else "") + "</td></tr>"
        for label, k in out_rows)
    hand = (f"☐ Nothing was typed in by hand &nbsp; ☒ Something was — {_esc(f['by_hand'])}"
            if f["by_hand"] else "☒ Nothing was typed in by hand &nbsp; ☐ Something was")
    return (
        "<div class='ln'>"
        "<h3>Live test — short note</h3><div class='ln-sub'>Finale morning, 15 October 2026</div>"
        f"<h4>1 · The run</h4><table class='ln-kv'>{kv}</table>"
        "<h4>2 · What came out</h4><table class='ln-fig'><thead><tr><th></th><th>Engine A</th>"
        f"<th>Engine B</th></tr></thead><tbody>{fig}</tbody></table>"
        "<div class='ln-two'>"
        f"<section><h4>3 · What worked</h4>{_lines_html(f['worked'])}</section>"
        f"<section><h4>4 · What broke</h4>{_lines_html(f['broke'])}</section></div>"
        f"<h4>5 · What a reviewer should be cautious about</h4>{_lines_html(f['caution'])}"
        f"<h4>6 · Anything done by hand</h4><p>{hand}</p>"
        "<h4>7 · Declaration</h4><p class='ln-sub'>Signed, named and initialled on the printed "
        "copy.</p></div>")


def brief_screen(*, economy: str, pillar: int, ocr_label: str, llm_label: str) -> None:
    """The live-test surface as a top-level screen, reached before any run exists.

    It used to be a tab inside the results, which meant it was unreachable until a run had
    already been done — and on the day there is no earlier run to open it from. Worse, the tab
    version ended with "run engine A from the sidebar", and the sidebar had been removed two
    redesigns earlier: an instruction pointing at a control that no longer exists.

    Here the run buttons run. Pressing one hands the request to the same pipeline the Run
    screen uses, records which engine slot it belongs to, and returns to this screen with the
    result captured — so the operator never leaves the checklist.
    """
    from . import geo                                   # noqa: PLC0415 — avoids an import cycle

    st.markdown("#### Live stress test")
    st.caption("One economy and one pillar, read out by the steward on the day. Engine A runs "
               "live; engine B re-reads engine A's documents and fetches nothing, so the only "
               "difference between the two passes is the engine.")
    if "livetest" not in st.session_state:
        st.session_state["livetest"] = new_state()
    econ_names = st.session_state.get("_econ_names") or {}
    request = render(st.session_state["livetest"], econ_names, readiness=geo.readiness())
    if request:
        # Drive the ordinary pipeline. The slot is remembered so the completed run is filed
        # against the right engine without the operator copying anything.
        st.session_state["economy"] = request["code"]
        st.session_state["pillar"] = request["pillar"]
        st.session_state["use_samples"] = False
        st.session_state["fresh_run"] = True
        st.session_state["llm_provider"] = request["provider"]
        st.session_state["llm_model"] = request["model"]
        # This engine's own key, or None so the run reads the provider's key from the
        # environment — never a key left over from another provider on the Engines screen.
        st.session_state["llm_key"] = engine_key(request["slot"], request["provider"])
        st.session_state["lt_pending"] = request["slot"]
        st.session_state["lt_started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # The whole point of the second pass: no portal is contacted.
        first = st.session_state["livetest"]["runs"].get("A", {}).get("result")
        st.session_state["lt_reuse"] = (list(first.meta.documents)
                                        if request["slot"] == "B" and first else None)
        st.session_state["run_requested"] = True
        st.rerun()
