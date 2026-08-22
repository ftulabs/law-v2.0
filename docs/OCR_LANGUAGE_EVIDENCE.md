# OCR engine and language evidence

Research date **14 Aug 2026**, with measurements added **21 Aug 2026** (marked inline). This records *why* each default was chosen, and — more
importantly — where no evidence exists. Every claim below is either a citable measurement or
is explicitly marked unproven. The point of the file is that a judge (or a future maintainer)
can tell the two apart.

Three cautions apply to almost every published number in this area:

1. **PaddleOCR "accuracy" is line-level exact match, not CER.** The `th_PP-OCRv5_mobile_rec`
   model card states the rule: *"If any character (including punctuation) in a line was
   incorrect, the entire line was marked as wrong."* Its Thai figure of 82.68% therefore does
   **not** mean ~17% character error. Never compare it to a CER gate.
2. **Synthetic benchmarks flatter low-resource scripts.** `dots.ocr` scores 79.0 on rendered
   Lao (GlotOCR, Apr 2026) and 0.89 on real Lao documents (MORE, Jul 2026). Only
   real-document evidence is used below.
3. **No benchmark anywhere evaluates OCR on legal gazette scans** in these languages. All
   figures are transferred from adjacent domains.

## Language coverage

✅ dedicated model · 🟡 generic script-group model · ❌ none

| | Thai | Lao | Chinese | Russian | Vietnamese | Mongolian (Cyr) | Mongolian (vert.) | Latin |
|---|---|---|---|---|---|---|---|---|
| RapidOCR / PaddleOCR v5 | ✅ `th` | ❌ | ✅ `ch` | ✅ `ru` | ❌ *(was 🟡)* | ❌ *(was 🟡)* | ❌ | ✅ |
| Tesseract 5 | ✅ `tha` | ✅ `lao` | ✅ `chi_sim` | ✅ `rus` | ✅ `vie` | ✅ `mon` | ❌ | ✅ |
| EasyOCR | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| docTR | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Azure Document Intelligence | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Google Cloud Vision | ✅ | ✅ `lo` | ✅ | ✅ | ✅ | 🟡 experimental | ❌ | ✅ |

Two traps worth naming:

* **docTR looks multilingual and is not.** Its `vocabs.py` defines `thai`, `lao`, `mongolian`,
  `simplified_chinese` — but every shipped recognition checkpoint declares
  `vocab=VOCABS["french"]`. Those vocabs are training scaffolding, not capability. A loaded
  docTR model physically cannot emit a Thai codepoint.
* **PP-OCRv6 (Jun 2026) does not help the hard scripts.** Its "50 languages in one model" is
  Chinese, Traditional Chinese, English, Japanese plus 46 *Latin-script* languages. No Thai,
  no Cyrillic, no Lao. It supplements PP-OCRv5's per-script models rather than replacing them.

### Measured 21 Aug 2026 — against the models' own character dictionaries

The two 🟡 cells above were downgraded to ❌ by reading the shipped recognition dictionaries
rather than the vendor's language list. This is the cheapest possible measurement — the
dictionary is a plain list inside `inference.yml` — and it is decisive, because **an engine can
only emit characters that exist in its output dictionary.** A missing letter is not a low
score, it is an impossibility, and it arrives as fluent text with no error anywhere.

| Model | Dictionary size | Finding |
| :--- | ---: | :--- |
| `eslav_PP-OCRv5_mobile_rec` | 517 | **No Ө Ү ө ү.** Mongolian Cyrillic loses four letters |
| `eslav_PP-OCRv5_mobile_rec` | 517 | **No Ә Ғ Қ Ң Ө Ұ Ү Һ** or their lower case — **sixteen of Kazakh's 42 letters are absent** (only І/і are present) |
| `latin_PP-OCRv5_mobile_rec` | 836 | Carries đ ă ơ ư but **none of the 45 precomposed Vietnamese tone forms** (ế ộ ữ ạ ằ …) |

Two consequences are now pinned by tests (`tests/test_final_round.py`):

* `PROFILES["MN"].paddle` and `PROFILES["KZ"].paddle` are `None`. The disqualification is
  measured, not inherited caution.
* `PROFILES["VN"].paddle` is `None`, and this one is a trap rather than a gap: PaddleOCR
  **accepts `lang="vi"` without raising** and quietly loads that same `latin` model. A
  configuration that looks like it works, and does not.

### The language keys changed under us

The registry recorded `paddle="cyrillic"` and `paddle="eslav"`. PaddleOCR 3.x raises
`ValueError: No models are available for the language 'eslav'` on both — those keys no longer
exist. The factory caught the exception and reported *"no engine can read Cyrillic"*, while the
engine sat installed the whole time under the key `ru`.

**Russia was recoverable by fixing a string.** The lesson generalises: a registry that names
another project's identifiers is a copy of that project's API at a moment in time, and it needs
a test that actually constructs the engine. `test_paddle_language_keys_match_the_installed_paddleocr`
is that test.

