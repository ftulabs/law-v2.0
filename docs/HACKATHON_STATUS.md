# VeriTrade — Status & Open Questions

_A ~10-minute read. Sections 1–4 are plain enough for anyone; Section 6 lists the questions still open for the mentor, each with the background spelled out first._

---

## 1. The problem we're solving

To build the RDTII ranking, researchers today read each country's laws by hand, work out which provisions say something about data, and map them to a set of indicators. It is slow and manual: more than ten researchers, one to four weeks per country, over 2,600 regulations reviewed so far.

VeriTrade does that job automatically. You give it a country and a pillar (e.g. *Singapore, Pillar 6*), and the tool goes out to the official government legal portal, finds the relevant laws, downloads them, reads them, and points to the exact provisions that match each indicator — with a verbatim quote, an article-level citation, and a link back to the source.

We follow two rules the brief insists on: the tool must **find the laws itself at run time** (no pre-loaded corpus of answers), and it must work from the **topic alone** — we never hand it the names of the laws to look for.

---

## 2. How it works, end to end

Think of a new researcher doing the task. The tool follows the same six steps.

1. **Find the law.** Much like typing a query into a search engine to land on the right law page on the government portal. The three portals are all awkward to crawl directly, so we search the web for the correct URL on the official site, then go there to download.

2. **Download it.** We fetch the law's PDF, politely (size limits, no hammering the server) and cache it so we never download the same thing twice.

3. **Read and split.** We turn the PDF into clean text and split it into individual articles/sections. If the PDF is a scanned image rather than real text, we run OCR to read the characters off the image.

