# Where each piece of the panel's evidence dies

Branch `feat/precompute-corpus` · measured 2026-08-17 · `python tools/trace_pipeline.py`

Aggregate recall says "we lost 2 of 19" and nothing about *why*. `backend/eval/trace.py` walks
every provision the RDTII panel accepted through the real stages in order and records the
**first** stage that dropped it. Attribution is strictly ordered: a target lost at extraction
is never also charged to retrieval or to the grader.

Unit of analysis: an **(indicator, law) target** — one piece of the panel's evidence. A single
Database row often cites 3–5 instruments, so 27 indicator rows expand to **69 targets**. That
is deliberately stricter than the earlier indicator-level metric, because the goal is to be *at
least as comprehensive as the panel*, not merely to answer each indicator once.

## Result

| stage | lost | what it means |
|---|---|---|
| DISCOVERY | 5 | instrument not in the catalogue |
| FETCH | **0** | everything catalogued was downloaded and built |
| EXTRACTION | 7 | built, but the cited section is not among the extracted provisions |
| **RETRIEVAL** | **21** | the provision exists but never reached the indicator's shortlist |
| GRADING | 12 | reached the LLM and was rejected |
| CONFIDENCE | **0** | nothing the grader accepted was routed out of a submission |
| **SURVIVED** | **24** | end to end |

**18 of 23 indicators** keep at least one piece of the panel's own evidence end to end.

By economy — SG `{survived 8, discovery 5, grading 3, extraction 2}`,
AU `{survived 7, retrieval 8, grading 4}`, MY `{survived 9, retrieval 13, grading 5, extraction 5}`.

## Retrieval is the largest loss, not the LLM

**This overturns the previous round's conclusion.** After the discovery work I reported that
"the bottleneck has moved to the grader"; measured per piece of evidence, retrieval loses
**21** and grading **12**. The earlier claim came from an indicator-level metric that is
satisfied by *any* one hit, which hides every additional instrument the panel cited.

The 21 split into two very different problems:

| | n | |
|---|---|---|
| the law reached the shortlist, but not the **cited section** | **14** | depth-within-law |
| the law never surfaced at all | 7 | law-level ranking |

The 14 are concentrated in AU P7-I5, where the panel cites "Section 10" across five telecom
Acts. The shortlist contains 10–73 provisions *of those same Acts* — just not s10. A global
top-300 spends its budget on each law's strongest matches; a specific cross-cutting section
sits below that cut in a 1,226-provision Act.

