# VeriTrade — Project State

**The file to read first, in any session, before doing anything else.**
It carries what a new session cannot re-derive from the code: what the panel actually
requires, what has been decided and why, what is measured, and what is still owed.

`CLAUDE.md` explains how the system is BUILT. This file records where the PROJECT stands.
When the two disagree about a fact, this file is the newer one — fix CLAUDE.md, don't fork it.

---

## How to keep this file useful

1. **Read** §1–§3 at the start of a session. That is the briefing.
2. **Update** at the end of a session: tick what you finished, add what you learned, record
   any decision that a future session would otherwise re-litigate.
3. **One line per item.** A checklist entry is a claim, a file path and a status — not a
   narrative. If it needs a paragraph it needs a `docs/` page, and this file links to it.
4. **Prune on a schedule.** Whenever §5 (Recently done) exceeds ~15 lines, delete everything
   older than the last two milestones: it is already in git history. Whenever an entry in §4
   stops being true, delete it rather than annotating it — a stale warning is worse than none.
5. **Never record a number without where it was measured.** "SG needs k=40" is an opinion.
   "SG prov-recall 1.000 at k=40, `logs/sweep_final.json`, 2026-08-19" is a fact.

---

## §1 The panel's rules — verified against `Finalist Orientation/` (2026-08-27)

Source of truth: `Finalist Orientation/Finalist Orientation_Slide.pdf` + `Meeting notes.docx`.
Read them before trusting any restatement, including this one.

| | |
|---|---|
| **Country list** | **8**: China, India, Indonesia, Lao PDR, Mongolia, Russian Federation, Thailand, **Timor-Leste** |
| **Mandatory** | Singapore, Malaysia, Australia (always, in addition to the 8) |
| **Minimum coverage** | **6 economies**: the 3 mandatory + **at least 3** from the list of 8. More scores higher, but "quality over breadth" |
| **Language** | at least 3 of the new countries must be non-English / non-standard formats; **Timor-Leste carries a bonus** for difficulty |
| **Pillars** | 6 and 7 mandatory; further RDTII domains score extra (C1b) |
| **Live test** | **15 Oct, sealed**, announced at the start of the hour, "draws from any listed country, any pillar" → **11 possible economies** |
| **Second pass** | the tool must re-process **already-downloaded** documents without re-fetching — the live test may require it |
| **Engines** | declared on 30 Sep are **frozen**; at least **one must be open-weight** |
| **Code freeze** | 30 Sep · **Grand Finale** 15 Oct, Bangkok |
| **Deliverables (30 Sep)** | submission Word doc · evidence workbook (13 Round-1 columns **+ Language of Source**) · working UI + 5-min walkthrough · public repo at a release tag, Apache 2.0, deployable from its own docs in under 30 min |
| **On 15 Oct only** | live-test evidence files, a comparable output from the **second** engine, and the live-test short note |

**Rubric** (100): C1a jurisdiction 15 · C1b domains 15 · C1c language 10 · C2a mapping
consistency 10 · C2b citation fidelity 10 · C3a audit / human-in-the-loop 10 · C3b UI+export 5 ·
C4a handover 8 · C4b no vendor lock-in 7 · C5 live test 10 (discovery 6 + engine swap 4).

