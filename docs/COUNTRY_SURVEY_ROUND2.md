# Country Survey — Round 2 / Finals Economies

**Purpose:** decide which 3 (+1 optional) of the 8 finals economies VeriTrade adds.
**Fieldwork:** 13–14 Aug 2026, from a US egress IP, using plain HTTP clients (`curl`, `urllib`, `httpx`) and PyMuPDF for PDF inspection.
**Supersedes / verifies:** `Khảo sát các quốc gia cho vòng 2.xlsx` (the .xlsx itself was **not modified**).

## How to read the tags

| Tag | Meaning |
|---|---|
| **VERIFIED** | We fetched the source ourselves and observed the stated fact. Reproducible. |
| **REPORTED** | From the original sheet or a secondary source. Plausible, not independently confirmed. |
| **CORRECTED** | The original sheet was wrong. Both the old and the right value are stated. |
| **NOT VERIFIED** | We tried and could not establish it, or did not test it. Never a guess. |

Anything not tagged VERIFIED must not be presented to judges as fact.

---

## 0. What the judges actually require (context for the ranking)

**VERIFIED** — from `docs/reference/hackathon-overview.pdf` (ESCAP Orientation Workshop, 1 Jun 2026), pp. 3, 5, 9:

- Finals: **3 of these 8 additional economies are mandatory**, on top of the Round-1 three.
- Point weights: Thailand, China, India, Indonesia, Russian Federation, Lao PDR, Mongolia = **10 each**. **Timor-Leste = 20** ("BONUS for a hard challenge").
- The finals set is characterised by the organisers as *"NOT in English, Unorganized websites, Complex legal architecture, No single repository."*
- Scoring: 40% substantive accuracy (framework alignment, **discovery of new evidence beyond the sample kit**, citation fidelity), 30% technical resilience (live crawl 10 pts, OCR on scanned PDFs 10 pts, end-to-end 10 pts), 30% architecture (modular backend 15, audit trail 15, cost).
- **"Wrong or unclear citation = point deduction. Paraphrased snippets cannot be audited and your points will be deducted."** This is why the script/encoding findings below are weighted so heavily: a verbatim snippet that is *visually* right but not *byte*-right is a scored defect.
- The organisers' own worked example uses a **Thailand PDPA sample kit** and names **`laws.go.th`** as the crawl target.

### Judges' database coverage — sheet row 9 is correct, and now citable

