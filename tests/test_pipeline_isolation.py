"""The runtime pipeline must never read a pre-built corpus.

The final round settles this in one line of the Run Record sheet: *"if no documents were
fetched during the hour, C5a scores zero regardless of what the evidence file contains."* A
pre-computed corpus is therefore not merely unhelpful on 15 October — a run that quietly served
stored documents instead of fetching them would produce a full, plausible evidence file and
score nothing, with nothing on screen to say why.

`backend/corpus/` stays in the tree as an OFFLINE MEASUREMENT FIXTURE: it is what the retrieval
harness scores against, and deleting it would remove the only way we can put a number on a
retrieval change. This test is the guarantee that comes with keeping it — the boundary is
asserted, not assumed, so it cannot be crossed by accident during six weeks of edits.

If this test fails, do not relax it. Move whatever needed the corpus into `backend/eval/`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Everything reachable from a live run. `backend/eval` and `tools/` are deliberately absent:
# measurement code is allowed — and expected — to read the corpus.
RUNTIME_PACKAGES = ["backend/pipeline", "backend/providers", "backend/export", "backend/rdtii",
                   "backend/review", "backend/storage", "frontend"]
RUNTIME_MODULES = ["backend/config.py", "backend/schemas.py", "backend/main.py", "backend/cli.py",
                   "main.py", "run.py", "batch_run.py"]

FORBIDDEN = ("backend.corpus", "corpus.store", "corpus.build", "corpus.catalogue", "corpus.cli")


def _runtime_files() -> list[Path]:
    files: list[Path] = []
    for pkg in RUNTIME_PACKAGES:
        d = ROOT / pkg
        if d.is_dir():
            files += [p for p in d.rglob("*.py") if "__pycache__" not in p.parts]
    files += [ROOT / m for m in RUNTIME_MODULES if (ROOT / m).exists()]
    return files


def _imported_names(path: Path) -> set[str]:
    """Every module name this file imports, absolute and relative resolved to a dotted path."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:                      # not our concern here; other tests catch it
        return set()
    names: set[str] = set()
    pkg_parts = path.relative_to(ROOT).parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                   # relative: rebuild the absolute dotted path
                base = list(pkg_parts[:len(pkg_parts) - node.level + 1])
                names.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                names.add(node.module)
    return names


@pytest.mark.parametrize("path", _runtime_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_runtime_module_does_not_import_the_precomputed_corpus(path):
    offending = sorted(n for n in _imported_names(path)
                       if any(n == f or n.startswith(f + ".") for f in FORBIDDEN))
    assert not offending, (
        f"{path.relative_to(ROOT)} imports {offending}. The runtime pipeline must fetch "
        f"documents, not read a pre-built corpus — a run that serves stored documents scores "
        f"zero on C5a. Put this code in backend/eval/ instead."
    )


def test_the_guard_actually_covers_something():
    """A guard that scans nothing passes forever."""
    files = _runtime_files()
    assert len(files) > 20, f"only {len(files)} runtime files scanned — the path list is wrong"
