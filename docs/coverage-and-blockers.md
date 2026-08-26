# Coverage and blockers — measured, 2026-08-22

Every number here came from a run or from counting a registry. Where something has not been
measured the row says so rather than estimating.

---

## 0 · Re-measured 2026-08-25 — all six reference economies run live end to end

Each economy below was re-run from zero seed URLs (`--live --fresh`), both pillars in one run,
on the declared engines. "Rows" counts the 14-column submission CSV; every run addresses all
nine indicators, either with evidence or with an explicit "No provision found" placeholder
row — so the pillar-6+pillar-7 requirement is met structurally even where the evidence is thin.

| Economy | Docs | Provisions | Rows | Wall clock | Cost | Answer-key reach |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Singapore | 37 | 6,752 | 128 | 27 min | $1.08 | not scored here (Round-1 key) |
| Australia | 30 | 4,948 | 128 | 29 min | $0.84 | not scored here (Round-1 key) |
| Malaysia | 31 → **10 fetched** | 489 | 41 | 7 min | $0.20 | not scored here (Round-1 key) |
| China | 40 → 12 fetched | 220 | 40 | 9 min | $0.18 | **6/9 indicators · 6/31 citations** |
| India | 121 → 27 fetched | 983 | 44 | 26 min | $0.21 | **6/9 indicators · 7/43 citations** |
| Mongolia | 22 | 535 | 55 | 6 min | $0.26 | **3/9 indicators · 3/11 citations** |