> **Corrected in code 2026-08-28, finished 2026-08-30.** The old `LIVE_TEST_NINE` listed nine
> economies including Viet Nam and Kazakhstan, which are on no list the panel published, and
> omitted Timor-Leste, which is on it and carries the bonus. The "final-round instructions"
> quoted in that constant's comment appear in no document in this repo; the orientation material
> is gitignored, so it was never opened and the list was inferred instead. The code now has
> `FINAL_ROUND_LIST` (the panel's 8) and `LIVE_TEST_POOL` (those 8 + the mandatory 3).
> **Viet Nam and Kazakhstan are removed outright** — enum, UN names, aliases, portal lanes,
> language profiles, native query terms, map polygons and tests. Timor-Leste has all of those.

---

## §2 Where the run actually stands

| Economy | Lane | Corpus built | Labels | Budget measured | End-to-end |
|---|---|---|---|---|---|
| SG | portal adapter, verified | yes (14,610 prov) | yes | **cap 80** (prov+law recall 1.000 from k=40) | 2026-08-28 · **7/7** at 760 calls |
| AU | portal adapter, verified | yes (18,262) | yes | **cap 450** — genuinely needs the depth (1.000 only from k=300) | 2026-08-28 · **8/8** |
| MY | portal adapter, verified | yes (14,903) | yes | **cap 150** (law recall 1.000 from k=80; prov flat 0.875 at every k) | 2026-08-28 · robots carve-out landed: 489 → 5,931 provisions |
| CN | 2 portal lanes, unverified | eval, 10 docs / 251 prov (10 shells, 3 dead links) | yes | no | **2026-08-30 · 8/9 answer-key indicators** |
| IN | 5 lanes, unverified | eval, 11 docs / 222 prov (**20 failed: link rot + robots**) | yes | no | **2026-08-30 · 7/8** |
| MN | 1 lane, unverified | eval, 4 docs / 397 prov | yes | no | **2026-08-30 · 6/8** |
| TH | generic websearch only | eval, 6 docs / 206 prov | yes | no | **no** |
| ID | generic websearch only | eval, 11 docs / 252 prov | yes | no | **no** |
| LA | generic websearch only | eval, 2 docs / 226 prov | yes | no | **no** |
| RU | body route open, discovery open | eval, 3 docs / **2 prov** ⚠ garant blocks, IPS unreachable | yes | no | no |
| **TL** | gazette lane, unverified | no | **impossible** (no database sheet) | no | reachable only |

"Labels" = rows parsed from the panel's own databases by `backend/eval/ground_truth.py`
(223 rows / 10 economies / 90 indicator-pairs). "eval" corpora are seeded from the panel's own
citations by `backend/corpus/catalogue_database.py` — an EVALUATION corpus, never discovery: the
live pipeline imports nothing from `backend/corpus`, and a test pins that. SG/AU/MY are built
from their real portal enumerators and are the only ones whose numbers are self-contained.

---

## §3 Open work — the checklist

Priority order. `[ ]` not started · `[~]` in progress · `[x]` done (move to §5 and prune).

### Scored against the panel's 2025 database — the six committed economies (2026-08-30)

All six re-run live on current code, exported CSV diffed against the answer key
(`tools/compare_to_key.py`). **44 of 48 answer-key indicators reached.**

| | docs | provisions | rows | LLM calls | cost | min | answer key |
|---|---|---|---|---|---|---|---|
| SG | 35 | 6,752 | 183 | 760 | $0.25 | 11 | **7/7** |
| AU | 28 | 4,948 | 344 | 2,272 | $0.76 | 25 | **8/8** |
| MY | 31 | 5,931 | 313 | 1,390 | $0.46 | 10 | **8/8** |
| CN | 41 | 888 | 138 | 584 | $0.15 | 6 | **8/9** (misses P6-I3) |
| IN | 1,111 | 1,615 | 183 | 769 | $0.31 | 14 | **7/8** (misses P6-I2) |
| MN | 40 | 648 | 103 | 498 | $0.14 | 6 | **6/8** (misses P7-I2, P7-I5) |

Total for the whole six-economy submission: **$2.07 and 72 minutes.**

**Per-PROVISION scorecard** (`tools/provision_scorecard.py`) — "indicators reached" is too
coarse to act on, because one lucky row scores a whole indicator. Counting the provisions:

| | panel cites | HIT | wrong indicator | missing | our rows | NEW |
|---|---|---|---|---|---|---|
| SG | 12 | 9 | 0 | 3 | 167 | 158 |
| AU | 15 | 6 | 1 | 8 | 299 | 292 |
| MY | 48 | 12 | 10 | 26 | 272 | 251 |
| CN | 37 | 14 | 3 | 20 | 138 | 121 |
| IN | 16 | 7 | 2 | 7 | 172 | 161 |
| MN | 20 | 7 | 9 | 4 | 101 | 71 |
| **all** | **148** | **55 (37%)** | **25** | **68** | **1,149** | **1,054** |

Three different failures needing three different fixes:
· **WRONG INDICATOR (25)** — the text was found and read, and filed under the wrong indicator.
  **13 of the 25 were filed as P7-I1**, from six different source indicators: P7-I1 is acting
  as a magnet, because "establishes a data-protection framework" is true of loosely anything
  in a data-protection law. Second pattern: P7-I4 (DPO/DPIA) → P7-I2 (cybersecurity), 4 cases.
  Cheapest fix of the three: the documents are already in hand.
· **MISSING (68)** — never cited at all. **Not "discovery or fetch", as this file said until
  2026-08-31**: `tools/missing_ladder.py` splits the label into the five failures it conflates,
  and **44 of the 68 were already in the corpus**, extracted and citable. Run the ladder before
  acting on this column.
· **NEW (1,054)** — seven rows for every one the panel cites. Audited 2026-08-30 by a different
  model with a control group (`tools/audit_rows.py`): **roughly half do not survive an
  independent reading**, and the failure is concentrated, not spread — P6-I1 83% refused,
  P6-I3 80%, P6-I2 67%, against P7-I2's 28%. Gates shipped 2026-08-31; see §5.

Corpus-side retrieval (k = the whole corpus, so this is the ceiling chunking and ranking
impose once the documents are in hand — it does NOT include discovery):
MN prov 0.857 · ID 0.778 · TH 0.714 · CN 0.571 · IN 0.143 (20 of 27 documents never
downloaded) · LA 0.000 (linkage maps no cited law to the corpus — open).

### The missing 68, by where they actually fall out (`tools/missing_ladder.py`, 2026-08-31)

| | not catalogued | fetch failed | not split | article absent | **in corpus** |
|---|---|---|---|---|---|
| before the day's fixes | 2 | 8 | 10 | 4 | **44** |
| after | **0** | 8 | **1** | 4 | **55** |

What remains upstream is eight fetch failures that are the panel's own link rot (HTTP 404) or
hosts answering nothing at all from this network (`www.mca.gov.in`, `upload.indiacode.nic.in` —
both time out on robots.txt *and* on the document, so a robots override would buy nothing).
Everything else is retrieval or grading, which is where the budget below bites.

- [ ] **MN P7-I2 and P7-I5, CN P6-I3, IN P6-I2** — four named misses, each now a specific
      question rather than a general worry. Worth reading the four before any broad change.
- [ ] LA corpus-side recall is 0.000 because linkage links none of its cited laws to the
      corpus, though `link_all` reports 5 of 6 linked. Diagnose before trusting any LA number.

### Owed right now — asked for on 2026-08-28, not yet done
1. [x] **Country list corrected** (2026-08-28) — `FINAL_ROUND_LIST` / `LIVE_TEST_POOL` /
       `NOT_ON_PANEL_LIST` in `backend/schemas.py`, followed through `ECONOMY_UN_NAME`,
       aliases, `frontend/livetest.py`, `tools/readiness.py` and both test files.
       Timor-Leste gained a UN name, aliases, a Portuguese language profile, Portuguese seed
       query terms and a gazette lane (`mj.gov.tl/jornal`, probed 2026-08-28: HTTP 200,
       server-rendered, no WAF). Readiness now rates it **reachable**.
2. [~] **Committed set for 30 Sep: SG · MY · AU + China · India · Mongolia** (decided
       2026-08-28), **plus Russia if it can be made to work**. Six is the minimum; RU is seven.
       RU status after probing 2026-08-28 — **fetch solved, discovery open**:
       · `pravo.gov.ru` robots.txt forbids NOTHING, and its IPS returns whole documents at
         `?doc_itself=&nd=<id>&page=1&rdk=0` (13.8k chars measured). Encoding is **cp1251**,
         including the query string; `?docbody=&nd=<id>` is a frameset holding 586 chars of
         chrome, so the obvious URL looks fine and contains no law.
       · `publication.pravo.gov.ru` is a DEAD END for bodies, and the old "build the lane on
         the sitemap" plan is wrong: the sitemap lists only index/calendar pages, and
         `/Document/View/<id>` carries metadata only (854 chars). Bodies are under `/File`,
         which that host's robots.txt disallows.
       · **Open:** the IPS search reports a result count but injects rows client-side — plain
         HTTP and a default browser render both yield zero `nd=` ids. Try the list frame's own
         XHR, or the rubricator browse. Do NOT chase the answer key's URLs: 24 of the panel's
         28 Russian references are commercial mirrors (garant, consultant), one is official.
3. [x] **Budget re-validated on real output** (2026-08-28), `tools/compare_to_key.py`.
       Live SG/MY/AU, both pillars, exported CSV diffed against the panel's own laws:

       | | provisions | LLM calls | cost | minutes | rows | answer-key indicators |
       |---|---|---|---|---|---|---|
       | SG | 6,752 → 6,752 | **3,083 → 760** | $1.08 → **$0.25** | 27 → 11 | 129 → 183 | **7/7 → 7/7** |
       | AU | 4,948 → 4,948 | 2,272 → 2,272 | $0.84 → $0.76 | 29 → 25 | 139 → 344 | 6/8 → 8/8 |
       | MY | 489 → 5,931 | 400 → 1,390 | $0.20 → $0.46 | 7 → 10 | 47 → 313 | 1/8 → 8/8 |

       **Only SG is a test of the budget.** Same corpus both times, three quarters of the
       calls removed, answer-key coverage unchanged and 42% more rows exported. AU's cap does
       not bind at its corpus size, so it ran the *same* 2,272 calls — its 6/8 → 8/8 is
       somebody else's improvement, not this one. MY's corpus went from 489 provisions to
       5,931 when the `lom.agc.gov.my` robots carve-out landed, so its jump is the carve-out.
       Attributing either to the budget would be taking credit for another change.

### Decisions owed by the team (blocking)
- [ ] **Which further economies**, if any, beyond the six committed above. Timor-Leste carries
      a bonus and has nothing built; TH/ID/LA have labels but no lane and no corpus.

### Coverage (scores C1a, C1c)
- [x] **Evaluation corpora built for all seven Round-2 economies** (2026-08-30),
      `python -m backend.corpus.cli catalogue --economy CN --from-database && … build`.
      They are seeded from the panel's citations, so they measure retrieval and extraction —
      never discovery. What building them immediately exposed, per economy:

      | | docs | provisions | chars/doc | chars/provision |
      |---|---|---|---|---|
      | MN | 4 | 397 | 182,000 | 1,303 |
      | IN | 7 | 224 | 57,300 | 1,649 |
      | TH | 6 | 103 | 76,300 | 1,439 |
      | LA | 2 | 452 | 43,800 | 188 |
      | CN | 19 | 261 | **1,966** | 127 |
      | ID | 7 | **7** | 3,465 | 3,465 |
      | RU | 2 | **2** | 1,150 | 1,150 |

      (SG/AU/MY, built from their portals, run 55k–102k chars/doc and 880–1,157 chars/provision.)
- [x] **Article splitters for the four civil-law drafting styles** (2026-08-30) —
      `ARTICLE_PATTERNS` in `extraction.py`: Indonesian **Pasal**, Russian **Статья**, Thai
      **มาตรา**, Portuguese **Artigo N.º**, each written against a real document fetched that
      day and each line-anchored, because most occurrences are cross-references (Thai: 18 of
      76 are headings; Indonesian: 24 of 39). Thailand went from 2 whole-document blocks to
      206 article-level provisions. Portuguese is the one pattern that is case-SENSITIVE:
      "Artigo" opens an article, "artigo" cites one. `tests/test_civil_law_splitting.py`.
- [x] **Fetch fixed where it was ours to fix** (2026-08-30). Three changes, all general:
      · a refusal now escalates to the stealth browser even with `crawl_browser` off
        (`fetch_browser_on_block`) — bpk.go.id refused httpx AND Scrapling with 403 and served
        the browser the same page in full, and `sources.yaml` had said so since 21 August
        while nothing acted on it;
      · a known landing page is followed to the instrument (`_BODY_ROUTES`): bpk
        `/Details/<id>` → the `/Download/…pdf` it links;
      · a fetch failure records WHICH KIND it was instead of "fetch failed" for everything.
      **Indonesia went from 0 usable provisions to 252** (three real statutes, Pasal-labelled).
- [x] **A landing page can no longer masquerade as a provision** — `build._looks_like_a_shell`
      marks a version `shell`, not `split`, when one whole-document block is all that came out
      of under 8,000 characters. `load_provisions` filters on `split`, so a shell cannot enter
      retrieval, a budget or a recall figure. It caught 10 in China, 3 in Indonesia, 2 in India
      and 1 in Russia that had all been counted as built documents.
- [ ] **Most of what is still missing is NOT ours to fix, and that is the finding.** Across
      all seven, the failure taxonomy is now: **13 × HTTP 404 (the panel's own link has
      rotted)**, **11 × robots.txt forbids the path** (mca.gov.in, irdai.gov.in, pfrda.org.in,
      ifsca.gov.in, pbc.gov.cn, ojk.go.id), 4 × 403 the browser could not clear (garant.ru),
      4 × other. So an evaluation corpus can never be complete from the answer key alone —
      each economy needs its own portal adapter. India is the clearest case: 20 of 27
      instruments, almost all link rot or robots.
- [ ] One Thai PDF extracts as `(cid:N)` mojibake — a broken font encoding, the
      `legacy_encoding_risk` hazard the language profile names. OCR would read it; the text
      layer must be rejected first.
- [ ] Indonesian labels show `Pasal 3O` / `Pasal 4O` — a text-layer misread of 30/40. Left
      alone deliberately: Indonesian articles really do carry letter suffixes ("Pasal 28J"),
      so a rule that rejected them would lose real citations to catch a cosmetic one.
- [ ] Portal adapters for TH · ID · LA · RU (today: generic websearch, `verified: false`).
      Measured 2026-08-25: TH and ID time out on the DuckDuckGo HTML endpoint; LA's gazette
      host does not resolve.
- [ ] Timor-Leste: no lane, no language profile, no OCR path. Carries a scoring bonus.
- [ ] CN principal statutes must survive `cac.gov.cn` being unreachable (PIPL / CSL / DSL).
- [ ] MY: one cited provision never reaches the shortlist at ANY budget (prov-recall flat
      0.875 from k=40 to k=450, `data/retrieval_budget.json` curve). Depth is not the fix —
      find out which provision and why the ranker cannot see it.

### Cost and reliability (scores C5, and stops burning the shared key)
- [x] Circuit breaker + honest failure classification in the grading loop (2026-08-27).
- [x] Per-economy retrieval budget, measured not hand-tuned (`tools/measure_budget.py`).
- [ ] Re-measure the budget for CN/IN/MN/TH/ID/LA/RU **once their corpora exist** — until then
      they correctly keep the conservative default and pay the old call count.
- [ ] **Prompt caching for the grading call.** The SYSTEM prompt is 2,525 tokens, identical on
      every call — 64% of input cost. ~968 calls on a Singapore pillar-6 run = 2.4M repeated
      prompt tokens. Nothing about recall changes; it is pure refund.
- [ ] Second-pass mode the panel explicitly asks for: re-run engines over already-downloaded
      documents without re-fetching. Check whether the corpus cache already satisfies this.
- [ ] Engine declaration for 30 Sep: pick the frozen pair, one of them open-weight, and record
      each one's measured cost and latency here.

### Submission mechanics
- [ ] Evidence workbook: indicator IDs must be written **as text** — entered as numbers,
      "12.10" collapses to "12.1". Verify the exporter does this.
- [ ] 30-minute clean-machine deploy, walked by someone who did not build it (C4a, 8 points).
- [ ] 5-minute UI walkthrough recording (C3b).

---

## §4 Decisions and traps a future session must not re-litigate

- **Retrieval parameters are measured, not tuned.** `hybrid_alpha=0.65`, `retrieve_max_top_k`,
  `retrieve_fraction`, `retrieve_per_law_k=0` come from sweeps against the panel's Database.
  Two counter-intuitive results are settled: a law-level prefilter makes recall WORSE, and
  `per_law_k=3` degenerates into one-provision-per-law. Re-measure before touching:
  `tools/sweep_retrieval.py` then `tools/validate_retrieval.py`. (`docs/retrieval-redesign.md`)
- **A measured budget IS the shortlist depth; an unmeasured economy keeps the global default.**
  Superseded 2026-08-31 the earlier rule "a budget may only ever NARROW a shortlist". Written
  that way — `min(n, cap, max(floor, 5% of n))` — the heuristic stayed in charge and a
  measurement could only ever shrink a shortlist, so Singapore's measured k=450 would have been
  overridden by `ceil(5% x 6,752) = 338` on a real crawl and the measured number never tested.
  The asymmetry behind the old rule still holds and is why the DEFAULT is generous: spending
  too much costs money, spending too little costs a submission row nothing downstream can
  notice is missing. (`backend/pipeline/retrieval_budget.py`)
- **Recall against the panel's labels is counted PER PROVISION, three ways, and the three
  differ enormously.** One bit per indicator saturates on the first hit (Malaysia read 7/8
  against 72 cited provisions). Every cited provision counts documents that never fetched, so
  no depth can move it (India: 1/16, of which 15 never arrived). The number a shortlist budget
  is derived from is `prov_recall_available` — cited provisions the corpus actually holds.
  India is 1/1 and 1/16 simultaneously and both are true. (`backend/eval/harness.py`)
- **A `--live` re-run measures the OLD code unless you pass `--fresh`.** `batch_run.py` has a
  result cache keyed on (economy, pillars, config): a six-economy re-run on 2026-08-31 finished
  in six seconds, exported every CSV, JSON and master file, and exited 0. The only sign was one
  `[cache] result cache hit` line per economy. Reporting those numbers as "after the fix" would
  have been reporting the numbers from before it.
- **The budget table is generated, never hand-edited.** `tools/measure_budget.py` writes it
  with the recall it observed and the date. A hand-typed cap is an opinion wearing a number.
- **"Chapter N" is not a provision target.** `harness.section_key()` returns None for
  structural headings, so a Chapter label can never match and would only depress measured
  recall with no pipeline at fault. `ground_truth._ARTICLE_RE` deliberately excludes it.
- **The deployed site's API keys come from `${VERITRADE_BASE}/.env` ON THE SAGER BOX**, not
  from this repo's `.env`. They are now written there by `deploy/redeploy.sh` from the
  repository secrets (`gh secret set OPENROUTER_API_KEY`), because a key that lives on one
  machine is a key nobody can see rot: the deployed one was revoked, the dashboard still
  reported the engine "ready" (it only ever asked whether a key EXISTS), and every run failed
  with 401 "User not found" while local runs were fine on a different file. The deploy now
  makes one real call against the running container, so a dead key is a red deploy.
- **The shared OpenRouter key has a $20/day cap** (checked 2026-08-27: $18.32 already spent
  that day, $1.68 left). It reports exhaustion as HTTP 403 "Key limit exceeded", which is NOT
  a dead key. `GET https://openrouter.ai/api/v1/key` answers the question in one call.
- **A failed run is not an empty economy.** If grading calls fail, the run still exports a CSV.
  The breaker now says so in the log ("coverage is INCOMPLETE"); never read a zero-row run as
  "this economy has no such law" without checking the `[error]` lines first.
- **Never write a translation into `Verbatim Snippet` or `Law Name`.** The snippet IS the
  citation; a translated snippet is a false citation. Translations live in 2 extra columns.
- **7.1 and 7.2 have INVERTED polarity** in the RDTII scoring rubric — a comprehensive /
  dedicated horizontal framework scores 0. Roll-up takes MIN for those, MAX otherwise.
- **`OUTPUT_TEMPLATE_31MAY.xlsx` mislabels P7-I2** as "purpose limitation". It is
  **cybersecurity**. Ignore that "Indicator Reference" sheet.
- **Streamlit on Windows: `pkill -f "streamlit run"` does not kill it.** Stale code keeps
  serving 8501. Stop it with PowerShell `Stop-Process` and verify by the port-8501 owner.
- **All UI work goes through the `ui-ux-pro-max` skill** before interface code is written.
  Do not reintroduce the retired parchment/serif "Legal Dossier" look.

---

## §5 Recently done

- [x] **Phase 1 — pre-retrieval failures made loud** (2026-09-07). Serper answered HTTP 400
      "Not enough credits" and `_serper()` returned `[]`, so a spent key read as an economy
      with no law; `data/cache/_search.json` held 890 entries last written 2026-08-31 with no
      TTL, and Singapore (websearch-only) was replaying them. Engines now raise
      `EngineUnavailable`, cache entries carry `fetched_at` + engine and expire after
      `search_cache_max_age_days=7`, and `discovery.explain_empty_discovery` emits the
      `[error]` pair. `tools/cache_gc.py` gives the 1.3 GB cache a lifecycle.
      `tests/test_websearch_diagnostics.py`, `test_empty_discovery.py`, `test_cache_gc.py`.

- **2026-08-31** All six economies re-run live on the day's fixes (`outputs/after_fixes/`,
  `logs/rerun_20260831.log`). **$7.39 and 186 minutes**, against $2.07 / 72 min before.

  | | panel cites | HIT | wrong indicator | missing | rows exported |
  |---|---|---|---|---|---|
  | SG | 12 | 9 → 9 | 0 → 0 | 3 → 3 | 167 → 349 |
  | AU | 15 | 6 → 8 | 1 → 1 | 8 → 6 | 299 → 402 |
  | MY | 48 | 12 → 19 | 10 → 6 | 26 → 23 | 272 → 426 |
  | CN | 37 | 14 → 21 | 3 → 1 | 20 → 15 | 138 → 473 |
  | IN | 16 | 7 → 7 | 2 → 2 | 7 → 7 | 172 → 162 |
  | MN | 20 | 7 → 8 | 9 → 10 | 4 → 2 | 101 → 309 |
  | **all** | **148** | **55 → 72** | **25 → 20** | **68 → 56** | **1,149 → 2,121** |

  Cited provisions found rose 31%, misfilings fell, misses fell — and output volume nearly
  DOUBLED. China gained most (the `</html>` parser fix took its corpus from 335 to 765
  provisions); India moved not at all, because 15 of its 16 cited provisions are on hosts that
  answer nothing.
