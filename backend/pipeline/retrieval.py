"""ZONE 2c — retrieval.

Indicator-grounded retrieval: for each RDTII indicator we build a query from its
title + query_terms and rank candidate provisions. This is the grounding layer —
the mapper only ever sees provisions surfaced here, never the whole corpus, which
is what keeps mappings citation-bound.

Default ranker is BM25 (rank_bm25) with a transparent pure-Python fallback so the
pipeline runs even if the dependency is missing. A dense FAISS/Chroma stage can be
added behind `retrieve()` without changing callers (see ARCHITECTURE.md).
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from ..config import settings
from ..rdtii import get_indicator
from ..rdtii.query_terms_i18n import native_terms
from ..schemas import Provision

# Scripts written WITHOUT inter-word spaces: CJK, kana, Thai, Lao, Khmer, Myanmar. A run of
# these is one undivided "word" to any whitespace/ASCII tokeniser, which is why BM25 scored a
# flat zero on every Chinese provision — not a low score, zero, because [a-z0-9]+ matched
# nothing at all in 不得向境外提供. Runs like that are indexed as overlapping CHARACTER BIGRAMS
# (the classic dependency-free CJK IR approach, as in Lucene's CJKAnalyzer): 个人信息 →
# 个人, 人信, 信息. It needs no segmenter model, and for BM25 it performs on par with word
# segmentation on Chinese while degrading gracefully on Thai/Lao.
_NOSPACE = (r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"     # kana + Han
            r"\u0e00-\u0e7f\u0e80-\u0eff\u1780-\u17ff\u1000-\u109f")    # Thai, Lao, Khmer, Myanmar
# Every other letter-bearing script: Latin-1/extended, Greek, Cyrillic, Armenian, Hebrew,
# Arabic, Devanagari through Sinhala, Georgian. These ARE spaced, so they tokenise as words.
_OTHER_LETTERS = (r"\u00c0-\u024f\u0370-\u03ff\u0400-\u052f\u0530-\u058f"
                  r"\u0590-\u05ff\u0600-\u06ff\u0900-\u0dff\u10a0-\u10ff")
# Branch order is load-bearing: the ASCII branch is kept EXACTLY as it was so that Latin-script
# corpora tokenise bit-identically to Round 1 and the measured retrieval parameters still hold
# (see CLAUDE.md §7 — these were swept, not chosen). Only non-ASCII text takes a new path.
_TOKEN = re.compile(f"[{_NOSPACE}]+"                 # no-space scripts → bigrams below
                    r"|[a-z0-9]+"                    # ASCII: unchanged from Round 1
                    f"|[{_OTHER_LETTERS}]+")         # Cyrillic, Devanagari, … → words
_NOSPACE_RE = re.compile(f"[{_NOSPACE}]")
_RETRIEVAL_SNIPPET_LEN = 2048   # chars fed to embedding model (MiniLM ~512 tokens ≈ 2k chars)


def _tok(text: str) -> list[str]:
    """Lexical tokens for BM25, script-aware.

    Latin/Cyrillic/Devanagari runs become words; a run in a no-space script becomes its
    character bigrams (and the bare character when the run is a single glyph).
    """
    out: list[str] = []
    for w in _TOKEN.findall(text.lower()):
        if _NOSPACE_RE.match(w):
            out.extend([w[i:i + 2] for i in range(len(w) - 1)] or [w])
        else:
            out.append(w)
    return out


@dataclass
class Retrieved:
    provision: Provision
    score: float            # normalised 0..1
    raw_context: str        # the window the mapper sees
    log: list[str]


class _FallbackBM25:
    """Minimal BM25 used only if rank_bm25 isn't installed."""
    def __init__(self, corpus: list[list[str]], k1=1.5, b=0.75):
        self.corpus, self.k1, self.b = corpus, k1, b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.N, 1)
        self.df = Counter()
        for d in corpus:
            for w in set(d):
                self.df[w] += 1
        self.tf = [Counter(d) for d in corpus]

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def get_scores(self, query: list[str]) -> list[float]:
        scores = []
        for i, d in enumerate(self.corpus):
            s = 0.0
            for term in query:
                if term not in self.tf[i]:
                    continue
                freq = self.tf[i][term]
                denom = freq + self.k1 * (1 - self.b + self.b * len(d) / max(self.avgdl, 1))
                s += self._idf(term) * (freq * (self.k1 + 1)) / denom
            scores.append(s)
        return scores