Movement against the 2026-08-22 numbers: India improved 3/9 → **6/9** (its second source,
`meity.gov.in`, now contributes the DPDP Rules 2025 — the operative cross-border instrument);
China slipped 7/9 → 6/9 — see the two new blockers below, both are portal-state, not code
regressions. Mongolia is unchanged at 3/9, and inspection shows part of that is the key citing
different record versions of the same law (our Cybersecurity-Law and Banking-Law citations
exist in the CSV under the same titles; the key's `lawId`s differ).

**New blocker 1 — Malaysia's primary portal is currently PDF-less for us.**
`lom.agc.gov.my/robots.txt` returns **HTTP 500** (measured twice on 2026-08-25). The fetch
layer treats an unreadable robots file as "disallowed", so every statute PDF on the AGC
portal was skipped — the run above survived only because `pdp.gov.my` (the PDP Commissioner's
site) carried the PDPA Amendment Act 2024, the cross-border Guidelines 3/2025 and the DPIA
guideline. The India lane already has the correct carve-out (RFC 9309 §2.3.1.4: a 5xx robots
response is not a refusal — proceed); Malaysia needs the same one-line treatment.

**New blocker 2 — China's principal statutes depend on network reachability.**
`cac.gov.cn` (the mirror lane the horizontal laws ride on) **TLS-timed-out** from the test
network on 2026-08-25, and `flk.npc.gov.cn` serves a JS shell with no static law text, so
PIPL, the Cybersecurity Law and the Data Security Law did not enter this run's corpus at all.
The 6/9 reach above was achieved on `moj.gov.cn` / `mee.gov.cn` mirrors (Network Data Security
Regulation, Counter-Terrorism Law). If cac.gov.cn is reachable from the run network the
horizontal laws return; the lesson is that CN needs either a rendered flk.npc.gov.cn lane or
more mirrors, because one unreachable host currently decides whether China's most-cited law
exists in the run.

**The live-test six remain unready.** TH, VN, ID, KZ, LA and RU have only generic
`websearch` lanes with zero portal-scoped queries and `verified: false` in `data/sources.yaml`.
Measured 2026-08-25: TH and ID discovery timed out (the lanes hang on the DuckDuckGo HTML
endpoint from this network), and VN returned 22 documents of pure noise — EU GDPR guidance,
Canada's Digital Services Tax, India's Income Tax Act — because `OFFICIAL_PORTAL` has no VN
entry so the queries run unscoped. KZ, LA and RU share the same lane shape (LA's gazette host
does not resolve; RU's document path sits under a robots-disallowed `/File`). These six need
per-portal adapters of the kind CN/IN/MN received; no amount of retrieval tuning substitutes
for that.

---

## 1 · The three economies that run end to end

End to end here means what it says: from an economy and a pillar, with no seed URLs, through
discovery, fetching, extraction and mapping, to a submission CSV in the official 14-column
format. All three do that. Whether the *content* is right is the separate question in §2.

| | Documents | Provisions | Rows | Laws cited | Wall clock | Cost |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| China · pillar 6 | 18 | 268 | 20 | 10 | 105 s | — (cached) |
| China · pillar 7 | 17 | 420 | 51 | 9 | 244 s | $0.1377 |
| India · pillar 6 | 18 | 18 | 1 | 1 | 76 s | $0.0317 |
| India · pillar 7 | 18 | 18 | 8 | 5 | 219 s | $0.0522 |
| Mongolia · pillar 6 | 15 | 52 | 1 | 1 | 115 s | $0.0873 |
| Mongolia · pillar 7 | 18 | 76 | 39 | 4 | 262 s | $0.2149 |

India's 18 documents → 18 provisions is not a defect: India Code publishes one SECTION per
record, so one provision per document is the publisher's own unit.

Against the panel's Round-2 answer key (`tools/score_round2.py`, matching on portal URL first
and instrument name second):

| | Indicators reached | Citations matched | How |
| :--- | :--- | :--- | :--- |
| China | **7 of 9** | 8 of 31 | by name |
| Mongolia | 3 of 9 | 3 of 11 | by URL — exact `lawId` |
| India | 3 of 9 | 3 of 43 | by name |

Read those two columns together. China reaches most indicators but few citations because the
key names three to five *sectoral* instruments per indicator and we find the horizontal
national law. India's 3-of-43 is the same shape, much worse: 19 of the key's 43 citations sit
under 7.3 alone, almost all of them RBI, SEBI and PMLA instruments.

> Mongolia scored **0 of 9** on the first attempt, and that was a measurement error, not a
> result. The key writes the instrument in English ("Law on Personal Data Protection");
> legalinfo.mn serves it in Mongolian. No string comparison bridges that. The scorer now
> matches on the portal id in the URL first, which is language-independent.

---

## 2 · Blockers, per economy that runs

### China — the sectoral tail

The horizontal laws are found reliably: PIPL, the Cybersecurity Law, the Data Security Law,
the Network Data Security Regulation, the Cybersecurity Review Measures. What is missed is the
long tail the panel's analysts also recorded — ride-hailing measures, online lending, credit
reporting, population health information, map management, online publishing, e-mail services,
the Counter-Terrorism and Counter-Espionage Laws, GB/T technical standards.

**Why.** Those are sectoral instruments whose titles contain no data vocabulary at all. Neither
a concept query nor a title fragment reaches 《网络预约出租汽车经营服务管理暂行办法》 from
"cross-border data transfer".

**What would close it.** A sector sweep: for each pillar, a list of the sectors RDTII treats as
in scope (transport, lending, credit, health, mapping, publishing, e-mail, payments) crossed
with the pillar's obligation phrase. It is more queries, not a new mechanism.

**Also open.** `flk.npc.gov.cn` returns `"permission": {"download": 0}` — the operator saying
the documents are not to be downloaded. We do not engineer around that. cac.gov.cn carries the
same national laws and is the lane we use.

### India — the law is not in the statute book

India Code is the cleanest source we have: a DSpace API, one record per section, operative text
and an in-force flag included. The problem is not the portal.

**Why.** India's P6/P7 evidence is overwhelmingly *subordinate*: the IT (Reasonable Security
Practices) Rules 2011, the IT (Interception) Rules 2009, the DPDP Rules, RBI Master Directions,
SEBI circulars, PMLA rules. Those are gazette PDFs on `meity.gov.in` and `rbi.org.in`. India
Code holds Central **Acts**. We are searching the right index for the wrong tier.

**What would close it.** A second India source, the way Malaysia has `pdp.gov.my` beside the
AGC catalogue — `meity.gov.in` and `rbi.org.in`, PDF-only, on obligation phrases.

**Fixed on the way here.** The adapter lane checked its document budget after each query and
broke out of the loop. Fine when a query returns a handful; fatal when one returns 46. India
Code answered `'personal data protection'` with 46 sections, the cap tripped on the first
query, and the run never searched for retention, government access or cybersecurity — pillar 7
came out as 17 sections of one Act. Queries are round-robined now.

