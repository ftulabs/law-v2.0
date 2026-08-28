"""The live run, shown as work rather than as a log.

A run takes minutes. The old screen printed the pipeline's own log — `[discovery]
economy=SG pillars=[6]` — which tells a policy researcher nothing about whether the thing
is progressing or has died. This module turns the same stream into five stages, four
counters, one plain-English sentence about what is happening right now, and the findings
landing as they are made. The raw log is still written, into a collapsed expander, because
a technical reviewer does need it.

Nothing here talks to the pipeline: it consumes the same `log()` strings the pipeline
already emits, so the pipeline needs no changes and the two cannot drift apart.
"""
from __future__ import annotations

import html
import re

# Which log prefixes belong to which stage. Order matters — the run only ever moves
# forward, so a late `[fetch]` line (a retry, say) never drags the display backwards.
STAGES = [
    ("Discover", "official portals",
     ("discovery", "discover", "websearch", "zone1", "tag", "doc", "dedup", "crosscheck")),
    ("Fetch", "download documents", ("fetch", "scrapling", "cache")),
    ("Read", "text layer & OCR", ("ocr", "extract", "placeholder")),
    ("Match", "law → indicator",
     ("map", "mapping", "retrieve", "retrieval", "lightrag", "result")),
    ("Score", "confidence & export", ("score", "done", "export")),
]
_STAGE_OF = {p: i for i, (_, _, prefixes) in enumerate(STAGES) for p in prefixes}

_ICONS = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-4.3-4.3"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/>'
    '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"><path d="M4 5h16v14H4z"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"><path d="M4 7h7M4 12h5M4 17h7"/><path d="m14 9 3 3-3 3"/>'
    '<path d="M20 12h-6"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"><path d="M12 3.5 14.6 9l6 .9-4.3 4.2 1 6-5.3-2.8L6.7 20l1-6L3.4 9.9 9.4 9z"/></svg>',
)


def new_state() -> dict:
    return {"stage": 0, "docs": [], "hits": [], "provisions": 0, "pages": 0,
            "now": "Starting up", "sub": "warming the pipeline", "done": False,
            # A run that broke for a KNOWABLE reason used to look exactly like a run that
            # found nothing: same five stages, same counters, same zero. The reason was
            # written — into the collapsed raw log, where the person who needs it never
            # looks. `problem` is (what went wrong, what to do about it); the second half
            # is not optional, because an error with no recovery path is a dead end.
            "problem": None}


def _esc(s) -> str:
    return html.escape(str(s), quote=False)


def absorb(st_: dict, msg: str) -> None:
    """Fold one log line into the display state.

    Every branch is a *translation*, not a filter: the same line still reaches the raw
    log, so nothing a reviewer might need is dropped on the way to plain English.
    """
    m = re.match(r"\[([a-z0-9_]+)\]\s*(.*)", msg, re.S)
    if not m:
        return
    tag, rest = m.group(1), m.group(2).strip()
    st_["stage"] = max(st_["stage"], _STAGE_OF.get(tag, st_["stage"]))

    if tag == "doc":
        title, _, url = rest.partition(" | ")
        st_["docs"].append((title.strip(), url.strip()))
        st_["now"] = "Searching the official portal"
        st_["sub"] = f"{len(st_['docs'])} documents found so far"

    elif tag == "discovery" and "documents" in rest:
        st_["now"] = "Search finished"
        st_["sub"] = rest

    elif tag == "fetch":
        if rest.startswith(("fetched", "cached", "cache hit", "304")):
            st_["now"] = "Downloading the documents"
            st_["sub"] = rest.split(":")[0][:90]
        elif rest.startswith("SPA shell"):
            st_["now"] = "This portal hides its text behind JavaScript"
            st_["sub"] = "opening it in a real browser so the law is readable"

    elif tag == "ocr":
        if rest.startswith("engine="):
            st_["sub"] = rest
        else:
            st_["now"] = "Reading " + rest.split(" via ")[0][:70]
            cer = re.search(r"cer=([\d.]+)", rest, re.I)
            pages = re.search(r"pages=(\d+)", rest)
            if pages:
                st_["pages"] += int(pages.group(1))
            st_["sub"] = (f"character error rate {float(cer.group(1)):.2%} — under the 5% limit"
                          if cer else "reading the text layer, no OCR needed")

    elif tag == "extract":
        n = re.search(r"->\s*(\d+)\s*provisions", rest)
        if n:
            st_["provisions"] += int(n.group(1))
            st_["now"] = "Splitting into articles and sections"
            st_["sub"] = f"{st_['provisions']:,} provisions so far"

    elif tag in ("map", "mapping"):
        st_["now"] = "Testing every provision against the indicators"
        st_["sub"] = rest[:110]

    elif tag == "result":
        # "[result] P7-I2 | Cybersecurity Act 2018 — Section 14 | conf=0.95"
        parts = [p.strip() for p in rest.split("|")]
        ind = parts[0] if parts else rest
        law = parts[1] if len(parts) > 1 else ""
        conf = ""
        for p in parts[2:]:
            c = re.search(r"([\d.]+)", p)
            if c:
                conf = c.group(1)
        st_["hits"].append((f"{ind} — {law}" if law else ind, conf))
        st_["now"] = "Matching laws to indicators"
        st_["sub"] = f"{len(st_['hits'])} matches so far"

    elif tag == "score":
        st_["now"] = "Rating how restrictive each law is"
        st_["sub"] = rest[:110]

    elif tag == "error":
        # The pipeline emits these in pairs: what happened, then what to do. Keep the first
        # as the headline and let the second replace the advice, so the panel always ends on
        # an action rather than on a diagnosis.
        what, advice = st_["problem"] or ("", "")
        if rest.lower().startswith("what to do:"):
            advice = rest.split(":", 1)[1].strip()
        elif what:
            advice = advice or rest
        else:
            what = rest
        st_["problem"] = (what, advice)

    elif tag == "done":
        st_["done"] = True
        st_["now"] = "Finished"
        st_["sub"] = rest[:120]


