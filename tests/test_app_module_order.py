"""A Streamlit script runs top to bottom, so a helper must be defined above its call.

`frontend/app.py` is not a library — Streamlit re-executes the whole module on every
interaction. A `def` placed below the code that calls it is a NameError, but only on the
branch that reaches the call, which is why this one shipped: `_meter_table` was appended
after the live-test TAB, that tab was later removed, and the helpers ended up after
`site_footer()` at the very bottom while the Download tab still called them near the middle.
Every other screen worked. The one that produces the submission file did not.

Nothing in the suite could see it — the frontend has no import-time execution to test, and the
failure needs a completed run in the session to reach. So this checks the property directly.
"""
import ast
from pathlib import Path

import pytest

SCREENS = sorted((Path(__file__).resolve().parents[1] / "frontend").glob("*.py"))


def _module_level_defs(tree: ast.Module) -> dict[str, int]:
    return {n.name: n.lineno for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _first_use_outside_a_def(tree: ast.Module, names: set[str]) -> dict[str, int]:
    """Earliest line where a module-level statement mentions each name.

    Bodies of functions and classes are skipped: those run when called, by which point every
    module-level `def` has been evaluated. Only the script's own straight-line code matters.
    """
    first: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in names:
                first.setdefault(sub.id, sub.lineno)
                first[sub.id] = min(first[sub.id], sub.lineno)
    return first


@pytest.mark.parametrize("path", SCREENS, ids=lambda p: p.name)
def test_no_helper_is_called_before_it_is_defined(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defs = _module_level_defs(tree)
    for name, used_at in _first_use_outside_a_def(tree, set(defs)).items():
        assert defs[name] < used_at, (
            f"{path.name}: `{name}` is used at line {used_at} but defined at line "
            f"{defs[name]}. Streamlit executes this file top to bottom, so that is a "
            f"NameError on whichever screen reaches the call.")
