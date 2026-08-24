"""Does the indicator vocabulary reach the instrument at all? -- the lexical floor.

Retrieval is the ceiling on everything downstream: a provision that never reaches
the shortlist cannot be graded, so it can never be answered. This task measures
the floor beneath that ceiling -- whether an indicator's query vocabulary produces
any lexical signal at all against the instrument the panel actually cited, under
one tokenisation rule, in one economy's own script.

It exists because of a defect that shipped and was invisible. Round 1 tokenised
with `[a-z0-9]+`, which is correct for Singapore, Australia and Malaysia and
returns the empty list for 不得向境外提供. BM25 is 65% of the hybrid score, so every
Chinese provision scored a flat 0.0 -- and nothing threw. The run completed and
reported "No provision found", which is indistinguishable from an economy that
has no such law. `backend/pipeline/retrieval._tok` fixed it by making tokenisation
script-aware. This task is the measurement that fix never had.

**The code under test is imported, never copied.** `_tok` and `_FallbackBM25` are
the shipped implementations; `_ascii_tok` is the Round-1 rule, reproduced from the
comment that pins it in `retrieval.py` and from the regression test that holds the
ASCII path byte-identical. Benchmarking a reimplementation of a tokeniser measures
the reimplementation.

Three metrics, and the first is the one that matters:

  reachable      share of the economy's gold pairs whose instrument receives a
                 NON-ZERO score. This is the silent-failure metric: a zero here is
                 not a ranking that went badly, it is a document the query cannot
                 see.
  recall_at_5    share whose instrument lands in the top five of the pooled
                 index -- half the grading budget of the next line.
  recall_at_10   share whose instrument lands in the top ten of the pooled index.
  mrr            mean reciprocal rank over the full ranking, 0 when unreachable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable

# The tenant's own root, so `backend` and `bench` import the same way they do
# under pytest or the CLI. Ledger puts the manifest directory on sys.path, but a
# task must not depend on how it was invoked.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.retrieval import _FallbackBM25, _tok          # noqa: E402
from backend.rdtii import get_indicators                            # noqa: E402
from backend.rdtii.query_terms_i18n import native_terms             # noqa: E402
from bench import corpus                                            # noqa: E402

# How much real Mongolian catalogue noise each cell indexes alongside the gold.
# A constant rather than a task parameter on purpose: it changes the experiment,
# so it must change the code commit, and the commit is already in every record's
# provenance stamp. A knob that alters a result without altering the provenance
# is exactly the hole this pipeline exists to close.
N_DISTRACTORS = 2000

# Two shortlist budgets, not one. Ten was an arbitrary choice, and the shortlist
# size is not a free parameter for this tenant: `backend/eval/harness.py` counts
# `n_calls` precisely because "recall is meaningless without it -- anyone can hit
# 100% recall by grading everything". A five-item shortlist is half the grading
# cost of a ten-item one, so reporting both says what the cheaper budget costs in
# recall rather than leaving it to be assumed.
TOP_KS = (5, 10)

# Round 1's tokeniser, verbatim. `retrieval.py` keeps the ASCII branch of `_TOKEN`
# bit-identical to this so the swept retrieval parameters still hold, and
# `test_ascii_tokenisation_is_unchanged_from_round1` pins it. Reproduced here as
# the control arm; it is the thing being ablated, not a helper.
_ASCII_TOKEN = re.compile(r"[a-z0-9]+")


def _ascii_tok(text: str) -> "list[str]":
    return _ASCII_TOKEN.findall(text.lower())


TOKENISERS: "dict[str, Callable[[str], list[str]]]" = {
    "ascii_only": _ascii_tok,
    "script_aware": _tok,
}


def _query_text(indicator: Any, economy: str, use_native: bool) -> str:
    """The query for one indicator: its English vocabulary, optionally plus native.

    Native terms are ADDED, never substituted -- `query_terms_i18n` is explicit
    that a wrong guess should only be able to fail to match, never to displace a
    term that was working. Keeping that here means the ablation measures the
    addition, which is the decision a deployment actually makes.
    """
    parts = [indicator.title, " ".join(indicator.query_terms)]
    if use_native:
        parts.extend(native_terms(indicator.indicator_id, economy))
    return " ".join(p for p in parts if p)


def run(config: "dict[str, Any]", ctx: Any) -> "dict[str, float]":
    """One cell: one economy, one tokeniser, one query vocabulary, one draw.

    Ledger's task contract. Everything returned that the manifest declares under
    `metrics:` becomes the record's result; the rest travels as `extra`, where it
    is kept for audit but never aggregated and never charted.
    """
    economy = str(config["economy"])
    tokeniser_name = str(config["tokeniser"])
    use_native = str(config["terms"]) == "english_plus_native"
    seed = int(config["seed"])

    if tokeniser_name not in TOKENISERS:
        raise ValueError(
            "unknown tokeniser %r; the matrix may only name %s"
            % (tokeniser_name, ", ".join(sorted(TOKENISERS)))
        )
    tok = TOKENISERS[tokeniser_name]

    documents, gold = corpus.build(N_DISTRACTORS, seed)
    pairs = [p for p in gold if p.economy == economy]
    if not pairs:
        # Refuse rather than return a clean-looking zero. An economy with no gold
        # pairs is a manifest that names an economy the reference set never
        # covered, and averaging a 0.0 in would publish that as a measurement.
        raise ValueError(
            "no gold pairs for economy %r in the RDTII reference set; known: %s"
            % (economy, ", ".join(sorted({p.economy for p in gold})))
        )

    index_of = {d.doc_id: i for i, d in enumerate(documents)}
    bm25 = _FallbackBM25([tok(d.text) for d in documents])

    by_indicator = {ind.indicator_id: ind for ind in get_indicators(None)}

    n_reachable = 0
    n_at_k = {k: 0 for k in TOP_KS}
    rr_total = 0.0
    empty_queries = 0

    for pair in pairs:
        indicator = by_indicator.get(pair.indicator_id)
        if indicator is None:
            raise ValueError(
                "the reference set cites indicator %r, which backend.rdtii does not "
                "define" % pair.indicator_id
            )
        query = tok(_query_text(indicator, economy, use_native))
        if not query:
            # The query itself tokenised to nothing. Counted, not silently scored:
            # this is the same failure as an unreachable document, one step earlier.
            empty_queries += 1
            continue
        scores = bm25.get_scores(query)
        target = index_of[pair.doc_id]
        target_score = scores[target]
        if target_score <= 0.0:
            continue
        n_reachable += 1
        # Rank among documents that scored strictly higher, so ties do not flatter
        # the result: a target tied with fifty others is ranked behind all of them.
        rank = 1 + sum(1 for s in scores if s > target_score)
        rr_total += 1.0 / rank
        for k in TOP_KS:
            if rank <= k:
                n_at_k[k] += 1

    n = len(pairs)
    n_native, n_instruments = corpus.native_share(economy)
    return {
        "reachable": n_reachable / n,
        "recall_at_5": n_at_k[5] / n,
        "recall_at_10": n_at_k[10] / n,
        "mrr": rr_total / n,
        # Diagnostics. They travel with the record and are never aggregated,
        # because a count that reaches a figure is a number nobody meant to
        # publish.
        "n_pairs": n,
        "n_docs": len(documents),
        "n_empty_queries": empty_queries,
        "n_instruments": n_instruments,
        "n_instruments_non_latin": n_native,
    }
