# Pre-retrieval discovery for all eleven economies — design

**Date:** 2026-09-07 · **Status:** approved, ready for planning
**Scope:** everything upstream of retrieval — discovery, fetch, extract — for the eleven
economies in `LIVE_TEST_POOL`. Retrieval, grading, scoring and the UI are out of scope.

---

## 1. The problem, as measured on 2026-09-07

Three defects, not one, and they are ordered by how much damage they do.

### 1.1 The shared web-search substrate is dead, and it fails silently

Every engine in `backend/pipeline/websearch.py`, probed directly:

| engine | result |
|---|---|
| Serper (the only reliable one) | **HTTP 400 `{"message":"Not enough credits"}`** |
| DuckDuckGo html / lite | HTTP 202 anomaly-challenge page (intermittently 200) |
| Mojeek | HTTP 200, 5.5 KB, no result markup |
| Scrapling → DuckDuckGo | HTTP 202, body contains `anomaly` and `challenge` |

`_serper()` reads `if r.status_code != 200: return []`. A dead key is therefore
indistinguishable from an economy with no such law — the exact failure shape this project
keeps meeting.

### 1.2 Three economies appear to work only because their search cache is warm

`data/cache/_search.json` holds **890 cached queries, last written 2026-08-31**, and has **no
TTL** (document bodies have `fetch_ttl_hours = 24`; search results have nothing).

```
559 results  site:sso.agc.gov.sg      ← SG "works"
501 results  site:legislation.gov.au
 43 results  site:law.go.th           ← TH does not
  0 results  Laos, Timor-Leste
```

Singapore's **only** discovery lane is `adapter: websearch`. It is not discovering laws live;
it is replaying a cache written a week ago. Same code, same failure, different cache age.

On 15 October the panel runs a sealed live test. A cold cache plus a dead key is a zero-row
run that reports success.

### 1.3 Five economies have no portal-native lane at all

`tools/readiness.py` states it exactly: *"portal answers; no discovery adapter has produced
provisions from it"* — ID, RU, TL. TH and LA are worse (`declared`).

(§2 resolves all of these but RU. This section records the state the work started from.)

---

## 2. What each portal actually serves — probed 2026-09-07, not inferred

The decisive question per economy is **"can this portal be enumerated without a search
engine?"** For **ten of eleven**, the answer is now yes — Russia is the sole exception.

| Economy | Route, verified this date | Needs a search engine? |
|---|---|---|
| **SG** | `enumerate_sg()` sort-window union (SSO ignores `CurrentPage`) → 524 Acts + 5,843 subsidiary. Body `/Act/{id}?ViewType=Pdf` | No — but today it depends on one entirely |
| **AU** | OData `api.prod.legislation.gov.au/v1/titles?$filter=contains(name,…) and collection eq 'Act' and isInForce eq true` | No (lane already live) |
| **MY** | `lom.agc.gov.my/json-updated-2024.php` + `json-amendment-2024.php` | No (lane already live) |
| **CN** | `cac.gov.cn` index pages `A<N>index_<N>.htm`, article pages `//www.cac.gov.cn/YYYY-MM/DD/c_<id>.htm` — **200, 356 links, server-rendered**. Second lane `gov.cn/zhengce/xxgk/` — 200, 209 KB, 921 links | **No** — overturns the "CN needs search" assumption |
| **IN** | India Code DSpace 7 REST, `/server/api`, 130,580 items, one record per section | No (lane already live) |
| **MN** | `/sitemap.xml` → 13,070 lawId; body via `POST /mn/downloadFile?lawId=N&fDownload=1` | No (lane already live) |
| **LA** | Yii app: `?r=site/index&Document_page=N` (paginated list, 300 links/page, 46 PDF refs) → `?r=site/display&id=N` → `/kcfinder/upload/files/*.pdf`. English at `?r=site/switchpage&lc=en` | **No** |
| **TL** | Static frameset tree: `/jornal/lawsTL/RDTL-Law/sidehome-e.htm` → `RDTL-Laws/RDTL-Laws.htm` (**127 PDFs, `Law-YYYY-NN.pdf`**), plus `RDTL-Decree-Laws/`, `RDTL-Gov-Decrees/`, Portuguese twins (`-P`) | **No** |
| **ID** | `peraturan.bpk.go.id` — **403 to httpx on every path**, HTTP 200 to the browser lane. `/Details/<id>` → `/Download/*.pdf` (already in `fetch._BODY_ROUTES`) | No, but **browser-first is mandatory** |
| **TH** | **`POST apig.law.go.th/dga-user-service-phase2/law`** → 200, 114 KB JSON, `rows[]` each carrying **`content_all` — the full Thai statutory text**. Also `GET …/law/master` (200, 50 KB) and `GET …/law/detail/{id}`. Header `x-api-key` is a public constant shipped in the app bundle (§2.1) | **No** |
| **RU** | Fetch is solved: `pravo.gov.ru/proxy/ips/?doc_itself=&nd=<id>&page=1&rdk=0`, cp1251, 13.8 KB of real statute. Discovery is not: the IPS list frame returns 142 KB with 11 links, 8 of them `javascript:;` — rows are injected client-side | **Unresolved — research task** |

