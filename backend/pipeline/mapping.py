"""ZONE 2d — provision → RDTII indicator mapping (retrieval-grounded).

For each indicator we retrieve candidate provisions, then ask the LLM to grade
ONLY what it was given (verbatim snippet + the indicator's legal test), forbidding
any conclusion not supported by the snippet. The model returns structured signals;
we never let it invent law text, article numbers, or URLs — those are carried from
extraction, not generation. That separation is the core anti-hallucination control.
"""
from __future__ import annotations

import hashlib
import math

from ..config import settings
from ..providers import get_llm_provider
from ..providers.llm_base import LLMProvider
from ..rdtii import get_indicator, siblings
from ..schemas import DiscoveryTag, EvidenceMapping, Provision
from . import confidence
from .retrieval import Retrieved, retrieve


def _select_retriever(indicators, provisions, top_k, llm, log):
    """Decide the Zone-2 retriever. Returns a precomputed {indicator_id: [Retrieved]}
    dict when LightRAG should drive retrieval, else None → the caller uses the per-indicator
    hybrid retriever. Honours settings.retriever (auto|hybrid|lightrag).

    auto = LightRAG when it is installed, a real (non-mock) indexing LLM + key are available,
    and the corpus is large enough to benefit (live-crawl scale, >= lightrag_min_provisions);
    else the built-in hybrid retriever. hybrid = always hybrid. lightrag = force LightRAG on
    every run (any corpus size) — handy for a demo. With a funded/local LLM the KG build is
    reliable; on a starved free key retrieve_all degrades to hybrid on ANY failure (never
    crashes), so enabling it is always safe."""
    mode = (settings.retriever or "auto").lower()
    if mode == "hybrid":
        return None
    from . import retrieval_lightrag
    has_key = bool(settings.openrouter_api_key or settings.openai_api_key or settings.gemini_api_key)
    base_ok = (retrieval_lightrag.available() and has_key
               and getattr(llm, "name", "mock") != "mock" and provisions)
    if not base_ok:
        return None
    if mode == "auto" and len(provisions) < settings.lightrag_min_provisions:
        # small corpus → grade-all on the hybrid path already covers everything; skip KG cost
        return None
    log(f"[retrieval] using LightRAG graph-RAG ({len(provisions)} provisions)")
    return retrieval_lightrag.retrieve_all(indicators, provisions, top_k=top_k, llm=llm, log=log)

