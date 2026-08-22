# Round-2 expansion — China, India, Mongolia

Round 1 shipped SG, AU and MY. All three publish legislation in English, and that single fact
was load-bearing across far more of the pipeline than it looked. This document records what
actually broke when the assumption was removed, what was changed, and what is still unproven.

The three economies were chosen against the judges' own Round-2 Database, which is the source
of the reference dataset in `data/ground_truth/rdtii_reference_p67.csv` (180 rows across the
six economies). They span the three hard cases deliberately:

| Economy | Statutory language | Script | Why it is on the list |
|---|---|---|---|
| India | English | Latin | The cheap one. Nothing linguistic changes; it tests that expansion itself works. |
| China | Chinese (Simplified) | Han | No inter-word spaces — the case that breaks lexical retrieval outright. |
| Mongolia | Mongolian | Cyrillic | Spaced but non-Latin, and agglutinative — the case that breaks it subtly. |

---

## The failure that mattered most was not the LLM

The obvious worry going in was the grader: would a model asked in English reason correctly
about a provision written in Chinese? That is a real question and it is addressed below, but
it was not the biggest problem. The biggest problem was four characters in the retriever:

```python
_TOKEN = re.compile(r"[a-z0-9]+")
```

Applied to 不得向境外提供 this returns `[]`. Not a weak match — **no tokens at all**. Every
Chinese provision therefore scored exactly 0.0 on BM25, which carries `hybrid_alpha = 0.65` of
the final hybrid score. The ranking collapsed onto the dense signal alone, silently, with
nothing in any log to indicate it. Mongolian Cyrillic failed the same way.

This is the characteristic shape of every bug in this expansion: **nothing throws**. A Chinese
run completes, produces a CSV, and reports "No provision found" for indicators whose laws are
sitting right there in the corpus — output indistinguishable from a country that genuinely has
no such law.

---

## What changed

### 1. Tokenisation — `backend/pipeline/retrieval.py`

Three alternating branches, ordered:

1. Runs in a **no-space script** (Han, kana, Thai, Lao, Khmer, Myanmar) → indexed as
   overlapping **character bigrams**: 个人信息 → 个人, 人信, 信息. This is the approach
   Lucene's `CJKAnalyzer` uses; it needs no segmenter model, and for BM25 it performs
   comparably to word segmentation on Chinese while degrading gracefully on Thai/Lao.
2. **ASCII** → `[a-z0-9]+`, byte-for-byte the Round-1 behaviour.
3. **Other scripts** (Cyrillic, Greek, Devanagari, Arabic, Hebrew, Georgian) → whole words.

Branch 2 is deliberately untouched and pinned by a test. The retrieval parameters in
CLAUDE.md §7 were *measured* on a 383-law corpus, not chosen, and they remain valid only if
Latin tokenisation is identical to what they were measured against.

### 2. Native retrieval vocabulary — `backend/rdtii/query_terms_i18n.py` (new)

A tokeniser that can represent Chinese does not help if the query is still English: BM25 needs
lexical overlap, and there is none between "shall not be transferred" and 不得向境外提供. The
new module adds statutory phrases per indicator per language.

Two properties matter:

- **Additive, never a replacement.** English terms are always kept. A wrong native term can
  only fail to match; it can never displace a term that was working.
- **Lexical side only.** Native terms go into BM25 and the phrase bonus. The dense query stays
  English on purpose — the embedding model is cross-lingual by construction, so an English
  question already reaches Chinese text, whereas mixing two scripts into one query vector
  blurs it.

Provenance is recorded in the module and it is not uniform. The Chinese phrases are quoted
from named operative articles (PIPL art.40 「应当在中华人民共和国境内存储」, art.38 安全评估,
art.52 个人信息保护负责人; Cybersecurity Law art.21 留存不少于六个月). **The Mongolian set is a
seed vocabulary, not quoted statute text, and is unverified.** Mongolian is agglutinative —
BM25 indexes "дамжуулахыг", so the stem "дамжуулах" may never match. Run
`tools/audit_native_terms.py --economy MN --suggest` once a Mongolian corpus exists; it reports
each term as OK / DEAD (0 hits) / NOISE (matches >25% of the corpus) and lists the corpus's own
frequent phrases as replacements.

