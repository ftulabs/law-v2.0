"""ZONE 2d — provision → RDTII indicator mapping (retrieval-grounded).

For each indicator we retrieve candidate provisions, then ask the LLM to grade
ONLY what it was given (verbatim snippet + the indicator's legal test), forbidding
any conclusion not supported by the snippet. The model returns structured signals;
we never let it invent law text, article numbers, or URLs — those are carried from
extraction, not generation. That separation is the core anti-hallucination control.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time

from ..config import settings
from ..providers import get_llm_provider
from ..providers.llm_base import LLMProvider, LLMTerminalError
from ..rdtii import get_indicator, siblings
from ..schemas import DiscoveryTag, EvidenceMapping, Provision
from . import confidence, retrieval_budget
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
    "partially, leave it null — one provision may map to several indicators. Sibling OVERLAP is "
    "expected and correct for localisation rules: a prohibition on holding/keeping/taking data "
    "outside the country is BOTH a ban (P6-I1) AND a local-storage requirement (P6-I2) — RDTII "
    "scores it under both, so whichever of the two is the target, satisfies_target=true and "
    "better_sibling=null. NEVER use better_sibling to force one-indicator exclusivity.\n"
    "4. relevant = satisfies_target AND better_sibling is null.\n"
    "5. legal_match (0..1): 1.0 = rule IS exactly this test; 0.7 = satisfies, minor wording gap; "
    "0.5 = one element of a multi-part test; <=0.3 = mention only (then satisfies_target=false).\n"
    "6. SCOPE — 'sectoral' means the instrument binds ONLY a narrow regulated sector (e.g. only "
    "licensed banks, telcos, insurers, healthcare providers). Scope matters ONLY for the "
    "comprehensive-framework indicator P7-I1 (a sectoral rule is NOT a general framework): there, "
    "flag scope_flag='SECTORAL_NOT_NATIONAL' and lower scope_alignment. For the LOCALISATION, "
    "storage, retention and government-access indicators a sectoral instrument STILL fully "
    "satisfies the test (e.g. a health-sector law banning records being held abroad is a valid "
    "P6-I1 answer) — keep scope_alignment HIGH and do NOT set scope_flag. A law of GENERAL "
    "application that binds every company, "
    "taxpayer or employer (e.g. a Companies/Corporations Act, Income Tax Act, Employment Act) is "
    "NATIONAL in scope — do NOT flag it sectoral. Note that the storage/retention indicators "
    "(P6-I2 local storage, P7-I3 minimum retention) are satisfied by requirements to keep records "
    "IN-COUNTRY or retain them for a minimum period — including business, accounting, tax and "
    "employment RECORDS — even though those records are not themselves labelled 'personal data'. "
    "Measures applying ONLY to GOVERNMENT data do NOT satisfy (RDTII excludes them).\n"
    "7. CITATION — the snippet may be a whole multi-subsection section. If the operative rule "
    "you relied on sits in ONE identifiable subsection/paragraph, set subsection to its bracketed "
    "citation copied VERBATIM from the snippet (e.g. '(2)' or '(3)(a)'). If it spans the whole "
    "section, several non-contiguous subsections, or the snippet has no subsection numbering, set "
    "subsection to null — never invent a subsection number the snippet doesn't literally show.\n"
    "8. LANGUAGE \n"
    "The snippet is the AUTHORITATIVE statute text and may NOT be in English; its language "
    "is given in <SNIPPET_LANGUAGE>. Read and reason over it AS WRITTEN. Do not translate it "
    "back to us, do not restate it, and never rewrite it into English: the verbatim text is "
    "what gets cited, and a translation would make the citation false. Your OUTPUT is a "
    "different matter — operative_rule and rationale must be written in ENGLISH whatever the "
    "snippet language, because the submission is English. `subsection` is the exception: copy "
    "it character-for-character from the snippet, keeping its own numbering and punctuation "
    "(Chinese drafting uses the full-width forms, not (1)(2)). A provision is judged on what "
    "it ENACTS, never on the language it is in — do not lower legal_match because the text is "
    "not English, and do not raise it because a word happens to resemble an English one.\n"
    "CONSERVATIVE DEFAULT: judge only the snippet; if you are unsure the rule truly meets the "
    "test, set satisfies_target=false (a precise MISS beats a wrong OVER-ASSIGN).\n"
    "rationale <=300 chars, EXACT format: 'This [section] [prohibits/requires/permits/"
    "establishes] [what]. Maps to [indicator] because [one-sentence legal logic].'\n\n"
    "Return ONLY this JSON: {operative_rule:str, satisfies_target:bool, better_sibling:str|null, "
    "relevant:bool, legal_match:0..1, scope_alignment:0..1, scope_flag:str|null, "
    "subsection:str|null, rationale:str}\n\n"
    "WORKED EXAMPLES (real RDTII items with verified answers — TARGET :: SNIPPET → JSON):\n"
    # 0 — China, Personal Information Protection Law art.40 → 6.2 local storage. Placed FIRST,
    # and left in the original Chinese on purpose: it DEMONSTRATES the language rule (reason in
    # Chinese, answer in English) instead of only stating it. The answer is the panel's own —
    # the RDTII Round-2 Database scores PIPL art.40 under 6.2.
    "P6-I2 :: '关键信息基础设施运营者和处理个人信息达到国家网信部门规定数量的个人信息处理者，"
    "应当将在中华人民共和国境内收集和产生的个人信息存储在境内。确需向境外提供的，应当通过国家"
    "网信部门组织的安全评估。' → {\"operative_rule\":\"Requires critical-information-"
    "infrastructure operators and large-scale personal information processors to store "
    "domestically collected personal information inside China, with export permitted only "
    "after a state security assessment\",\"satisfies_target\":true,\"better_sibling\":"
    "null,\"relevant\":true,\"legal_match\":1.0,\"scope_alignment\":1.0,"
    "\"scope_flag\":null,\"subsection\":null,\"rationale\":\"This Article requires "
    "personal information collected in China to be stored within the territory. Maps to P6-I2 "
    "because the operative rule fixes the STORAGE location in-country; the export route it "
    "leaves open is separately a P6-I4 conditional flow.\"}\n"
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
    # 2b — negative phrasing of local storage (ban-worded) → 6.2 STILL true, no better_sibling
    "P6-I2 :: 'The operator of the register must not hold or take the records, or process or "
    "handle information in the records, outside the country.' → {\"operative_rule\":\"Prohibits "
    "holding, taking or processing the records outside the country\",\"satisfies_target\":true,"
    "\"better_sibling\":null,\"relevant\":true,\"legal_match\":0.9,\"scope_alignment\":1.0,"
    "\"scope_flag\":null,\"rationale\":\"This Section prohibits holding or processing the records "
    "outside the country. Maps to P6-I2 because forbidding offshore holding is the same obligation "
    "as requiring in-country storage; it also satisfies P6-I1 but that never displaces this "
    "target.\"}\n"
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
    """Per-indicator candidate shortlist, capped at `global_k`, that no verbose law can
    monopolise. We RESERVE each law's own top-`per_law_k` (round-robin: every law's #1 before
    any law's #2), so a short on-point Act (My Health Records s77) is graded even when a
    485-section Act would fill a pure global top-k; then we fill the rest of the budget with
    the globally-best provisions. Total never exceeds global_k — the per-law guarantee is
    carved OUT of the budget, not added on top (which had ballooned it to ~60/indicator).

    At AU's live-crawl scale (18-26 discovered laws x per_law_k=3 = 54-78 reserved slots)
    the reservation phase alone can exceed global_k=40, so it runs out of budget PARTWAY
    through a rank pass. Bug fixed here: within each rank pass, candidates used to be added
    in dict/declaration order (by_law.values(), i.e. discovery order) — so whichever law's
    #2/#3 pick happened to be enumerated LATE silently lost its reserved slot to an earlier
    law's lower-scoring pick, not because it was less relevant. Confirmed on a live AU P6
    run: My Health Records s77 ranked #2 within its OWN law for P6-I1 (0.455, a solid
    mid-range score) yet never reached the LLM — purely a document-processing-order
    accident. Sort each rank pass by score before spending the remaining budget, so a
    budget-exhausted cutoff is score-fair, not order-dependent."""
    from collections import defaultdict
    chosen: dict[str, Retrieved] = {}

    by_law: dict[str, list] = defaultdict(list)
    for p in provisions:
        by_law[p.doc_id].append(p)

    # 1. reserved per-law slots, round-robin so no law is starved (caps at global_k)
    if per_law_k > 0 and len(by_law) > 1:
        per_law = [retrieve(indicator_id, lp, top_k=min(per_law_k, len(lp))) for lp in by_law.values()]
        depth = max((len(lst) for lst in per_law), default=0)
        for rank in range(depth):
            at_rank = sorted((lst[rank] for lst in per_law if rank < len(lst)),
                             key=lambda r: r.score, reverse=True)
            for r in at_rank:
                if len(chosen) >= global_k:
                    break
                chosen.setdefault(r.provision.provision_id, r)

    # 2. fill the remaining budget with the globally-best provisions
    if len(chosen) < global_k:
        for r in retrieve(indicator_id, provisions, top_k=global_k):
            if len(chosen) >= global_k:
                break
            chosen.setdefault(r.provision.provision_id, r)

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


def _snippet_language(prov: Provision) -> str:
    """The language the LLM should expect, named the way a person would say it."""
    from ..providers.ocr_languages import profile_for
    return profile_for(getattr(prov.economy, "value", prov.economy)).language


def _user_prompt(ind, prov: Provision) -> str:
    return (
        f"<TARGET_INDICATOR>{ind.indicator_id} — {ind.title}</TARGET_INDICATOR>\n"
        f"<INDICATOR_QUESTION>{ind.description}</INDICATOR_QUESTION>\n"
        f"<INDICATOR_SCOPE>{ind.scope}</INDICATOR_SCOPE>\n"
        f"<LEGAL_TEST>{ind.legal_test}</LEGAL_TEST>\n"
        f"<QUERY_TERMS>{' | '.join(ind.query_terms)}</QUERY_TERMS>\n"
        f"<SIBLINGS>\n{_siblings_block(ind)}\n</SIBLINGS>\n"
        f"<LAW>{prov.law_name} — {prov.article_section}</LAW>\n"
        f"<SNIPPET_LANGUAGE>{_snippet_language(prov)}</SNIPPET_LANGUAGE>\n"
        f"<SNIPPET>{prov.verbatim_snippet}</SNIPPET>\n"
        "Follow steps (1)-(9). Decide independently whether THIS provision satisfies the "
        "TARGET; only reject for a better sibling if the target is a genuine mislabel. "
        "Return the JSON object only."
    )


def _build_notes(prov: Provision, scope_flag: str | None, topical_ok: bool = True) -> str | None:
    """Template 'Notes' — flag unusual cases: scope, off-topic snippet, OCR quality, etc."""
    parts = []
    if scope_flag:
        parts.append(f"{scope_flag}: sectoral instrument — verify before treating as national.")
    if not topical_ok:
        parts.append("OFF_TOPIC_SNIPPET: snippet contains none of the pillar's concept terms — "
                     "likely a mis-mapping; verify the provision actually concerns this indicator.")
    if prov.ocr.used:
        mc = prov.ocr.mean_confidence
        if prov.ocr.provider == "markitdown":
            parts.append("Text extracted from PDF via MarkItDown; verify wording vs source.")
        else:
            parts.append(f"OCR-extracted via {prov.ocr.provider}"
                         + (f" (mean conf {mc:.2f})" if mc is not None else "") + "; verify wording vs source.")
    # A non-English Verbatim Snippet is deliberate — it is the authoritative statute text, and
    # translating it would make the citation false. Say so in the row, so a reviewer reading the
    # CSV knows the foreign text is the answer and not an extraction failure.
    lang = _snippet_language(prov)
    if lang != "English":
        parts.append(f"Verbatim snippet is the authoritative {lang} text (not translated); "
                     f"the rationale is in English.")
    # MY snippets come from the official English PDF; the Malay sibling is authoritative
    url = prov.source_url or ""
    if prov.economy.value == "MY" and url.lower().endswith("e.pdf"):
        parts.append(f"Official English translation (bilingual source); authoritative Malay text: {url[:-5]}.pdf")
    return " ".join(parts) or None


_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _format_last_amended(amendment_date: str | None, law_name: str | None) -> str | None:
    """'Month Year' when the month is verified, else 'Year'; never invents a month.
    'Original' (portal positively shows the law was never amended) passes through verbatim —
    the judges' Q&A: never-amended laws get "Original", not a blank and not the enactment
    year."""
    d = (amendment_date or "").strip()
    if d == "Original":
        return "Original"
    m = re.match(r"^((?:19|20)\d{2})-(\d{2})", d)
    if m:
        month = int(m.group(2))
        if 1 <= month <= 12:
            return f"{_MONTHS[month - 1]} {m.group(1)}"
    if re.match(r"^(?:19|20)\d{2}", d):
        return d[:4]
    yr = re.search(r"\b(19|20)\d{2}\b", law_name or "")
    return yr.group(0) if yr else None


class _CallBudget:
    """Thread-safe cap on cross-check calls per run (grading runs on a thread pool)."""

    def __init__(self, n: int):
        self.n = n
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.n <= 0:
                return False
            self.n -= 1
            return True


def _build_crosscheck(primary: LLMProvider, log):
    """(second, tiebreak, primary_model, budget) — the cross-model panel for borderline
    rejections, or (None, ...) when disabled. openrouter-only: the panel needs distinct
    models behind one gateway; mock/local/single-model providers can't supply independent
    second opinions, and mock must stay deterministic for offline runs."""
    if not settings.crosscheck_enabled or primary.name != "openrouter":
        return (None, None, "", None)
    try:
        second = get_llm_provider("openrouter", model=settings.crosscheck_model)
        tiebreak = get_llm_provider("openrouter", model=settings.crosscheck_tiebreak_model)
    except Exception as e:  # noqa: BLE001 — no key / bad model → run without the panel
        log(f"[crosscheck] disabled ({type(e).__name__}: {e})")
        return (None, None, "", None)
    return (second, tiebreak, primary.model_version, _CallBudget(settings.crosscheck_max_calls))


def _relevant(graded: dict) -> bool:
    rel = graded.get("relevant")
    if rel is None:
        rel = bool(graded.get("satisfies_target")) and not graded.get("better_sibling")
    return bool(rel)


def _borderline_rejection(graded: dict) -> bool:
    """A rejection worth an independent second opinion: the grader itself signalled the
    provision is legally close — it named a sibling (the P6-I1/I2 overlap failure mode) or
    scored a material legal_match despite rejecting. Clear misses (no sibling, ~0 match)
    are never re-asked."""
    return bool(graded.get("better_sibling")) or float(graded.get("legal_match") or 0.0) >= 0.3


def _crosscheck_rejection(ind, prov, xc, log) -> dict | None:
    """Independent cross-model panel on a borderline verdict, in EITHER direction.

    Each call is a fresh, context-free request — the model never sees the primary's answer or
    ours — so this is majority voting over independent judgments, not persuading one model.
    Returns the OVERTURNING model's full graded response when the panel goes 2-1 against the
    primary, else None (the primary verdict stands).

    Conservative on any doubt in BOTH directions: budget spent, call error, or a failover
    landing the "independent" vote back on the primary model all leave the primary verdict
    alone. That is deliberately not symmetric in effect — an unresolved borderline acceptance
    stays a row and an unresolved borderline rejection stays absent — because the alternative
    is letting an infrastructure failure silently change the submission.
    """
    second, tiebreak, primary_model, budget = xc
    if second is None or budget is None or not budget.take():
        return None
    primary_relevant = False
    user = _user_prompt(ind, prov)
    try:
        g2 = second.complete_json(SYSTEM, user)
    except Exception:  # noqa: BLE001 — an opinion call must never crash the run
        return None
    if not g2 or g2.get("_parse_error") or second.model_version == primary_model:
        return None                      # no usable INDEPENDENT vote → primary stands
    if _relevant(g2) == primary_relevant:
        log(f"[crosscheck] {ind.indicator_id} | {prov.article_section}: second model agrees "
            f"— rejected 2-0")
        return None
    # 1-1 split → a third, distinct model decides
    if tiebreak is None or not budget.take():
        return None
    try:
        g3 = tiebreak.complete_json(SYSTEM, user)
    except Exception:  # noqa: BLE001
        return None
    if not g3 or g3.get("_parse_error") or tiebreak.model_version in (primary_model,
                                                                      second.model_version):
        return None
    if _relevant(g3) == primary_relevant:
        log(f"[crosscheck] {ind.indicator_id} | {prov.article_section}: rejection upheld 2-1")
        return None
    log(f"[crosscheck] {ind.indicator_id} | {prov.article_section}: overturned 2-1 "
        f"({second.model_version} + {tiebreak.model_version} vs {primary_model})")
    g2["_crosscheck_note"] = ("Accepted by cross-model majority (2-1): the primary grader "
                              "rejected, two independent models satisfied the legal test.")
    return g2


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

    # ── circuit breaker ───────────────────────────────────────────────────────────────────
    # Shared by every grading worker. `stop` is set the moment a failure is known to be
    # systemic; workers that have not started yet return immediately instead of repeating a
    # doomed call. Without this, an exhausted key produced 968 identical 403s and a run that
    # looked like "the economy has no such law".
    # RLock, not Lock, and the difference is a hang: the failure paths below count under the
    # lock and then call _trip(), which takes it again. A plain Lock is not reentrant, so the
    # 25th consecutive failure deadlocked the worker holding it and every worker behind it —
    # the run stopped dead with no error, which is a worse failure than the one this whole
    # mechanism exists to report.
    breaker = {"stop": threading.Event(), "lock": threading.RLock(),
               "ok": 0, "bad": 0, "skipped": 0, "reason": "", "hint": "", "kind": ""}

    def _trip(reason: str, kind: str, hint: str) -> None:
        with breaker["lock"]:
            if not breaker["reason"]:
                breaker["reason"], breaker["kind"], breaker["hint"] = reason, kind, hint
        breaker["stop"].set()

    # retrieval backend: LightRAG graph-RAG at scale, else built-in hybrid (citations
    # preserved either way — the grader below still judges the verbatim snippet).
    _t_retr = time.perf_counter()
    ranked_by_ind = _select_retriever(indicators, provisions, top_k, llm, log)
    crosscheck = _build_crosscheck(llm, log)

    # Coverage policy. A small corpus (a sample run, a single Act) → grade EVERY provision
    # against EVERY indicator so nothing relevant is missed: the rubric rewards coverage and
    # one provision may legitimately satisfy several indicators. A large corpus (full live
    # crawl) → a retrieval shortlist whose size SCALES with the corpus (retrieve_fraction of
    # the provisions, floor retrieve_top_k) instead of a fixed cap, so long Acts aren't
    # under-covered yet the run stays tractable.
    n = len(provisions)
    grade_all = ranked_by_ind is None and n <= settings.grade_all_max_provisions
    eff_top_k = top_k
    budget_note = ""
    if ranked_by_ind is None and not grade_all:
        # recall-safe shortlist: scale gently with the corpus but clamp to [floor, cap] so a
        # 1200-provision crawl grades ~40/indicator (not 360) — the rerank already front-loads
        # the relevant provisions, so a bigger shortlist only adds latency + cost, not recall.
        # The clamp is PER ECONOMY where it has been measured (retrieval_budget), because the
        # single fitted curve over-spends badly on the economies whose targets rank high.
        econ = str(provisions[0].economy.value if hasattr(provisions[0].economy, "value")
                   else provisions[0].economy) if provisions else None
        eff_top_k, budget_note = retrieval_budget.shortlist_size(econ, n, top_k)
    if ranked_by_ind is None:
        log(f"[mapping] {'grade-all: every' if grade_all else f'retrieval shortlist {budget_note} of'} "
            f"{n} provisions x {len(indicators)} indicators "
            f"= {'n/a' if grade_all else eff_top_k * len(indicators)} grading calls")

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
        if breaker["stop"].is_set():
            with breaker["lock"]:
                breaker["skipped"] += 1
            return None
        try:
            graded = llm.complete_json(SYSTEM, _user_prompt(ind, prov))
        except LLMTerminalError as e:
            # The provider has told us the NEXT call fails the same way. Stop the run's
            # grading here rather than proving it 900 more times.
            _trip(str(e)[:200], e.kind, e.hint)
            return ("FAIL", f"{e.kind}: {e}"[:160], ind.indicator_id, prov.provision_id)
        except Exception as e:  # noqa: BLE001 — one rate-limited call must not crash the run
            reason = f"{type(e).__name__}: {e}"[:160]
            with breaker["lock"]:
                breaker["bad"] += 1
                # Nothing has EVER worked and we are this far in: the fault is systemic, not
                # per-provision. Trip on the count rather than on any one error's wording, so
                # a provider that reports its outage in prose we have never seen still stops.
                if breaker["ok"] == 0 and breaker["bad"] >= settings.mapping_failure_breaker:
                    _trip(reason, "systemic",
                          "no grading call has succeeded — check the LLM provider, key and network")
            return ("FAIL", reason, ind.indicator_id, prov.provision_id)

        # An empty or unparseable response is a FAILED call, not a considered rejection.
        # Treating it as "not relevant" silently deleted known-good mappings: a reasoning
        # model whose thinking overran the token budget returned truncated/empty JSON, and
        # the row vanished with zero warnings (live case: Insurance Act 49Q → P6-I2 lost on
        # ~2/3 of runs). Route it through the failure path so it's counted and surfaced.
        # It also counts against the breaker: a model whose every answer is truncated is just
        # as systemically broken as one that refuses to answer, and costs the same money.
        if not graded or graded.get("_parse_error"):
            reason = "empty/unparseable LLM response (likely reasoning-token truncation)"
            with breaker["lock"]:
                breaker["bad"] += 1
                if breaker["ok"] == 0 and breaker["bad"] >= settings.mapping_failure_breaker:
                    _trip(reason, "truncation",
                          "no grading call has returned parseable JSON — raise "
                          "OPENROUTER_MAX_TOKENS or pick a non-reasoning model")
            return ("FAIL", reason, ind.indicator_id, prov.provision_id)
        with breaker["lock"]:
            breaker["ok"] += 1

        # relevant = satisfies the target AND not a mislabel for a better sibling. Prefer the
        # model's explicit `relevant`; else derive it (real LLMs return satisfies_target/
        # better_sibling; the offline mock returns `relevant` directly).
        # Borderline REJECTIONS get an independent cross-model panel; an overturn replaces
        # `graded` with the accepting model's response.
        #
        # Voting on borderline ACCEPTANCES was tried (2026-08-27) to stop one sampling of one
        # model deciding whether a row existed, and REVERTED the same day once the run-to-run
        # instability was actually diagnosed. It was not sampling noise: it was two blind spots
        # in the indicator definitions, and each made a MAJORITY of models wrong in the same
        # direction. Voting on that does not cancel the error, it ratifies it — the reverted
        # code was observed removing the panel's own answer for Mongolia 6.4 ("acceptance
        # OVERTURNED 2-1" on the Personal Data Protection Law article 14) on two wrong votes.
        # A majority is only worth taking where the members fail INDEPENDENTLY; a shared
        # definitional gap is a common-mode failure and defeats the premise.
        #
        # The asymmetry that remains is therefore deliberate. An overturned rejection ADDS a
        # row a reviewer then reads; a wrongly-overturned acceptance silently deletes evidence,
        # and nothing downstream can notice it is gone.
        if not _relevant(graded):
            overturned = (_crosscheck_rejection(ind, prov, crosscheck, log)
                          if _borderline_rejection(graded) else None)
            if overturned is None:
                return None
            graded = overturned

        legal_match = float(graded.get("legal_match", 0.0) or 0.0)
        scope_alignment = float(graded.get("scope_alignment", 0.0) or 0.0)
        scope_flag = graded.get("scope_flag") or None
        rationale = graded.get("rationale", "")

        # Citation granularity (per-mapping, not per-extraction — the same section can be cited
        # at different subsections for different indicators, or as a whole for another). Only
        # trust a subsection the grader returns if it's a well-formed bracketed ref AND literally
        # appears in the snippet — same "carried from extraction, not generation" rule as the law
        # text itself applies to citations: never let the model invent a subsection number.
        subsection = (graded.get("subsection") or "").strip()
        article_section = prov.article_section
        if subsection and re.fullmatch(r"(?:\(\w{1,4}\))+", subsection):
            first_group = subsection[:subsection.index(")") + 1]
            if first_group in prov.verbatim_snippet:
                article_section = f"{prov.article_section}{subsection}"

        xc_note = graded.get("_crosscheck_note")
        src_text = source_texts.get(prov.doc_id, prov.verbatim_snippet)
        grounding = confidence.snippet_grounding(prov.verbatim_snippet, src_text)
        ctx_before, ctx_after = "", ""
        if prov.char_span and src_text:
            s0, s1 = prov.char_span
            ctx_before = src_text[max(0, s0 - 300):s0]
            ctx_after = src_text[s1:s1 + 300]
        # Sectoral scope only disqualifies for the comprehensive-framework indicator (P7-I1); for
        # localisation/storage/retention/access a sectoral law is a valid answer, so don't cap it.
        apply_scope_cap = ind.indicator_id in confidence.SCOPE_SENSITIVE_INDICATORS
        # Topical guard: a snippet with no pillar concept vocabulary is almost certainly a
        # fabricated mapping (weak grader inventing a reading of off-topic boilerplate).
        topical_ok = confidence.topical_grounded(prov.verbatim_snippet, ind.pillar)
        breakdown = confidence.score(
            retrieval_score=r.score, legal_match=legal_match, grounding=grounding,
            scope_alignment=scope_alignment, scope_flag=scope_flag,
            apply_scope_cap=apply_scope_cap, topical_ok=topical_ok,
        )
        _last_amended = _format_last_amended(prov.amendment_date, prov.law_name)
        status = confidence.route(breakdown.final)
        if status.value == "auto_accepted":
            # A structured, parseable line — the dashboard's "results so far" panel renders
            # these live as they complete, so a researcher can start reading high-confidence
            # hits during the run instead of waiting for the whole thing to finish.
            log(f"[result] {ind.indicator_id} | {prov.law_name[:60]} — {article_section} | "
                f"{breakdown.final:.2f}")
        return EvidenceMapping(
            mapping_id=_mapping_id(run_id, ind.indicator_id, prov.provision_id),
            run_id=run_id, economy=prov.economy, pillar=ind.pillar, indicator_id=ind.indicator_id,
            law_name=prov.law_name, law_number=prov.law_number,
            last_amended=_last_amended,
            article_section=article_section, location_ref=prov.location_ref,
            verbatim_snippet=prov.verbatim_snippet, source_url=prov.source_url,
            mapping_rationale=(rationale or "")[:300], confidence_score=breakdown.final,
            discovery_tag=doc_tags.get(prov.doc_id, DiscoveryTag.KNOWN),
            coverage=("Sectoral" if scope_flag else "Horizontal"),
            notes=" ".join(filter(None, [_build_notes(prov, scope_flag, topical_ok), xc_note])) or None,
            review_status=status,
            provision_id=prov.provision_id, source_pdf_path=prov.source_pdf_path,
            raw_context=r.raw_context, raw_context_before=ctx_before, raw_context_after=ctx_after,
            confidence=breakdown, ocr=prov.ocr, model_version=llm.model_version,
            retrieval_log=r.log, scope_flag=scope_flag,
        )

    _retr_secs = time.perf_counter() - _t_retr   # retrieval + shortlist/work-list build
    _t_grade = time.perf_counter()
    workers = max(1, min(settings.mapping_concurrency, len(work) or 1))
    if workers > 1 and work:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_grade, work))
    else:
        results = [_grade(it) for it in work]
    _grade_secs = time.perf_counter() - _t_grade
    attempted = len(work) - breaker["skipped"]
    log(f"[timing] mapping: retrieval/build {_retr_secs:.1f}s · LLM grading {_grade_secs:.1f}s "
        f"({attempted} calls, {workers}-way, {attempted/_grade_secs:.2f} calls/s"
        + (f", {breaker['skipped']} not attempted" if breaker["skipped"] else "") + ")"
        if work and _grade_secs > 0 else
        f"[timing] mapping: retrieval/build {_retr_secs:.1f}s · {attempted} grading calls")

    first_reason = ""
    for res in results:
        if res is None:
            continue
        if isinstance(res, tuple):  # ("FAIL", reason, ind, prov)
            failures += 1
            first_reason = first_reason or res[1]
            if failures <= 3:
                log(f"[warn] LLM call failed ({res[1]}); skipping {res[2]}/{res[3]}")
            continue
        mappings.append(res)
    if breaker["reason"]:
        # The breaker tripped: the provider itself classified the fault, so report THAT rather
        # than guessing from the wording of an error string. This line is the difference
        # between "your key is broken" (it was not) and "your key's daily spend cap is used
        # up" (it was), and between one wasted call and nine hundred.
        skipped = breaker["skipped"]
        log(f"[error] grading stopped after {failures} failed call(s) — {breaker['kind']}: "
            f"{breaker['reason']}")
        log(f"[error] what to do: {breaker['hint'] or 'see the message above'}"
            + (f" · {skipped} of {len(work)} pairings were not attempted, so this run's "
               f"coverage is INCOMPLETE — it is not evidence that the economy has no such law."
               if skipped else ""))
    elif failures:
        # Surface the ACTUAL first-failure reason (auth vs truncation vs rate-limit) instead
        # of always blaming rate limits — a dead API key looks nothing like a 429.
        if "quota" in first_reason:
            hint = "the key's spend limit is used up — check the cap/reset window, or use another key"
        elif "401" in first_reason or "auth" in first_reason or "rejected" in first_reason:
            hint = "check the LLM key/provider"
        elif "truncation" in first_reason or "unparseable" in first_reason:
            hint = "responses truncated/unparseable — try raising OPENROUTER_MAX_TOKENS"
        else:
            hint = "possible rate limits — try a paid key or fewer pillars"
        log(f"[warn] {failures} of {len(work)} LLM call(s) failed and were skipped ({hint})")
    # most confident first
    mappings.sort(key=lambda m: m.confidence_score, reverse=True)
    return mappings