def _build_bm25(corpus: list[list[str]]):
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi(corpus)
    except Exception:
        return _FallbackBM25(corpus)


# ── dense (semantic) stage — optional, lazy, cached ──────────────────────────
_MODEL = None            # SentenceTransformer instance (loaded once per process)
_MODEL_FAILED = False
# keyed by hash of the exact embedded text — identical text ⇒ identical vector
_EMB_CACHE: dict[str, "list[float]"] = {}   # in-memory
_DISK_CACHE: dict | None = None             # on-disk tier, survives restarts

# Concept gate: a provision whose text contains NONE of the pillars' concept vocabulary can
# never rank into a shortlist — skip its (expensive) embedding; it keeps BM25 only.
_CONCEPT_RE = re.compile(
    r"personal (?:data|information)|data protection|privacy|cross[- ]border|transfer|"
    r"overseas|outside +(?:of +)?(?:the +)?(?:country|territory|jurisdiction|singapore|australia|malaysia)|"
    r"localis|localiz|stor(?:e[ds]?|age|ing)\b|server|data cent(?:re|er)|"
    r"retain|retention|keep .{0,20}record|record[s]? .{0,30}(?:kept|keep|maintain)|not less than|"
    r"consent|cyber|security|breach|disclos|intercept|warrant|surveillance|"
    r"protection officer|impact assessment|computer|database|electronic (?:data|record)|"
    r"access .{0,30}(?:data|information|record|computer)|law enforcement|investigation|"
    r"produc(?:e|tion)[^.]{0,40}(?:book|record|document|information)|production order|inspection of books|"
    r"furnish[^.]{0,40}(?:information|record|document|particular|return)|books of",
    re.I)


def _embed_text(p: Provision) -> str:
    """The exact string fed to the embedding model for a provision (see _dense_scores)."""
    return f"{p.article_section}: {p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN]}"


def _embed_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _disk_cache_path():
    # model + snippet-len in the filename → changing either invalidates the cache
    slug = re.sub(r"[^a-z0-9]+", "-", (settings.embed_model or "model").lower()).strip("-")
    return settings.cache_path / f"_emb_{slug}_{_RETRIEVAL_SNIPPET_LEN}.npz"


def _load_disk_cache() -> dict:
    global _DISK_CACHE
    if _DISK_CACHE is not None:
        return _DISK_CACHE
    _DISK_CACHE = {}
    if not settings.embed_cache_enabled:
        return _DISK_CACHE
    p = _disk_cache_path()
    if p.exists():
        try:
            import numpy as np
            data = np.load(p, allow_pickle=False)
            keys, vecs = data["keys"], data["vecs"]
            _DISK_CACHE = {str(k): vecs[i] for i, k in enumerate(keys)}
        except Exception:
            _DISK_CACHE = {}            # unreadable/corrupt cache → re-embed, don't crash
    return _DISK_CACHE


def _save_disk_cache(new: dict) -> None:
    """Merge newly-embedded vectors into the on-disk store (atomic replace)."""
    if not new or not settings.embed_cache_enabled:
        return
    try:
        import os

        import numpy as np
        cache = _load_disk_cache()
        cache.update(new)
        keys = list(cache.keys())
        mat = np.asarray([cache[k] for k in keys], dtype="float32")
        p = _disk_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "wb") as fh:      # file-object form: np.savez won't append ".npz"
            np.savez(fh, keys=np.asarray(keys), vecs=mat)
        os.replace(tmp, p)
    except Exception:
        pass                            # caching is best-effort; never fail a run over it


def _dense_enabled() -> bool:
    mode = (settings.dense_retrieval or "auto").lower()
    return mode in ("on", "auto")