### 3. Cross-encoder — `backend/pipeline/ranking.py`

`cross-encoder/ms-marco-MiniLM-L-6-v2` is English-only. Scoring a Chinese provision with it
does not produce a weak signal, it produces an arbitrary one — and that arbitrary number is
fused into the final ranking with the same weight as BM25 and the embeddings.

Non-Latin economies now load `BAAI/bge-reranker-v2-m3` (`cross_encoder_model_multilingual`).
If it is unavailable, the reranker is **switched off** rather than falling back to the English
model: two good signals beat three when the third is noise. The loader caches per model name,
so a mixed-economy batch run does not thrash between them.

### 4. Provision boundaries — `backend/pipeline/extraction.py`

- **China**: `第<numeral>条`, with the numeral usually in Han digits (第四十条) rather than
  Arabic. Line-anchored, because 第X条 also appears mid-sentence as a cross-reference
  (依照本法第三十八条的规定) — the same trap the Latin patterns guard against.
- **Mongolia**: `<n> дүгээр зүйл`, with the ordinal suffix varying by vowel harmony
  (дүгээр/дугаар/дэх/дахь). The 14.1 / 20.1.5 forms beneath are *clauses inside* an article;
  splitting on those would shatter one article into a dozen fragments and destroy the context
  the grader needs. The Latin fallback only applies if it finds **more** boundaries, so a short
  two-article Mongolian instrument is not thrown away for a regex that matches nothing.
- **India**: joins the existing SG/MY numbered branch unchanged — the India Code prints
  "43A. Compensation for failure to protect data." in the same numbered margin form.

### 5. The grading prompt — `backend/pipeline/mapping.py`

The question was whether to ask in English and feed local-language provisions, or to translate.
**Translating is not an option**, and not for a quality reason: the Verbatim Snippet column is
the statute's actual text. A translated snippet would be a false citation, and the panel checks
citations.

So the prompt keeps English instructions, feeds the provision unchanged, and adds three things:

- `<SNIPPET_LANGUAGE>` names the language explicitly. A model told "this is Mongolian" behaves
  measurably better than one left to infer it.
- A **step 8** stating the split: reason over the original as written, never rewrite it, but
  produce `operative_rule` and `rationale` in **English** because the submission is English.
  It also states that a provision is judged on what it *enacts*, never on its language —
  neither penalised for being foreign nor credited for resembling an English term. `subsection`
  is copied character-for-character, keeping the source's own numbering (Chinese drafting uses
  the full-width （一）（二）forms, not (1)(2)).
- A **worked example in Chinese** placed first — PIPL art.40 → P6-I2, which is the panel's own
  answer in the Round-2 Database. It demonstrates the rule rather than describing it.

### 6. Economies and discovery

`Economy` gains CN/IN/MN with aliases (PRC, Bharat, …). Resolution order was corrected while
doing so: containment now runs **before** fuzzy matching, because once "republic of india"
existed as an alias, difflib scored it 0.70+ against "Republic of Singapore" and answered
India. The fuzzy cutoff also moved 0.7 → 0.8, since at 0.7 "Indonesia" resolved to India —
which would silently produce a complete Indian run for an Indonesian request.

`data/sources.yaml` gains five lanes: NPC for Chinese national laws plus gov.cn for the State
Council / CAC administrative measures that carry much of China's P6 evidence; India Code plus
MeitY for the IT Rules that are not in India Code; and legalinfo.mn. Discovery queries for CN
and MN are written in the portal's language, because a site-scoped web search can only find
what the index holds. They remain **obligation phrases, never law titles** — 个人信息 境内存储
describes the rule a localisation law imposes, exactly as "records must not be held outside"
does for AU.

---

## Live portal results — measured, not assumed