### 2.1 Thailand — how the route was found, and why using it is ordinary access

`www.law.go.th` is a React SPA that returns the same 1,256-byte shell on every path. Its bundle
publishes a sourcemap (`main.7a41c7a0.js.map`), and the original `src/api/law.js` and
`src/configs/axios.js` are inside it. They give the whole interface:

```
base    https://apig.law.go.th/
header  x-api-key: 4nEZYvTwRFlUVn7aK85cZ2xSU83dOFai
POST    dga-user-service-phase2/law                  → rows[] with content_all (full text)
POST    dga-user-service-phase2/law/searchResult     → 400 until the payload shape is right
GET     dga-user-service-phase2/law/detail/{id}
GET     dga-user-service-phase2/law/master           → agencies, law types (50 KB)
```

The `x-api-key` is a **public constant compiled into the JavaScript every visitor downloads**,
not a credential anyone must obtain or was issued. It is a routing token for an AWS API
Gateway: unauthenticated requests to a path that does not exist return
`{"message":"Missing Authentication Token"}`, which is the gateway's *route-not-found* reply,
not a refusal.

Recorded so it is not re-litigated: `www.law.go.th/robots.txt` is `User-agent: *` with **no
`Disallow` line at all**. We read public statutes, at a polite rate, with exactly the access an
ordinary visitor has, and we cite each provision to its source URL. This is the same test the
project already applied to `peraturan.bpk.go.id` (permitted to us, forbidden to a named AI
crawler) and to `flk.npc.gov.cn` (the operator's `"download": 0` is a refusal, and we honour
it). Nothing here is routed around.

### 2.2 Corrections this probing forces on `data/sources.yaml`

- **LA "host does not resolve" is false.** `laoofficialgazette.gov.la` answers HTTP 200,
  110 KB, 12,477 Lao characters, and is fully paginated. Laos was recorded as the weakest
  economy of the nine; it is in fact one of the most tractable.
- **TH "TLS self-signed, document path unknown" is stale, and so is the whole entry.**
  `krisdika.go.th` now returns **404 on every path** — the site was restructured, and it is no
  longer a TLS problem. More consequentially, the entry says *"Thai statutes are published as
  PDF, frequently scanned… this is the OCR-heavy lane."* **False.** `law.go.th` serves clean
  full text as JSON. Thailand is one of the two cleanest sources of the eleven, alongside
  India — no PDF, no OCR, no scan, and no article-splitting heuristic if `content_all` carries
  มาตรา markers (`ARTICLE_PATTERNS` already has the Thai one).
- **`tools/probe_portals.py` crashes on Windows cp1252** while printing a portal name — it died
  on RU and ID, the two economies most in need of probing.

---

## 3. Architecture

Hybrid (option C). One shared interface, reusable strategies, bespoke modules only where a
portal genuinely does not fit a strategy.

```
backend/pipeline/
  portal.py             PortalEnumerator protocol + the adapter registry
  portal_strategies.py  reusable: json_catalogue · paginated_index · sitemap ·
                        rest_api · frameset_crawl · browser_first
  adapter_common.py     robots-aware fetch · pagination · browser escalation ·
                        DiscoveredDoc construction · budget accounting
  adapter_singapore.py  NEW  sort-window union
  adapter_china.py      NEW  paginated_index over cac.gov.cn + gov.cn
  adapter_laos.py       NEW  Yii routes
  adapter_timor.py      NEW  static frameset tree
  adapter_indonesia.py  NEW  browser_first
  adapter_thailand.py   NEW  rest_api over apig.law.go.th
  adapter_russia.py     NEW  after the research task lands
  adapter_india.py      EXISTING — one record per section; stays bespoke
  adapter_mongolia.py   EXISTING — POST export, fleeting-vowel matching; stays bespoke
```

