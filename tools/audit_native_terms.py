"""Check the native-language retrieval terms against a real crawled corpus.

`backend/rdtii/query_terms_i18n.py` ships two very different kinds of vocabulary. The Chinese
phrases are quoted from named articles and can be checked against the statute. The Mongolian
set is a seed vocabulary of ordinary statutory words that nobody has yet confirmed appears in
Mongolian legislation as drafted — and an unverified retrieval term fails in a way that leaves
no trace: BM25 simply never scores it, retrieval returns the wrong provisions, and the run
reports "no provision found" exactly as it would for a country with no such law.

This makes that visible. For each indicator term it reports how many provisions in the corpus
contain it, so a term can be judged on evidence:

    DEAD    0 hits          — wrong wording, wrong inflection, or the concept is worded
                              differently in this jurisdiction. Replace it.
    NOISE   > ~25% of the   — matches most of the corpus, so it cannot discriminate between
            corpus            indicators. Worse than dead: it drags unrelated provisions up.
    OK      in between      — carries signal.

Agglutinative languages are the usual reason for DEAD: Mongolian inflects "дамжуулах" into
"дамжуулахыг", and BM25 indexes the inflected surface form, so the stem alone never matches.
The fix is to take the wording from the corpus, which is what the `--suggest` output is for.

    python tools/audit_native_terms.py --economy MN
    python tools/audit_native_terms.py --economy CN --suggest
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rdtii import get_indicators                                  # noqa: E402
from backend.rdtii.query_terms_i18n import ECONOMY_QUERY_LANG, native_terms   # noqa: E402

NOISE_FRACTION = 0.25          # a term matching more than this share of the corpus cannot rank


def load_corpus(economy: str) -> list[str]:
    """Provision texts for an economy from the precomputed corpus store."""
    from backend.eval import harness
    return [p.verbatim_snippet for p in harness.load_provisions(economy)]


def audit(economy: str, texts: list[str]) -> list[tuple[str, str, int, str]]:
    """(indicator, term, hits, verdict) for every native term configured for this economy."""
    lowered = [t.lower() for t in texts]
    n = len(lowered)
    rows = []
    for ind in get_indicators(6) + get_indicators(7):
        for term in native_terms(ind.indicator_id, economy):
            t = term.lower()
            hits = sum(1 for text in lowered if t in text)
            if hits == 0:
                verdict = "DEAD"
            elif n and hits / n > NOISE_FRACTION:
                verdict = "NOISE"
            else:
                verdict = "OK"
            rows.append((ind.indicator_id, term, hits, verdict))
    return rows


def suggest(texts: list[str], economy: str, top: int = 25) -> list[tuple[str, int]]:
    """Frequent multi-word sequences from the corpus, as raw material for better terms.

    Deliberately dumb: it surfaces what the statutes ACTUALLY say so a human picks the
    discriminating phrases. Guessing them from a dictionary is what produced the DEAD rows.
    """
    from backend.providers.ocr_languages import profile_for
    spaced = profile_for(economy).spaces_between_words
    counts: Counter = Counter()
    for text in texts:
        if spaced:
            words = re.findall(r"[^\W\d_]{3,}", text.lower())
            counts.update(" ".join(words[i:i + 2]) for i in range(len(words) - 1))
        else:
            run = re.sub(r"[\s\d\W]+", "", text)
            counts.update(run[i:i + 4] for i in range(len(run) - 3))
    return counts.most_common(top)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economy", required=True, help="economy code, e.g. CN or MN")
    ap.add_argument("--suggest", action="store_true",
                    help="also list the corpus's own frequent phrases as replacement candidates")
    args = ap.parse_args()
    economy = args.economy.upper()

    if not ECONOMY_QUERY_LANG.get(economy):
        print(f"{economy} publishes in English — it has no native term pack to audit.")
        return 0

    texts = load_corpus(economy)
    if not texts:
        print(f"No provisions in the corpus for {economy}. Build it first:\n"
              f"    python -m backend.corpus.cli catalogue --economy {economy}\n"
              f"    python -m backend.corpus.cli build --economy {economy}")
        return 1

    rows = audit(economy, texts)
    print(f"{economy}: {len(texts)} provisions, {len(rows)} native terms "
          f"(lang={ECONOMY_QUERY_LANG[economy]})\n")
    width = max(len(t) for _, t, _, _ in rows) if rows else 10
    for indicator, term, hits, verdict in rows:
        pct = 100 * hits / len(texts)
        flag = "  <-- fix" if verdict != "OK" else ""
        print(f"  {indicator:<7} {term:<{width}}  {hits:>6} ({pct:5.2f}%)  {verdict}{flag}")

    tally = Counter(v for _, _, _, v in rows)
    print(f"\n  OK {tally['OK']} · DEAD {tally['DEAD']} · NOISE {tally['NOISE']}")

    if args.suggest:
        print(f"\nMost frequent sequences in the {economy} corpus — pick discriminating ones:")
        for phrase, count in suggest(texts, economy):
            print(f"  {count:>6}  {phrase}")
    return 0 if tally["DEAD"] == 0 and tally["NOISE"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