Verified installed and working on this machine: `ru`, `vi`, `th`, `ka`, `en`, `ch`.
Verified rejected: `cyrillic`, `eslav`, `east_slavic`, `latin`.

### Cross-encoder, measured on the same day

Not OCR, but the same class of question — does the model actually handle the script? Asked to
rank five PIPL/CSL articles against the 6.2 legal test:

| Model | Params | Throughput | Rank order | Correct article |
| :--- | ---: | ---: | :--- | :--- |
| `ms-marco-MiniLM-L-6-v2` | 23M | 72.7 pairs/s | `[2,3,1,4,0]` | **last of five** |
| `BAAI/bge-reranker-v2-m3` | 568M | 4.2 pairs/s | `[0,3,1,4,2]` | first |

So an English cross-encoder on Chinese is not merely uninformative, it is **inverted** — which
is why a non-Latin economy never falls back to it. Two lighter multilingual alternatives were
tried and neither runs here: `Alibaba-NLP/gte-multilingual-reranker-base` (306M) raises an
IndexError inside its custom modelling code, and `jinaai/jina-reranker-v2-base-multilingual`
(278M) needs a `transformers` API the pinned version no longer exports. bge-m3 is therefore not
the best multilingual reranker available — it is the only one that runs.

## Accuracy on real documents

From **MORE** (arXiv 2607.02956, Jul 2026, 149 languages, real documents). Metric is NED,
higher is better; `100 − score` approximates character error.

| Language | Best score | ≈ error | Verdict against a <5% CER bar |
|---|---|---|---|
| Thai | 99.19 | ~0.8% | Comfortable |
| Russian | 99.02 | ~1.0% | Comfortable |
| Vietnamese | 98.12 | ~1.9% | Comfortable |
| Mongolian (Cyrillic) | ~97 | ~3% | Probably fine, unmeasured for our engines |
| **Lao** | **64.50** | **~35%** | **Fails by roughly 7×** |
| Mongolian (traditional) | no data | — | No engine support at all |

Those scores are VLM results and are **not** achievable on our CPU-only path — every strong
2026 VLM is GPU-class (9–53 s/page on CPU where a CPU path exists at all). They establish the
*ceiling* per language, not what our engines will deliver.

Our own measured figure remains **CER 1.11%** (RapidOCR, bundled scanned SG notice, English
print). That is the only measurement we have made, and it does not transfer to other scripts.

## Decisions

| Economy | Engine | Code | Why |
|---|---|---|---|
| SG · AU · MY · ID | RapidOCR | `latin` | Round-1 scope, measured at 1.11% CER |
| Thailand | RapidOCR | `th` | Only dedicated Thai model; Apache-2.0 weights |
| China | RapidOCR | `ch` | Flagship path for the script |
| Russia | RapidOCR | `eslav` | East-Slavic model beats the 34-language `cyrillic` bucket |
| Mongolia | RapidOCR | `cyrillic` | Cyrillic Khalkha only. **Pin ≥ PP-OCRv5** — the v3/v4 dictionary omits Ө/Ү entirely |
| Vietnam | Azure DI, else Tesseract | `vi` / `vie` | **Paddle-family disqualified**, see below |
| Laos | Tesseract | `lao` | Only offline option in existence. **Unvalidated** |

### Why Vietnamese is excluded from the Paddle family

A charset audit of `ppocrv5_latin_dict.txt` (836 entries — the output dictionary of the model
PaddleOCR assigns to Vietnamese) found the base letters `ă â đ ê ô ơ ư` present but **all 45
precomposed tone-marked forms absent** (`ế ộ ữ ấ ầ ằ …`), with zero combining-mark entries.
The loss is therefore deterministic, not probabilistic: the model has no route to emit them.
For a pipeline whose deliverable is a verbatim legal quotation that is disqualifying, and no
benchmark is needed to establish it. Measured alternatives on VieBookRead: Azure 0.04 CER,
Tesseract `vie` 0.12, EasyOCR 0.25.

### Why Lao is declared a gap rather than covered

No Lao model exists in PaddleOCR, RapidOCR, EasyOCR, docTR or Azure Document Intelligence.
Tesseract `lao` is the only offline option; its weights date from the 2016–17 training round
and **no measured accuracy of any kind has ever been published** for it.

On the cloud side the position is sharper than "Azure lacks it, Google has it":

* **Azure Document Intelligence lists Lao only under language *detection*, not under
  printed-text extraction** for either the Read or Layout model. It can tell you a document
  is Lao; it is not documented to transcribe it.
* **Google Cloud Vision lists Lao `lo` in its first-tier *Supported* table**, which Google
  defines as prioritised and regularly evaluated — as opposed to the *Experimental* tier
  (under development, not regularly evaluated) where Mongolian sits. That tiering is a
  support commitment, not an accuracy measurement, and no CER for Lao is published by
  anyone.

