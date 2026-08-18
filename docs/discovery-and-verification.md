# Discovery coverage + how we verify extraction

Branch `feat/precompute-corpus` · measured 2026-08-17

Two questions drove this round:

1. **How do we know the discovery/extraction fixes are actually right?** Reading verbatim
   output until it "looks reasonable" is what we did before, and it kept missing things.
2. **Close the discovery gap** — the instruments the judges cite that an Acts-only catalogue
   structurally cannot hold.

---

## 1. Verification: an audit, not an eyeball

`backend/eval/extraction_audit.py` (`python tools/audit_extraction.py`) runs five checks that
fail loudly without anyone reading a snippet. Four of them are independent of the RDTII labels
entirely, and the point of each is that it can only pass for one reason.

| | check | why it cannot be faked |
|---|---|---|
| **A** | page count vs the **portal's own** `pageCount` | external ground truth from the register; a missing volume shows up as arithmetic |
| **B** | provision spans vs extracted characters | if the splitter drops law text, coverage falls below 1.0 |
| **C** | section-label sequence inside a law | duplicates = chrome/TOC split as provisions; a run that stops dead = lost text |
| **D** | re-read the cited page with a **different extractor** (pypdfium2, not pdfplumber) | compares our stored text against the source through a second code path |
| **E** | our text for a cited section vs the **panel's own description** of it | tests meaning: is the text under "s 187C" the provision they were describing? |

### What it caught immediately

Reading the output would never have found this: **the `Location Reference` page numbers were
interpolated**, not counted. `_location_ref` computed `offset / total_chars × pages`, which
assumes every page holds the same number of characters — false for any statute with schedules
or tables. Check D re-read each cited page and found the citation wrong **about half the time
while the snippet text was perfectly verbatim**. The text looked right, so no amount of reading
it would have raised a flag; the page number beside it was fiction.

Fix: `ocr._join_pages` now marks every page boundary with a self-describing sentinel
(`\x0c<page>\x0c`) so the page is *counted*. Two iterations were needed, and the audit caught
both:

* a bare delimiter was not enough — the TOC/chrome strippers **delete spans** and took the
  delimiters with them, so every page after a deleted block was numbered short;
* the extraction cache served pre-sentinel text until `EXTRACT_FORMAT_VERSION` was bumped.

Controlled result, checking every provision of three Acts against the real PDF:

| | provisions | page citations correct |
|---|---|---|
| SG Business Trusts Act 2004 | 159 | **0.975** |
| AU My Health Records Act 2012 | 189 | **0.984** |
| MY Personal Data Protection Act 2010 | 151 | **0.980** |

(before the fix: 0.000)

### Corpus-wide audit, 783 law versions

| check | SG | AU | MY |
|---|---|---|---|
| A pages vs portal | *no feed* | 198/253 reconciled, **49 mismatched** | *no feed* |
| B median text coverage | 0.961 | 0.831 | 0.920 |
| C laws with duplicate section labels | 118/265 | 83/252 | 113/266 |
| D verbatim round-trip pass rate | 0.70 | 0.78 | 0.75 |
| E cited section beats a random section | 8/8, ×5.9 | 8/11, ×3.2 | 18/24, ×2.1 |

Read honestly, that says: **the text is right, the structure is noisy.**

* **E is the reassuring one.** For a section the panel cited, our stored text matches their
  description 2–6× better than a random section of the same law does. The labels are attached
  to the right text.
* **C is the known defect.** Numbered list items inside Schedules and Forms are labelled
  "Section N", so one Act can hold four different "Section 4"s. The snippet is verbatim; the
  *citation* is wrong. This is the next thing to fix, and it is now measured rather than
  suspected.
* **A found 49 AU documents whose page count disagrees with the register** — more
  partial-extraction cases of the multi-volume family. Also next, also now measured.
* **D at 0.70–0.78 corpus-wide vs ~0.98 per-Act** is mostly the ± page window: a provision
  whose opening line sits at the foot of the previous page counts as a failure.

The honest summary is that we can now *state* extraction quality per check instead of
asserting it, and every future change re-runs the same five numbers. `tools/audit_extraction.py`
exits non-zero on any ERROR finding, so it can gate a build.

---

## 2. Discovery: from Acts-only to instruments

### The gap, analysed

Of 37 instruments the panel cites, 10 were outside the catalogue. They are not one problem:

| class | instruments | where they live | why Acts-only missed them |
|---|---|---|---|
| subordinate legislation | AU Telecommunications Regulations 2021 | legislation.gov.au | we enumerated `collection eq 'Act'` only; this is a `LegislativeInstrument` |
| regulator codes & standards | MY Codes of Practice (banking, communications), PDP Standard 2015 | pdp.gov.my | not on the statute portal at all |
| regulator guidance | SG PDPC advisory guidelines + DPIA guide; AU OAIC PIA guidance; AU Cyber Security Strategy | pdpc.gov.sg, oaic.gov.au, homeaffairs.gov.au | ditto — and several are HTML pages, not PDFs |
| licence conditions | SG IMDA facilities-based licence, IP telephony T&Cs | imda.gov.sg media library | ditto |

The Malaysian Codes matter most: they carry evidence for **10 indicator rows** on their own.

### The redesign

`backend/corpus/regulator.py` enumerates a regulator site from **its own index**, trying four
generic strategies and unioning the results:

* **wp_rest** — read `/wp-json/wp/v2/types`, then walk *every* public post type. Media alone
  was not enough: pdp.gov.my publishes its Codes as a custom `docs` type (92 items) invisible
  to `/media`, `/pages` and `/posts` alike. For a content item, the PDF linked from its body is
  the instrument; the page stays as the citation.