SYSTEM = (
    "You are a legal-evidence grader for the UNESCAP RDTII 2.1 framework (Pillar 6 = "
    "cross-border data; Pillar 7 = domestic data protection). Decide whether ONE provision "
    "satisfies ONE TARGET indicator. The sibling indicators are close, so two errors are "
    "equally bad: OVER-ASSIGN (the snippet only MENTIONS the topic) and MISS (its operative "
    "rule DOES satisfy the target but you reject it because it also touches a neighbour).\n\n"
    "Steps:\n"
    "1. OPERATIVE RULE — one sentence: what binding rule does the snippet enact? Ignore "
    "definitions/recitals. It may enact several rules (a restriction AND an exception); note each.\n"
    "2. TARGET TEST — check the rule(s) against the TARGET's legal_test, OBEYING its "
    "'Distinguish from…' notes. satisfies_target=true ONLY for operative effect, not topical "
    "overlap or a bare definition.\n"
    "3. BETTER SIBLING — set better_sibling to a sibling id ONLY if NO rule satisfies the target "
    "AND a sibling clearly fits (the target is a mislabel). If the target is satisfied even "
    "partially, leave it null — one provision may map to several indicators.\n"
    "4. relevant = satisfies_target AND better_sibling is null.\n"
    "5. legal_match (0..1): 1.0 = rule IS exactly this test; 0.7 = satisfies, minor wording gap; "
    "0.5 = one element of a multi-part test; <=0.3 = mention only (then satisfies_target=false).\n"
    "6. SCOPE — sector-specific instrument (financial/telecom/health) vs a national indicator: "
    "scope_flag='SECTORAL_NOT_NATIONAL', lower scope_alignment. Measures applying ONLY to "
    "GOVERNMENT data do NOT satisfy (RDTII excludes them).\n"
    "CONSERVATIVE DEFAULT: judge only the snippet; if you are unsure the rule truly meets the "
    "test, set satisfies_target=false (a precise MISS beats a wrong OVER-ASSIGN).\n"
    "rationale <=300 chars, EXACT format: 'This [section] [prohibits/requires/permits/"
    "establishes] [what]. Maps to [indicator] because [one-sentence legal logic].'\n\n"
    "Return ONLY this JSON: {operative_rule:str, satisfies_target:bool, better_sibling:str|null, "
    "relevant:bool, legal_match:0..1, scope_alignment:0..1, scope_flag:str|null, rationale:str}\n\n"
    "WORKED EXAMPLES (real RDTII items with verified answers — TARGET :: SNIPPET → JSON):\n"
    # 1 — Armenia, Law on Protection of Personal Data 2015, Art.27 → 6.4 (NOT a ban)
    "P6-I4 :: 'Personal data may be transferred to other country by the data subject's consent... "
    "may be transferred to other state without the permission of the authorised body, where the "
    "given State ensures an adequate level of protection of personal data.' → {\"operative_rule\":"
    "\"Permits cross-border transfer on the data subject's consent or where the destination state "
    "ensures adequate protection\",\"satisfies_target\":true,\"better_sibling\":null,\"relevant\":"
    "true,\"legal_match\":0.95,\"scope_alignment\":1.0,\"scope_flag\":null,\"rationale\":\"This "
    "Article permits cross-border transfer on consent or destination adequacy. Maps to P6-I4 "
    "because transfer stays possible once a condition is met — conditional flow, not a ban (P6-I1).\"}\n"
    # 2 — Kazakhstan, Law No.94-V 2013, Art.12(2) → 6.2 local storage
    "P6-I2 :: 'Personal data shall be stored by the owner and/or operator, as well as by a third "
    "party in a database located in the territory of the Republic of Kazakhstan.' → {\"operative_"
    "rule\":\"Requires personal data to be stored in a database located in Kazakhstan\",\"satisfies"
    "_target\":true,\"better_sibling\":null,\"relevant\":true,\"legal_match\":0.95,\"scope_"
    "alignment\":1.0,\"scope_flag\":null,\"rationale\":\"This Article requires personal data to be "
    "stored in a domestic database. Maps to P6-I2 because it is a local-storage obligation, not "
    "mandated local servers/infrastructure (P6-I3).\"}\n"
    # 3 — China, ride-hailing rules, Art.5 → 6.3 infrastructure
    "P6-I3 :: 'Any applicant... shall... ensure that the database of the network service platform "
    "is connected to the regulatory platform..., locate its servers within the territory of "
    "Mainland China; and maintain network security management systems.' → {\"operative_rule\":"
    "\"Requires ride-hailing operators to locate their servers within Mainland China to operate\","
    "\"satisfies_target\":true,\"better_sibling\":null,\"relevant\":true,\"legal_match\":0.9,"
    "\"scope_alignment\":1.0,\"scope_flag\":null,\"rationale\":\"This Article requires operators to "
    "site servers domestically. Maps to P6-I3 because mandating local physical infrastructure goes "
    "beyond where data is stored (P6-I2).\"}\n"
    # 4 — Bhutan, Code of Practice for Info Security/Cybersecurity 2024 → 7.2 cybersecurity
    "P7-I2 :: 'For remote access, the licensee must ensure connections have strong encryption...; "
    "develop a policy on cryptographic controls...; restrict data flow to one-way... to mitigate "
    "cybersecurity risks.' → {\"operative_rule\":\"Requires strong encryption, cryptographic "
    "controls and network-security measures to mitigate cybersecurity risks\",\"satisfies_target\":"
    "true,\"better_sibling\":null,\"relevant\":true,\"legal_match\":0.9,\"scope_alignment\":1.0,"
    "\"scope_flag\":null,\"rationale\":\"These Sections require encryption, cryptographic controls "
    "and network-security duties. Maps to P7-I2 because these are cybersecurity obligations, not "
    "personal-data protection (P7-I1).\"}\n"
    # 5 — Singapore, Criminal Procedure Code 2010, s39 → 7.5 government access
    "P7-I5 :: 'A police officer or an authorised person investigating an arrestable offence may... "
    "access, inspect and check the operation of a computer... to search any data contained... and "
    "to make a copy of any such data.' → {\"operative_rule\":\"Empowers police to access, search "
    "and copy data on a computer when investigating an arrestable offence\",\"satisfies_target\":"
    "true,\"better_sibling\":null,\"relevant\":true,\"legal_match\":0.9,\"scope_alignment\":1.0,"
    "\"scope_flag\":null,\"rationale\":\"This Section gives police power to access, search and copy "
    "data for law-enforcement. Maps to P7-I5 because it enables government access to data, not a "
    "cybersecurity duty on private entities (P7-I2).\"}\n"
    # 6 — India, Digital Personal Data Protection Act 2023, s10 → 7.4 DPO/DPIA
    "P7-I4 :: 'The Significant Data Fiduciary shall (a) appoint a Data Protection Officer...; (b) "
    "appoint an independent data auditor...; (c) undertake... Data Protection Impact Assessment.' "
    "→ {\"operative_rule\":\"Requires a Significant Data Fiduciary to appoint a DPO and data "
    "auditor and conduct a DPIA\",\"satisfies_target\":true,\"better_sibling\":null,\"relevant\":"
    "true,\"legal_match\":0.95,\"scope_alignment\":1.0,\"scope_flag\":null,\"rationale\":\"This "
    "Section requires appointing a DPO and conducting a DPIA. Maps to P7-I4 because it imposes the "
    "DPO/DPIA accountability duties, distinct from the general framework (P7-I1).\"}"
)


