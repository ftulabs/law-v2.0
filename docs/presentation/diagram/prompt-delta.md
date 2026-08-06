# Prompt sửa — dán tiếp vào phiên Claude design đang dựng deck

```
Four changes to what you're building. Everything else stays as instructed.

=== CHANGE 1 — LEAVE THE FIRST FOUR SLIDES ALONE ===

Title, Executive Summary, Problem Statement and Project Objectives are presented by a different
speaker with their own time budget. Keep them exactly as they are in the original deck: no rail, no
dimming, no highlight, no re-flow. They are slides 1-4 of the output; my 14 slides follow them.

=== CHANGE 2 — DROP THE "TECHNOLOGY & INNOVATION" SLIDE ENTIRELY ===

I'm not showing it. Its techniques get spoken over other slides instead. Rebuild my sequence from
this table — it replaces the 12-row table I gave you earlier. Same three rules as before (rail on
the right, exactly one highlighted region, everything else dimmed but intact).

 1. Duplicate "System Architecture" · highlight the whole INPUT -> ZONE 1 -> ZONE 2 -> OUTPUT strip
    plus the "IN PLAIN TERMS" line · rail: no stage lit, whole pipeline neutral ·
    note: one run, input to checkable evidence
 2. Duplicate "Evaluation & Performance" · highlight the metric tiles Citation fidelity, Coverage,
    OCR quality (CER), Discovery precision · rail: `13-column CSV` active, `Extract` + `Confidence`
    related · caption: quote · citation · URL · confidence ·
    note: every row is verifiable by a second reviewer
 3. Duplicate "Backend Logic (1/2)" · highlight the "1. Discover" block, first bullet only (two
    query lanes) · rail: `Discover` active · caption: two lanes — name + obligation phrase ·
    note: "data must be stored in" finds the Companies Act
 4. Duplicate "Backend Logic (1/2)" · highlight the "1. Discover" block, second and third bullets
    (version resolution; repealed/bill hits dropped, AU re-verified in force) ·
    rail: `Resolve versions` active, `Discover` related · caption: one statute identity, in-force
    only · note: "Last Amended" read from the portal's own timeline, never guessed
 5. Duplicate "Backend Logic (1/2)" · highlight the whole "2. Fetch" block ·
    rail: `Fetch` active · caption: handshake impersonation, then stealth browser ·
    note: WAFs block the knock, not the words
 6. Duplicate "Competitive Advantage" · highlight only the "Survives real portals" card ·
    rail: `Fetch` active, `Discover` related · caption: broken search · invisible portal · JS shell ·
    note: the silent failure is a crawler that "succeeds" on menus — 0 here
 7. Duplicate "Backend Logic (1/2)" · highlight the "3. Extract" block, first bullet (text-density
    detector, CER measured) · rail: `Extract` active · caption: scan detector, then OCR — CER 1.11%
    · note: measured against ground truth, not claimed
 8. Duplicate "Backend Logic (1/2)" · highlight the "3. Extract" block, second and third bullets
    (SG/MY margin numbering, AU bold typeface, page-chrome stripping, character spans) ·
    rail: `Extract` active · caption: one splitting profile per drafting style ·
    note: verbatim is machine-checkable, not a promise
 9. Duplicate "Backend Logic (1/2)" · highlight the bottom band "Finding the relevant sections,
    5-signal hybrid retrieval" including the grade-all line beneath it · rail: `Retrieve` active ·
    caption: BM25 + dense + phrase + sibling + rerank · note: retrieval is a signal, never a gate
10. Duplicate "Backend Logic (2/2): Map & Verify" · highlight "Sibling-aware LLM mapping" +
    "Cross-model second opinion" + the Singapore P6-I4 example box · rail: `Map` active,
    `Confidence` related · caption: the legal test plus every sibling test ·
    note: borderline rejections go to a cross-model 2-1 panel
11. Duplicate "Competitive Advantage" · highlight only the "Zone 3 scoring, polarity included" card
    · rail: `Score` active, `13-column CSV` related · caption: including the inverted polarity of
    7.1 / 7.2 · note: the optional zone, implemented

Slides 12-14 are new — specified in change 4.

=== CHANGE 3 — THE VISUAL DESIGN IS YOURS ===

Ignore the palette and styling I dictated earlier. You decide the rail's colours, shapes, spacing,
connectors and how the five stage states (active / related / done / upcoming / slot) are
distinguished. The only constraints: it must sit coherently beside the original deck's slides, the
active stage must be obvious from across a Zoom share, and the whole rail must stay legible when
the deck is exported to PDF and printed in black and white.

=== CHANGE 4 — REPLACE MY CLOSING WITH THREE NEW SLIDES ===

These are new slides, not duplicates, so you're free with layout. They carry the last 60 seconds and
need to land harder than a bullet list. Keep them visually of a piece with the rest of the deck.

--- SLIDE 12 · PERFORMANCE (25 seconds) ---

Two real charts, not tiles. Design them as one visual system: one accent for the production
configuration, neutral greys for everything else, values labelled directly on the marks rather than
read off a gridline, no 3D, no legend if direct labels will do.

CHART A — "Recall vs shortlist size": how much evidence survives retrieval as we shrink the
candidate list. X axis = shortlist size K, Y axis = recall of the official answer key's provisions.
  K:       5      10     20     40     60     80     120
  recall:  24.8%  39.8%  59.3%  99.1%  100%   100%   100%
  cheaper: 871x   436x   221x   112x   74x    55x    37x   (vs grading every provision)
Mark K = 40 as the operating point and annotate it: "99.1% recall at 112x fewer model calls".
The story is the knee of the curve — we buy almost all the recall for almost none of the cost.

CHART B — "Does every signal earn its place?": horizontal bars, recall per retrieval configuration.
  BM25 only ................................. 73.5%
  + dense embeddings ........................ 78.8%
  + cross-encoder rerank (what we ship) ..... 99.1%
  what we ship, minus per-law reserved slots  76.1%
Highlight the shipped configuration; the last bar is the ablation that shows one 485-section act
would otherwise crowd out a short, on-point one.

Below the charts, a compact strip of measured figures:
  13,067 provisions from 69 laws · 117,603 -> 1,054 model calls · CER 1.11% against a 5% bar ·
  ~$0.07 per economy, $0.00 open-weight · 10-17 minutes per economy, CPU-only
Title it so the point is unmissable: measured, and re-derivable from our own output files.

--- SLIDE 13 · THE STACK (15 seconds) ---

Take the same pipeline diagram from the rail, expand it to fill the slide, and label each stage
with the tools that actually run it. The point I'm making: this is an entirely open, swappable
stack, and you can see exactly which component does which job.

  Discover ............ Serper.dev search API (DuckDuckGo / Mojeek fallback) · AU OData API ·
                        MY portal catalogue JSON
  Resolve versions .... BeautifulSoup · per-portal revision-timeline parsing
  Fetch ............... Scrapling (TLS/JA3 impersonation) -> stealth browser -> httpx
  Extract ............. MarkItDown (text layer) · pdfplumber (font/glyph data) ·
                        RapidOCR / PaddleOCR (scans)
  Retrieve ............ rank_bm25 · sentence-transformers, multilingual MiniLM-L12-v2 ·
                        ms-marco MiniLM-L-6-v2 cross-encoder
  Map ................. DeepSeek V4 Flash via OpenRouter, swappable · panel: gemini-2.5-flash +
                        gpt-4o-mini · pydantic-validated JSON verdicts
  Confidence .......... in-house 4-signal scorer
  Score ............... RDTII rubric, 0 / 0.5 / 1
  Output .............. 13-column CSV + JSON audit trail · Streamlit dashboard · SQLite audit store

Footer: every library MIT / Apache-2.0 / BSD · project Apache-2.0 · runs CPU-only · LLM and OCR
engines swap via one config value.

--- SLIDE 14 · WHAT STANDS IN THE WAY, AND HOW WE GET PAST IT (20 seconds) ---

Four pairs, barrier on one side, the route through on the other. Make the pairing the visual idea —
I want the judges to see that each barrier already has a slot in the architecture.

  More languages (Thai, Chinese, Russian, Lao)
    -> embeddings are already multilingual; the one English-only component, the reranker, swaps for
       bge-reranker-v2-m3 in one config line; grade-all means retrieval can't silently drop a
       non-English provision
  New drafting conventions ("Dieu 5", the Chinese and Thai article forms)
    -> one extraction profile each; the adapter pattern is already proven three times
  Messier portals, no single repository
    -> one entry strategy per portal: search, official API, or the portal's own data source
  Worse scans, older gazettes, mixed text-and-image files
    -> scan detection moves from per-document to per-page; CER recalibrated on real gazettes

On the rail for this slide, put `Discover` and `Extract` in the "slot" state and caption them
"+1 entry strategy per economy" and "+1 extraction profile per drafting style". Close the slide with
one line: none of this needs new architecture — every item plugs into a slot the system already has.
```