def _get_model():
    """Load the embedding model once. Returns None if unavailable (→ BM25-only)."""
    global _MODEL, _MODEL_FAILED
    if _MODEL is not None or _MODEL_FAILED:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(settings.embed_model)
    except Exception:
        _MODEL_FAILED = True            # not installed / model not downloadable → fall back silently
        _MODEL = None
    return _MODEL


def _embed(texts: list[str]):
    model = _get_model()
    if model is None:
        return None
    import numpy as np
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype="float32")


def _mostly_ascii(text: str) -> bool:
    if not text:
        return True
    non = sum(1 for ch in text[:1000] if ord(ch) > 127)
    return non / min(len(text), 1000) < 0.15


def _dense_scores(dense_query: str, provisions: list[Provision], must_embed: set | None = None):
    """Cosine similarity (0..1) of each provision to the query, or None if disabled.

    Provision text: article_section + first 2 k chars of snippet (no law_name — the law name
    dominates embeddings and makes every PDPA section look like a P7-I1 hit regardless of
    what the section actually says). The embedding model max sequence is ~512 tokens ≈ 2k chars
    so longer snippets are silently truncated anyway; being explicit avoids wasted encoding.
    """
    if not _dense_enabled():
        return None
    import numpy as np
    disk = _load_disk_cache()
    texts = [_embed_text(p) for p in provisions]
    # gate: skip embedding only when a provision has no concept vocab AND no BM25 signal AND
    # is English text (non-Latin scripts rely on the multilingual embedding — never gate them)
    must_embed = must_embed or set()
    active = [i for i, t in enumerate(texts)
              if not settings.dense_concept_gate or i in must_embed
              or _CONCEPT_RE.search(t) or not _mostly_ascii(t)]
    to_embed, idx_map, keys = [], [], {}
    cached: dict[int, "list[float]"] = {}
    for i in active:
        key = keys[i] = _embed_key(texts[i])
        vec = _EMB_CACHE.get(key)
        if vec is None and key in disk:         # promote disk → in-memory
            vec = _EMB_CACHE[key] = disk[key]
        if vec is not None:
            cached[i] = vec
        else:
            idx_map.append(i)
            to_embed.append(texts[i])
    if to_embed:
        embs = _embed(to_embed)
        if embs is None:
            return None                 # model unavailable → BM25-only
        fresh = {}
        for j, i in enumerate(idx_map):
            cached[i] = _EMB_CACHE[keys[i]] = embs[j].tolist()
            fresh[keys[i]] = embs[j]
        _save_disk_cache(fresh)
    qv = _embed([dense_query])
    if qv is None:
        return None
    # gated provisions get the neutral 0.5 an orthogonal embedding would score — approximates
    # their true (uncomputed) similarity so rankings stay ~unchanged
    scores = [0.5] * len(provisions)
    if active:
        mat = np.asarray([cached[i] for i in active], dtype="float32")
        sims = mat @ qv[0]               # L2-normalised → dot == cosine
        for i, s in zip(active, sims):
            scores[i] = (float(s) + 1.0) / 2.0   # [-1,1] → [0,1]
    return scores


# ── cross-encoder score cache (disk) ─────────────────────────────────────────
_CE_DISK: dict[str, dict[str, float]] = {}      # model name -> {key: score}


def _ce_cache_path(model_name: str):
    slug = re.sub(r"[^a-z0-9]+", "-", (model_name or "ce").lower()).strip("-")
    return settings.cache_path / f"_ce_{slug}.npz"


def _load_ce_cache(model_name: str) -> dict[str, float]:
    if model_name in _CE_DISK:
        return _CE_DISK[model_name]
    out: dict[str, float] = {}
    if settings.cross_encoder_cache_enabled:
        p = _ce_cache_path(model_name)
        if p.exists():
            try:
                import numpy as np
                d = np.load(p, allow_pickle=False)
                out = {str(k): float(v) for k, v in zip(d["keys"], d["scores"])}
            except Exception:
                out = {}                        # unreadable/corrupt -> rescore, never crash
    _CE_DISK[model_name] = out
    return out