This is exactly what `retrieve_per_law_k` was meant to guarantee, and which the previous round
measured as harmful and turned off. Both measurements are right, because they measure
different goals: at **indicator level** (any evidence counts) per-law reservation dilutes the
shortlist and costs recall; at **evidence level** (match the panel's full set) it is the only
mechanism that reaches deeper into a law already known to be relevant. Reconciling those two —
probably a per-law guarantee applied *only to laws already ranked highly*, scored globally
rather than within-law — is the next retrieval experiment. Not changed here: the brief was to
prove where the loss is first.

## Is the grader overly strict? No — it is being asked the wrong question

36 targets reached the LLM: **24 accepted (67 %), 12 rejected.** `legal_match` is bimodal —
median **0.90** on accepted, **0.00** on rejected — so this is not a threshold that could be
nudged; the model is making a categorical judgement.

Of the 12 rejections:

* **8 are law-level targets** where the panel named no section. The trace had to pick one
  provision as a proxy, and picked (by length) a *definitions* section. The grader's rationales
  say exactly that: *"This Section 5 is a definitions section only; it does not impose any
  cybersecurity obligations"*, *"purely definitional, defining terms like 'cybersecurity' and
  'critical information infrastructure'"*. **The grader is right and the question was wrong.**
* **3 are rejections of the panel's own primary operative section** — and every one of them is
  a row **the panel itself scored 0.0**:

  | | section | panel Raw Score | grader |
  |---|---|---|---|
  | SG P7-I3 PDPA 2012 | s 25 | **0.0** | "a storage-limitation/deletion duty, not a minimum retention period — it is the opposite" |
  | MY P6-I1 PDPA (Act 709) | s 6 | **0.0** | "requires consent or a lawful basis; neither bans cross-border transfer nor requires local processing" |
  | MY P6-I1 Code of Practice | s 6 | **0.0** | "lists consent exemptions, not a ban on cross-border transfer" |

  The panel cited these instruments as *what they examined*, then scored the indicator 0
  because the requirement does not exist. The grader reached the same legal conclusion.

Combined with the previous round's adversarial run — **zero false positives on 102 negatives**,
including 84 sibling-indicator pairs — the verdict is that the grader is **precise and
substantively correct**, not over-strict.

### The real gap: framework indicators have no document-level path

P7-I1 ("comprehensive data-protection framework") and P7-I2 ("dedicated cybersecurity
framework") ask whether an *instrument as a whole* exists. The pipeline only ever asks "does
**this provision** satisfy the test?", so the question is unanswerable however good the model
is: no single section of the Cybersecurity Act 2018 "is" a cybersecurity framework. Three of
the five dead indicators are exactly this (AU/P7-I1, AU/P7-I2, SG/P7-I2), and all three failed
on a definitions section.

These indicators need a document-level decision — the law's title, long title and structure,
or an aggregation over its provisions — rather than a provision-level one. That is a design
gap in mapping, not a grader defect, and it is the single highest-value fix identified here.

## Extraction losses (7)

| economy | cited | cause |
|---|---|---|
| SG ×2 | PDPC guidance, s 11(3) | HTML shell — 1 provision of nav chrome (see below) |
| MY ×5 | Act 709 s 12A, COP ss 5.5/7.4, Computer Crimes ss 15/27/36, A1727 | section numbering the splitter did not produce: the "12A"-style suffixed sections and the decimal clause numbering (`5.5`, `7.4`) used by Codes of Practice |

Codes of Practice number clauses `3.1.1` / `5.5`, not "Section 5". The splitter's per-country
profiles cover statute drafting only, so a Code enters as ~14 coarse chunks and its cited
clause cannot be addressed. This is the extraction counterpart of the framework gap.

## HTML documents: chunking is not the problem

The brief asked whether HTML documents need a different chunking strategy. Measured across the
corpus, the answer is that **there is nothing to chunk**:

| | HTML | PDF |
|---|---|---|
| documents | 122 | 663 |
| median provisions/document | **1** | 27 |
| documents yielding ≤1 provision | **121 (99 %)** | 76 (11 %) |
| median extracted characters | **228** | 21,551 |
| median text/bytes ratio | **0.0013** | 0.0727 |

A PDPC guidance page is 190 KB of markup that extracts to 238 characters — **175 KB of it is
inside `<script>` tags** and only 854 characters are real markup text. What lands in the corpus
is the page furniture: *"Skip to main content … Browse related tags … Share: facebook linkedin
whatsapp"*. Zero of the 122 pages link a same-domain PDF, and zero carry a JS-framework marker,
so `ocr.is_js_app_shell` — which requires such a marker — fires on **0 of 122** and lets every
one of them through as a "provision". Fetching one through Scrapling's browser path returned
byte-identical text, so this is not fixed by simply enabling rendering.

So, in priority order:

1. **Detect** — a text-density guard for `fmt == html` (text/bytes < 0.01, or < 2 KB of text
   from > 20 KB of HTML) flags **117 of 122**, where the framework-marker test flags none. The
   equivalent PDF threshold must stay separate: 118 of 663 PDFs are legitimately below it
   before OCR. Until this exists, nav chrome is retrievable and gradeable as if it were law.
2. **Acquire** — the body has to come from the page's own data source (the content sits behind
   the site's client-side app) or from the document the page publishes. This is a fetch
   problem, not a parsing one.
3. **Then** chunk — and only then does the chunking question become real. Guidance documents
   have no "Section N" structure, so the right unit is heading-based segmentation with a
   size cap, not the statute regexes. Note the same need appears for Codes of Practice, which
   *are* being fetched correctly but are numbered `5.5` / `3.1.1`.

Doing (3) without (1) and (2) would chunk nav chrome more finely.

## Two measurement bugs found while doing this

Both inflated or corrupted the picture and are fixed:

* **Linkage, single-token URL match.** "Privacy Act 1988" normalises to the single token
  `privacy` (the type word and year are stripped), so any cited URL containing "privacy"
  satisfied the URL-identity rule — and the Act was linked to an OAIC data-breach blog page
  with 1 provision instead of the 389-provision statute. Three AU targets were being scored
  against the wrong document. Now a URL must share **≥ 2** distinctive tokens.
* **Trace harness, topical guard.** The harness evaluated `topical_grounded` on the model's
  quoted snippet; `mapping.py` evaluates it on the full provision text. That difference alone
  quarantined five correct record-keeping mappings (Companies Act s 199, Income Tax s 82,
  Service Tax s 24) at exactly `TOPICAL_FAIL_CAP = 0.45`. Under the production formula all five
  survive (four auto-accepted, one pending review) — which is why the CONFIDENCE row above is
  0, not 5.