def track_html(st_: dict) -> str:
    """The five-stage track, the live sentence, and the four counters."""
    stage, done = st_["stage"], st_["done"]
    nodes = ""
    for i, (name, note, _) in enumerate(STAGES):
        cls = "done" if (done or i < stage) else ("active" if i == stage else "")
        rail = ("" if i == len(STAGES) - 1 else
                f'<div class="rvrail"><i style="width:'
                f'{100 if (done or i < stage) else 0}%"></i></div>')
        nodes += (f'<div class="rvstage {cls}">{rail}'
                  f'<div class="rvnode" aria-hidden="true">{_ICONS[i]}</div>'
                  f'<b>{name}</b><span>{note}</span></div>')

    counters = [("Documents found", len(st_["docs"]), ""),
                ("Pages read", st_["pages"], ""),
                ("Provisions read", st_["provisions"], ""),
                ("Laws matched", len(st_["hits"]), "hit")]
    cells = "".join(
        f'<div class="rvc {cls}"><b>{n:,}</b><span>{lab}</span></div>'
        for lab, n, cls in counters)

    spin = "" if done else '<span class="rvspin" aria-hidden="true"></span>'

    # A problem outranks the live sentence: while one is showing, "Testing every provision
    # against the indicators" is not what the run is doing. It is announced with role="alert"
    # (a status region is for progress, not for a stop), and it is marked by a word and a
    # symbol as well as by colour, so it survives a colourblind reader and a greyscale print.
    if st_["problem"]:
        what, advice = st_["problem"]
        body = (f'<div class="rvbad" role="alert">'
                f'<span class="rvbadge" aria-hidden="true">!</span>'
                f'<div><b>This run could not finish properly</b>'
                f'<div class="rvsub">{_esc(what)}</div>'
                + (f'<div class="rvfix"><b>What to do:</b> {_esc(advice)}</div>' if advice else "")
                + '</div></div>')
    else:
        body = (f'<div class="rvnow{" fin" if done else ""}" role="status" aria-live="polite">'
                f'{spin}<div><b>{_esc(st_["now"])}</b>'
                f'<div class="rvsub">{_esc(st_["sub"])}</div></div></div>')

    return (f'<div class="rvtrack">{nodes}</div>{body}'
            f'<div class="rvcounters">{cells}</div>')


def streams_html(st_: dict) -> str:
    """Documents found and matches landing, newest first — the run's visible output."""
    def _rows(items, empty, fmt):
        if not items:
            return f'<li class="rvempty">{empty}</li>'
        return "".join(fmt(x) for x in reversed(items[-40:]))

    docs = _rows(st_["docs"], "Searching…",
                 lambda d: f'<li><span class="rvtick" aria-hidden="true">✓</span>'
                           f'<span>{_esc(d[0][:78])}</span>'
                           f'<span class="rvhost">{_esc(_host(d[1]))}</span></li>')
    hits = _rows(st_["hits"], "Nothing matched yet — this starts after the documents are read.",
                 lambda h: f'<li><span>{_esc(h[0][:80])}</span>'
                           f'<span class="rvhost">{_esc(h[1])}</span></li>')
    return (
        '<div class="rvstreams">'
        f'<div class="rvstream"><div class="rvsh">Documents found<span>{len(st_["docs"])}</span></div>'
        f'<ul>{docs}</ul></div>'
        f'<div class="rvstream"><div class="rvsh">Laws matched, as they land<span>{len(st_["hits"])}</span></div>'
        f'<ul>{hits}</ul></div>'
        '</div>')


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else ""