def _diverse_shortlist(indicator_id, provisions, global_k, per_law_k, log):
    """Per-indicator candidate shortlist that no single verbose law can monopolise.

    Union of (a) the GLOBAL top-`global_k` provisions for the indicator and (b) each law's
    OWN top-`per_law_k` — so a short, on-point Act is graded even when a 485-section Act
    would otherwise fill the global top-k. Each provision keeps its best retrieval score."""
    from collections import defaultdict
    chosen: dict[str, Retrieved] = {}
    for r in retrieve(indicator_id, provisions, top_k=global_k):
        chosen[r.provision.provision_id] = r
    if per_law_k > 0:
        by_law: dict[str, list] = defaultdict(list)
        for p in provisions:
            by_law[p.doc_id].append(p)
        if len(by_law) > 1:                       # diversity only matters across multiple laws
            for law_provs in by_law.values():
                k = min(per_law_k, len(law_provs))
                for r in retrieve(indicator_id, law_provs, top_k=k):
                    prev = chosen.get(r.provision.provision_id)
                    if prev is None or r.score > prev.score:
                        chosen[r.provision.provision_id] = r
    out = sorted(chosen.values(), key=lambda r: r.score, reverse=True)
    laws = len({r.provision.law_name for r in out})
    top = out[0] if out else None
    log(f"[retrieve] {indicator_id}: {len(out)} candidates from {laws} law(s)"
        + (f" — best: {top.provision.law_name[:28]} {top.provision.article_section} ({round(top.score,2)})" if top else ""))
    return out


def _siblings_block(ind) -> str:
    # Format kept mock-parseable (id :: title — desc :: terms :: legal_test): the offline
    # grader reads field [2] (terms); a real LLM also gets each sibling's legal_test [3] to
    # distinguish it from the target.
    lines = []
    for s in siblings(ind.indicator_id):
        terms = " | ".join(s.query_terms[:4])
        lines.append(f"{s.indicator_id} :: {s.title} — {s.description} :: {terms} :: {s.legal_test}")
    return "\n".join(lines)


def _user_prompt(ind, prov: Provision) -> str:
    return (
        f"<TARGET_INDICATOR>{ind.indicator_id} — {ind.title}</TARGET_INDICATOR>\n"
        f"<INDICATOR_QUESTION>{ind.description}</INDICATOR_QUESTION>\n"
        f"<INDICATOR_SCOPE>{ind.scope}</INDICATOR_SCOPE>\n"
        f"<LEGAL_TEST>{ind.legal_test}</LEGAL_TEST>\n"
        f"<QUERY_TERMS>{' | '.join(ind.query_terms)}</QUERY_TERMS>\n"
        f"<SIBLINGS>\n{_siblings_block(ind)}\n</SIBLINGS>\n"
        f"<LAW>{prov.law_name} — {prov.article_section}</LAW>\n"
        f"<SNIPPET>{prov.verbatim_snippet}</SNIPPET>\n"
        "Follow steps (1)-(8). Decide independently whether THIS provision satisfies the "
        "TARGET; only reject for a better sibling if the target is a genuine mislabel. "
        "Return the JSON object only."
    )