`tools/probe_portals.py` (robots.txt, reachability, body content, search-index depth) and
`tools/smoke_round2.py` (discover -> fetch -> extract, no LLM call) were run against all five
lanes. **No portal disallows us in robots.txt and none is unreachable.** Four of five lanes work.

| Lane | Reachable | Search index | End-to-end |
|---|---|---|---|
| `gov.cn` / `cac.gov.cn` | OK | OK | **5 docs, 127 provisions — incl. PIPL (74)** |
| `flk.npc.gov.cn` (NPC) | SPA | thin | discovery only — bodies are not downloadable |
| `wb.flk.npc.gov.cn` (CN docs) | expired TLS | thin | 3 docs, 110 provisions (provincial tier) |
| `indiacode.nic.in` / `meity.gov.in` | OK / JS shell | OK | **4 docs, 81 provisions — incl. DPDP Act 2023** |
| `legalinfo.mn` | OK | OK | **2 laws, 134 provisions** |

The Mongolian result is the strongest evidence the multilingual work is real: the query
`хувь хүний мэдээлэл хамгаалах` — an obligation phrase, not a title — returns
`legalinfo.mn/mn/detail?lawId=16390288615991`, which is **exactly the URL the panel cites** in
the Round-2 Database for Mongolia's Law on Personal Data Protection. No seed URL was involved.

### Five ingestion defects the live run exposed

Every one was silent. The run completed, produced a CSV, and simply contained less.

1. **`wb.flk.npc.gov.cn` has an expired TLS certificate.** It is the static document host for
   China's National Laws database — every statute PDF and DOCX the search index points at lives
   there. Verifying it cost the entire economy: fetch failed, discovery still listed the
   documents, and the run reported "No provision found" for all of China. Handled with a narrow
   host allowlist in `fetch._TLS_RELAXED_HOSTS`, never a global `verify=False`; the trade is
   spelled out at the definition, and every use is logged. Scrapling verifies TLS through curl
   and cannot be told not to, so it is skipped for those hosts instead of burning three retries
   per document.
2. **Chinese PDFs put spaces between glyphs.** The Hainan Informatisation Regulations extract as
   `第 一 条`, and the unspaced pattern found **3 headings in a 46-article statute**. The
   separator class is `[ \t　]` and deliberately not `\s`, so a heading cannot straddle a line
   break. 3 -> 46 provisions.
3. **China serves many statutes as WORD, as `application/octet-stream`.** A `.docx` is a ZIP, so
   reading it as text produced one provision whose verbatim snippet began `PK docProps/app.xml`.
   Now classified by URL extension and read via MarkItDown, then python-docx. 1 junk -> 31 real
   provisions on the test document.
4. **`flk.npc.gov.cn` is a Vite SPA** whose shell markers none of the existing SPA patterns
   matched; de-chromed it yields the 9-character site title, which became a provision citing
   nothing. Fixing that exposed a second bug in the same function: the "does this page have
   legal structure" test used the Latin-only `SECTION_RE`, so a genuinely server-rendered
   Chinese or Mongolian statute matched nothing and would have been discarded as an empty
   shell — losing the whole document. It now asks in all three conventions.
5. **OCR resolution failed too early, and too late.** Too early: Mongolian resolves to an engine
   with no Cyrillic model, which raised at construction and killed a run whose documents are all
   HTML and never touch OCR. Too late: a profile recording `rapidocr=None` for Lao was still
   built, loading its default English dictionary — the exact silent, script-destroying
   corruption the None was recorded to prevent. Now: engines with no model for the script are
   never built, the best available alternative is substituted and logged
   (`substituted_for`), and if nothing can read the script an `UnavailableOCR` defers the error
   to the moment a scanned page actually needs it.

### China: the NPC database cannot be read, and that turned out not to matter

`flk.npc.gov.cn` is the obvious portal — it is China's official National Laws and Regulations
Database — and it is a dead end for document text. Traced all the way down:

* search *does* reach the right laws: an obligation-phrase query returns
  `/detail?id=<bbbs>&title=…`, and that title parameter decodes to 中华人民共和国个人信息保护法;
