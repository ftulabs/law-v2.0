"""Precompute-first corpus layer.

Layers (see docs/precompute-corpus.md §7):
  L0 catalogue  — the portal's own in-force list          (catalogue.py)
  L1 body       — fetched bytes, content-addressed        (build.py, reuses pipeline/fetch.py)
  L2 text       — extracted text + OCR metrics            (build.py, reuses pipeline/ocr.py)
  L3 provisions — split sections                          (build.py, reuses pipeline/extraction.py)
  L4 candidates — retrieval seam                          (NOT IMPLEMENTED — pending redesign)
  L5 evidence   — graded (provision, indicator) verdicts  (NOT IMPLEMENTED)
  L6 answer     — assembled CSV rows, never cached        (NOT IMPLEMENTED)

The build deliberately stops after L3: retrieval is being re-derived from measurements
(backend/eval/) before it is wired in.
"""
from . import store  # noqa: F401  — registers the corpus tables on the shared metadata