def _build_notes(prov: Provision, scope_flag: str | None) -> str | None:
    """Template 'Notes' — flag unusual cases: scope, OCR quality, etc."""
    parts = []
    if scope_flag:
        parts.append(f"{scope_flag}: sectoral instrument — verify before treating as national.")
    if prov.ocr.used:
        mc = prov.ocr.mean_confidence
        if prov.ocr.provider == "markitdown":
            parts.append("Text extracted from PDF via MarkItDown; verify wording vs source.")
        else:
            parts.append(f"OCR-extracted via {prov.ocr.provider}"
                         + (f" (mean conf {mc:.2f})" if mc is not None else "") + "; verify wording vs source.")
    return " ".join(parts) or None


def _mapping_id(run_id: str, indicator_id: str, provision_id: str) -> str:
    h = hashlib.sha1(f"{run_id}|{indicator_id}|{provision_id}".encode()).hexdigest()[:12]
    return f"map-{h}"


def map_provisions(
    run_id: str,
    provisions: list[Provision],
    pillar: int | None,
    indicators,
    source_texts: dict[str, str] | None = None,
    doc_tags: dict[str, DiscoveryTag] | None = None,
    llm: LLMProvider | None = None,
    top_k: int = 5,
    min_retrieval: float = 0.05,
    log=lambda *_: None,
) -> list[EvidenceMapping]:
    llm = llm or get_llm_provider()
    source_texts = source_texts or {}
    doc_tags = doc_tags or {}
    mappings: list[EvidenceMapping] = []
    failures = 0

    # retrieval backend: LightRAG graph-RAG at scale, else built-in hybrid (citations
    # preserved either way — the grader below still judges the verbatim snippet).
    ranked_by_ind = _select_retriever(indicators, provisions, top_k, llm, log)

    # Coverage policy. A small corpus (a sample run, a single Act) → grade EVERY provision
    # against EVERY indicator so nothing relevant is missed: the rubric rewards coverage and
    # one provision may legitimately satisfy several indicators. A large corpus (full live
    # crawl) → a retrieval shortlist whose size SCALES with the corpus (retrieve_fraction of
    # the provisions, floor retrieve_top_k) instead of a fixed cap, so long Acts aren't
    # under-covered yet the run stays tractable.
    n = len(provisions)
    grade_all = ranked_by_ind is None and n <= settings.grade_all_max_provisions
    eff_top_k = top_k
    if ranked_by_ind is None and not grade_all:
        # recall-safe shortlist: scale gently with the corpus but clamp to [floor, cap] so a
        # 1200-provision crawl grades ~40/indicator (not 360) — the rerank already front-loads
        # the relevant provisions, so a bigger shortlist only adds latency + cost, not recall.
        eff_top_k = min(n, settings.retrieve_max_top_k,
                        max(top_k, settings.retrieve_top_k, math.ceil(n * settings.retrieve_fraction)))
    if ranked_by_ind is None:
        log(f"[mapping] {'grade-all: every' if grade_all else f'retrieval shortlist top_k={eff_top_k} of'} "
            f"{n} provisions x {len(indicators)} indicators")

    # ── build the (indicator, retrieved-provision) work list ──────────────────────────────
    work: list[tuple] = []
    for ind in indicators:
        # LightRAG candidates when available, else (or when it returned nothing for this
        # indicator — e.g. the KG build was rate-limited) fall back to the hybrid retriever
        # so a retrieval-backend hiccup never silently drops an indicator's mappings.
        candidates = ranked_by_ind.get(ind.indicator_id) if ranked_by_ind is not None else None
        if not candidates:
            if grade_all:
                # every provision is a candidate; keep its real retrieval score (so confidence
                # stays meaningful) where the retriever surfaced it, default 0 for the rest —
                # but grade them ALL rather than dropping any below a top-k or score floor.
                scored = {r.provision.provision_id: r
                          for r in retrieve(ind.indicator_id, provisions, top_k=n)}
                candidates = [scored.get(p.provision_id)
                              or Retrieved(provision=p, score=0.0, raw_context=p.verbatim_snippet, log=[])
                              for p in provisions]
            else:
                candidates = _diverse_shortlist(ind.indicator_id, provisions, eff_top_k,
                                                settings.retrieve_per_law_k, log)
        for r in candidates:
            if grade_all or r.score >= min_retrieval:
                work.append((ind, r))

    # ── grade each pairing (one independent LLM call) concurrently ────────────────────────
    def _grade(item):
        ind, r = item
        prov = r.provision
        try:
            graded = llm.complete_json(SYSTEM, _user_prompt(ind, prov))
        except Exception as e:  # noqa: BLE001 — one rate-limited call must not crash the run
            return ("FAIL", type(e).__name__, ind.indicator_id, prov.provision_id)

        # relevant = satisfies the target AND not a mislabel for a better sibling. Prefer the
        # model's explicit `relevant`; else derive it (real LLMs return satisfies_target/
        # better_sibling; the offline mock returns `relevant` directly).
        relevant = graded.get("relevant")
        if relevant is None:
            relevant = bool(graded.get("satisfies_target")) and not graded.get("better_sibling")
        if not relevant:
            return None

        legal_match = float(graded.get("legal_match", 0.0) or 0.0)
        scope_alignment = float(graded.get("scope_alignment", 0.0) or 0.0)
        scope_flag = graded.get("scope_flag") or None
        rationale = graded.get("rationale", "")

        src_text = source_texts.get(prov.doc_id, prov.verbatim_snippet)
        grounding = confidence.snippet_grounding(prov.verbatim_snippet, src_text)
        ctx_before, ctx_after = "", ""
        if prov.char_span and src_text:
            s0, s1 = prov.char_span
            ctx_before = src_text[max(0, s0 - 300):s0]
            ctx_after = src_text[s1:s1 + 300]
        breakdown = confidence.score(
            retrieval_score=r.score, legal_match=legal_match, grounding=grounding,
            scope_alignment=scope_alignment, scope_flag=scope_flag,
        )
        return EvidenceMapping(
            mapping_id=_mapping_id(run_id, ind.indicator_id, prov.provision_id),
            run_id=run_id, economy=prov.economy, pillar=ind.pillar, indicator_id=ind.indicator_id,
            law_name=prov.law_name, law_number=prov.law_number,
            last_amended=(prov.amendment_date or "")[:4] or None,
            article_section=prov.article_section, location_ref=prov.location_ref,
            verbatim_snippet=prov.verbatim_snippet, source_url=prov.source_url,
            mapping_rationale=(rationale or "")[:300], confidence_score=breakdown.final,
            discovery_tag=doc_tags.get(prov.doc_id, DiscoveryTag.KNOWN),
            coverage=("Sectoral" if scope_flag else "Horizontal"),
            notes=_build_notes(prov, scope_flag), review_status=confidence.route(breakdown.final),
            provision_id=prov.provision_id, source_pdf_path=prov.source_pdf_path,
            raw_context=r.raw_context, raw_context_before=ctx_before, raw_context_after=ctx_after,
            confidence=breakdown, ocr=prov.ocr, model_version=llm.model_version,
            retrieval_log=r.log, scope_flag=scope_flag,
        )

    workers = max(1, min(settings.mapping_concurrency, len(work) or 1))
    if workers > 1 and work:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_grade, work))
    else:
        results = [_grade(it) for it in work]

    for res in results:
        if res is None:
            continue
        if isinstance(res, tuple):  # ("FAIL", err, ind, prov)
            failures += 1
            if failures <= 3:
                log(f"[warn] LLM call failed ({res[1]}); skipping {res[2]}/{res[3]}")
            continue
        mappings.append(res)
    if failures:
        log(f"[warn] {failures} LLM call(s) failed and were skipped "
            f"(free-tier rate limits? try a paid key or fewer pillars)")
    # most confident first
    mappings.sort(key=lambda m: m.confidence_score, reverse=True)
    return mappings