CSS = """
  .rvtrack{display:grid;grid-template-columns:repeat(5,1fr);gap:0;position:relative;
    padding:1.5rem 1.1rem 1.2rem;border:1px solid var(--rule);border-radius:14px;
    background:var(--panel);box-shadow:var(--shadow);}
  .rvstage{position:relative;text-align:center;padding:0 .4rem;}
  .rvstage .rvnode{width:42px;height:42px;margin:0 auto .55rem;border-radius:13px;
    display:grid;place-items:center;background:var(--panel-2);border:1.5px solid var(--rule);
    color:var(--ink-faint);transition:background .3s ease,border-color .3s ease,
    color .3s ease,transform .3s ease;}
  .rvstage .rvnode svg{width:18px;height:18px;}
  .rvrail{position:absolute;top:21px;left:calc(50% + 29px);right:calc(-50% + 29px);height:2px;
    background:var(--rule);overflow:hidden;}
  .rvrail i{display:block;height:100%;background:var(--accent);transition:width .5s linear;}
  .rvstage b{display:block;font-size:.8rem;font-weight:600;color:var(--ink);}
  .rvstage span{display:block;font-size:.7rem;color:var(--ink-faint);margin-top:1px;}
  .rvstage.active .rvnode{background:var(--accent);border-color:var(--accent);
    color:var(--accent-ink);transform:scale(1.06);}
  .rvstage.done .rvnode{background:var(--good-soft);border-color:var(--good);color:var(--good);}
  @media (prefers-reduced-motion:reduce){.rvstage .rvnode,.rvrail i{transition:none;}}

  .rvnow{display:flex;align-items:center;gap:.7rem;padding:.85rem 1.1rem;margin-top:.75rem;
    border-radius:12px;background:var(--accent-soft);
    border:1px solid color-mix(in srgb,var(--accent) 26%,transparent);}
  .rvnow.fin{background:var(--good-soft);border-color:color-mix(in srgb,var(--good) 30%,transparent);}
  .rvnow b{font-size:.85rem;color:var(--ink);}
  .rvsub{font-family:var(--mono);font-size:.72rem;color:var(--ink-soft);
    overflow-wrap:anywhere;}
  /* Blocked run. Same shape as .rvnow so the eye lands in the same place, in the palette's
     existing "set aside" red — the one already documented as an exception to one-accent. */
  .rvbad{display:flex;align-items:flex-start;gap:.7rem;padding:.85rem 1.1rem;margin-top:.75rem;
    border-radius:12px;background:var(--bad-soft);
    border:1px solid color-mix(in srgb,var(--bad) 34%,transparent);}
  .rvbad b{font-size:.85rem;color:var(--ink);}
  .rvbadge{flex:none;width:20px;height:20px;border-radius:50%;background:var(--bad);
    color:#fff;font-weight:700;font-size:.78rem;line-height:20px;text-align:center;}
  .rvfix{margin-top:.45rem;font-size:.78rem;color:var(--ink);overflow-wrap:anywhere;}
  .rvfix b{font-size:.78rem;}
  .rvspin{width:15px;height:15px;border-radius:50%;flex:none;
    border:2px solid color-mix(in srgb,var(--accent) 35%,transparent);
    border-top-color:var(--accent);animation:rvsp .8s linear infinite;}
  @keyframes rvsp{to{transform:rotate(360deg)}}
  @media (prefers-reduced-motion:reduce){.rvspin{animation:none;}}

  .rvcounters{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
    gap:.7rem;margin-top:.75rem;}
  .rvc{padding:.8rem .95rem;border-radius:12px;background:var(--panel);
    border:1px solid var(--rule);}
  .rvc b{display:block;font-family:var(--mono);font-size:1.55rem;font-weight:600;
    line-height:1.1;font-variant-numeric:tabular-nums;color:var(--ink);}
  .rvc span{font-size:.68rem;color:var(--ink-faint);text-transform:uppercase;
    letter-spacing:.06em;}
  .rvc.hit b{color:var(--good);}

  .rvstreams{display:grid;grid-template-columns:1fr 1fr;gap:.9rem;margin-top:.9rem;}
  @media (max-width:900px){.rvstreams{grid-template-columns:1fr;}}
  .rvstream{border:1px solid var(--rule);border-radius:13px;background:var(--panel);
    overflow:hidden;}
  .rvstream .rvsh{margin:0;padding:.65rem .9rem;font-size:.75rem;font-weight:600;
    color:var(--ink-soft);border-bottom:1px solid var(--rule);background:var(--panel-2);
    display:flex;justify-content:space-between;align-items:center;}
  .rvstream .rvsh span{font-family:var(--mono);color:var(--ink-faint);}
  .rvstream ul{list-style:none;margin:0;padding:.35rem;max-height:190px;overflow-y:auto;}
  .rvstream li{display:flex;gap:.6rem;align-items:baseline;padding:.4rem .6rem;
    border-radius:8px;font-size:.75rem;color:var(--ink);}
  .rvstream li:hover{background:var(--panel-2);}
  .rvstream li .rvhost{font-family:var(--mono);font-size:.65rem;color:var(--ink-faint);
    margin-left:auto;flex:none;}
  .rvstream li .rvtick{color:var(--good);flex:none;}
  .rvstream li.rvempty{color:var(--ink-faint);font-style:italic;}
"""