**VERIFIED.** The in-repo `ESCAP-RDTII-2.1_ Round 1 Database.xlsx` contains only Australia, Malaysia and Singapore — it is **not** a coverage list for the finals. The real coverage statement is in *Digital Trade Regulatory Review for Asia and the Pacific, 2025*, p. 2 ([dtri.uneca.org PDF](https://dtri.uneca.org/assets/data/publications/ESCAP-2025-RP-Digital-trade-regulatory-review-AP-en.pdf), fetched 14 Aug 2026), which lists the **48 economies** in RDTII 2.1:

> Armenia, Australia, Azerbaijan, Bangladesh, Bhutan, Brunei Darussalam, Cambodia, **China**, Cook Islands, Fiji, French Polynesia, Georgia, **India**, **Indonesia**, Japan, Kazakhstan, Kiribati, Kyrgyzstan, **Lao People's Democratic Republic**, Maldives, Malaysia, Marshall Islands, Micronesia (FS), **Mongolia**, Myanmar, Nauru, Nepal, New Caledonia, New Zealand, Niue, Palau, Pakistan, Papua New Guinea, Philippines, Republic of Korea, **Russian Federation**, Singapore, Solomon Islands, Sri Lanka, Tajikistan, **Thailand**, Türkiye, Turkmenistan, Tuvalu, Uzbekistan, Vanuatu, Viet Nam, Hong Kong China.

**Timor-Leste is absent.** The sheet's "Không" for Timor-Leste and "Có" for the other seven are both **VERIFIED**. The consequence is stated in §3: no RDTII answer key for Timor-Leste can exist, so its 20 points cannot be earned on substantive-accuracy comparison the way the other seven can.

---

## 1. Verification of the existing sheet

### Table 1 — Portal URLs

| Country | Sheet URL | Status | Correct official URL | Tag |
|---|---|---|---|---|
| China | `flk.npc.gov.cn/search` | Live, HTTP 200 | same — 国家法律法规数据库 (NPC Standing Committee) | **VERIFIED** |
| India | `indiacode.nic.in` | Live, HTTP 200, DSpace 5.5 | same — Legislative Dept, Min. of Law & Justice | **VERIFIED** |
| Lao PDR | `laoofficialgazette.gov.la` | Live, HTTP 200, LiteSpeed/Yii; newest PDF 5 Aug 2026 | same | **VERIFIED** |
| Mongolia | `legalinfo.mn` | Live, 302 → `/mn`, HTTP 200, nginx | same — Unified Legal Information System | **VERIFIED** |
| Russia | `http://pravo.gov.ru/` | Live **on port 80 only** — :443 refuses connections | same, but **must stay plain HTTP**; add `publication.pravo.gov.ru` (API) + `pravo.gov.ru/proxy/ips/` (text) | **VERIFIED** |
| Thailand | `krisdika.go.th` | **DEAD.** Self-signed placeholder cert (`C=XX, O=Default Company Ltd`); every path returns HTTP 404 from a Huawei CloudWAF error page | **`https://www.ocs.go.th/`** — same body (Office of the Council of State), HTTP 200 | **CORRECTED** |
| Indonesia | `peraturan.go.id` | **UNREACHABLE.** DNS resolves to 103.145.96.87 but TCP 80/443/8080 all time out, sustained over ~45 min | **`https://peraturan.bpk.go.id/`** — official JDIH node, HTTP 200 | **CORRECTED** |
| Timor-Leste | `http://www.jornal.gov.tl/` | **DEAD.** SERVFAIL from 8.8.8.8, 1.1.1.1 and 9.9.9.9 — no A record at all (apex or `www`) | **`https://www.mj.gov.tl/jornal/`** — Jornal da República, Drupal 7, HTTP 200, HTTPS | **CORRECTED** |

**Three of eight portal URLs in the sheet would fail 100% of live runs.** That is the single most operationally important finding in this document.

Additional portal notes:
- **Indonesia — this is not our network. VERIFIED:** the entire `103.145.96.0/24` Kemenkum/BPHN block is unreachable (`peraturan.go.id`, `jdihn.go.id`, `jdih.kemenkum.go.id`), while `jdih.jakarta.go.id` and `jdih.setneg.go.id` return 200 from the same machine. Whether this is a sustained outage or a geo-fence is **NOT VERIFIED**.
- **Russia — `duma.gov.ru` and `sozd.duma.gov.ru` time out on both ports. VERIFIED** as unreachable; **NOT VERIFIED** whether the cause is geo-blocking or outage. Do not depend on Duma.
- **Blacklist `eastimorlawjournal.org`. VERIFIED:** the domain has been lost to squatters and now serves an Indonesian gambling site (`<title>SINDOPLAY: Link Slot777 …</title>`). If any seed list still references it, remove it.
- **Reject ConsultantPlus and Garant** (Russia) — commercial aggregators, not publication channels. Unnecessary: the official API is better than both.
- **`prsindia.org`** (India) is an NGO, not government. Useful for amendment history, never citable as authoritative text.

### Table 2 — Language of the authoritative text

| Country | Sheet | Authoritative text | Official English? | Tag |
|---|---|---|---|---|
| China | Chinese (simplified) | **Simplified Chinese only.** `flk.npc.gov.cn/en` returns the bare SPA shell; no app-level i18n | **No.** NPC English site titles its own page `Laws（Translation for Reference Only）`; **8 items total**, newest 2024 | **VERIFIED** |
| India | English, Hindi | **English is authoritative.** Const. Art. 348(1)(b); Authoritative Texts (Central Laws) Act 1973 s.2 expressly *excludes* Hindi; Official Languages Act 1963 s.5 makes Hindi a translation *from* English. India Code's own disclaimer: *"in case of any discrepancy, the English version of the Acts shall prevail"* | N/A — English **is** the original | **VERIFIED**; sheet's "English, Hindi" is right but hides the hierarchy |
| Lao PDR | Lao | **Lao only** | The gazette **does** publish English PDFs, first line `(Unofficial Translation)`. Also on `laotradeportal.gov.la`. **No official English exists** | **VERIFIED** — sheet incomplete |
| Mongolia | Mongolian | **Mongolian Cyrillic** | English section exists, homepage counter **324 translations** vs ~950 laws (~34%). Unofficial characterisation is **REPORTED** (no disclaimer text fetched); the 324 count is **VERIFIED** | **VERIFIED** |
| Russia | Russian | **Russian only.** `/en`, `/en/`, `/english` all 404; all API payloads and errors in Russian | **No** | **VERIFIED** |
| Thailand | Thai | **Thai only.** Disclaimer read verbatim off an OCS English PDF: *"THIS TEXT … CONTAINS NO LEGAL AUTHORITY … THE ORIGINAL THAI TEXT … SHALL IN ALL EVENTS REMAIN THE SOLE AUTHORITY HAVING LEGAL FORCE."* / *"Unofficial Translation"* | **No.** Coverage **27 of 1,885 laws (1.4%)** — and **neither the PDPA nor the Cybersecurity Act is among them** | **VERIFIED** |
| Indonesia | Bahasa Indonesia | **Bahasa Indonesia only.** Portal metadata field literally reads `Bahasa: Bahasa Indonesia`; no English toggle on any page | **No** (REPORTED for the legal characterisation) | **VERIFIED** |
| Timor-Leste | Portuguese, Tetum | **Portuguese in practice.** Counted language labels in the gazette tables: Leis **280 PT / 17 TET** (5.7%); Decretos-Leis **919 PT / 23 TET** (2.4%) | Tetum files are **translations, not co-originals** — `9_2002_tet.pdf` opens `DNAJL – Departamento de Tradução / TRADUÇÃO / Título Original "LEI DA NACIONALIDADE"`. **No English series** — English token count **0** in all 5 PDFs analysed; `public/docs/english/` → 404 | **CORRECTED** — sheet implies parity; Portuguese dominates ~19:1 |

**Operational rule:** for every one of the eight, verbatim snippets must come from the local-language text. English is admissible in Mapping Rationale only, with the "unofficial translation" caveat carried into Notes.

### Table 3 — Bot blocking

| Country | Sheet | Observed | Tag |
|---|---|---|---|
| China | *(blank)* | **WAF present but passive.** Header `WZWS-RAY: …waf05fst` (ChinaCache). **No robots.txt, no sitemap** (all unmatched paths return the same 455-byte SPA shell with HTTP 200). **Zero UA filtering** — `curl`, `python-requests` and an empty UA all got 200. Reachable from outside mainland CN. A `captchaImage` endpoint exists but **never gated** any search/detail/download call. **Real risk is flakiness: 2 of 20 rapid calls failed** (timeout / `schannel: server closed abruptly`) → budget ~10% transient failure + retries | **VERIFIED** (fills a blank) |
| India | Có (Captcha, WAF) | **WAF: real, and it is User-Agent matching.** Same URL, same second: `python-requests/2.31.0` → **404** (a *disguised* block), `Scrapy/2.11` → **403**, `curl/8.4.0` → 200, Chrome UA → 200, empty UA → 200. **Captcha: NOT FOUND** — zero `captcha\|recaptcha\|hcaptcha` matches on homepage, search results or Act page; search returned results unchallenged. `robots.txt` is a real file and **disallows `/discover` and `/simple-search`** — the discovery routes | **CORRECTED** — "Captcha" is unsubstantiated; the block is UA-based and is defeated by one config line. The fake-404 is a silent-failure trap (looks like "law not found") |
| Lao PDR | Không | **Confirmed none.** `/robots.txt` returns HTTP 200 but `text/html`, 135,818 bytes — i.e. the homepage; there is no robots file. No Cloudflare, no WAF, no captcha, no geo-block. ~80 requests incl. 20+ PDF downloads, zero 429/403 | **VERIFIED** |
| Mongolia | Có (Rate limit) | **Not observed.** `robots.txt` → genuine 404. No Cloudflare, no WAF, no captcha (an `api/captcha` endpoint exists but guards the feedback form only). ~40 requests incl. a 5.5 MB sitemap and multi-MB pages — no 429, no throttling | **CORRECTED** at survey volume. Sustained high-rate crawling **NOT VERIFIED** — a limit may exist above that |
| Russia | Có (WAF, chặn IP ngoại) | **False on both counts.** `pravo.gov.ru/robots.txt` → `User-Agent: *` / `Disallow:` — fully permissive. `publication.pravo.gov.ru/robots.txt` disallows only infrastructure paths **and advertises a sitemap** (`/sitemap.xml`, 116,072 B, HTTP 200). **No Cloudflare, no Qrator, no DDoS-Guard, no captcha.** Dozens of API calls and PDF downloads from a **US IP** over ~30 min: zero rate-limiting, zero challenges | **CORRECTED** — this is a project-*saver*. The real obstacle is the HTTP-only quirk (Table 6 / §2 note) |
| Thailand | Không | **False.** `ratchakitcha.soc.go.th` (Royal Gazette, the authoritative publication) → **HTTP 403, `Server: cloudflare`, `Cf-Mitigated: challenge`, `<title>Just a moment...</title>`** — full JS interstitial, including on its own `/robots.txt`. `law.go.th` → **403 CloudFront** "Request blocked". `data.go.th` → **403 Cloudflare**. `krisdika.go.th` → Huawei CloudWAF 404. **`www.ocs.go.th` passes cleanly with a plain UA, no challenge** | **CORRECTED** — Thailand is the most WAF-encumbered of the eight; only one door is open |
| Indonesia | Có (Cloudflare, Captcha) | **Cloudflare: confirmed** on `peraturan.bpk.go.id` (`Server: cloudflare`, `CF-RAY`, `__cf_bm`, `_cfuvid`), with an F5 BIG-IP ASM layer beneath (`TS…` cookies). **Captcha: NOT FOUND** — no interstitial, no challenge; plain `curl` succeeded every time. **The real blocker is policy, not technology:** `robots.txt` carries `Content-Signal: search=yes, ai-train=no, use=reference` and explicit `Disallow: /` for **ClaudeBot, GPTBot, CCBot, Google-Extended, Bytespider, Amazonbot, meta-externalagent, Applebot-Extended** | **CORRECTED** on captcha; **new finding** on AI-crawler denial — see Risk 3 in §3 |
| Timor-Leste | Không | **Confirmed none.** Plain Apache, `X-Generator: Drupal 7`. Stock Drupal robots.txt, **does not disallow AI crawlers**, sets `Crawl-delay: 10` (honour it). Every request succeeded first try | **VERIFIED** |

### Table 4 — Document structure markers (native script, regex-exact)

This is where the sheet had its worst error and where most of the engineering risk sits.

| Country | Sheet | Verified markers | Tag |
|---|---|---|---|
| **Lao PDR** | `ภาค (Chương) -> มาตรา (Điều)` | **These are THAI (U+0E00–0E7F), not Lao (U+0E80–0EFF).** Real tokens, observed in live statute text: Part **`ພາກທີ`** (`0E9E 0EB2 0E81 0E97 0EB5`) + **Roman numerals**; Chapter **`ໝວດທີ`** (`0EDD 0EA7 0E94 …`) *or* **`ຫມວດທີ`** (`0EAB 0EA1 0EA7 0E94 …`); Article **`ມາດຕາ`** (`0EA1 0EB2 0E94 0E95 0EB2`); Item **`ຂໍ້`** (`0E82 0ECD 0EC9`). **Number always FOLLOWS the token.** Lao digits U+0ED0–0ED9: **zero occurrences anywhere** | **CORRECTED** — the flagged error is confirmed |
| China | 第xx条, chapters, `( )` sub-items | Article **`第[一二三四五六七八九十百千零〇]+条`** — **1,314 hits; `第\d+条` and full-width `第［０-９］+条` both ZERO.** CJK numerals only, up to **第一千二百六十条**. Chapter `第…章` (174), Section `第…节` (79), Book `第…编` (24), item `（一）` (374) | **VERIFIED**, sheet correct but under-specified |
| India | Act → Part/Chapter → Section → sub-section → clause | `CHAPTER I`…`CHAPTER XIII` (Roman) incl. **`CHAPTER XIIA`** (letter-suffixed inserts); `Section 1.` with trailing period, incl. **`Section 3A.`, `6A.`, `7A.`, `10A.`**; `(1)`/`(2)`; `(a)`/`(w)`. ToC header `ARRANGEMENT OF SECTIONS` | **VERIFIED** |
| Mongolia | `Бүлэг` → `Зүйл` → `Хэсэг` → `Заалт` | Marker *names* right, **forms wrong.** Real: chapter = **spelled-out ordinal + `БҮЛЭГ`, no digits** (`НЭГДҮГЭЭР БҮЛЭГ`, `ХОЁРДУГААР`…). Article = **`N дугаар зүйл.`** — digit, *then* ordinal suffix, *then* зүйл — **not** "Зүйл 5". **Vowel harmony is mandatory**: last digit ∈ {1,4,9} → `дүгээр`, else `дугаар`. Regex `\d+\s+д[үу]г[эа]{2}р\s+зүйл`. **No space after the period** (`1 дүгээр зүйл.Хуулийн зорилт`). Sub-provisions are hierarchical decimals `1.1.`, `10.1.1.` | **CORRECTED** on form |
| Russia | `Раздел → Глава → Статья → Часть → Пункт` | Verified against 152-FZ *О персональных данных*: **`^Статья\s+\d+(\.\d+)?\.`** (42 hits) and **`^Глава\s+\d+\.`** (6) — **heading text is on the SAME line as the marker**. **`Раздел`: 0 hits** (used in Codes, not ordinary federal laws). **`Часть`/`Пункт` are NOT heading tokens** — they appear only as lowercase cross-references (`часть` 66×, as "часть 1 статьи 5"). Actual sub-hierarchy is bare `N.` then `N)` | **CORRECTED** — a regex looking for literal `Часть` at line start matches nothing |
| Thailand | `หมวด → มาตรา → khoản` | Verified against the real PDPA (44 pp, 86,476 chars): `มาตรา` **279**, `หมวด` **15**, `ส่วนที่` **7**. **`หมวด`/`ส่วนที่` sit ALONE on their line, heading on the NEXT line; `มาตรา` has text on the SAME line.** Note the **double space** after markers (`มาตรา  ๒๖`) → use `\s+`. **`ลักษณะ` (14 hits) are all false positives** (common noun); **bare `ส่วน` (633) unusable** (mostly `ส่วนบุคคล`); `วรรค` (128) is cross-reference only | **VERIFIED** + refined |
| Indonesia | `BAB → Pasal → ayat → huruf` | Verified against UU 27/2022 (PDP Law): `BAB I`…(Roman, all-caps) **14**; **`Pasal 1`** (capital P, space, Arabic) **213**; `(1)` **125**; `a.` **143**; `Bagian Kesatu` **6**. `BUKU`/`Paragraf` absent from ordinary UU — **NOT VERIFIED** | **VERIFIED** |
| Timor-Leste | `Capítulo → Artigo → n.º/alíneas` | Verified against `SERIE_I_NO_29.pdf` (2026): `Capítulo` + Roman **19**, `Secção` **3**, `Artigo N.º` **115**, `n.º` **42**, `alíneas a)` **121** | **VERIFIED** + a trap, below |

#### Two regex traps that will silently drop whole documents

**Lao — the precomposed/decomposed split (VERIFIED by byte-counting).** `U+0EDD` (ໝ) has a **`<compat>`** decomposition to `0EAB 0EA1` (ຫ+ມ). Because it is *compat* and not *canonical*, **NFC will not merge, and NFD will not split** — only NFKC/NFKD unifies, and it maps *downward*. Both forms are live, and **the two ingestion paths systematically disagree**:

| Source | `ໝ` U+0EDD | `ຫ`+`ມ` |
|---|---|---|
| Gazette HTML | 543 | 2 |
| Penal Law PDF (text layer) | 509 | 55 |
| FAOLEX OCR'd decree | **0** | **19** |
| lo.wikipedia Constitution | 40 | 26 |

Government HTML emits precomposed; OCR emits decomposed. **A single-form regex loses every chapter heading from one path.** Use `(?:ໝ|ຫມ)ວດ`, or NFKC everything. Two more `<compat>` pairs behave identically and also alternate in the wild: **`ຳ` U+0EB3 vs `ໍາ` (U+0ECD U+0EB2)** and **`ຫຼ` U+0EBC vs `ຫລ`**.
*Also:* bare `ພາກ` hits ພາກເໜືອ/ພາກກາງ/ພາກໃຕ້ (north/central/south) — 82 non-structural hits; bare `ຂໍ້` hits ຂໍ້ຕົກລົງ (agreement, 102×) and ຂໍ້ມູນ (data). **Never match either without a trailing numeral.**

**Timor-Leste — four different ordinal characters (VERIFIED).** `Artigo N.º` is written with **four distinct codepoints across official PDFs**:

| Rendering | Codepoint | Where | Count |
|---|---|---|---|
| `Artigo 1.º` | `U+00BA` MASCULINE ORDINAL INDICATOR | 2026 gazette, 2003 Lei, Constitution | 115 / 1 / 168 |
| `Artigo 1.°` | `U+00B0` **DEGREE SIGN** | Tetum translation PDF | 17 |
| `Artigo 1.˚` | `U+02DA` **RING ABOVE** | Constitution | 2 |
| `Artigo 1o` | `U+006F` plain ASCII **letter o** | Tetum translation | 33 |

Use `Artigo\s+\d+\s*[.]?\s*[º°˚o]`. Matching only `U+00BA` silently drops whole documents. Same for `n.º`/`n.°`/`no`.

### Table 5 — Amendment tracking and consolidated texts

| Country | Sheet: amendment method | Verified | Sheet: consolidated | Verified | Tag |
|---|---|---|---|---|---|
| China | 公布日期 / 施行日期 | **Confirmed.** API fields `gbrq` (promulgation) / `sxrq` (effective) on every record; UI labels 公布日期/施行日期/历史沿革 present in the JS bundle | Có | **Yes.** Consolidated text is a distinct record (《宪法（2018年修正文本）》) alongside separate amendment instruments. Status field `sxx`: 4=not yet in force, 3=in force, 2=amended/superseded, 1=repealed — **filterable** | **VERIFIED** |
| India | "Amended by" or footnotes | **Footnotes, not a table.** A dedicated machine-readable `footnote` field per section: *"Subs. by Act 10 of 2009, s. 3, for sub-section (4) (w.e.f. 27-10-2009)"*. There is **no "Amended by" block** — the 1973 Act's page contains zero occurrences of "amend" despite being amended in 1988 | Có | **Yes, genuinely as-amended.** IT Act s.66A shows `Omitted.` (struck down — not silently retained); ss.3A/6A/7A/10A/43A present; currency to 2025. **Caveat: `Last Updated` is inconsistent or absent**, so per-Act currency cannot be established programmatically | **VERIFIED** with caveat |
| Lao PDR | Date at end of gazette issue | **Partially.** Listing tables carry `sort=legal.effective_from` and `legal.issue_date`; per-issue dates are in filenames (`707-5-8-2026_0001.pdf`). **No per-article amendment history** | Không | **Confirmed no.** Separate listings for in-force vs superseded (`?r=site/list&old=1`, "ນິຕິກຳເກົ່າ") — point-in-time documents only | **VERIFIED** |
| Mongolia | Per-article history (Нэмэлт, өөрчлөлт) | **Confirmed and excellent.** A `Нэмэлт өөрчлөлт` tab (`Нийт (16)` for the PDP law) plus **inline provision-level annotations**: */Энэ хэсгийг 2023 оны 05 дугаар сарын 04-ний өдрийн хуулиар өөрчлөн найруулсан./* | Có | **Yes, decisively.** Counted inline consolidation annotations: Law on Legislation **239**, Constitution 24, Public Information Transparency 32 | **VERIFIED** — best in the survey |
| Russia | Редакция + effective date | **Confirmed.** IPS carries an explicit edition ledger — 152-FZ has **37 numbered editions**, each with date + amending-law number; `&rdk=N` selects the edition. **Caveat: two editions are flagged `(не готова)` ("not ready")** — check the flag before trusting a text | Có | **Yes, but not where the sheet implies.** `publication.pravo.gov.ru` serves **as-published acts only** (holdings start ~2011). Consolidation lives at `actual.pravo.gov.ru` → **`pravo.gov.ru/proxy/ips/`** | **VERIFIED** with an important split — see §2 |
| Thailand | `ฉบับแก้ไขเพิ่มเติม` table at end | **Wrong for base acts.** `ฉบับแก้ไขเพิ่มเติม` and `แก้ไขเพิ่มเติม` → **0 occurrences** in the PDPA. What exists is `หมายเหตุ :- เหตุผลในการประกาศใช้…` (reason for enactment). **Amendment lineage is in the JSON metadata `childrens` array**, not the PDF | Có | **Partial.** Only **1,088 of 1,891 records (58%) have a downloadable file**; the other 42% carry a stub deferring to the Cloudflare-challenged Gazette. An explicit "updated to [date]" stamp: **NOT VERIFIED** | **CORRECTED** |
| Indonesia | Status Peraturan (Mengubah/Diubah oleh/Dicabut) | **Confirmed on BPK.** A `STATUS PERATURAN` block with exactly those labels, plus a separate `UJI MATERI` block for Constitutional Court rulings. **Caveat: can be empty** (`Belum Tersedia` on UU 27/2022) | **Có** | **NO — the sheet is wrong.** UU 11/2008 (ITE) has been amended twice and partially repealed, yet `FILE-FILE PERATURAN` offers exactly one file: the **original 2008 text**. No as-amended view, no version selector, anywhere | **CORRECTED** — major finding, see §3 Risk 4 |
| Timor-Leste | Compare Série I / II dates | **Confirmed.** Série I (node/27), Série II (node/28), `Outros Actos` (node/29) all exist. **No amendment metadata whatsoever** — flat tables `NUMÉRO / DESCRIÇÃO / PUBLICADA EM / PDF`. Amendment relations exist **only as Portuguese prose inside the title**: *"Segunda alteração à Lei n.º 3/2004, de 14 de abril…"* → extracting the graph requires NLP over ordinals + `Lei n.º X/YYYY` | Không | **Confirmed no** | **VERIFIED** |

### Table 6 — Download formats and PDF nature

| Country | Sheet formats | Verified formats | PDF nature | OCR on critical path? | Tag |
|---|---|---|---|---|---|
| China | Word via 下载 → 点击下载 | **DOCX + PDF + OFD** via `GET /law-search/download/pc?bbbs=…&format=docx\|pdf\|ofd` → pre-signed OBS URL. Both downloaded OK (DOCX 197,879 B; PDF 1,205,952 B / 176 pp) | **Text-layer.** Civil Code: 176 pp, **0 pages with zero text, 0 embedded images**, 115,160 chars | **No** | **CORRECTED** (understated) |
| India | PDF | **PDF (EN + HI) + HTML + JSON.** English/Hindi bitstreams distinguished by an `A`/`H` filename prefix | **Text-layer even at the extremes.** IT Act 2000: 41 pp, 0 images. **Bengal Indigo Contracts Act 1836: 1 p, 0 images, 3,459 chars** — retyped, not photographed | **No** | **CORRECTED** ("PDF only" is wrong) |
| Lao PDR | PDF, HTML | PDF (`/kcfinder/upload/files/*.pdf`, no auth). **No DOCX.** HTML full text for a subset | **Worst in the survey — see below** | **Yes, and no engine can do it well** | **CORRECTED** |
| Mongolia | Word, PDF, HTML | **DOCX confirmed by direct fetch** — `/storage/uploads/process/202202/file_….docx` → 200, real `PK\x03\x04`, 39,724 B, unauthenticated, parses cleanly. PDF + HTML also | Moot — text served as HTML and DOCX | **No — zero OCR needed** | **VERIFIED** |
| Russia | PDF, RTF/Word, ZIP | **PDF only confirmed** (`/file/pdf/{eoNumber}` → 200, valid PDF 1.4). `/file/rtf/`, `/doc/`, `/zip/`, `/text/`, `/html/`, `/xml/` **all 404** | **100% SCANNED.** 4/4 documents from 4 different authority blocks: **0 text characters, exactly one image per page** — *including documents published this week (Aug 2026)*. Corroborated by `/api/DocumentText` returning literal `false` | **YES — on 100% of documents** | **CORRECTED** on both |
| Thailand | PDF, Word | **PDF confirmed.** Word/DOCX **NOT VERIFIED** — no endpoint observed | **Text-layer** (PDPA 44 pp / 86,476 chars, 1 crest image; Cybersecurity Act 32 pp / 61,750 chars). No mojibake, no TIS-620 corruption. **But a systematic extraction defect — see below** | **No raster OCR** — but a text-repair pass is mandatory | **CORRECTED** (Word unconfirmed) |
| Indonesia | PDF | **PDF only.** HTML carries metadata + `Abstrak`, never article text | **UU / PP / Perpres = SCANS with a dirty pre-existing OCR layer.** UU 27/2022: one 3392×5192 PNG per page, single non-embedded `Helvetica`. Permen = born-digital | **YES — and the shipped OCR layer must be discarded** | **CORRECTED** |
| Timor-Leste | PDF | **PDF only** — and note the PDF is **the whole gazette issue**, not a single law, so instruments must be segmented *within* the file after download | **Born-digital throughout**, ~4,000–5,200 chars/page, masthead logo only. Producers: doPDF 9.4 (2026), OpenOffice.org 2.0 (2003), MS Word 2007. **Even the earliest 2002–2003 issues are born-digital, not photographed** | **No** | **VERIFIED** — the "old scans" concern did not reproduce |

#### The three text-quality landmines

**1. Lao — both failure modes at once (VERIFIED).** We sampled **18 PDFs** from the in-force listing with PyMuPDF:

```
18 analysed | text-layer: 0 | image-only scans: 18
Producers: HP Scan Extended Application ×4, Mac OS X Quartz PDFContext ×4, PDF7 ×3, unknown ×7
```

Every one: **0 chars, 0 fonts, exactly 1 image per page** — literally flatbed-scanned. A *second* class of named documents does carry a text layer, and those are **legacy-font mojibake in two distinct encodings**:
- **Upper-ASCII (Saysettha-Lao / LSWin):** `Penal Law.pdf` — 81,763 clean Lao chars, but chapter headings extract as `Ï¸©-êó 1` = ໝວດທີ 1. Only **3 of ~11** chapter headings survive. **The mojibake is 0.1% of characters but sits exactly on the structural headings you chunk by — a CER gate scores this PDF "clean" and you still lose the hierarchy.**
- **Lower-ASCII (SengChanh/alice_0 style):** `Law on Science and Technology.pdf` extracts as `tr.lil.rauuy5o uvqrfiU"tm` — **~100% mojibake** (39,733 chars, 68 Lao). `Draft of Penal Code.pdf`: 108,515 Latin-1 chars vs 40,042 Lao, five Lao fonts across two encoding regimes in one file.

**The saving grace:** a subset of gazette detail pages serve the **full statute as clean Unicode HTML**. Sampling 20 random detail pages: **6/20 full HTML, 14/20 PDF-only** — and the six cluster in the **low-id band (~356–428), i.e. the curated core laws**, which is exactly where P6/P7 instruments live. High ids (1199+) are scan-only.

**2. Thailand — SARA AM (U+0E33) is destroyed on extraction (VERIFIED, 100% reproducible).**

| Correct | Extracted | Correct / broken |
|---|---|---|
| `สำนักงาน` (office) | `ส านักงาน` | 0 / **128** |
| `คำ` (word) | `ค า` | 0 / **61** |
| `กระทำ` (to do/act) | `กระท า` | 0 / **45** |
| `จำกัด` (limit) | `จ ากัด` | 0 / **5** |

**Not a single instance of U+0E33 survived** in either Act. Tone-mark reordering also observed (`หน้า ๙๔` → `หนา   ๙๔่`). Consequences: (a) **verbatim snippets are silently wrong** — a judge comparing against the Gazette sees corrupted text, which alone can fail the citation criterion; (b) keyword retrieval breaks on `จำกัด` (limit), `กำหนด` (prescribe), `ทำ`, `นำ`, `คำ` — **exactly the verbs that P6 conditional/restrictive mapping depends on**; (c) a standard CER gate *understates* the damage (~1–2% by character) while the semantic damage is far larger. Fixable with a repair pass (reinsert U+0E33 where `<consonant> <space> <consonant>` yields a dictionary word) or by re-extracting with `pdftotext -layout`/`pdfplumber` and diffing. **Validate on the PDPA before submission — highest-value single Thai fix.**

**3. Indonesia — the shipped OCR layer is corrupt exactly where it matters (VERIFIED).** Observed errors: `REPUELIK INDONESIA`, `REPUBUK`, `TAHVN 2022`, `NOMOR 35 TAHUN 2O2I` (letter O for zero), and critically **`Pasal 5 ayat (l)`** — letter *l* for digit *1*. **Do not trust the embedded text layer for citations.** Re-OCR the rasters; expect the shipped layer to blow past the 5% CER gate.

Also note the **Penjelasan trap (VERIFIED and worse than expected)**: BPK metadata for UU 27/2022 says `penjelasan hlm. 35 sd 50`; page 35 begins the Elucidation, page 36 restarts numbering at `-2-`, and **`Pasal` numbering restarts** — which is why `Pasal N` matched **213 times in a 76-article law**. And the heading itself is OCR-garbled to `PENJEI,ASAN ATAS UNDANG-UNDANG REPUBUK INDONESI,A`, so **a literal `PENJELASAN` regex finds nothing**. Split on the metadata page range or the page-number reset, never on the string.

---

## 2. Extended survey (new information)

### Table 7 — Machine access and corpus size

The single biggest cost driver. For reference, Round 1 needed three different entry strategies: web search (SG), an OData API (AU), and the portal's own DataTables JSON (MY).

| Country | Entry strategy | Headless browser? | Corpus (verified from the portal's own counters) |
|---|---|---|---|
| **China** | **Open, unauthenticated JSON API under `/law-search/`** (not `/api/`). `POST /search/list` (discovery), `GET /search/flfgDetails?bbbs=` (metadata + TOC), `POST /search/hitDisplay` (article text), `GET /download/pc?bbbs=&format=` (DOCX/PDF/OFD), `GET /index/aggregateData` (counters), `GET /search/enumData` (taxonomy). Vue 3 SPA, but the axios interceptor adds **no auth headers** | **No** | 宪法 1 · **法律 310 in force** (473 all statuses) · 行政法规 607 · 地方法规 15,808 · 司法解释 561 · **all in force 17,317**. Sheet's "~300 national laws" → **exactly 310** |
| **India** | Documented APIs all **dead** (`/rest/` 404, `/server/api` 404, OAI-PMH 404, sitemap points at `localhost:8080`). **But two undocumented routes work:** (1) **`GET /SectionPageContent?actid=…&sectionID=…`** → JSON with `content` (clean consolidated section text) **and `footnote`** (amendment provenance) — *article-level text plus amendment history, no PDF parsing*; (2) `GET /handle/123456789/1362/browse?type=shorttitle&offset=N&rpp=20` enumerates everything | **No** (one browser UA required) | **845 Central Acts in force**, enumerable in ~43 requests. Context: **4,633 repealed** + 14 spent are separately listed — the dead set is **5.5× the live set**, so name-matching without an in-force filter mostly surfaces repealed law |
| **Lao PDR** | **Plain server-rendered HTML.** No API, no JSON, no sitemap — and none needed. `?r=site/index&Document_page=N` (deep pagination verified to page 120), `?r=site/display&id=N` (detail), `?r=site/list&legaltype=N` (filter). PDF hrefs are in the raw HTML | **No** | **1,471 in-force instruments**; national **laws** ≈ **176**. Sheet's "~150–200 laws" right for laws, understates total instruments 8× |
| **Mongolia** | **`sitemap.xml` — 5,594,094 B, ~37,000 `<loc>` entries, of which 36,833 are `/mn/detail?lawId=N`.** The entire corpus is enumerable from **one file**. Combine with direct `/storage/uploads/…` DOCX fetches. **No JSON API** (`/api/front/index.html` is a static Constitution microsite, not API docs) | **No** | **950 laws · 2,584 parliamentary resolutions · 3,236 administrative regulations · 324 translations · 19,874 total acts.** Sheet's "~500–800" understates it |
| **Russia** | **A fully documented OpenAPI REST service.** Swagger UI at `/swagger/index.html`, spec at `/swagger/v1/swagger.json` (113 KB, **48 paths**, `Architect.Public.OpenApi` v1), **no auth**. `GET /api/Documents` takes ~30 params incl. **`DocumentText` full-text search**, `Block`, `DocumentTypes`, date ranges. Plus `/api/Rss`, `/sitemap.xml`, and **`/OpenData/list.json`** (bulk datasets: acts published in last 30/90/360 days, JSON + CSV) | **No** | Published-document counts by block: regional **1,560,779** · government **57,670** · federal executive **46,521** · treaties **2,188** · federal assembly **195**. **The 195 is implausibly low for federal laws and is almost certainly period-filtered — NOT VERIFIED as a true count.** An unscoped crawl faces 1.5M+ regional documents; scope hard on `Block` + dates |
| **Thailand** | **A clean undocumented JSON API.** `GET https://www.ocs.go.th/searchlaw/indexs/list_table_search?page=1&perpage=100` → `{"meta":{...,"total":1885,"pages":19},"data":[…]}` (served as `text/html`, parses as JSON). Fields incl. `lawCode`, `lawNameTh/En`, `publishDate`, `fileUUID` (direct signed PDF URL), **`childrens`** (amendment lineage). **Whole corpus harvested in 19 requests** | **No** for `ocs.go.th`; **YES (Playwright) for `ratchakitcha.soc.go.th`** | `meta.total` **1,885** (1,891 collected across 19 pages). **พระราชบัญญัติ (Acts) 1,414**, orders 216, notifications 176, emergency decrees 57, constitutions 15, codes 7. **1,088 have a downloadable file; 27 have English.** Spans 1877 → 2568 BE (2025 CE) |
| **Indonesia** | **No API, no sitemap** (`/api/peraturan` 404, `?format=json` → HTML, `/sitemap.xml` → 404 page). **But cleanly scrapeable:** `GET /Search?keywords=&tahun=&jenis=…` → `/Details/{id}/{slug}` → `/Download/{fileId}/{name}.pdf`, all plain GET, server-rendered. `GET /Home/Jenis` returns the full type taxonomy **with counts**. `jdih.setneg.go.id` is a **Next.js SPA with empty `__NEXT_DATA__.pageProps`** and zero PDF links in a 2.4 MB page — needs browser automation, not recommended. JDIHN's documented API is a **push** sync for member institutions, not a public read API (**REPORTED**, host unreachable) | **No** for BPK | **National:** UU **1,927** · Perpu 170 · PP **4,996** · Perpres **2,675** · Keppres 6,973 → **~17,400 central**, core UU+Perpu+PP+Perpres ≈ **9,768**. **Regional: ~265,500** (Perbup 144,975; Perda 63,416; Perwali 37,931…). **~94% is regional noise — filtering by `jenis` is mandatory.** Cumulative historical, not in-force |
| **Timor-Leste** | No API, no sitemap (`/sitemap.xml` → Drupal 404), RSS exists but is 3.2 KB of index nodes only. **But the ergonomics are the best of all eight:** every instrument type has **one flat HTML table listing all years 2002→2026 at once, no pagination, no JS** — `?q=node/12` (Leis), `?q=node/13` (Decretos-Leis), `?q=node/10`, `/18`, `/19`, `/20`, `/23`. Full-text search at `?q=search/node/<term>`. PDF patterns: `public/docs/{YYYY}/serie_1/SERIE_I_NO_{n}.pdf`, legacy `public/docs/2002_2005/…` | **No** | **Leis do Parlamento Nacional 278 · Decretos-Leis do Governo 906**, both 2002–2026 → core primary legislation ≈ **1,184**, fully crawlable. Sheet's "low hundreds" right for Leis; Decretos-Leis are ~3× that. **Two HTTP GETs give you the entire national statute book index** |

#### Four API gotchas that fail silently

- **Russia `PageSize` is a non-obvious enum.** `10/30/100/200` → 200 OK. **`20` and `50` → HTTP 400.** A natural default of 20 or 50 fails every call.
- **Thailand `perpage` caps at 100.** `150/200/500/1000/1885` → **`total:0` with an empty array — a silent failure, not an error.**
- **China `orderByParam:""` → HTTP 500** (use `null`, `{}`, or omit). And the search body **must be sent as raw UTF-8 bytes** — passing Chinese through a shell argument silently yields `searchContent:null` and 0 rows.
- **India punishes `python-requests` with a fake 404**, which logs as "law not found" rather than "blocked". Set a browser UA.

#### Two structural notes worth budgeting for

- **Russia's good API and its readable text are on different systems.** `publication.pravo.gov.ru` gives clean JSON metadata over **scanned** PDFs; `pravo.gov.ru/proxy/ips/` gives real consolidated text but is a legacy frame-based CGI app, **windows-1251 encoded, with no API**. You need both, plus a join between them. Whether IPS covers every act is **NOT VERIFIED**.
- **China's `flfgDetails` returns an outline only** — leaf nodes are `{id,parentId,title:"第一条",…}` with **no body text**. Full text must come from the DOCX/PDF, or piecemeal from `hitDisplay` (which does return real text).

### Table 8 — Script, encoding and tokenization hazards

| Language | Unicode block | Legacy-encoding hazard | Inter-word spaces? | Stacking marks? | Segmenter needed |
|---|---|---|---|---|---|
| **Lao** | U+0E80–0EFF | **SEVERE — the worst in the survey.** Lao never adopted a usable 8-bit standard. LaoScript's vendor docs state it directly: *"unlike Thai, no 8-bit coding standard for Lao was ever adopted or supported by Microsoft or application developers."* ≥8 mutually incompatible conventions (LSWin, Lao 95, Lao 2000, IBM-STENO, Alice, SengChanh, Sayawath, Unicode). Saysettha/Chanthabouli put Lao in **upper-ASCII**; SengChanh and alice_0 replace the *Latin* letters outright, putting Lao on **plain 7-bit ASCII**. **Confirmed present in live gazette PDFs** (see §1) | **NO** — Unicode 17.0 §16: *"Lao words are not separated by spaces."* UAX #14 class **SA (Complex_Context)** | **Yes** | `laonlp` (PyPI 1.3.0, Jan 2026, Apache-2.0 — but it is a PyThaiNLP port with a hard `pythainlp` dependency, F1 ≈ 0.71 **REPORTED**) or **ICU/PyICU** (`laodict.txt` + `LaoBreakEngine`, automatic — the more defensible production choice) |
| **Thai** | U+0E00–0E7F | **TIS-620 / Windows-874 real but not observed on OCS.** The live defect is different and worse: **broken ToUnicode / SARA AM destruction** (§1). Corroborated upstream — PyMuPDF Discussion #3264, maintainer: *"none of my PDF-to-text converters can successfully handle this file."* *Note:* misordered marks **as a reproduced extractor bug** is **NOT VERIFIED**; what is documented is display-vs-copy mismatch, and Unicode L2/18-248 recording that **both mark orders are already in use in the wild** — the ambiguity is in the data, not only the extractor | **NO** — Unicode 17.0 §16 | **Yes** — ThaiOCRBench (arXiv 2511.04479) names *"the absence of inter-word spacing"* and *"stacked diacritics"* as the core difficulties | **`pythainlp`** (`newmm` default; PyPI 5.3.5, Jul 2026, actively maintained) |
| **Chinese** | CJK | **Not an issue on live portals.** `flk.npc.gov.cn`, `gov.cn`, `cac.gov.cn`, `miit.gov.cn` all serve `charset=utf-8`; GB18030 is a Unicode superset. **The hazard is inside PDFs** — pdfminer.six #566 / PyMuPDF #2367, #3801 document GBK-based CMaps breaking extraction. **Our own traps: U+3000 IDEOGRAPHIC SPACE after `第N条` (1,973×), full-width digits `２０２１` in dates (435×) → NFKC or date parsing fails silently** | **NO** | No | **`jieba`** — standard, but **frozen** (last PyPI release 0.42.1, Jan 2020) |
| **Russian** | Cyrillic | **Effectively a non-issue in 2026** — W3Techs (14 Aug 2026): Windows-1251 0.1%, KOI8-R <0.1%. Treat as archival risk only. **Exception: `pravo.gov.ru/proxy/ips/` is windows-1251** — decode explicitly | Yes | No | None |
| **Mongolian (Cyrillic)** | Cyrillic | **Real and confirmed with hard evidence.** Mongolian adds Ө/ө (U+04E8/9) and Ү/ү (U+04AE/AF), which CP1251-family pages lack. The contamination is **baked into Tesseract's own `mon` training corpus**: Ө+ө 413,329 correct vs Є+є 22,101 substituted (**~5.1%**); Ү+ү 394,666 vs Ї+ї 18,921 (**~4.6%**) | Yes | No | None |
| **Mongolian (traditional)** | U+1800–18AF | Vertical top-to-bottom, columns **left-to-right**; four Free Variation Selectors; **Unicode 17.0 itself flags the model as unstable** — *"StandardizedVariants.txt for Mongolian has not yet been updated to synchronize with … Unicode Technical Note #57"* | — | — | **Moot — see the finding below** |
| **Devanagari** | U+0900–097F | India Code's **Hindi PDFs have a broken ToUnicode CMap** — `H2000-21.pdf` extracts `अगिगनयम` where the correct text is `अधिनियम`. **Silently corrupted.** Another reason to take English only | Yes | **Yes** — shirorekha headline, conjuncts, four-way matra attachment | None (taking English) |
| **Indonesian** | Latin | None | Yes | No | None |
| **Portuguese** | Latin | Diacritics extract cleanly as proper codepoints (ç U+00E7, ã U+00E3, õ, é) — **no mojibake, VERIFIED**. **The one real trap is the ordinal indicator**, and it is an asymmetry: `unicodedata` shows **U+00BA has `<super> 006F`, so NFKC folds `º` → `o`, while U+00B0 (degree sign) has no decomposition and survives NFKC unchanged.** So `Artigo 1.º` and `Artigo 1.°` — the same citation, one correct and one OCR-substituted — normalise to **two permanently non-matching strings**. Map U+00B0 → U+00BA *before* NFKC | Yes | No | None |

#### Mongolia's vertical script: a risk that does not materialise

**VERIFIED.** Raw-byte scans for U+1800–U+18AF across nine pages returned **zero occurrences everywhere**: `legalinfo.mn/mn` (108,398 B), `/en` (93,965 B), the Constitution (755,990 B), the Criminal Code (2,799,093 B), **the National Mongol Script Program III page itself** (145,801 B), and `parliament.mn` gazette 2026 no.18 (111,143 B). Zero also in the PDP Law DOCX. **No script toggle exists** — only `mn` ⇄ `en`, both Cyrillic/Latin.

On the mandate: **(a) it is real and in force — VERIFIED**, Law on Mongolian Language (2015) Art. 7.2, commenced by Art. 24.2 on 1 Jan 2025. **(b) Compliance is partial — REPORTED** (2021 survey of ~150,000 civil servants: 53.6% ready; full transition target 2030; no 2026 audit found). **(c) Crucially, the scope excludes legislation — VERIFIED:** Art. 7.2 binds *албан хэрэг хөтлөлт* — administrative record-keeping and correspondence by state bodies. **Nothing requires statutes to be enacted or published in vertical script**, and the observed data agrees.

**Net: Mongolia needs no Mongol Bichig capability.** A defensive U+1800–U+18AF range check that flags-and-quarantines rather than OCRs is a one-line, judge-defensible answer — and the right one, since no engine supports the script and a Cyrillic model would emit confident garbage.

### Table 9 — Which OCR engine can actually read it

Independently re-verified 13–14 Aug 2026 against primary docs; consistent with the repo's own `docs/OCR_LANGUAGE_EVIDENCE.md`.

| Language | PaddleOCR | RapidOCR | EasyOCR | Tesseract | **Azure Doc Intelligence** | Azure AI Vision Read | Google Cloud Vision |
|---|---|---|---|---|---|---|---|
| Simplified Chinese | ✅ `ch` | ✅ `ch` | ✅ | ✅ `chi_sim` | ✅ | ✅ | ✅ |
| English | ✅ | ✅ | ✅ | ✅ `eng` | ✅ | ✅ | ✅ |
| Devanagari / Hindi | ✅ | ✅ (≥3.5.0) | ✅ | ✅ `hin` | ✅ | ✅ | ✅ |
| **Lao** | ❌ | ❌ | ❌ | ✅ `lao` | ❌ *(detect-only)* | ❌ | ✅ `lo` |
| Mongolian Cyrillic | ✅ via `cyrillic` | ✅ (≥3.5.0) | ✅ | ✅ `mon` | ✅ | ✅ | ⚠ *Experimental tier* |
| **Traditional Mongolian** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Russian | ✅ `eslav` | ✅ `eslav` | ✅ | ✅ `rus` | ✅ | ✅ | ✅ |
| **Thai** | ✅ `th` *(new in PP-OCRv5)* | ✅ (≥3.4.0) | ✅ | ⚠ weak | ✅ | **❌** | ✅ |
| Indonesian | ✅ `latin` | ✅ `latin` | ✅ | ✅ `ind` | ✅ | ✅ | ✅ |
| Portuguese | ✅ `latin` | ✅ `latin` | ✅ | ✅ `por` | ✅ | ✅ | ✅ |

Sources (all fetched 13–14 Aug 2026): [PaddleOCR PP-OCRv5 multilingual list](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md) · [RapidOCR model list](https://raw.githubusercontent.com/RapidAI/RapidOCRDocs/main/docs/model_list.md) · [EasyOCR](https://www.jaided.ai/easyocr/) + `easyocr/config.py` · tessdata/tessdata_best via GitHub API · [Azure DI OCR language support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr) · [Azure AI Vision language support](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/language-support) · [Google Cloud Vision languages](https://docs.cloud.google.com/vision/docs/languages).

**Four things this table changes:**

1. **The Lao claim is CONFIRMED, with a sharper edge.** Azure DI *does* list Lao `lo` — **but only in its language-*detection* table**, which the doc explicitly separates from extraction (*"this list differs from list of languages we support extracting text from"*). Azure can tell you a page is Lao and still cannot read it. **That is worse than a clean "no", because a naive integration will look like it succeeded.**
2. **PaddleOCR now supports Thai** (`th_PP-OCRv5_mobile_rec`). Any note saying otherwise is out of date.
3. **The two Azure products diverge.** Document Intelligence `prebuilt-read` lists Thai; **Azure AI Vision Read does not list Thai at all.** The repo's `ocr_azure.py` currently calls **AI Vision** — so the Azure fallback cannot read the language the config assigns to it. *(Already logged as an open defect in `docs/OCR_LANGUAGE_EVIDENCE.md`; restated here because it now bears on a Round-2 country choice.)*
4. **RapidOCR version pins are load-bearing.** `th` needs `rapidocr>=3.4.0`; `cyrillic`/`devanagari` need `>=3.5.0`; **the default pip install ships Chinese+English only.** If `requirements.txt` floats below those, the language codes resolve to nothing at runtime.

**Lao accuracy ceiling (REPORTED, from `docs/OCR_LANGUAGE_EVIDENCE.md`):** best open real-document result is **~64.5/100 NED ≈ 35% error** (MORE, arXiv 2607.02956) — **~7× over the 5% CER gate** — while two widely-cited open models collapse to 0.89 and 0.00 on the same test. Tesseract `lao` has **never had any accuracy figure published**. Thai for comparison: 99.19 NED (~0.8% error).

---

## 3. Per-country assessment and recommendation

### Scores

1–5, higher is better. **Accessibility** = can we reach it and are we allowed to crawl it. **Machine-readability** = cost of enumeration + text retrieval. **OCR viability** = is raster OCR on the critical path and can any engine meet <5% CER. **Parsing** = cost of a correct per-country provision splitter. **Key** = covered by the RDTII 2.1 answer key.

| Country | Access | Machine-read | OCR viability | Parsing | Key | **Total /25** | Points |
|---|---|---|---|---|---|---|---|
| **India** | 4 | 5 | 5 | 5 | 5 | **24** | 10 |
| **Mongolia** | 5 | 5 | 5 | 4 | 5 | **24** | 10 |
| **China** | 4 | 5 | 5 | 4 | 5 | **23** | 10 |
| **Thailand** | 3 | 5 | 3 | 3 | 5 | **19** | 10 |
| **Timor-Leste** | 5 | 4 | 5 | 3 | **1** | **18** | **20** |
| **Russia** | 3 | 4 | 1 | 4 | 5 | **17** | 10 |
| **Lao PDR** | 5 | 4 | **1** | 2 | 5 | **17** | 10 |
| **Indonesia** | 2 | 3 | 1 | 2 | 5 | **13** | 10 |

### The recommendation: India, Mongolia, China

**Take India, Mongolia and China as the three mandatory finals economies.**

The reasoning is a single sentence: **all three deliver article-level text without raster OCR, all three have a machine-readable enumeration path, and none of them requires a headless browser.** For a one-person team with 8 weeks on CPU-only hardware, that removes the entire OCR-accuracy risk class from the critical path, and OCR accuracy is the one risk this team cannot buy its way out of without a GPU.

**India (24/25) — the cheapest by a wide margin.** English is the *authoritative* text, not a translation, so verbatim citation is legally clean and the existing English extraction stack in `backend/pipeline/extraction.py` (which already handles `Section 1.`, `CHAPTER` + Roman, `(1)`, `(a)` for SG/MY) transfers almost unchanged. The undocumented `/SectionPageContent` JSON API returns **consolidated section text plus machine-readable amendment footnotes**, so India needs neither PDF parsing nor OCR nor a language model change. Cost: one browser User-Agent, an in-force filter (the repealed set is 5.5× the live set), and letter-suffix handling for `Section 3A.` / `CHAPTER XIIA`. The counter-argument — that the organisers framed the finals as *"NOT in English"* — is real but is a presentation problem, not a scoring one; the points are 10 either way, and taking India cheaply is what buys the time to do China properly.

**Mongolia (24/25) — the survey's biggest surprise, and it inverts the sheet's intuition.** The nominally scariest script is the *easiest* portal of all eight: one 5.5 MB `sitemap.xml` enumerates 36,833 law URLs with no crawling and no pagination; source documents are fetchable as **DOCX**, so there is zero OCR; and the served text is **consolidated with per-provision amendment provenance**, which means article-level citation *and* the "Last Amended" column come free from the same fetch. Cyrillic is Unicode-safe, word-spaced, and covered by the multilingual MiniLM embedder already in the stack — no segmenter, no new retrieval work. The only genuine cost is a splitter with vowel harmony (`\d+\s+д[үу]г[эа]{2}р\s+зүйл`) plus hierarchical decimals, which is an afternoon. Mongolia also lets the team demonstrate non-English capability *and* a defensible answer on vertical Mongol Bichig (detect the U+1800–18AF range, flag it unextractable, cite the statute showing the mandate does not reach legislation) — a good story in the interview.

**China (23/25) — the highest substantive yield per unit of effort.** A completely open, unauthenticated JSON API gives search, status filtering, metadata and DOCX/PDF/OFD downloads; the corpus is **exactly 310 national laws in force**, which is small enough to reason about exhaustively and precisely filterable via `sxx=3`; PDFs are clean text-layer. China is also the canonical P6 data-localisation jurisdiction — PIPL, the Data Security Law and the Cybersecurity Law map directly onto P6-I1/I2/I4 and P7-I1/I2 — so the substantive-accuracy return is high. Costs are all encoding-shaped and all deterministic: CJK-numeral article regex handling 千/百 compounds, U+3000 after `第N条`, NFKC for full-width date digits, `jieba` for BM25 tokenization, and ~10% transient-failure retries.

### Why not the other four

**Thailand (19/25) — the strongest case for swapping in, and the one to reconsider if time allows.** It has real attractions: the organisers' own worked example uses Thailand, so a sample kit will exist; the OCS JSON API yields the entire 1,885-record corpus in 19 requests, which is ideal for the "discovery of new evidence beyond the sample kit" differentiator; and both target laws (PDPA 2019 and Cybersecurity Act 2019) are confirmed present with downloadable files. Two things hold it back. First, **the SARA AM defect attacks the single most heavily weighted criterion** — every snippet containing `สำนักงาน`, `กำหนด` or `จำกัด` is byte-wrong on extraction, and "paraphrased snippets cannot be audited and your points will be deducted" is the judges' own language. It is fixable, but it must be *fixed and validated*, not assumed. Second, the authoritative Royal Gazette is behind a Cloudflare JS challenge, so any cross-check against the publication of record needs Playwright. **If the team fixes and validates the SARA AM repair pass in week 1, swap Thailand in for India.**

**Russia (17/25) — killed by a fact the sheet had backwards.** The sheet's blocking claim is wrong in the team's favour (the portal is open, permissive, and has a documented 48-path OpenAPI service reachable from a US IP), but the PDFs are the problem: **4 of 4 sampled documents from 4 different authority blocks had zero text characters and exactly one image per page — including documents published this week.** Russia is 100% raster OCR, with Cyrillic CER unmeasured against the 5% gate, on CPU. The IPS text route mitigates it, but that means integrating two unrelated systems (a modern JSON API for discovery, a windows-1251 frame-based CGI app for text) and joining them — and IPS coverage is unverified. Too much surface for 8 weeks. *One fix is worth making regardless of the decision:* our own `WebFetch` auto-upgrades http→https and therefore sees the entire `pravo.gov.ru` family as dead. Any fetcher that forces HTTPS returns zero Russian documents.

**Lao PDR (17/25) — the honest answer is that no engine can read it.** The portal is delightful (wide open, no robots, simple pagination) and the corpus is small, but 18 of 18 sampled PDFs are flatbed scans, the text-layer minority is legacy-font mojibake landing *precisely on the chapter headings you chunk by*, no model exists in PaddleOCR / RapidOCR / EasyOCR / Azure DI, and the best open real-document result is ~35% error against a 5% gate. There is one real path — the ~30% of detail pages serving clean Unicode HTML, concentrated in exactly the low-id core-law band where P6/P7 instruments live — and if the team ever wants Lao, that is the route. But it means declaring up front that coverage is partial and PDF-only laws are unreachable. Not a place to spend a mandatory slot.

**Indonesia (13/25) — last, and the sheet's one substantive legal error is why.** The sheet says consolidated versions exist; **they do not**. UU 11/2008 has been amended twice and partially repealed, and the portal offers exactly one file: the original 2008 text. Producing the operative ITE law today means fetching UU 11/2008 + UU 19/2016 + UU 1/2024, subtracting the articles repealed by UU 1/2023, and applying Constitutional Court rulings — **a legal-reasoning task, not a retrieval task**, and one that cannot be honestly automated in the time available. Stacked on top: the official portal is unreachable; UU/PP PDFs are scans whose *shipped* OCR layer corrupts `Pasal 5 ayat (l)`; the Penjelasan duplicates every article number behind an OCR-garbled heading; and `peraturan.bpk.go.id/robots.txt` explicitly disallows ClaudeBot and every other AI crawler. Avoid.

### Timor-Leste: yes — as the optional fourth, not as one of the three

**Take it, but only after the mandatory three are green, and go in with the limitation stated out loud.**

The case for it is strong and slightly paradoxical: **Timor-Leste is technically the easiest country in the survey and legally the hardest.** Two HTTP GETs return the entire national statute book index (278 Leis + 906 Decretos-Leis, flat HTML, all years, no pagination, no JS). Every PDF sampled is born-digital — *including 2002–2003 issues*, so the "early scans" worry does not reproduce. There is no WAF, no captcha, no geo-block, and the robots.txt does not disallow AI crawlers. Portuguese is Latin script, and the existing extraction stack handles it after a small ordinal-character fix. **It is worth 20 points where every other country is worth 10, and it is the best points-per-engineering-hour on the board.**

Three things must be said plainly rather than discovered by a judge:

1. **There is no answer key.** RDTII 2.1 covers 48 economies and Timor-Leste is not among them (verified above). Substantive accuracy cannot be scored against a key the way it can for the other seven — which is presumably part of why it is worth double. Treat every Timor-Leste mapping as new evidence and route it to human review.
2. **No consolidated text, and the amendment graph exists only as Portuguese prose in document titles** (*"Segunda alteração à Lei n.º 3/2004, de 14 de abril"*). Reconstructing it needs NLP over ordinals plus `Lei n.º X/YYYY` — doable, but it is the same class of problem that disqualified Indonesia, just at 1/8th the corpus size.
3. **The PDF is the whole gazette issue, not one law**, so instruments must be segmented *within* the file after download — a step none of the other seven require.

Net: the 20 points are real and the engineering cost is the lowest of the eight. The risk is not technical, and pretending otherwise would be the mistake.

---

## Corrections log

| # | Field | Sheet said | Correct | Severity |
|---|---|---|---|---|
| 1 | Thailand URL | `krisdika.go.th` | **`www.ocs.go.th`** — old domain dead, Huawei WAF 404 + self-signed cert | **Blocker** |
| 2 | Indonesia URL | `peraturan.go.id` | **`peraturan.bpk.go.id`** — whole 103.145.96.0/24 block unreachable | **Blocker** |
| 3 | Timor-Leste URL | `jornal.gov.tl` | **`www.mj.gov.tl/jornal/`** — DNS SERVFAIL, no A record | **Blocker** |
| 4 | Lao markers | `ภาค → มาตรา` (**Thai script**) | **`ພາກທີ` → `ໝວດທີ`/`ຫມວດທີ` → `ມາດຕາ` → `ຂໍ້`** | **Blocker** |
| 5 | Indonesia consolidated | Có | **No** — amendments published standalone; operative text must be reconstructed | **Major (legal)** |
| 6 | Russia bot blocking | WAF + foreign-IP blocking | **Neither.** Permissive robots, no WAF, reachable from a US IP, documented OpenAPI service | Major (favourable) |
| 7 | Russia PDF nature | *(implied text)* | **100% scanned images**, incl. documents published Aug 2026 | **Major** |
| 8 | Thailand bot blocking | Không | **Royal Gazette behind Cloudflare JS challenge; `law.go.th` CloudFront-blocked; `data.go.th` blocked** | Major |
| 9 | Indonesia PDF nature | *(implied text)* | **UU/PP/Perpres are scans with a corrupt shipped OCR layer** (`Pasal 5 ayat (l)`) | **Major** |
| 10 | Lao PDF nature | "PDF, HTML, simple structure" | **18/18 sampled are flatbed scans**; text-layer minority is legacy-font mojibake on the headings | **Major** |
| 11 | India bot blocking | Captcha + WAF | **No captcha found anywhere.** UA-based WAF; `python-requests` gets a *fake 404* | Moderate |
| 12 | Mongolia bot blocking | Rate limit | **Not observed** across ~40 requests (high-volume untested) | Moderate |
| 13 | Mongolia markers | `Зүйл`, `Бүлэг` | **`N дугаар зүйл.`** with mandatory vowel harmony; chapters are spelled-out ordinals, no digits | Moderate |
| 14 | Russia markers | `Часть`, `Пункт` as tokens | **Not heading tokens** — cross-references only. Real sub-hierarchy is bare `N.` then `N)`. `Раздел`: 0 hits in ordinary federal laws | Moderate |
| 15 | Thailand amendments | `ฉบับแก้ไขเพิ่มเติม` table in the PDF | **0 occurrences.** Lineage is in the JSON `childrens` array | Moderate |
| 16 | India formats | PDF | **PDF (EN+HI) + HTML + JSON section API** | Moderate |
| 17 | China formats | Word | **DOCX + PDF + OFD**, all via a documented format parameter | Minor |
| 18 | Russia formats | PDF, RTF/Word, ZIP | **PDF only confirmed**; all other `/file/*` paths 404 | Minor |
| 19 | Thailand formats | PDF, Word | **PDF confirmed; Word NOT VERIFIED** | Minor |
| 20 | Mongolia "modern data structure" | (note) | **PHP + jQuery, server-rendered** — not an SPA, no headless browser needed | Minor (favourable) |
| 21 | Corpus sizes | — | Lao **1,471** instruments (176 laws) · Mongolia **950** laws / 19,874 acts · China **310** laws · India **845** Acts · Thailand **1,885** (1,414 Acts) · Indonesia ~9,768 core national · Timor-Leste **1,184** | Moderate |
| 22 | Timor-Leste language | Portuguese, Tetum (implied parity) | **Portuguese ~19:1**; Tetum files are MoJ translations; **no English series** | Moderate |
| 23 | Lao language | Lao | Gazette **also publishes "(Unofficial Translation)" English PDFs** | Minor |

## Biggest risks

1. **Three dead portal URLs.** Corrections 1–3 would each cause a 100% failure rate on the live path. Fix before anything else.
2. **`WebFetch` forces http→https, so all of `pravo.gov.ru` reads as dead.** A live tooling bug today, and it will silently zero out any Russian run.
3. **Verbatim fidelity is attacked by encoding, not by OCR, in the two most tempting countries.** Thailand's SARA AM destruction and Indonesia's corrupt shipped OCR layer both produce text that *looks* fine and fails a byte-comparison — and a standard CER gate under-reports both. The judges deduct points specifically for unverifiable snippets.
4. **Indonesia and Timor-Leste have no consolidated text.** Reporting "Last Amended" honestly there means reconstructing amendment chains — legal reasoning, not retrieval. Do not claim automated coverage.
5. **`peraturan.bpk.go.id` explicitly disallows ClaudeBot and every other AI crawler in robots.txt.** This is a compliance decision the team must make deliberately and be able to defend, not a technical obstacle to route around.
6. **Lao is unreadable at the required accuracy.** No model in Paddle/Rapid/EasyOCR/Azure DI; Tesseract `lao` has no published accuracy of any kind; best open real-document result is ~7× over the gate. The clean-HTML subset is the only honest path, and it covers ~30% of documents.
7. **Four APIs fail silently on natural defaults** (Russia `PageSize` 20/50 → 400; Thailand `perpage` >100 → `total:0`; China `orderByParam:""` → 500 and shell-passed Chinese → 0 rows; India `python-requests` → fake 404). Each looks like "no results" rather than an error.
8. **`ocr_azure.py` calls Azure AI Vision, which has no Thai model**, while the config assigns Thai to Azure. If Thailand is selected, this must be repointed to Document Intelligence `prebuilt-read`.
9. **`eastimorlawjournal.org` is now a gambling site.** Blacklist it.

## Explicitly not verified

- Whether Indonesia's `103.145.96.0/24` unreachability is an outage or a geo-fence.
- Whether Russia's `duma.gov.ru` timeout is geo-blocking or an outage.
- Whether Russia's IPS consolidated database covers every act (only `publication` coverage was established).
- Russia's true in-force federal-law count (the API's `assembly` block reports 195, which is implausible and probably period-filtered).
- Behaviour of any portal under sustained high-volume crawling, or from a mainland-China IP.
- Thailand: Royal Gazette PDF nature (blocked by Cloudflare); whether an explicit consolidation "updated to" stamp exists; whether Word downloads exist; `data.go.th` legislation dataset.
- Mongolia: whether an official/unofficial disclaimer is published for the 324 English translations.
- Lao: whether the PDF mojibake mechanism is a documented library bug (the *mechanism* is verified; no Lao-specific tracker issue or paper was found — run a controlled test rather than citing this as established).
- Thai misordered tone marks **as a reproduced extractor bug** (display-vs-copy mismatch is documented; the reordering may be in the source data).
- Relative Devanagari accuracy ranking across engines (all seven have models; no head-to-head benchmark found).