def _save_ce_cache(model_name: str, fresh: dict[str, float]) -> None:
    if not fresh or not settings.cross_encoder_cache_enabled:
        return
    try:
        import os

        import numpy as np
        cache = _load_ce_cache(model_name)
        cache.update(fresh)
        keys = list(cache.keys())
        p = _ce_cache_path(model_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.savez(fh, keys=np.asarray(keys),
                     scores=np.asarray([cache[k] for k in keys], dtype="float32"))
        os.replace(tmp, p)
    except Exception:
        pass                                    # caching is best-effort


def _cross_scores(query_text: str, provisions: list[Provision], combined: list[float],
                  top_k: int, economy: str | None = None) -> list[float] | None:
    """Cross-encoder relevance (0..1) for the hybrid shortlist; None if the model/setting
    is off. Only the top ~3·top_k hybrid candidates are scored (the rest can't win), so
    the rerank stays cheap. Non-shortlisted provisions keep score 0."""
    from . import ranking
    ce = ranking._cross_encoder(economy)
    if ce is None:
        return None
    import math
    n = min(len(provisions), max(top_k * settings.cross_encoder_pool_mult, 8))
    shortlist = sorted(range(len(provisions)), key=lambda i: combined[i], reverse=True)[:n]

    # Memoise on (model, query, provision text). The cross-encoder is by far the slowest
    # component — 21 pairs/s on this CPU against 45 embeddings/s — and it was the ONLY layer
    # without a cache, so every re-run and every experiment re-scored pairs whose inputs had
    # not changed. Under precompute that is the difference between an afternoon and a minute:
    # a re-split or a shortlist-size sweep reuses every pair, and a rebuilt law only pays for
    # its own provisions. Scores are deterministic for fixed inputs, so this changes nothing
    # but the clock.
    model_name = ranking._ce_model_for(economy)
    disk = _load_ce_cache(model_name)
    qk = hashlib.sha1(query_text.encode("utf-8")).hexdigest()[:12]
    texts = [provisions[i].verbatim_snippet[:512] for i in shortlist]
    keys = [f"{qk}:{hashlib.sha1(t.encode('utf-8')).hexdigest()[:20]}" for t in texts]
    todo = [j for j, k in enumerate(keys) if k not in disk]
    if todo:
        try:
            raw = ce.predict([(query_text, texts[j]) for j in todo],
                             batch_size=settings.cross_encoder_batch_size,
                             show_progress_bar=False)
        except Exception:
            return None
        fresh = {}
        for j, sc in zip(todo, raw):
            v = 1.0 / (1.0 + math.exp(-float(sc)))      # sigmoid -> 0..1
            disk[keys[j]] = v
            fresh[keys[j]] = v
        _save_ce_cache(model_name, fresh)
    scores = [0.0] * len(provisions)
    for i, k in zip(shortlist, keys):
        scores[i] = disk[k]
    return scores


def _phrase_bonus(ind, provisions: list[Provision], native: list[str] | None = None) -> list[float]:
    """Bonus for multi-word query terms appearing literally in the provision text.
    Multiple phrase hits accumulate (capped at 0.30) so a provision matching several of
    the indicator's own phrases ranks clearly above one with just one incidental match."""
    bonuses = [0.0] * len(provisions)
    phrases = _phrases(ind, native)
    if not phrases:
        return bonuses
    for i, p in enumerate(provisions):
        text_lower = p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN].lower()
        count = sum(1 for ph in phrases if ph in text_lower)
        bonuses[i] = min(0.30, count * 0.10)
    return bonuses


def _economy_of(provisions: list[Provision]) -> str | None:
    """The economy a provision set belongs to (a run is always single-economy)."""
    for p in provisions:
        code = getattr(p.economy, "value", p.economy)
        if code:
            return str(code)
    return None