* **sitemap** — robots.txt `Sitemap:` → `/sitemap.xml` → nested indexes (pdpc 816 URLs, imda
  11,316).
* **crawl** — bounded BFS (pages and depth capped) over same-host links that look like an
  instrument index.
* **search** — site-scoped web search. Deliberately **not** PDF-only: an earlier version
  appended `filetype:pdf` to every query, which structurally excluded the HTML guidance that
  OAIC and Home Affairs publish.

`data/sources.yaml` gains a `regulators:` block holding **domains and remits only** — the same
portal-level fact the existing entries carry, and what the judges' own portal reference
document records. No instrument names, no document paths, so a Finals economy is added by
naming its regulators. `remit: data_protection` takes every document the authority publishes;
`remit: sectoral` applies a subject gate, because a telecoms or home-affairs site publishes
thousands of unrelated documents.

AU also now enumerates the `LegislativeInstrument` collection (24,320 in-force instruments).

### Result

| | cited instruments located | catalogue size |
|---|---|---|
| before | 27/37 | 6,529 laws |
| **after** | **34/37** | **31,564 laws** (incl. 24,320 AU instruments, 1,032 regulator documents) |
| SG | 9/12 | 1,269 |
| **AU** | **14/14** | 29,290 |
| **MY** | **11/11** | 1,614 |

AU and MY are **complete**. The three SG remainders, with causes:

1. **PDPA (Amendment) Act 2020** — SSO consolidates amendments into the principal Act, so it
   is not published as a separate current instrument. Its text *is* in the catalogue, inside
   PDPA 2012. Arguably a correct absence rather than a gap.
2. **IMDA facilities-based licence** and **IP telephony terms & conditions** — files under
   `/-/media/Imda/Files/…`, absent from the sitemap and reachable only from a licensee-list
   page the bounded crawl did not reach at 150 pages. Both are evidence for P7-I3, where four
   other cited SG laws *are* catalogued.

### Evaluator fixes found along the way

The linkage evaluator had to be corrected three times, each time because it was **inflating**
the score:

* row-level URL matching linked "Privacy Act 1988" to the Security of Critical Infrastructure
  Act — a Database row lists several laws and several references with no correspondence, so a
  URL is only usable as a key when its own path spells out the instrument's words;
* the instrument-type guard compared raw strings, so a Malay title was rejected for a "type
  conflict" against its English label; and "Licensees" (who a code binds) matched the type word
  "license" by substring;
* duplicate catalogue rows for one PDF tied at 0.67 and tripped the ambiguity guard against the
  correct document.

---

## 3. Re-run of the judging-panel evaluation

Same script, same labels, after both fixes (`tools/validate_retrieval.py`, production code):

| | before discovery fix | after |
|---|---|---|
| provisions in corpus | 36,590 | **47,775** |
| law-level | 22/22 (1.000) | **22/23 (0.957)** |
| provision-level | 17/18 (0.944) | **17/19 (0.895)** |
| SG · AU · MY (provision) | 5/5 · 5/5 · 7/8 | 5/5 · 5/6 · 7/8 |

The rates dip because **the denominator grew**: instruments the panel cites that we previously
could not even locate are now in scope and therefore in the measurement. Absolute hits held
(17 → 17) while coverage of the panel's evidence went from 27 to 34 of 37 instruments. The two
targets not retrieved are the newly added AU policy documents (Cyber Security Strategy, OAIC
PIA guidance) — HTML pages with no section structure, which enter the corpus as a single
provision each.

Reporting the rate alone would have looked like a regression; it is the opposite, and the
denominators are why.

---

## 4. LLM confidence-weight experiment (now runnable — key works)

239 labelled pairs, `deepseek-v4-flash`, **$0.12 spent** of the $5 budget, 219 graded (20 calls
failed on provider errors).

**Confidence weights: no change justified.** The grid search over the four weights returns
AUC **0.6504** — identical to the shipped weights — and its "best" corner is degenerate (0.95
on `scope_alignment`, which is near-constant in this data). `snippet_grounding` carried no
signal in the experiment because the grader mostly returns no snippet, so the harness fed it
the provision text itself. So `backend/pipeline/confidence.py` is **unchanged**, and the
honest statement remains that those weights are hand-chosen.

**The finding that matters is about the grader, not the weights:**

| | n | grader accepts |
|---|---|---|
| every section the panel *mentions* | 117 | 0.291 |
| the **primary operative** section only | 41 | **0.537** |
| **indicators with ≥1 accepted cited provision** | 18 | **16/18** |
| sibling negatives (a confirmed answer for a *sibling* indicator) | 84 | **0.000** |
| random negatives | 18 | **0.000** |

The 0.291 is a floor artefact: the mentioned-sections set includes the panel's incidental
cross-references (Companies Act s 4 *defines* "accounting records"), and the grader rejects
those correctly — its rationales say so explicitly. On the operative section it accepts 54 %,
and at the level that decides a submission — does the indicator get at least one accepted
piece of the panel's own evidence — **16 of 18**.

Precision is the striking half: **zero false positives on 102 negatives**, including 84
adversarial sibling pairs (a P6-I2 answer offered to P6-I1, etc.) that are exactly the
confusion the legal tests exist to prevent.

**So the bottleneck has moved.** Retrieval now delivers ~90 % of the panel's cited provisions
into the shortlist; the grader is where evidence is lost, and it errs strongly toward silence
rather than invention. That is the right direction for a scored submission, and it makes grader
recall — not retrieval — the next thing to work on.