* the SPA's own API answers — `/law-search/search/flfgDetails?bbbs=<id>` returns the title, the
  tier (`flxz: 法律`), the issuing body, promulgation and effect dates, and an object-store path;
* but that path resolves only through a signed OFD reader whose file host is an **internal
  RFC1918 address**, and the same API returns `"permission": {"download": 0}`.

`download: 0` is the operator stating these documents are not to be downloaded. **We stop
there** — that is a compliance answer, not an obstacle, and the same judgement already applied
to `peraturan.bpk.go.id` in robots.txt. What remains reachable on `wb.flk.npc.gov.cn` is the
provincial tier (地方性法规), which extracts correctly but is the wrong tier for national
indicators.

None of that costs us China, because `cac.gov.cn` publishes the same national instruments as
ordinary server-rendered pages — and it is where half the panel's own China citations point.
Measured end-to-end: **中华人民共和国个人信息保护法 74 provisions**, 数据出境安全评估办法 20,
个人信息出境认证办法 19, 互联网域名管理办法 58, and the 2017 个人信息和重要数据出境安全评估办法
18 — whose Article 2 is verbatim the P6-I2 local-storage rule (应当在境内存储). The lane order in
`data/sources.yaml` was flipped so this one runs first; leaving NPC first let it spend the whole
document budget on provincial regulations.

Residual noise: cac.gov.cn also carries 答记者问 press Q&A pages about the measures. They fetch
and split into a single block, so they are visibly *not* statutes rather than mistaken for
them — the grader rejects them, but a tier filter would spend fewer LLM calls.

## What is NOT done

Being explicit, because these are the parts that would embarrass a demo.

1. **No corpus has been built for CN/IN/MN**, so nothing is yet measured against the reference
   dataset in `data/ground_truth/rdtii_reference_p67.csv`. Discovery and extraction are proven
   to work; retrieval and mapping accuracy on these economies are not.
2. **Mongolian native terms remain a seed vocabulary.** Now that a Mongolian corpus can actually
   be built, run `tools/audit_native_terms.py --economy MN --suggest` and replace what never
   fires. Mongolian is agglutinative — BM25 indexes "дамжуулахыг", so the stem "дамжуулах" may
   never match.