4. **Find the relevant provisions — by meaning, not keywords.** This is the heart of it. We do **not** just keyword-match (that's the trap the judges flagged: a law with "financial" in its title gets pulled to the top even when its content is irrelevant). Instead the tool reads and understands each provision, ranks them by genuine relevance, and a second "AI reviewer" (a cross-encoder) re-checks the top ones for precision.

5. **Map to the right indicator.** A language model reads the provision and the indicator's definition and decides which indicator it satisfies. We wrote the instructions carefully so the model doesn't confuse neighbouring indicators and doesn't drop a provision that legitimately matches more than one.

6. **Write the output and self-rate confidence.** Each mapping becomes one row, with a confidence score; low-confidence rows are flagged for human review. We produce two files: a **CSV** in the official 13-column template (for the policy judges) and a richer **JSON** (for the technical judges).

---

## 3. What's working today (tested on real data)

- **Discovery:** "Singapore + cross-border data transfer" finds the **Personal Data Protection Act (PDPA)** on the official portal — it even points at **Section 26**, the cross-border transfer clause. For Australia it finds the **Privacy Act 1988** through the portal's official JSON API.
- **Download + read:** we pulled the real PDPA PDF (461 KB) and split it into **218 provisions** with clean spacing, and we now keep the **full, exact text** of each provision (per the template).
- **Understanding:** asked about "individuals' rights over their data", the tool picks the right access/correction provisions and correctly **rejects** a cybersecurity clause that merely shares a few words.
- **Correct indicator set:** we rewrote the indicators to match the **RDTII Methodology** (Pillar 6 = data-localisation: ban / local storage / infrastructure / conditional flow; Pillar 7 = framework: data-protection law / cybersecurity / retention / DPIA-DPO / government access). We checked this against **all six of the judges' worked examples** (Armenia→6.4, Kazakhstan→6.2, Vietnam→6.3, India→7.4, Singapore CPC→7.5, Bhutan→7.2) — every one maps correctly.
- **KNOWN vs NEW:** any law that appears in the judges' sample database is tagged KNOWN; anything the tool finds on its own is tagged NEW (the higher-value tag).
- **OCR quality / CER:** when a scanned PDF has a reference text, we now **measure the real Character Error Rate** and record whether it's under the 5% bar; the JSON carries this per document.
- **Robust input:** the tool accepts mis-spelt or alternate country names ("Singapor", "austrlia", "MALAYSIA ") — the brief asks for tolerance to inputs you didn't anticipate.
- **No vendor lock-in:** the LLM and OCR engines are swappable with one config line. The tool runs with Gemini, OpenRouter, a self-hosted model, or fully offline; OCR can be MarkItDown, RapidOCR, Tesseract, etc.
- **Runs from the command line** (the GUI is optional) and passes its test suite.

---

## 4. What's still rough or unfinished

1. **Discovery can stall.** Free search engines rate-limit us if we query too fast. We've softened this (a free search API key plus caching), but for a live demo a key makes it reliable.
2. **Malaysia isn't fully proven end-to-end.** Its portal is the hardest, and many documents are scanned images in Malay — we haven't tested that path thoroughly.
3. **The mapping hasn't been validated on a strong real LLM yet.** We tuned the prompt against an offline stand-in and the judges' examples, but we haven't yet run it through a real model at scale — and this is the biggest scoring block (substantive accuracy). We have a Gemini integration ready; its free quota is currently exhausted, and a 4× V100 GPU box is coming online to host our own model (see Section 7).
4. **Law numbers** ("Act 709", "B.E. 2562") aren't reliably extracted yet for laws the tool finds itself.
5. **Deployment to the Jetson/GPU box** is designed but not built.
6. **The cost report and README quick-start** still need real measured numbers filled in.

---

## 5. Things the mentor has already settled (so we don't re-ask)

- **Indicator set:** use the **Methodology** indicators (6.1–6.4 / 7.1–7.5), not the "Indicator Reference" sheet. ✅ Done and validated.
- **Input at judging:** **country + pillar**. ✅ Matches how the tool already runs.
- **Verbatim snippet:** quote the **full, exact provision**. ✅ Done.
- **Scoring (the 0 / 0.5 / 1 step):** optional, worth **extra points only**; criteria provided. We'll add it if time allows.
- **Source URL:** the **landing page** is preferred but a direct PDF link is also fine. ✅ We now output the landing page.

---

## 6. Open questions for the mentor

**6.1 — One best provision per indicator, or every relevant one?**
For each indicator we currently surface several ranked candidates, but the sample database usually records just one law per (country, indicator). Do you want a single best-fit provision per indicator, or an exhaustive list of everything that touches it? And if we include an extra mapping that turns out wrong, does that cost points, or is it simply ignored? This decides whether we tune the tool to be strict (fewer, very precise) or broad (more coverage, some over-tagging risk).

**6.2 — Is there a labelled set of (provision → correct indicator) we can test against?**
The mapping is the largest scoring block, but we can only check it against the few worked examples in your slides. A labelled set would let us measure accuracy properly and tune the prompt. Do you have one we can use? (The RDTII documents you offered to share may already cover the per-indicator definitions we've been guessing at.)

**6.3 — Coverage column: "Horizontal/Sectoral", or the specific sector name?**
We fill Coverage with "Horizontal" or "Sectoral". Your sample database uses more specific values like "Cross-cutting", "Financial sector", or "Telecommunications services". Should we output the specific sector, or is Horizontal/Sectoral enough?

**6.4 — KNOWN/NEW at law level, and how do you treat a new provision in a known law?**
Your sample list identifies known examples at the law level — it doesn't name a specific article — so we mark a mapping KNOWN if its law is on the list and NEW otherwise. Two questions: (1) is law-level KNOWN/NEW acceptable? (2) If we discover a genuinely new provision inside a law that's already on the list, does that provision count as NEW or KNOWN? Since NEW carries most of the points, we want to get this exactly right.

**6.5 — How exactly do you measure CER, and against what?**
We can now measure Character Error Rate on our side, but to match your bar we need to know your method: do you compare our text to a reference you hold, or to the source PDF? Is it measured per provision or per whole document? And does the 5% limit apply to every PDF, or only to scanned/image PDFs?

**6.6 — Law Number: how important, and is there a clean source?**
For laws the tool finds itself, we reliably get the title but rarely the official law number; parsing it from the first page is inconsistent across countries. How heavily is this field weighted, and is there a clean source (e.g. portal metadata) you expect us to use?

**6.7 — Is using a web search engine to locate the law accepted as "autonomous crawling"?**
The three portals are hard to crawl directly (Singapore blocks bots; Malaysia loads results with JavaScript). Your slides describe the human workflow as searching "official databases, government websites, and the web", so we search for the correct law URL on the official portal and download it from there. Does this count as autonomous discovery, or do you require us to navigate the portal's own menus directly?

**6.8 — Do our confidence numbers matter to you, or are they just for us?**
We set our own thresholds (auto-accept at 0.85, flag for review below 0.60) and our own confidence formula. Is there a calibration you expect, or is confidence purely an internal triage signal that helps us flag rows for review?

**6.9 — What happens if a portal changes or is down during judging?**
The tool fetches live at run time, and real portals occasionally change URLs or go offline. If a portal is unreachable when you grade us, how is that handled — may we keep a cached snapshot to fall back on?

**6.10 — Which exact indicator code do you want in the file — "P6-I4" or "6.4"?**
We write "P6-I4"; your Methodology and examples write "6.4". They're the same by number, but we want to print exactly the string you validate against.

**6.11 — Per run, one pillar at a time, or both Pillars 6 and 7 together?**
We've confirmed the input is (country + pillar). Just to be sure on packaging: when you test a country, do you run each pillar separately, or expect a single output file covering both pillars?

---

## 7. Infrastructure note (self-hosted model)

A 4× Tesla V100 GPU server is being brought into production. Because our LLM layer is already abstracted, this needs **no code changes**: the box runs an OpenAI-compatible model server, and we point one config line at it. The payoff is large — it lets us run the indicator mapping on a strong open-weight model that is **free, private, and unlimited** (no Gemini quota), which is exactly the model we want for the 40-point substantive-accuracy step. It also speeds up the embedding/re-ranking and OCR by moving them onto the GPU, and it makes the cost story clean: self-hosted on owned hardware is effectively $0 per document.

---

## 8. What we're proudest of

1. **It isn't fooled by law titles.** The judges warned that keyword-matching on a law's name promotes irrelevant laws. We rank on the actual provision text and add a second AI reviewer, which avoids exactly that failure.
2. **It doesn't confuse or drop indicators.** RDTII's indicators are easy to mix up. Our prompt separates "does this provision satisfy the target indicator?" from "is a neighbouring indicator a better fit?" — so it neither mislabels nor silently drops a provision that matches more than one.
3. **It's self-reliant and cheap.** LLM and OCR are swappable, and the whole thing can run on a self-hosted model — meeting both the "no vendor lock-in" and the cost/sustainability criteria.
