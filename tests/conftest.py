"""Make `pytest tests/` work from a clean checkout.

The README tells a reviewer to run `pytest tests/`, and on a fresh clone that command failed
with `ModuleNotFoundError: No module named 'backend'` for every test file. It passed on our
machines only because we habitually typed `python -m pytest`, and the `-m` form puts the
current directory on `sys.path` while the bare `pytest` entry point does not.

So the failure was invisible to everyone who had ever run the suite, and visible to everyone
who had not — which is exactly the population criterion C4a is marked by: a competent
programmer reaching a working system from the README alone, on a clean machine.

The project is a plain source tree rather than an installed package (no setup.py, no
pyproject), and that is deliberate — a reviewer clones and runs, with no build step. This file
is what makes that true for the tests as well.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