3. **No OCR engine on this machine reads Cyrillic or Lao.** It degrades safely (text-layer
   documents are unaffected, and Mongolia's are all HTML), but a scanned Mongolian PDF would
   fail. `pip install 'rapidocr>=3.9'` or a Tesseract install with `mon` would close it.
4. **`BAAI/bge-reranker-v2-m3` has not been benchmarked**, and it is ~2.2 GB — material on a
   CPU-only judging box. Its absence degrades gracefully (reranker off), so it is safe, but
   "safe" is not "measured".
5. **Round-1 was re-validated and is unchanged.** `tools/validate_retrieval.py` after the
   multilingual work reproduces the pre-change numbers exactly: SG 1.0/1.0, AU 1.0/1.0,
   MY 1.0/0.875, coverage 9/9 for all three. The ASCII tokenisation branch is byte-identical
   by construction and pinned by a test.

## Next steps, in order

1. Build corpora, in the order the evidence supports: Mongolia and India are cleanest, China
   via the cac.gov.cn lane. Then audit the Mongolian native terms against the real corpus.
2. Run the retrieval harness against `data/ground_truth/rdtii_reference_p67.csv` and get the
   first accuracy numbers for these three economies.
3. Consider a cheap tier filter for cac.gov.cn (答记者问 pages) to cut wasted LLM calls.
4. Only then tune. The parameters in CLAUDE.md §7 were measured on an English corpus; whether
   `hybrid_alpha = 0.65` still holds when BM25 runs on bigrams is an open question, and
   `tools/sweep_retrieval.py` can answer it with data rather than argument.

---

# Addendum, 2026-08-22 — Mongolia reads, and China was searching for the wrong thing

Four findings, and three of them began as something recorded wrongly in this repo. They are
kept in that order because the pattern matters more than the fixes: none of the three raised an
error, and all three produced a complete CSV that said "No provision found".

## 1. Mongolia — the body was one POST away the whole time

The `data/sources.yaml` entry has now been wrong twice, in opposite directions.

**First** it said the text was there: "12.4k Cyrillic characters in the response body, so OCR
is not on the critical path". Those characters are the navigation menu, a registration modal,
the Cyrillic alphabet index and a list of industry sectors. `main-huuliin-content` and
`law_content` are present in the markup but EMPTY — the body is injected client-side. Zero
article headings. Counting Cyrillic is not the same as reading it, and it is the same mistake
that had India recorded as "a JS shell" when the portal had simply moved.

**Then** it said the text was not there at all: "no .doc or .docx downloads, unlike China; body
retrieval is unsolved". Falsifiable in one request. The detail page's own toolbar has

```html
<a onclick="downloadAnnexFile(this, '', '4801')">Word</a>
```

and `assets/custom/legal/js/static.js` defines it as

```js
$.fileDownload(URL_APP + URL_LANG + '/downloadFile?file=' + path + '&lawId=' + lawId + '&fDownload=1',
               {httpMethod: "POST"})
```

`POST /mn/downloadFile?file=&lawId=N&fDownload=1` returns the whole instrument. Two useful
surprises in the response:

* it is labelled `.doc` but the bytes begin `<html xm…` — Word-flavoured HTML in UTF-8. There
  is nothing to OCR and no binary format to parse.
* `Content-Disposition: filename="…"` carries the law's Mongolian title, which is the only
  place a title exists without running JavaScript.

Measured against the panel's own Round-2 answer key, which cites lawIds directly:

| lawId | Instrument | Chars | Articles found |
| :--- | :--- | ---: | ---: |
| 16390288615991 | Law on Personal Data Protection | 34,196 | 32 |
| 16390263044601 | Law on Transparency of Public Information | 61,900 | — |
| 523 | Law on Communications | 55,972 | 33 |
| 108 | Banking Law | 134,165 | 76 |
| 16531350476261 | Law on Cyber Security (English text) | 30,931 | 25, via the Latin fallback |

**The bug worth naming.** The first `export_text` flattened the document with a single
`\s+ → " "` and returned 34,196 characters of perfectly good Mongolian, from which
`_STRUCT_RE_MN` found **zero** articles — it is anchored to `^` to keep cross-references out,
and a law arriving as one 34k-character line has exactly one line start. Extraction succeeds,
mapping succeeds, export succeeds; every indicator reads "No provision found". Block elements
are now restored as newlines before the tags are stripped, and `tests/test_mongolia.py` pins
both the fix and the counter-example.

**Discovery** is `/sitemap.xml`: 200, 5.5 MB, **36,833 distinct `lawId`** values (the earlier
note said 13,070 — that was the `/mn/detail?lawId=` form only). Five of the six answer-key
lawIds are in it; the sixth is the `/en/edtl/` English route, a separate id space.

Titles need a catalogue because legalinfo.mn's listing pages build their rows in the browser —
there is no server-rendered index to scrape a title from. `tools/build_mn_catalogue.py` walks
the sitemap once at six concurrent requests and writes `data/catalogues/MN_titles.json`: id,
title, byte size. **No provision text, no indicator, no mapping** — a table of contents, the
same arrangement Malaysia already uses, and every body is fetched live at run time.

Also fixed: `_STRUCT_RE_MN` matched only digit ordinals (`14 дүгээр зүйл`). The 1924 and 1940
constitutions spell them out (`Хоёрдугаар зүйл`, `Гучингуравдугаар зүйл` = articles 2 and 33),
and those are cited by operative laws. A trailing lookahead now rejects the genitive/dative
`зүйлийн` / `зүйлд`, which is how a cross-reference reads and which does start a line in a
preamble.

legalinfo.mn serves no `robots.txt` (404 — which under RFC 9309 grants rather than merely
failing to deny), so the catalogue build's pace is ours to choose. It is set low on purpose:
this is a small national portal, the build runs once, and finishing sooner is worth less than
not being a burden on it.

## 2. China — a source's queries were pillar-blind

`data/sources.yaml` let a source carry its own `queries:`, and they were used for every pillar.
The CN set was written for pillar 6 — 数据出境安全评估, 应当在境内存储, 服务器 设在境内 — so a
pillar-7 run searched for cross-border transfer, retrieved the pillar-6 corpus, and mapped
**互联网域名管理办法** (a domain-name administration measure) to the cybersecurity indicator
twelve times. 网络安全法 and 数据安全法 — the panel's own 7.1 and 7.2 answers — were never
fetched at all. Nothing errored. The wrong corpus answered a different question, confidently.

`discovery._source_queries()` now narrows a source's queries to the pillar being run, via
`queries_p6:` / `queries_p7:` keys alongside the pillar-agnostic `queries:`.

| | before | after |
| :--- | :--- | :--- |
| Rows | 21 | 51 |
| Laws reached | domain-name measures | 网络安全法, 个人信息保护法, 数据安全法, 网络数据安全管理条例, 网络安全审查办法, 互联网信息服务管理办法 |
| Indicators landing on a law the panel names | 0 of 5 | 4 of 5 |
| Wall clock / cost | — | 244 s / $0.1377 |

7.5 is the one still missing its named answers (反间谍法, 反恐怖主义法); the run does cite
网络安全法 arts. 28 and 30, which are genuine government-access provisions, so the indicator is
covered but not by the instruments the panel chose.

## 3. An official portal publishes more than law

cac.gov.cn carries the Cyberspace Administration's press Q&A (`《数据出境安全评估办法》答记者问`)
and expert commentary (`《中华人民共和国数据安全法》解读`) on the same site, in the same
template, using each measure's exact vocabulary. They retrieve at the top of the list and grade
confidently — three did, at 0.74 to 0.93. The tell is the citation: a press release has no
article to cite, so every one of them came out as `(document)`.

`rdtii/instrument.py` gains a `COMMENTARY` status. Deliberately NOT included: *guidance*,
*guideline*, *standard*, *specification*, *code of practice*. Those ARE the cited instrument in
several of the panel's own answers — Singapore's PDPC advisory guidelines, China's GB/T 39335
personal-information impact-assessment guide — and blocking them to catch a press release would
cost real evidence.

## 4. The other ten pillars now exist

Fifty-two indicators had criteria and weights in `data/rdtii/indicator_reference.json` and no
`legal_test`. At run time that is not "unsupported": it is a clean CSV of "No provision found"
for every indicator, indistinguishable from an economy with no such law — and the final-round
brief warns the sealed test may name "a pillar you have not worked on".

All 61 in-scope indicators now carry a legal test and query terms
(`backend/rdtii/indicators_wide.py`). Two deliberate separations:

* **The measured nine stay apart.** `INDICATORS` still holds only pillars 6 and 7, and
  `get_indicators(None)` still returns only those — `backend/eval/*` builds its corpus from
  that call, and the retrieval parameters were swept against exactly that set. The honest
  summary is: *the nine are measured, the fifty-two are declared*, and the UI says so per
  pillar rather than presenting twelve equal buttons.
* **The ID is the numeric code.** `P<pillar>-I<n>` cannot express this set: `4.01` and `4.1`
  are different indicators that both collapse to `P4-I1`, and `12.4.1` has three components.

Nine of the fifty-two are framed as an absence ("Lack of a copyright framework"). For those the
evidence to find is the framework itself, and finding it means the economy scores 0 — the same
inversion `scoring_rubric.py` documents for 7.1 and 7.2. `INVERTED` names them and each
`legal_test` says so in words, so a grader cannot read finding the law as a null result.

`--pillar` now accepts a pillar, a list (`6,7,9`) or `all12`. `all` still means 6 and 7: every
script, doc and cached result in the repo assumes it, and widening the default would have
multiplied the cost of every existing command by six.
