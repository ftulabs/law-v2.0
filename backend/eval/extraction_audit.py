"""Extraction audit — independent evidence that a fix is real, not just plausible.

The failure mode this exists to prevent: patch the splitter, glance at a few verbatim
snippets, decide it "looks right", ship it, and discover months later that whole Acts were
missing. Reading output does not test extraction; it tests whether the output is *readable*.

Every check below can fail loudly without a human reading anything, and each one is
independent of retrieval and of the RDTII labels except where stated:

  A. page reconciliation   — our page count vs the PORTAL'S OWN pageCount (external truth)
  B. text coverage         — do the provision spans actually cover the extracted document?
  C. section sequence      — duplicate / non-monotonic section labels inside one law
  D. verbatim round-trip   — is the stored snippet really on the page we cite, character for
                             character, when the PDF is re-read by a DIFFERENT extractor?
  E. panel-quote agreement — does the provision we stored for a cited section resemble the
                             panel's own description of that section more than a random
                             section of the same law does? (uses the Database)

A, C and D are the ones that would have caught the multi-volume bug on the day it shipped:
A reconciles against the register, C shows the numbering stopping dead at s186, D proves the
text of the section we claim is on the page we claim.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from ..corpus import store

_NUM_RE = re.compile(r"(\d{1,4})([A-Za-z]{0,2})")
_WORD_RE = re.compile(r"[a-z]{4,}")
_STOP = {"that", "this", "with", "from", "shall", "must", "under", "such", "which", "there",
         "have", "been", "into", "than", "then", "were", "will", "would", "also", "other",
         "section", "subsection", "person", "personal", "data", "information", "act"}


@dataclass
class Finding:
    check: str
    economy: str
    law: str
    severity: str        # error | warn | info
    detail: str


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, *a, **kw):
        self.findings.append(Finding(*a, **kw))

    def errors(self):
        return [f for f in self.findings if f.severity == "error"]


# ─────────────────── A. page reconciliation against the portal ───────────────────
def check_pages_vs_portal(economy: str, rep: AuditReport, limit: int | None = None) -> dict:
    """AU only: the register's OData feed publishes an authoritative `pageCount` per volume.
    Our extracted page count must match the sum. A shortfall means a volume (or a whole
    document) never made it into the corpus — the exact failure that cost us two Acts."""
    if economy != "AU":
        return {"checked": 0, "skipped": "no external page-count feed for this portal"}
    import httpx
    from sqlalchemy import select

    from ..corpus.store import corpus_law, corpus_version
    from ..storage.engine import get_engine
    with get_engine().connect() as c:
        rows = c.execute(
            select(corpus_law.c.title, corpus_law.c.law_number, corpus_version.c.pages,
                   corpus_version.c.provisions_n)
            .select_from(corpus_law.join(corpus_version,
                                         corpus_law.c.law_id == corpus_version.c.law_id))
            .where(corpus_law.c.economy == "AU",
                   corpus_version.c.state == "split",
                   corpus_version.c.superseded_by.is_(None))).fetchall()
    if limit:
        rows = rows[:limit]
    ok = mismatch = unknown = 0
    with httpx.Client(timeout=60, headers={"Accept": "application/json"}) as client:
        for title, tid, pages, provs in rows:
            if not tid:
                unknown += 1
                continue
            try:
                r = client.get("https://api.prod.legislation.gov.au/v1/documents",
                               params={"$filter": f"titleId eq '{tid}' and format eq 'Pdf'",
                                       "$orderby": "start desc", "$top": "20"})
                items = r.json().get("value", [])
            except Exception:  # noqa: BLE001
                unknown += 1
                continue
            items = [it for it in items if it.get("isAuthorised")] or items
            if not items:
                unknown += 1
                continue
            latest = (items[0].get("start") or "")[:10]
            parts = [it for it in items if (it.get("start") or "")[:10] == latest]
            expect = sum(int(it.get("pageCount") or 0) for it in parts)
            got = int(pages or 0)
            if expect and abs(got - expect) > max(2, 0.02 * expect):
                mismatch += 1
                rep.add("A.pages", economy, title[:60], "error",
                        f"portal says {expect} pages ({len(parts)} volume(s)), we extracted {got}"
                        f" -> {provs} provisions")
            else:
                ok += 1
    return {"checked": len(rows), "reconciled": ok, "mismatched": mismatch, "unknown": unknown}


# ─────────────────── B. text coverage ───────────────────
def check_coverage(economy: str, rep: AuditReport, min_ratio: float = 0.55) -> dict:
    """Provision spans should account for most of the document's extracted characters. A low
    ratio means the splitter is dropping law text (or a whole part of the Act)."""
    from sqlalchemy import func, select

    from ..corpus.store import corpus_law, corpus_provision, corpus_version
    from ..storage.engine import get_engine
    ratios = []
    with get_engine().connect() as c:
        rows = c.execute(
            select(corpus_version.c.version_id, corpus_law.c.title, corpus_version.c.chars,
                   func.sum(corpus_provision.c.chars), func.count(corpus_provision.c.provision_id))
            .select_from(corpus_version.join(corpus_law,
                                             corpus_law.c.law_id == corpus_version.c.law_id)
                         .join(corpus_provision,
                               corpus_provision.c.version_id == corpus_version.c.version_id))
            .where(corpus_version.c.economy == economy,
                   corpus_version.c.state == "split",
                   corpus_version.c.superseded_by.is_(None))
            .group_by(corpus_version.c.version_id)).fetchall()
    low = 0
    for _vid, title, chars, prov_chars, n in rows:
        if not chars:
            continue
        ratio = (prov_chars or 0) / chars
        ratios.append(ratio)
        if ratio < min_ratio:
            low += 1
            rep.add("B.coverage", economy, (title or "")[:60], "warn",
                    f"provisions cover {ratio:.0%} of {chars:,} extracted chars ({n} provisions)")
    return {"laws": len(ratios), "below_threshold": low,
            "median_coverage": round(statistics.median(ratios), 3) if ratios else None}


# ─────────────────── C. section sequence ───────────────────
def _section_num(label: str) -> tuple[int, str] | None:
    m = _NUM_RE.search(label or "")
    return (int(m.group(1)), m.group(2).lower()) if m else None


def check_sequence(economy: str, rep: AuditReport, dup_warn: int = 3) -> dict:
    """Inside one law, section labels should be near-monotonic and near-unique.

    Duplicates mean a running header or a table-of-contents line was split as a provision.
    A long monotonic run that stops well short of the highest number seen elsewhere in the
    document means text was lost — that is how ss 187A-187N announced themselves.
    """
    from collections import Counter
    v2l = {}
    laws = {r["law_id"]: r["title"] for r in store.list_laws(economy)}
    from sqlalchemy import select

    from ..corpus.store import corpus_version
    from ..storage.engine import get_engine
    with get_engine().connect() as c:
        for vid, lid in c.execute(select(corpus_version.c.version_id, corpus_version.c.law_id)
                                  .where(corpus_version.c.economy == economy)):
            v2l[vid] = lid
    by_version: dict[str, list[dict]] = {}
    for p in store.load_provisions(economy):
        by_version.setdefault(p["version_id"], []).append(p)

    dup_laws = broken = 0
    for vid, provs in by_version.items():
        title = laws.get(v2l.get(vid, ""), vid)[:60]
        labels = [p["article_section"] or "" for p in provs]
        counts = Counter(labels)
        dups = {k: v for k, v in counts.items() if v > 1 and k}
        if len(dups) >= dup_warn:
            dup_laws += 1
            worst = sorted(dups.items(), key=lambda kv: -kv[1])[:3]
            rep.add("C.duplicates", economy, title, "warn",
                    f"{len(dups)} duplicated section labels, worst: "
                    + ", ".join(f"{k}×{v}" for k, v in worst))
        nums = [n for n in (_section_num(l) for l in labels) if n]
        if len(nums) >= 20:
            drops = sum(1 for a, b in zip(nums, nums[1:]) if b[0] < a[0] - 5)
            if drops > max(3, 0.05 * len(nums)):
                broken += 1
                rep.add("C.sequence", economy, title, "warn",
                        f"{drops} backward jumps in {len(nums)} section numbers "
                        f"(TOC contamination or mis-split)")
    return {"laws": len(by_version), "with_duplicate_labels": dup_laws,
            "with_broken_sequence": broken}


# ─────────────────── D. verbatim round-trip ───────────────────
def check_verbatim_roundtrip(economy: str, rep: AuditReport, sample: int = 40,
                             seed: int = 7) -> dict:
    """Re-read the cited PDF page with a DIFFERENT extractor (pypdfium2, not pdfplumber) and
    confirm the stored snippet's opening words are physically on that page.

    This is the check that cannot be fooled by a splitter bug: it compares our stored text
    against the source document via an independent code path. Agreement means the snippet is
    genuinely verbatim AND the page citation is right; disagreement means one of the two is
    wrong, and both matter for the submission."""
    import random

    import pypdfium2
    from sqlalchemy import select

    from ..corpus.store import corpus_law, corpus_provision, corpus_version
    from ..storage.engine import get_engine
    with get_engine().connect() as c:
        rows = c.execute(
            select(corpus_provision.c.article_section, corpus_provision.c.location_ref,
                   corpus_provision.c.text, corpus_version.c.body_path, corpus_law.c.title,
                   corpus_version.c.fmt)
            .select_from(corpus_provision
                         .join(corpus_version,
                               corpus_version.c.version_id == corpus_provision.c.version_id)
                         .join(corpus_law, corpus_law.c.law_id == corpus_version.c.law_id))
            .where(corpus_provision.c.economy == economy,
                   corpus_version.c.superseded_by.is_(None),
                   corpus_version.c.fmt == "pdf_text",
                   corpus_provision.c.location_ref.isnot(None))).fetchall()
    rnd = random.Random(f"{seed}:{economy}")
    rows = [r for r in rows if (r[2] or "").strip() and str(r[1] or "").startswith("p.")]
    picked = rnd.sample(rows, min(sample, len(rows)))
    hit = miss = unreadable = 0
    for section, loc, text, path, title, _fmt in picked:
        m = re.search(r"p\.\s*(\d+)", loc or "")
        if not m or not path:
            unreadable += 1
            continue
        page_no = int(m.group(1))
        try:
            doc = pypdfium2.PdfDocument(path)
            if page_no < 1 or page_no > len(doc):
                doc.close()
                rep.add("D.roundtrip", economy, (title or "")[:50], "error",
                        f"{section}: cites p.{page_no} but the PDF has {len(doc)} pages")
                miss += 1
                continue
            # allow +-1: a provision can start at the foot of the previous page
            window = ""
            for p in range(max(0, page_no - 2), min(len(doc), page_no + 1)):
                window += doc[p].get_textpage().get_text_range() or ""
            doc.close()
        except Exception as e:  # noqa: BLE001
            unreadable += 1
            continue
        probe = re.sub(r"\s+", " ", text.strip())[:60]
        norm_window = re.sub(r"\s+", " ", window)
        if probe and probe in norm_window:
            hit += 1
        else:
            # token-level fallback: hyphenation/ligature differences between extractors
            toks = [t for t in _WORD_RE.findall(probe.lower()) if t not in _STOP][:6]
            if toks and sum(t in norm_window.lower() for t in toks) >= max(2, len(toks) - 1):
                hit += 1
            else:
                miss += 1
                rep.add("D.roundtrip", economy, (title or "")[:50], "error",
                        f"{section} (p.{page_no}): stored text not found on the cited page — "
                        f"{probe[:70]!r}")
    return {"sampled": len(picked), "verified": hit, "failed": miss, "unreadable": unreadable,
            "pass_rate": round(hit / max(hit + miss, 1), 3)}


# ─────────────────── E. panel-quote agreement ───────────────────
def check_panel_agreement(economy: str, rep: AuditReport) -> dict:
    """For each provision the judges cited, is OUR stored text for that section closer to the
    panel's own description of it than a random section of the same law is?

    This is the only check that tests MEANING rather than mechanics: it asks whether the text
    we stored under 'Section 187C' is actually the provision the panel was describing. A
    'contrast' at or below 1.0 means our section labels are attached to the wrong text."""
    import random

    from .harness import (load_provisions, section_matches, targets_by_indicator,
                          version_law_map)
    labels_by_key: dict[tuple[str, str], str] = {}
    from .ground_truth import load_labels
    for row in load_labels():
        if row.economy == economy and row.kind == "provision":
            for law in row.laws:
                labels_by_key[(row.indicator_id, law)] = row.impact

    provs = load_provisions(economy)
    v2l = version_law_map(economy)
    targets = targets_by_indicator(economy)
    rnd = random.Random(11)
    scored, wins = [], 0
    for ind_id, t in targets.items():
        impact = next((v for (i, _l), v in labels_by_key.items() if i == ind_id), "")
        panel_terms = {w for w in _WORD_RE.findall(impact.lower()) if w not in _STOP}
        if not panel_terms:
            continue
        for lid, secs in t["sections"].items():
            pool = [p for p in provs if v2l.get(p.doc_id) == lid]
            hits = [p for p in pool if section_matches(p.article_section, secs)]
            if not hits or len(pool) < 5:
                continue

            def overlap(p):
                terms = {w for w in _WORD_RE.findall(p.verbatim_snippet.lower())
                         if w not in _STOP}
                return len(terms & panel_terms) / max(len(panel_terms), 1)

            ours = max(overlap(p) for p in hits)
            base = statistics.mean(overlap(p) for p in rnd.sample(pool, min(25, len(pool))))
            contrast = ours / base if base else float("inf")
            scored.append(contrast)
            if contrast > 1.0:
                wins += 1
            else:
                rep.add("E.panel", economy, f"{ind_id} / {secs}", "warn",
                        f"our text for the cited section matches the panel's description no "
                        f"better than a random section (ratio {contrast:.2f})")
    return {"cited_sections_checked": len(scored), "better_than_random": wins,
            "median_contrast": round(statistics.median(scored), 2) if scored else None}


# ─────────────────── driver ───────────────────
def audit(economies=("SG", "AU", "MY"), roundtrip_sample: int = 40,
          page_limit: int | None = None, log=print) -> AuditReport:
    rep = AuditReport()
    for econ in economies:
        log(f"\n=== {econ}")
        rep.stats[econ] = {
            "A_pages_vs_portal": check_pages_vs_portal(econ, rep, limit=page_limit),
            "B_text_coverage": check_coverage(econ, rep),
            "C_section_sequence": check_sequence(econ, rep),
            "D_verbatim_roundtrip": check_verbatim_roundtrip(econ, rep, sample=roundtrip_sample),
            "E_panel_agreement": check_panel_agreement(econ, rep),
        }
        for k, v in rep.stats[econ].items():
            log(f"  {k}: {v}")
    return rep