def _is_phrase(term: str) -> bool:
    """Is this query term specific enough to earn a literal-match bonus?

    Two words in a spaced script, or three characters in a no-space one — 境内存储 carries at
    least as much signal as "local storage" does, but `len(term.split()) >= 2` scores it zero
    because Chinese has no spaces to count.
    """
    if len(term.split()) >= 2:
        return True
    return bool(_NOSPACE_RE.search(term)) and len(term) >= 3


def _phrases(ind, native: list[str] | None = None) -> list[str]:
    return [t.lower() for t in list(ind.query_terms or []) + list(native or []) if _is_phrase(t)]


def _sibling_penalty(ind, provisions: list[Provision]) -> list[float]:
    """Down-score provisions whose text is dominated by a sibling indicator's phrases.

    P6-I1↔P6-I4 (ban vs conditional) and P7-I1↔P7-I2 (data-protection vs cybersecurity)
    are the most commonly confused pairs. If a provision contains more sibling multi-word
    phrases than target phrases, it is likely a mislabel at retrieval time — penalise it so
    the expensive LLM grading call is spent elsewhere.
    """
    from ..rdtii import siblings as _get_siblings
    from ..rdtii.query_terms_i18n import native_terms
    sibs = _get_siblings(ind.indicator_id)
    if not sibs:
        return [0.0] * len(provisions)

    econ = _economy_of(provisions)
    target_phrases = _phrases(ind, native_terms(ind.indicator_id, econ))
    penalties = [0.0] * len(provisions)

    for sib in sibs:
        sib_phrases = _phrases(sib, native_terms(sib.indicator_id, econ))
        if not sib_phrases:
            continue
        for i, p in enumerate(provisions):
            text_lower = p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN].lower()
            sib_hits = sum(1 for ph in sib_phrases if ph in text_lower)
            target_hits = sum(1 for ph in target_phrases if ph in text_lower)
            if sib_hits > 0 and sib_hits > target_hits:
                excess = sib_hits - target_hits
                penalties[i] = max(penalties[i], min(0.20, excess * 0.07))

    return penalties


