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
| SG | portal adapter, verified | yes (14,610 prov) | yes | **cap 80** (prov+law recall 1.000 from k=40) | 2026-08-28 · 7/7 answer-key indicators at 760 calls |
| AU | portal adapter, verified | yes (18,262) | yes | **cap 450** — genuinely needs the depth (1.000 only from k=300) | 2026-08-28 · 8/8 answer-key indicators |
| MY | portal adapter, verified | yes (14,903) | yes | **cap 150** (law recall 1.000 from k=80; prov flat 0.875 at every k) | 2026-08-28 · robots carve-out landed: 489 → 5,931 provisions |
| CN | 2 portal lanes, unverified | eval, 19 docs / 261 prov ⚠ 1.9k chars/doc | yes | no | 2026-08-25 (fragile) |
| IN | 5 lanes, unverified | eval, 7 docs / 224 prov | yes | no | 2026-08-25 |
| MN | 1 lane, unverified | eval, 4 docs / 397 prov | yes | no | 2026-08-27 |
| TH | generic websearch only | eval, 6 docs / 103 prov | yes | no | **no** |
| ID | generic websearch only | eval, 7 docs / **7 prov** ⚠ unsplit | yes | no | **no** |
| LA | generic websearch only | eval, 2 docs / 452 prov | yes | no | **no** |
| RU | body route solved, discovery open | eval, 2 docs / **2 prov** ⚠ chrome only | yes | no | no |
| **TL** | gazette lane, unverified | no | **impossible** (no database sheet) | no | reachable only |

"Labels" = rows parsed from the panel's own databases by `backend/eval/ground_truth.py`
(223 rows / 10 economies / 90 indicator-pairs). "eval" corpora are seeded from the panel's own
citations by `backend/corpus/catalogue_database.py` — an EVALUATION corpus, never discovery: the
live pipeline imports nothing from `backend/corpus`, and a test pins that. SG/AU/MY are built
from their real portal enumerators and are the only ones whose numbers are self-contained.

---

## §3 Open work — the checklist

Priority order. `[ ]` not started · `[~]` in progress · `[x]` done (move to §5 and prune).

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
- [ ] **The splitter knows three drafting styles and the list has eight economies.**
      `extraction.py` handles English "Section", Chinese 第X条 and Mongolian "N.N." — there is no
      pattern for Indonesian **Pasal**, Russian **Статья**, Thai **มาตรา** or Portuguese
      **Artigo N.º**. Indonesia is the clean demonstration: 7 documents in, 7 provisions out,
      one undifferentiated block each. Article-level citation is criterion C2b, ten points.
- [ ] **RU and CN corpora hold chrome, not law.** RU's 1,150 chars/doc is the IPS frameset
      (measured 2026-08-28: the wrapper carries 586 characters and no statute); CN's 1,966 is
      a gov.cn landing page. Both need the body route wired before their numbers mean anything.
- [ ] India fetch: 20 of 27 cited instruments failed to download.
- [ ] Portal adapters for TH · ID · LA · RU (today: generic websearch, `verified: false`).
      Measured 2026-08-25: TH and ID time out on the DuckDuckGo HTML endpoint; LA's gazette
      host does not resolve.
- [ ] Timor-Leste: no lane, no language profile, no OCR path. Carries a scoring bonus.
- [ ] MY robots carve-out — `lom.agc.gov.my/robots.txt` returns HTTP 500 and the fetcher reads
      "unreadable" as "disallowed", so every statute PDF on the primary portal is skipped.
      India already has the RFC 9309 §2.3.1.4 carve-out; MY needs the same.
- [ ] CN principal statutes must survive `cac.gov.cn` being unreachable (PIPL / CSL / DSL).
- [ ] MY: one cited provision never reaches the shortlist at ANY budget (prov-recall flat
      0.875 from k=40 to k=450, `data/retrieval_budget.json` curve). Depth is not the fix —
      find out which provision and why the ranker cannot see it.

### Cost and reliability (scores C5, and stops burning the shared key)
- [x] Circuit breaker + honest failure classification in the grading loop (2026-08-27).
- [x] Per-economy retrieval budget, measured not hand-tuned (`tools/measure_budget.py`).
- [ ] Re-measure the budget for CN/IN/MN/TH/ID/LA/RU **once their corpora exist** — until then
      they correctly keep the conservative default and pay the old call count.
- [ ] Surface `[error]` lines on the Run screen. `frontend/runview.py` has no branch for that
      tag, so the breaker's plain-English cause reaches only the raw log — which is why a
      zero-row run still *looks* like an empty economy. UI work → invoke `ui-ux-pro-max` first.
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
- **A per-economy budget may only ever NARROW a shortlist, and only where measured.**
  An economy with no entry in `data/retrieval_budget.json` keeps the global default. Spending
  too much costs money; spending too little costs a submission row that nothing downstream can
  notice is missing. (2026-08-27, `backend/pipeline/retrieval_budget.py`)
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
- **2026-08-27** Round-2 labels: `ground_truth.py` reads both Database workbooks; added
  `_ARTICLE_RE`, because Round-2 economies cite "Article N" and every such row previously
  parsed to zero targets — silently. 223 label rows across 10 economies.
- **2026-08-27** Grading circuit breaker + honest failure classes (`LLMTerminalError`). A
  Singapore pillar-6 run on an exhausted key had made **968 doomed calls** and reported a
  spend cap as "check the LLM key/provider".
- **2026-08-27** Per-economy retrieval budget (`retrieval_budget.py`, `tools/measure_budget.py`,
  `data/retrieval_budget.json`). Measured on the shipped selector: **SG cap 80, MY 150,
  AU 450**. Effect on grading calls at the corpus sizes actually seen — SG pillar 6
  968 → **320**, SG pillars 6+7 3,043 → **720**, MY 4,050 → **1,350**, AU unchanged.
  One cited Malaysian provision is unreachable at *every* budget (prov-recall flat 0.875 from
  k=40 to k=450) — that is a retrieval-quality bug to chase separately, not a depth problem.
- **2026-08-27** Three silent Mongolia defects fixed (fleeting-vowel title matching, size-aware
  ranking, clause splitting) — pillar 6 went from 4 documents to 22.
- **2026-08-27** Working-translation layer (2 CSV columns after the mandatory 14).
- **2026-08-25** Live re-verification of SG/AU/MY/CN/IN/MN end-to-end on both pillars.

---

*Last updated 2026-08-27.*
