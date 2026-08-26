"""Working translations of the evidence, for a reviewer who does not read the statute language.

Six of the nine live-test economies legislate in a script the reviewer cannot read — Chinese,
Mongolian, Thai, Lao, Russian, Kazakh — and the two columns that carry the actual finding are
`Law Name` and `Verbatim Snippet`, both of which are the statute's own words by definition. So
the output of a correct run on Mongolia is a spreadsheet nobody on the team can check. Not
"hard to read": unverifiable. The mapping rationale is already written in English (see the
grading prompt), which tells you what the model CONCLUDED, and is exactly the thing you would
want to audit against the text rather than trust.

**These are additional columns. They never touch the originals.** `Verbatim Snippet` IS the
statute's text — it is what the panel checks the citation against — so a translated snippet
written into that column would be a false citation, and this module cannot produce one: it
only ever writes `law_name_translated` / `snippet_translated`, and the exporter appends those
AFTER the mandatory columns (the judges' Q&A permits extra columns in that position, which is
the same allowance `RDTII_Raw_Score` already uses).

Cost. Naively this is one LLM call per row per field, and a Mongolia run has ~65 rows. Two
things cut that to a fraction:

  • **Law names are translated once per distinct name, not once per row.** A run cites twenty
    laws across sixty-five rows, and the same Act supplies a dozen of them.
  • **A disk cache keyed by the source text.** Statute text does not change between runs, so
    the second run of an economy translates nothing. The cache is keyed on a hash of the
    text plus the target language, so changing the target language does not serve stale rows.

An economy that already legislates in the target language is skipped outright — SG/AU/MY/IN
against English cost nothing and get empty columns, which reads correctly: there is no
translation because none was needed.

Failure is non-fatal by construction. A translation is a convenience column; if the call
fails the row keeps its original text and the column is empty, and the run still produces a
valid submission.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..config import settings
from ..providers import get_llm_provider
from ..providers.llm_base import LLMProvider
from ..providers.ocr_languages import profile_for
from ..schemas import EvidenceMapping

#: Rows the exporter writes for an indicator with no evidence. Their "snippet" is the fixed
#: English phrase "No provision found", so translating it would spend a call to return the
#: input. Matched on law_name because that is what `_no_evidence_placeholders` sets.
PLACEHOLDER_LAW = "No provision found"

TRANSLATE_SYSTEM = (
    "You are a legal translator working on statutory text for a regulatory review. "
    "Translate the text you are given into {target}.\n\n"
    "Rules:\n"
    "1. Translate ONLY. Do not summarise, do not explain, do not add commentary, and do not "
    "omit anything — a clause you drop is a clause the reviewer will believe is absent.\n"
    "2. Keep every article, section and clause NUMBER exactly as it appears (14.1 stays 14.1).\n"
    "3. NEVER TRANSLITERATE. Romanising the source script is not a translation: "
    '"27 duugaar zuil. Niitiin medeeleliin san" is the same sentence the reviewer already '
    "could not read, and it is worse than useless because it LOOKS like an answer. Every "
    "word must come out as {target}. The single exception is a proper noun with no "
    "established {target} form — an agency or a place — which may be romanised, and only "
    "then. If you are unsure of a term, translate it by its meaning rather than by its "
    "sound.\n"
    "4. Keep legal terms of art in their standard {target} legal equivalent; where a term "
    "genuinely has no equivalent, give the nearest {target} wording and put the original in "
    "parentheses once.\n"
    "5. Preserve the paragraph and clause structure of the original, including line breaks.\n"
    "6. If the text is ALREADY in {target}, return it unchanged.\n\n"
    'Reply with JSON only: {{"translation": "..."}}'
)

#: Long snippets are truncated before the call, not after: the cost of a translation is set by
#: the input, and a snippet past this length is a whole article the reviewer will open the
#: source URL for anyway. The marker is appended so a truncated cell never reads as complete.
TRUNCATION_MARK = " […truncated — open the Source URL for the full article]"


def _cache_dir() -> Path:
    d = Path(settings.output_path).parent / ".cache" / "translations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(text: str, target: str) -> str:
    return hashlib.sha256(f"{target}\x00{text}".encode("utf-8")).hexdigest()[:32]


def _cache_get(text: str, target: str) -> str | None:
    f = _cache_dir() / f"{_key(text, target)}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("translation")
    except Exception:                       # noqa: BLE001 — a corrupt cache entry is not fatal
        return None


def _cache_put(text: str, target: str, translation: str) -> None:
    try:
        (_cache_dir() / f"{_key(text, target)}.json").write_text(
            json.dumps({"translation": translation}, ensure_ascii=False), encoding="utf-8")
    except Exception:                       # noqa: BLE001 — an unwritable cache is not fatal
        pass


def needs_translation(economy: str, target: str | None = None) -> bool:
    """False when the economy's statutes are already written in the target language."""
    target = (target or settings.translation_target_lang).strip().lower()
    return profile_for(economy).language.strip().lower() != target


