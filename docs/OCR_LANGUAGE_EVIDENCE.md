# OCR engine and language evidence

Research date **14 Aug 2026**. This records *why* each default was chosen, and — more
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
| RapidOCR / PaddleOCR v5 | ✅ `th` | ❌ | ✅ `ch` | ✅ `eslav` | 🟡 latin | 🟡 cyrillic | ❌ | ✅ |
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

### Why no VLM OCR as default

Every strong 2026 document VLM needs a GPU (measured CPU figures where they exist: olmOCR-2
~37 s/page, PaddleOCR-VL ~53 s/page), which alone breaks the CPU-only judging constraint. The
second reason is worse: they are generative. Documented failure modes include repetition
loops, dropped paragraphs, and silent corruption (olmOCR-2 turning the range "84-89" into
"84.89" while producing cleaner-looking output than the model that got it right). GlotOCR
found that across scripts only 12.5% of predictions land in the correct script while 68.4%
are cross-script hallucination. A detect-then-recognise engine cannot invent a clause that
is not in the image; a VLM can, and a fluent invented clause survives review where garbled
characters do not.

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
