# HTML documents currently ingested — inventory for manual inspection

Generated 2026-08-18 from the built corpus. **No pipeline changes made.**

Full machine-readable list: `logs/html_ingested_urls.csv`
(columns: economy, title, url, portal, collection, extracted_chars, provisions, bgk_target)

Regenerate with:

```bash
python - <<'PY'
from sqlalchemy import select
from backend.corpus.store import corpus_law, corpus_version
from backend.storage.engine import get_engine
with get_engine().connect() as c:
    for r in c.execute(select(corpus_law.c.economy, corpus_law.c.title, corpus_law.c.source_url,
                              corpus_version.c.chars, corpus_version.c.provisions_n)
        .select_from(corpus_version.join(corpus_law, corpus_law.c.law_id==corpus_version.c.law_id))
        .where(corpus_version.c.fmt=="html", corpus_version.c.state=="split",
               corpus_version.c.superseded_by.is_(None))):
        print(r)
PY
```

## 1. Scale and health, by host

122 HTML documents are in the corpus and therefore in the retrieval index. Extraction health is
**site-specific, not format-specific** — one of the four hosts extracts perfectly well:

| host | economy | docs | median extracted chars | max | shells (<2 KB) |
|---|---|---|---|---|---|
| `www.pdpc.gov.sg` | SG | 112 | **220** | 10,887 | **110 (98 %)** |
| `www.imda.gov.sg` | SG | 7 | **399** | 425 | **7 (100 %)** |
| `www.oaic.gov.au` | AU | 2 | **14,550** | 15,586 | **0 (0 %)** |
| `www.homeaffairs.gov.au` | AU | 1 | **949** | 949 | **1 (100 %)** |

For comparison, PDF documents in the same corpus have a median of 21,551 extracted characters.

A shell contributes exactly one "provision" made of page furniture — e.g.
`"PDPC | Guide to Data Protection Impact Assessments Skip to main content Browse related tags:
Getting Started Data Management Share: facebook linkedin whatsapp"` — and that text **is
indexed and retrievable** today.

## 2. The judges-cited HTML documents (4)

These are the ones that decide indicator outcomes. Note the recurring pattern: **we hold the
landing page; the panel cites the PDF (or a deeper page) that the landing page publishes.**

### 2.1 SG · P7-I4 · MISSED at EXTRACTION

Indicator P7-I4 (DPO / DPIA requirements). Panel Raw Score 1.0.

| | |
|---|---|
| title | Guide to Data Protection Impact Assessments |
| **our URL (HTML)** | `https://www.pdpc.gov.sg/organisations/resources/guidance-by-topic/guide-to-data-protection-impact-assessments` |
| **panel's URL (PDF)** | `https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Other-Guides/DPIA/Guide-to-Data-Protection-Impact-Assessments-14-Sep-2021.pdf` |
| extracted | 238 chars → 1 provision (nav chrome) |

| | |
|---|---|
| title | Advisory Guidelines on the PDPA for Children's Personal Data in the Digital Environment |
| **our URL (HTML)** | `https://www.pdpc.gov.sg/organisations/regulations-decisions/regulatory-guidance/advisory-guidelines-on-the-pdpa-for-childrens-personal-data-in-the-digital-environment` |
| **panel's URL (PDF)** | `https://www.pdpc.gov.sg/-/media/files/pdpc/pdf-files/advisory-guidelines/advisory-guidelines-on-the-pdpa-for-children's-personal-data-in-the-digital-environment_mar24.pdf` |
| extracted | 209 chars → 1 provision (nav chrome) |

(The third instrument the panel cites for SG P7-I4, PDPA 2012 s 11(3), **does** survive end to
end, so the indicator itself is answered — these two are lost comprehensiveness, not a lost
indicator.)

### 2.2 AU · P7-I2 · MISSED at RETRIEVAL

Indicator P7-I2 (dedicated cybersecurity framework). Panel Raw Score 0.5.

| | |
|---|---|
| title | Cyber security strategy |
| **our URL (HTML)** | `https://www.homeaffairs.gov.au/about-us/our-portfolios/cyber-security/strategy` |
| **panel's URL** | `https://www.homeaffairs.gov.au/about-us/our-portfolios/cyber-security/strategy/2023-2030-australian-cyber-security-strategy` |
| extracted | 949 chars → 1 provision |

We captured the **parent index page**, not the strategy document itself. AU P7-I2 currently has
no surviving evidence at all (its other three instruments were rejected by the grader as
definitions sections — see `pipeline-attribution.md`).

### 2.3 AU · P7-I4 · SURVIVED (shown because it proves HTML *can* work)

| | |
|---|---|
| title | Chapter 10: Directing a privacy impact assessment |
| our URL | `https://www.oaic.gov.au/about-the-OAIC/our-regulatory-approach/guide-to-privacy-regulatory-action/chapter-10-directing-a-privacy-impact-assessment` |
| extracted | **13,513 chars** → 1 provision |
| panel's URL | `https://www.oaic.gov.au/privacy/guidance-and-advice/privacy-management-framework-...` |

OAIC serves server-rendered HTML, so the body extracts cleanly. It still becomes a **single**
provision (no `Section N` structure), which is where the chunking question becomes real — but
only for sites like this one.

Also present, not currently a matched target: `Part 2: Preparing a data breach response plan`
(`https://www.oaic.gov.au/privacy/notifiable-data-breaches/preventing-preparing-for-and-responding-to-data-breaches/data-breach-preparation-and-response/part-2-preparing-a-data-breach-response-plan`,
15,586 chars). This is the page that the linkage bug had wrongly attached to "Privacy Act 1988".

## 3. The other 118

* **pdpc.gov.sg (112)** — regulatory guidance, advisory guidelines and enforcement decisions.
  110 of 112 are shells. A representative page is 190 KB of markup of which ~175 KB sits inside
  `<script>` tags and 854 characters are real markup text; there is no same-domain `.pdf` link
  in the served HTML and no JS-framework marker. The two that *do* extract are
  `personal-data-protection-regulation-2021` (10,887 chars) and `data-protection-notice-generator`
  (3,443 chars).
* **imda.gov.sg (7)** — all shells (43–425 chars), and all of them are incidental pages
  (quality-of-service performance reports, a standards committee page). The licence conditions
  and IP-telephony terms the panel actually cites were never reached at all; they live under
  `/-/media/Imda/Files/...` and are still missing from the catalogue.

## 4. What is being asked of you

For each site, the useful answer is *where the legal text actually lives* and how to reach it:

1. **pdpc.gov.sg** — is the body loaded from a JSON/API endpoint, or should we always resolve
   the landing page to its `/-/media/.../*.pdf` sibling? (The panel cites the PDF in both
   missed cases, which suggests the PDF is the canonical instrument.)
2. **homeaffairs.gov.au** — is the strategy a downloadable PDF, and is the deeper
   `/strategy/2023-2030-australian-cyber-security-strategy` page server-rendered?
3. **imda.gov.sg** — what index page lists the telecom licences, so licence conditions can be
   enumerated rather than crawled blindly?
4. **oaic.gov.au** — already extracts; the open question is only how a 13 KB guidance page
   should be *split* (by heading? whole-document?).