### Mongolia — the corpus is mostly not law

Discovery and body retrieval are solved: `/sitemap.xml` enumerates 36,833 instruments, and
`POST /mn/downloadFile` returns each one as UTF-8 HTML, so **no OCR is involved anywhere**.

**Open blocker 1 — the catalogue is nine parts paperwork to one part statute.** A term like
`банкны тухай` matches 193 titles, of which one is the Banking Law; the rest are orders and
rules made under it. `MN_MAX_PER_QUERY` takes the twelve shortest titles, which is a proxy for
"principal instrument" and not a good one.

**Open blocker 2 — instruments with no numbering at all.** A national programme's action plan
is a 24 KB table of measures with neither `зүйл` headings nor `N.N.` clauses. It still extracts
as one block. Arguably it is not law and should not be in the corpus at all, which is the
better fix.

**Two defects closed here, both worth remembering.**

*Extraction.* Only a Mongolian **law** numbers its articles `N дүгээр зүйл`. A журам, дүрэм or
заавар — the rules a ministry makes under one — heads chapters `Нэг.` and numbers clauses
`1.1.`, `2.3.`. Every one of them collapsed into a single provision. Measured on real
documents: a customs rule 1 → 29, a charter 1 → 34, an information-security audit rule 1 → 25.

*Vocabulary.* `хилийн чанад` was in the pillar-6 query set as "abroad". It matches 21 titles
and every one is a customs regulation about processing **goods** abroad. Twelve of seventeen
documents in a pillar-6 run were those. The word `хилийн` does not appear once in Mongolia's
Personal Data Protection Law — its article 14 says `гадаад улс дахь`, "in a foreign state".
**A term taken from a dictionary rather than from the statute cost the run its document set.**

---

## 3 · The query vocabulary, counted

The short answer to "is there a keyword set per economy per pillar" is **no**. There are three
layers with very different coverage, and only two economies have anything portal-specific.

| Layer | Covers | Where |
| :--- | :--- | :--- |
| English indicator terms | **491 terms, all 61 indicators, all 12 pillars** | `rdtii/indicators.py` + `indicators_wide.py` |
| Pillar concept phrases | all 12 pillars | `rdtii/keywords.PILLAR_SEARCH_TERMS` |
| Law-name fragments (name-only portals) | 10 pillars (6 and 7 have per-indicator sets instead) | `keywords.PILLAR_NAME_FRAGMENTS` |
| Hand-tuned name/description split | **9 of 61 indicators** — pillars 6 and 7 only | `keywords.INDICATOR_SEARCH_TERMS` |
| Native-language terms | **2 languages, 9 indicators each** — 82 terms total | `rdtii/query_terms_i18n.py` |
| Portal queries scoped per pillar | **China and Mongolia only** | `data/sources.yaml` |

Per economy, measured:

| | Adapter | P6 portal queries | P7 portal queries | Other pillars | Native language | Native terms |
| :--- | :--- | ---: | ---: | ---: | :--- | ---: |
| SG | websearch | 0 | 0 | 0 | English | — |
| AU | au_api | 0 | 0 | 0 | English | — |
| MY | my_catalogue | 5 | 5 | 5 | English | — |
| **CN** | websearch | **9** | **16** | 0 | zh | **49** |
| IN | in_dspace | 0 | 0 | 0 | English | — |
| **MN** | mn_legalinfo | **3** | **10** | 0 | mn | **33** |
| TH | websearch | 0 | 0 | 0 | th *(mapped, empty)* | **0** |
| VN | websearch | 0 | 0 | 0 | **not mapped** | 0 |
| ID | websearch | 0 | 0 | 0 | id *(mapped, empty)* | **0** |
| KZ | websearch | 0 | 0 | 0 | **not mapped** | 0 |
| LA | websearch | 0 | 0 | 0 | **not mapped** | 0 |
| RU | websearch | 0 | 0 | 0 | ru *(mapped, empty)* | **0** |

Three things that row structure makes visible:

1. **Thailand, Indonesia and Russia are mapped to a language that has no terms.**
   `ECONOMY_QUERY_LANG` says `th`, `id`, `ru`; `NATIVE_QUERY_TERMS` has only `zh` and `mn`. So
   `native_terms()` returns an empty list and nothing says so. That is the silent-empty failure
   mode this project keeps producing.