def _translate_one(llm: LLMProvider, text: str, target: str, log) -> str:
    """One cached translation. Returns "" on failure, never raises."""
    text = (text or "").strip()
    if not text:
        return ""
    cached = _cache_get(text, target)
    if cached is not None:
        return cached
    payload = text
    if len(payload) > settings.translation_max_chars:
        payload = payload[:settings.translation_max_chars].rstrip()
    try:
        out = llm.complete_json(TRANSLATE_SYSTEM.format(target=target), payload)
        got = (out.get("translation") or "").strip()
    except Exception as e:                  # noqa: BLE001 — a convenience column is not the run
        log(f"[translate] call failed ({type(e).__name__}); leaving the column empty")
        return ""
    if not got:
        return ""
    got = re.sub(r"\s+\n", "\n", got)
    if len(payload) < len(text):
        got += TRUNCATION_MARK
    _cache_put(text, target, got)
    return got


def translate_mappings(
    mappings: list[EvidenceMapping],
    llm: LLMProvider | None = None,
    target: str | None = None,
    log=lambda *_: None,
) -> list[EvidenceMapping]:
    """Fill `law_name_translated` / `snippet_translated` in place. Returns the same list.

    Runs AFTER mapping and scoring and alters nothing either of them decided — a translation
    is never an input to a grade, because a grade taken from a translation is a grade of our
    own paraphrase rather than of the statute.
    """
    if not mappings:
        return mappings
    target = (target or settings.translation_target_lang).strip()

    todo = [m for m in mappings
            if m.law_name != PLACEHOLDER_LAW and needs_translation(m.economy.value, target)]
    if not todo:
        log(f"[translate] nothing to translate — sources are already in {target}")
        return mappings

    llm = llm or get_llm_provider()

    # ── law names: once per DISTINCT name, then fanned back out over the rows ──────────────
    names = sorted({m.law_name for m in todo if m.law_name})
    log(f"[translate] {len(todo)} rows into {target} "
        f"({len(names)} distinct law names, snippets cached by text)")

    def _run(items, fn):
        workers = max(1, min(settings.mapping_concurrency, len(items)))
        if workers > 1:
            from concurrent.futures import ThreadPoolExecutor      # noqa: PLC0415
            with ThreadPoolExecutor(max_workers=workers) as ex:
                return list(ex.map(fn, items))
        return [fn(i) for i in items]

    name_map = dict(zip(names, _run(names, lambda n: _translate_one(llm, n, target, log))))

    def _snippet(m: EvidenceMapping) -> None:
        m.law_name_translated = name_map.get(m.law_name, "")
        m.snippet_translated = _translate_one(llm, m.verbatim_snippet, target, log)
        m.translation_target = target if (m.law_name_translated or m.snippet_translated) else None

    _run(todo, _snippet)

    done = sum(1 for m in todo if m.snippet_translated)
    log(f"[translate] {done}/{len(todo)} snippets translated into {target}"
        + ("" if done == len(todo) else " — the rest kept their original text only"))
    return mappings