`discovery.py` keeps its single dispatch line. Every adapter — strategy-driven or bespoke —
satisfies the same `PortalEnumerator` protocol, so the caller cannot tell them apart.

**Why hybrid rather than one-file-per-economy or all-YAML.** The Mongolia defects of
2026-08-27 (fleeting vowel, ranking by title length, clause split needing a space) are
*per-economy* faults that no YAML schema could express. The Malaysia robots defect
(`robots.txt` HTTP 500 read as "disallowed") is a *shared* fault that one-file-per-economy
would force us to fix eleven times. Each kind of fault gets the structure that fits it.

### The `backend/corpus` boundary — a correction, not a relaxation

`tests/test_pipeline_isolation.py` forbids the live pipeline from importing `backend.corpus`.
That rule is right and stays. But it is currently stranding `enumerate_sg()`,
`enumerate_au()` and `enumerate_my()` in `backend/corpus/catalogue.py`, and those are
**live HTTP enumerators, not stored corpora**. Enumerating a portal live is precisely what the
panel scores.

**Resolution: reverse the dependency.** Move the enumerators into `backend/pipeline/`, and let
`backend/corpus` import *from* the pipeline. The test then still passes unchanged, because the
pipeline still imports nothing from corpus, and the distinction the test exists to protect —
*never serve stored document bytes as though they were discovered live* — is untouched.

---

## 4. Phase 1 — make the silent failures loud (before any adapter)

Ordered first because until it lands, no measurement of a new adapter can be trusted: a green
result may only mean the cache was warm.

| # | Defect | Fix |
|---|---|---|
| 1.1 | `_serper()` swallows HTTP 400 | Log status and body; distinguish **engine failed** from **engine returned zero**; expose the last error to the caller |
| 1.2 | `_search.json` has no TTL and no provenance | Store `{results, fetched_at, engine}` per entry; entries older than `search_cache_max_age_days` are a miss; the run log reports **how many queries came from cache vs. the network** |
| 1.3 | Zero discovered documents is treated as success | Emit `[error]` with the cause chain: which lanes ran, what each returned, which engine failed. Wire `[error]` into `frontend/runview.py`, which today has no branch for it |
| 1.4 | A run cannot prove it was live | JSON trace records per-lane, per-query provenance: engine used, cache hit/miss, result count |
| 1.5 | `tools/probe_portals.py` dies on Windows | Wrap stdout as UTF-8 with replacement |
| 1.6 | Caches have no lifecycle | `tools/cache_gc.py`: age and size caps; drop superseded engine outputs (`_rapidocr_v4` alongside `_v5`); drop `lightrag/` when `RETRIEVER != lightrag` |

### On the accumulated downloads

`data/cache` is 1.3 GB (843 PDFs, 2,155 HTML, 2,854 extraction results, 210 MB of embedding
caches, 53 MB of unused LightRAG) and `outputs/` another 1.3 GB. **None of it is in git** —
`.gitignore` excludes `data/cache/` and `outputs/*`, and only 22 small files under `data/` are
tracked. The public-repo deliverable is unaffected.

The live pipeline is also already correctly scoped: `discovery_max_docs = 22` per run, and
`test_pipeline_isolation.py` prevents it reading the precomputed store. The bulk downloads came
from `backend/corpus/cli build`, a hand-run evaluation fixture, never from a live run.

So the defect is **an absent cache lifecycle**, not a wrong fetching policy — hence 1.6 rather
than a redesign. Two constraints govern any change here:

- The panel requires a document cache: *"the tool must re-process already-downloaded documents
  without re-fetching — the live test may require it."* `_extracted/` is that mechanism.
- Fetching stays discovery-scoped. Only documents discovery selected for this
  (economy, pillar) are fetched. No bulk sweep on any live path.

---

## 5. Phase 2 — portal-native lanes where the route is known

Eight adapters. Each is done when a live run produces ≥1 provision from that economy's own
portal with **zero seed URLs and zero search-engine results**.