- **2026-08-31** **The confidence formula has never rejected a row.** Of 2,320 mappings, 199
  were quarantined and ALL 199 came from the two hard caps (82 scope, 117 topical); ZERO came
  from the weighted sum. `snippet_grounding` is 1.000 on every row ever scored — the snippet is
  copied out by extraction and the model never writes it, so the question has one possible
  answer and 20% of the weight is inert. `scope_alignment` is 1.0 on 94%, and the model self-
  reports `legal_match` 0.9 on 79%. The floor is ~0.71 against a 0.60 quarantine threshold: the
  two cannot meet. 1,801 of the 2,121 surviving rows land in "needs review", so that band
  flags 85% of the output and tells a reviewer nothing.
- **2026-08-31** Acceptance concentrates in the three indicators whose test is not checkable.
  Same corpus, same model, same shortlist: AU P7-I4 ("appoint a DPO / run a DPIA") accepted 3
  rows; P7-I5 ("government access to personal data") accepted 143, P7-I1 106, P7-I3 59. The
  difference is that P7-I4 asks a yes/no question about a named artefact. That is the shape the
  P6 gates took on 2026-08-31 and the shape P7-I5/I1/I3 still need.
- **2026-08-31** **The AU evaluation corpus is 53% amending instruments** — 9,684 of 18,262
  provisions whose text is "omit X, substitute Y", carrying the vocabulary of the law they amend
  while not being operative law. Australia publishes COMPILATIONS, so their effect is already in
  the principal Act: they are duplicate text. Every AU retrieval number measured on 2026-08-31
  is therefore measured against a corpus half of which the live pipeline never sees — including
  the cap of 450 that doubled the LLM spend. On the filtered corpus, AU P7-I5 ranks improve
  665 → 268 (DAT Act s.104) and 901 → 434 (TIA Act s.10), and the top 12 goes from 13 amendment
  Acts, Hazardous Waste, Fair Work and an "ANZ submission" to 12 of 12 on-topic.
  The LIVE path is clean — `discovery._drop_amendment_docs` already runs for SG/AU, and 0 of
  402 exported AU rows come from an amending instrument. This is an evaluation-corpus defect,
  so it corrupts measurements, not the submission.