So Lao is currently a **cloud-API problem rather than an open-weights problem**: the best
open real-document result is ~64.5/100 (≈35% error) under a non-permissive licence, while two
widely-cited open models collapse to 0.89 and 0.00 on the same test. If Lao enters scope,
Google Cloud Vision is the primary candidate, Tesseract `lao` the offline fallback, and human
review is mandatory on every Lao provision either way.

Two further hazards specific to Lao:

* Lao never adopted an 8-bit encoding standard (unlike Thai's TIS-620). Legacy fonts such as
  Saysettha Lao map Lao characters into the upper-ASCII range with no agreed convention, so a
  Lao PDF **with a perfectly good text layer** can extract as mojibake with no OCR involved —
  and a CER-on-OCR metric will never see it. Lao needs a Unicode-range validity check, not
  just an OCR fallback.
* The Lao Official Gazette publishes legislation in Lao only, so the script cannot be avoided
  by preferring an English edition the way Malaysia's bilingual catalogue allows.

Position taken: attempt Lao with Tesseract, mark every Lao mapping unvalidated, route it to
human review, and state the limitation in the honesty section rather than claiming coverage.

### Why no VLM OCR as default — and why it is now the last-resort fallback

Every strong 2026 document VLM needs a GPU (measured CPU figures where they exist: olmOCR-2
~37 s/page, PaddleOCR-VL ~53 s/page), which alone breaks the CPU-only judging constraint. The
second reason is worse: they are generative. Documented failure modes include repetition
loops, dropped paragraphs, and silent corruption (olmOCR-2 turning the range "84-89" into
"84.89" while producing cleaner-looking output than the model that got it right). GlotOCR
found that across scripts only 12.5% of predictions land in the correct script while 68.4%
are cross-script hallucination. A detect-then-recognise engine cannot invent a clause that
is not in the image; a VLM can, and a fluent invented clause survives review where garbled
characters do not.

**Updated 21 Aug 2026.** All of the above still holds, and none of it was the whole picture. It
argues against a VLM as the *default*; it does not answer what to do when no detect-then-recognise
engine can read the script at all. Measured, that is four of the nine live-test economies:
Mongolian and Kazakh Cyrillic (letters missing from the dictionary), Vietnamese (tone forms
missing), and Lao (no maintained model anywhere).

"No installed OCR engine can read this script" is an honest answer and a useless one for a
sealed live test that names one economy of nine and gives an hour. So `providers/ocr_vlm.py`
exists as the **last** engine tried — never a default, never preferred, reached only when the
registry and the factory agree that nothing else can spell the script. The cautions above are
translated into the code rather than left in this file:

* temperature 0, and an instruction to transcribe rather than answer;
* an explicit instruction to write `[illegible]` rather than guess, because an invented sentence
  is far worse than an acknowledged gap when the text is quoted as a legal citation;
* `confidence=None` per page — a VLM emits no per-character probability, and a fabricated 0.9
  would flow into `ocr_quality.cer` and be read as measured;
* a `max_pages` ceiling, because a 600-page compilation silently costing 600 model calls is the
  kind of bill nobody notices until it has been paid;
* OpenAI chat-completions shape, so pointing `VLM_OCR_BASE_URL` at a local Ollama serving
  Qwen2.5-VL keeps the Section 3 "no proprietary API" declaration true.

The GPU objection is unchanged and is why it stays off the default path. The hallucination
objection is unchanged and is why every page it produces is marked.

## Known defects still open

* `ocr_azure.py` calls **Azure AI Vision Read**, whose printed-text list has no Thai, no
  Vietnamese and no Lao. It should call **Document Intelligence `prebuilt-read`**, which
  supports Thai (print and handwriting), Vietnamese, Mongolian Cyrillic and Indonesian. Until
  that is changed the Azure fallback cannot read the languages the table above assigns to it.
* `_measure_cer` only fires when a `*.ocr.txt` ground-truth sidecar sits next to the sample,
  and only one English sample ships one. Every per-language claim stays unmeasured until a
  sidecar exists per language. That is the cheapest way to convert any row above from
  inherited to measured.
* Traditional vertical Mongolian has no engine support anywhere, and Mongolia has mandated it
  alongside Cyrillic in official documents since Jan 2025. Such content must be detected and
  declared unextractable, never guessed at with a Cyrillic model.

## Sources

MORE (arXiv 2607.02956) · GlotOCR Bench (arXiv 2604.12978) · MDPBench (arXiv 2603.28130) ·
ThaiOCRBench (arXiv 2511.04479) · PP-OCRv5 multilingual docs and `th_PP-OCRv5_mobile_rec`
model card · PP-OCRv6 (arXiv 2606.13108) · VieBookRead results (arXiv 2410.13305) ·
docTR `vocabs.py` and recognition `default_cfgs` · Azure Document Intelligence and Azure AI
Vision language tables · Google Cloud Vision language support · tessdata / tessdata_best ·
EasyOCR `config.py` · Surya `MODEL_LICENSE` · laoscript.net font-encoding guides.