| Order | Economy | Strategy | Notes that must survive into the code |
|---|---|---|---|
| 1 | **TL** | `frameset_crawl` | Easiest and carries the panel's difficulty bonus. Honour `Crawl-delay: 10`. Language detection **per document** — the same instrument ships as `…_Portugues.pdf` and `…_tetum.pdf`. Record honestly that `home-e.htm` advertises an index "as of 31 August 2011"; check the newer `/jornal/files/` tree before trusting coverage |
| 2 | **LA** | `paginated_index` | Walk `Document_page`; ids come from the list page (a guessed `id=1` 404s). Prefer `lc=en` where a document has an English twin. Scanned PDFs → OCR; legacy Lao fonts can map into upper-ASCII, so `script_validity()` must gate the text layer |
| 3 | **TH** | `rest_api` | Route in §2.1. `content_all` is full text, so this lane skips fetch *and* OCR entirely. Two things to settle in code: the `searchResult` payload shape (400 today — read `SearchResult` from the sourcemap), and whether `content_all` carries มาตรา markers so `ARTICLE_PATTERNS`' Thai splitter applies, or whether `law/detail/{id}` must be called per row. Pin the `x-api-key` in `sources.yaml`, not in code, and record that it is a public bundle constant |
| 4 | **SG** | `sort_window_union` | Port `enumerate_sg()` per §3. Removes SG's total dependence on web search — the single largest live-test risk in the project |
| 5 | **CN** | `paginated_index` | Two real lanes (`cac.gov.cn`, `gov.cn/zhengce`) rather than one lane plus search fallback. Closes the standing item "CN principal statutes must survive `cac.gov.cn` being unreachable". Do **not** engineer around `flk.npc.gov.cn`: its API returns `"download": 0`, which is the operator refusing, and that decision stands |
| 6 | **ID** | `browser_first` | httpx 403s everywhere; go to the browser lane first rather than escalating after a refusal. `robots.txt` names nine AI crawlers as disallowed and grants the wildcard group — we fetch as `VeriTrade-Research/0.2` and must **never** send a named-crawler UA to this host, and never train on its text |
| 7 | **MY** | verify only | The `lom.agc.gov.my` HTTP-500 carve-out is already present in `robots.UNREACHABLE_OVERRIDE`. `PROJECT_STATE.md` §3 still lists it as open — a stale checklist entry to delete, not work to redo |
| 8 | **AU / IN / MN** | verify only | Lanes live. Confirm each still enumerates after Phase 1 lands, since Phase 1 changes what a zero result means |

---

## 6. Phase 3 — Russia, the one economy still unresolved

A **research task whose deliverable is a probe report naming the document route**, and only
then an adapter. Writing an adapter before the route is known is how `sources.yaml` acquired
its three stale entries.

**RU.** Fetch is solved and its two traps are documented: the encoding is cp1251 *including the
query string*, and `?docbody=&nd=<id>` is a 586-byte frameset whose body lives in an inner
frame — so the obvious URL returns a page that looks fine and contains no law. Discovery is the
open half: the IPS list frame reports a result count but injects its rows client-side, and
neither plain HTTP nor a default browser render surfaces a single `nd=` id. Next things to try,
in order: the list frame's own XHR, then the rubricator/classifier browse. Do **not** target
the answer key's URLs — 24 of the panel's 28 Russian references are commercial mirrors
(`garant.ru`, `consultant.ru`), only one is the official portal, and `garant.ru` already
refuses the browser lane with 403.

Thailand was in this section until 2026-09-07 and was resolved during the design (§2.1). Its
route came from the app's own published sourcemap, not from defeating a protection — worth
noting because it is the cheapest technique in this file and none of the other SPA portals
(`law.go.th` aside) has been checked for one yet. `flk.npc.gov.cn` is the exception that must
not be checked: its API states `"download": 0`.

If the RU research finds no polite route, that is a finding to record in `readiness.py`, not a
reason to route around an operator's refusal.

---

## 7. Acceptance

`tools/readiness.py` is the acceptance test, because it derives its table from the registries
the pipeline actually reads and so cannot claim a capability the code lacks.

- **Every economy with a resolved route reaches `extracted`**: a live run yields ≥1 provision
  from its own portal, zero seed URLs, zero search-engine results.
- **A run with a dead search key and a cold cache fails loudly**, naming the cause on the Run
  screen — verified by a test that simulates both.
- **`data/cache/_search.json` is not consulted for entries past its TTL** — tested.
- **Per-adapter regression tests**, in the style of `tests/test_mn_discovery_and_translation.py`:
  each pins the portal behaviour that was hard to discover, so a portal change fails a test
  rather than silently emptying an economy.
- `tests/test_pipeline_isolation.py` still passes unchanged.

---

## 8. Out of scope

Retrieval parameters (measured, see `docs/retrieval-redesign.md`), grading, scoring, the
translation layer, the review UI, and the submission workbook. This design stops where a
provision enters retrieval.
