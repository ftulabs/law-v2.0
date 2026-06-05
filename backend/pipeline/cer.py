"""ZONE 2 — Character Error Rate (CER) measurement.

The rubric requires extracted text to have CER < 5%. CER = edit_distance(ref, hyp)
/ len(ref) at the character level (WER is the word-level analogue). We use it two ways:
  • as an evaluation metric against a known-good reference, and
  • as a SELF-check: re-OCR a couple of rendered pages and compare against the text
    layer, giving a no-ground-truth quality estimate the run can flag on.

Pure-python (no native Levenshtein dep) with the linear-space two-row DP, capped so a
300-page Act doesn't blow up — we score representative samples, not the whole corpus.
"""
from __future__ import annotations

import re

_MAX = 20000   # cap per comparison; CER on a representative window is enough to flag quality


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER in [0, ~1]. 0 = identical. Whitespace-normalised, length-capped."""
    ref, hyp = _norm(reference)[:_MAX], _norm(hypothesis)[:_MAX]
    if not ref:
        return 0.0 if not hyp else 1.0
    return round(_edit_distance(ref, hyp) / len(ref), 4)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference).split()[:_MAX], _norm(hypothesis).split()[:_MAX]
    if not ref:
        return 0.0 if not hyp else 1.0
    # reuse char DP over token lists by mapping tokens to chars is fiddly; do a token DP
    prev = list(range(len(hyp) + 1))
    for i, rt in enumerate(ref, 1):
        cur = [i]
        for j, ht in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rt != ht)))
        prev = cur
    return round(prev[-1] / len(ref), 4)