def retrieve(indicator_id: str, provisions: list[Provision], top_k: int = 5) -> list[Retrieved]:
    ind = get_indicator(indicator_id)
    if ind is None or not provisions:
        return []

    # BM25 corpus: law_name kept for document-level discrimination (IDF handles it naturally);
    # snippet capped at _RETRIEVAL_SNIPPET_LEN to avoid long boilerplate dominating scores.
    corpus = [_tok(p.law_name + " " + p.article_section + " "
                   + p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN]) for p in provisions]
    bm25 = _build_bm25(corpus)

    # BM25 query: title + description + legal_test gives a much richer vocabulary than
    # query_terms alone. The legal_test includes "Distinguish from X" notes whose key terms
    # (e.g. "consent", "ban", "cybersecurity") discriminate confusable indicator pairs at the
    # BM25 stage — before the expensive cross-encoder rerank.
    # Native statutory vocabulary joins the LEXICAL query only. The dense stage is left in
    # English on purpose: the embedding model is cross-lingual by construction, so an English
    # question already reaches Chinese text, whereas mixing two scripts into one query vector
    # blurs it. BM25 has no such ability — without native terms it scores a flat zero here.
    econ = _economy_of(provisions)
    native = native_terms(indicator_id, econ)
    bm25_query_text = (
        f"{ind.title} {ind.description} {ind.legal_test} {' '.join(ind.query_terms)} "
        f"{' '.join(native)}"
    )
    query = _tok(bm25_query_text)
    bm = list(bm25.get_scores(query))
    bmax = max(bm) if bm and max(bm) > 0 else 1.0
    bm_norm = [s / bmax for s in bm]

    # Dense query: ind.description is already a natural-language question which fits the
    # sentence-embedding model better than a keyword list. Adding legal_test provides the
    # full operative context so the model can distinguish e.g. "consent" (P6-I4) from
    # "retention" (P7-I3) at the semantic level.
    dense_query_text = f"{ind.description} {ind.legal_test}"
    # BM25-visible provisions must always be embedded (protects concept-vocab misses)
    bm25_keep = set(sorted(range(len(provisions)), key=lambda i: bm[i], reverse=True)[:max(80, top_k * 3)])
    dense = _dense_scores(dense_query_text, provisions, must_embed=bm25_keep)   # None → BM25 only
    alpha = settings.hybrid_alpha if dense is not None else 1.0
    combined = [alpha * bm_norm[i] + (1 - alpha) * (dense[i] if dense else 0.0)
                for i in range(len(provisions))]

    # Phrase-presence bonus: provisions matching multiple indicator phrases rank higher.
    bonus = _phrase_bonus(ind, provisions, native)
    combined = [combined[i] + bonus[i] for i in range(len(provisions))]

    # Sibling-aware penalty: push down provisions whose text is dominated by a sibling
    # indicator's phrases. Catches P6-I1↔P6-I4 and P7-I1↔P7-I2 confusion before LLM grading.
    penalty = _sibling_penalty(ind, provisions)
    combined = [max(0.0, combined[i] - penalty[i]) for i in range(len(provisions))]

    # Cross-encoder precision rerank over a shortlist: bi-encoder/BM25 get RECALL, the
    # cross-encoder reads (indicator, provision) jointly for PRECISION. Use legal_test
    # (which contains "Distinguish from X" notes) as the cross-encoder query so it can
    # discriminate between indicators with overlapping surface vocabulary.
    ce_query = f"{ind.title}. {ind.legal_test} Keywords: {' '.join(ind.query_terms)}"
    cross = _cross_scores(ce_query, provisions, combined, top_k, econ)
    if cross is not None:
        combined = [0.5 * combined[i] + 0.5 * cross[i] for i in range(len(provisions))]

    order = sorted(range(len(provisions)), key=lambda i: combined[i], reverse=True)
    keep = order[:top_k]
    # Semantic-recall guarantee. The cross-encoder is general-domain + English, so it can
    # bury a provision that states the indicator's concept in OTHER words — e.g. a localisation
    # ban written "must not hold or take records outside Australia" (no "transfer"). The
    # bi-encoder DOES capture it (highest dense score), so also admit the strongest pure-dense
    # matches the blended/reranked cut dropped. The shortlist feeds the LLM grader, whose job
    # is precision — better to over-include on recall than silently miss the right provision.
    # OFF by default since the shortlist cap rose to 300: measured against the judges' Database
    # it then changes provision recall by 0.000 while adding ~10% more LLM calls, because the
    # budget already reaches deeper than the guarantee. Controlled by DENSE_RECALL_EXTRA.
    if dense is not None and len(provisions) > top_k and settings.dense_recall_extra > 0:
        seen = set(keep)
        extra = settings.dense_recall_extra
        for i in sorted(range(len(provisions)), key=lambda i: dense[i], reverse=True):
            if extra <= 0:
                break
            if i not in seen and dense[i] >= settings.dense_recall_floor:
                keep.append(i)
                seen.add(i)
                extra -= 1
    ranked = sorted(((i, combined[i]) for i in keep), key=lambda x: x[1], reverse=True)
    out: list[Retrieved] = []
    for i, score in ranked:
        norm = round(score, 3)
        if norm <= 0:
            continue
        p = provisions[i]
        phrase_hit = bonus[i] > 0
        log = [
            f"indicator={indicator_id} bm25_tokens={len(set(query))}",
            (f"hybrid={norm} (bm25={round(bm_norm[i],3)} dense={round(dense[i],3)} "
             f"alpha={alpha} phrase_bonus={bonus[i]:.2f} sibling_penalty={penalty[i]:.2f})"
             if dense is not None else
             f"bm25={norm} (dense off) phrase_bonus={bonus[i]:.2f} "
             f"sibling_penalty={penalty[i]:.2f} provision={p.provision_id}"),
            f"provision={p.provision_id}" + (" [phrase_match]" if phrase_hit else ""),
        ]
        out.append(Retrieved(provision=p, score=norm, raw_context=p.verbatim_snippet, log=log))
    return out