- **2026-08-31** Localisation precision. All 24 auditor-refused P6-I1/I2/I3 rows read, grouped
  by fault, and three negative gates written against the groups: the thing restricted must be
  DATA (India's Chemical Weapons Convention Act was exported as a cross-border data ban), a
  storage rule must NAME A PLACE (six record-keeping duties silent on where), an infrastructure
  rule must NAME INFRASTRUCTURE (a ministry's functions read as a server mandate). The fourth
  group — a conditional regime filed as a ban — is deliberately left alone: a rule strong enough
  to catch it loses Malaysia's PDPA s.129, which the panel scores as a ban because its gazette
  whitelist is empty. Measured by `tools/replay_grade.py` over 107 exported rows, twice,
  identically: **CONTROL 11/11 held, UPHELD 8/8 held, REJECTED fell 4 → 14 of 24.**
- **2026-08-31** `tools/replay_grade.py` — re-grades rows already exported under a proposed
  definition, no crawl. The previous definition change was judged by re-running three economies
  (forty minutes, real money, recovered nothing) when a definition edit can only alter the
  grader's verdict on a provision it was already shown. Staging area: `tools/candidate_indicators.py`.
- **2026-08-31** **`www.gov.cn` emits a stray `</html>` in its page header.** lxml obeys it,
  treats the document as finished and discards the entire statute — no exception, no warning, a
  short and perfectly valid string. Nine Chinese documents recorded as "shell" were this,
  losing **25x to 155x** of text (Counter-Espionage Law, Network Data Security Regulation,
  Industrial and Telecom Data Protection Measures). `ocr._soup` now checks the yield against a
  regex estimate and retries with html.parser. **CN: shells 10 → 1, split 9 → 18, provisions
  335 → 765.** `EXTRACT_FORMAT_VERSION` → v5, because the cache key is the document's bytes and
  a rebuild kept serving the collapsed text.
- **2026-08-31** Two smaller honesty defects found while diagnosing it: a document yielding
  ZERO characters was recorded as state "split" (built successfully), and "SKIPPED by
  robots.txt" was logged both for a host that refuses us and for one whose robots.txt is
  unreadable because it answers nothing. The second cost half an hour of misdirected diagnosis.
- **2026-08-31** Retrieval budget re-measured per provision (`logs/budget_measure_20260831.txt`,
  `data/retrieval_budget.json`). Of the cited provisions THE CORPUS HOLDS, reached at k=450:
  **SG 12/12 · CN 26/29 · MN 20/20 · AU 10/21 · MY 25/55 · IN 1/1**. Three readings:
  · **SG's shipped cap of 80 was losing 2 of its 12** — provisions already in the corpus that
    the shortlist never reached. That is part of the 55 "in corpus but not in the submission".
  · **India's 1/16 on all cited provisions is not a retrieval failure at all** — 15 of the 16
    never fetched. Splitting the metric is what makes that visible; a cap chosen from 1/16
    would only have bought calls.
  · **AU and MY are a RANKING problem, not a depth problem.** AU goes 3/21 → 10/21 while k
    rises elevenfold and still loses half. Extending the ladder past 450 buys recall at a very
    poor rate; a better ranker is the lever.
  Recall was still rising at k=450 for five of six, so every "plateau" claim in the file now
  says so — `_derive` used to assert a plateau unconditionally, which was false for five.
- **2026-08-31** A measured cap now IS the depth. It was written `min(n, cap, max(floor, 5% of
  n))`, so the heuristic stayed in charge and a measurement could only ever SHRINK a shortlist:
  Singapore's measured k=450 would have been overridden by ceil(5% x 6,752) = 338 on a real
  crawl, and the measured number never tested. Cost of the correction across the six
  economies: **~6,300 → ~21,000 grading calls, $2.07 → ~$6–7 a submission.**
- **2026-08-31** `harness.evaluate` recorded **one bit per indicator** — did ANY cited provision
  arrive — and the retrieval budget was derived from it. On Malaysia that bit reads 7/8 while
  the panel cites 72 linkable provisions there, so it saturates long before recall does.
  `prov_recall_each` (all cited) and `prov_recall_available` (those the corpus holds — the one a
  depth budget can move) are added; the old bit is unchanged, because the shipped retrieval
  parameters were swept against it.

- **2026-08-28** The deployed site could not judge a single provision: its key lives in a file
  on the Sager box, hand-edited and re-checked by nothing, and it had been revoked. Keys now
  come from the repository secrets, the deploy proves one real call inside the running
  container, and `rotate-key.yml` replaces a credential without queueing behind the suite.
- **2026-08-28** Country list corrected to the panel's eight; Timor-Leste now exists in the
  codebase (code, UN name, aliases, Portuguese profile, seed query terms, gazette lane, map).
- **2026-08-28** Budget validated on exported CSVs (see §3.3). Two defects found doing it: a
  non-reentrant lock in the circuit breaker that deadlocked the run and hung CI for two hours,
  and `openpyxl` never declared in requirements, so a clean clone could not read the panel's
  workbooks at all.

Older milestones (2026-08-25, 2026-08-27) are pruned per the rule in "How to keep this file useful" — they are in git history.

---

*Last updated 2026-08-31.*
