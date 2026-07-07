# Open questions for the judges (Q&A portal)

Draft questions to post on the ESCAP/KMITL Q&A portal. Kept here so the team can copy them
verbatim. Nothing in this file changes the tool's behaviour.

---

## Q1 — Where should a Zone-3 score be recorded? (the submission template has no score column)

**Context.** The Hackathon Overview lists **Zone 3 — Scoring (Optional → extra points)**, with
output described as *"score 0 / 0.5 / 1 with justification"*. However, the official
`OUTPUT_TEMPLATE_31MAY.xlsx` ("Output Data" sheet) and its **Instructions** sheet define **13
columns** with **no column for a raw score** (Economy, Law Name, Law Number/Ref, Last Amended,
Indicator ID, Article/Section, Discovery Tag, Location Reference, Verbatim Snippet, Mapping
Rationale, Source URL, Confidence, Notes). The Instructions also say *"Do not rename columns.
Column names and order must match this template exactly. Judges validate programmatically."*

**Question.** For a team that implements Zone 3, **where should the 0 / 0.5 / 1 score and its
justification be delivered** so that it is credited without breaking the programmatic validation
of the 13-column submission CSV? Specifically:
1. Should the score go in a **supplementary file** (e.g. a separate scored CSV and/or the JSON),
   and if so is any particular shape expected?
2. Is it acceptable to place the score/justification inside the optional **Notes** column of the
   submission CSV?
3. Or will an **extra column appended after Notes** be tolerated by the validator?

**Our current handling (pending your answer).** To avoid guessing, our tool does **NOT** put the
score anywhere in the official 13-column submission CSV (not even in Notes). The Zone-3 score
(`raw_score` ∈ {0, 0.5, 1}) + a one-line `impact` justification live only in (a) a **separate
`*_scored.csv`** that mirrors the answer-key Database column shape, and (b) the **JSON** export.
The submission CSV remains byte-for-byte on the template. We will move the score into whatever
location you specify.

---

## Q2 — Citation granularity: section vs. subsection (paragraph)

**Context.** Instructions: *"Include article number AND paragraph … Never write just 'Art. 26'"*
(example `s. 16(1)(a)`). Our extractor splits laws at the **section** level, so one output row's
Verbatim Snippet is the whole section (e.g. all of `Section 26 (1)–(5)`), and we cite `Section 26`.

**Question.** When a mapped provision's snippet spans an **entire multi-subsection section**, is
citing the **section** (`Section 26`) correct, or do you require the citation to be narrowed to the
specific **subsection/paragraph** that carries the operative rule (`Section 26(2)`) even though the
snippet covers the whole section? We want to avoid a "low-traceability" deduction while keeping the
citation faithful to the verbatim snippet we actually quote.

---

*(Add more as they arise.)*