2. **Viet Nam, Kazakhstan and Lao PDR are not mapped at all**, so they fall through to English
   against a non-English corpus.
3. **No native vocabulary exists for any of pillars 1–5 and 8–12, in any language.** Those 52
   indicators have English terms only — usable for India and the Round-1 three, useless for
   everyone else.

Of the 144 economy × pillar cells, **4 have portal-specific native queries** (CN and MN, pillars
6 and 7). The rest run on generated English.

**The lesson Mongolia taught, which shapes how the rest should be built.** Terms must be
measured against the portal's own index before they are trusted — how many titles does this
term match, and are they the right ones? `tools/audit_native_terms.py` exists for this and had
never been run against a real corpus. A term chosen from a dictionary is a guess with a
plausible accent.

---

## 4 · The six economies that do not run yet

Each has one concrete unknown. None of them is "the model is not good enough".

| | Portal | State | The question to answer next |
| :--- | :--- | :--- | :--- |
| **Thailand** | krisdika.go.th | TLS fixed (self-signed cert); `/`, `/th/` and `/web/guest/law` all 404 | **Where do the documents live?** The host answers but no path we have tried serves a statute. Needs the site's own JS to be read for its API, the way India's was. Thai statutes are frequently scanned PDFs, so this is also the first economy where OCR is on the critical path. |
| **Viet Nam** | vbpl.vn | portal answers; no adapter | Does vbpl.vn expose a document id in the URL (like legalinfo.mn) or is the text JS-gated (like AU)? That one answer decides whether this is a day or a week. |
| **Indonesia** | peraturan.bpk.go.id | portal answers; no adapter | Its robots.txt blocks nine **named** AI crawlers and grants the wildcard group with `Content-Signal: use=reference`. We are permitted as `VeriTrade-Research/0.2` — the question is whether the catalogue is enumerable, not whether we may read it. |
| **Kazakhstan** | adilet.zan.kz | portal answers; no adapter | robots.txt closes `/rus/search/` and `/rus/list/docs/` and leaves `/rus/docs/<id>` open. So enumeration cannot use the listing paths: **is there a sitemap, or must ids be discovered another way?** This is a design constraint on the adapter, not a fetch-time rejection. |
| **Lao PDR** | laoofficialgazette.gov.la | host does not resolve | The URL itself is wrong. **What is the current gazette host?** Nothing else can be asked until that is answered. |
| **Russia** | publication.pravo.gov.ru | portal answers; no adapter | robots.txt disallows `/File`, which is where the document bodies are, and permits `/document/<id>` and the sitemap. **Does the `/document/` page carry the text, or only a link into `/File`?** If the latter, this economy is closed to us by the operator's own rule. |

---

## 5 · System-wide questions still open

**Retrieval parameters were measured on English.** `hybrid_alpha=0.65`, `retrieve_max_top_k=300`
and the rest were swept on a 383-law English corpus. BM25 now runs on character bigrams for
no-space scripts. Whether 0.65 still holds when the lexical side changed shape is unknown, and
`tools/sweep_retrieval.py` can answer it with data rather than argument.

**The 52 new indicators have never been scored.** They have legal tests and query terms and
they run. Nothing has checked whether the definitions actually discriminate — and the Round-2
database contains all 12 pillars for 7 economies, so the material to check them against is
already in the repo.

**The cross-encoder is off for every non-Latin economy.** `bge-reranker-v2-m3` is declared as
the multilingual reranker and has never been benchmarked; it is ~2.2 GB, which is material on a
CPU-only judging machine. Its absence degrades gracefully, but "safe" is not "measured".

**No OCR engine on this machine reads Cyrillic or Lao.** It has not mattered yet: China,
India and Mongolia are all text. Thailand and Lao PDR are where it starts to.

**A portal publishing more than law.** cac.gov.cn carries press Q&A and expert commentary beside
each measure, in the same template and vocabulary; three graded confidently in a real run.
`rdtii/instrument.py` now classifies them, but the general problem — telling an instrument from
a page *about* an instrument — will recur on every portal that has a newsroom.

**Nothing has been run twice on different days.** Every measurement in this file is one run.
Live portals change; a number from a single run is a reading, not a rate.
