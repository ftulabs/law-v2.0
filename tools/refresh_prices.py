"""Refresh data/pricing.json from the providers' own published rates.

The README says the secretariat verifies cost claims against the code, so the prices behind
those claims must be fetched rather than remembered. OpenRouter publishes per-token rates for
every model on its catalogue endpoint; the rest are list prices with the date they were read,
because there is no API to ask.

    python tools/refresh_prices.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import ROOT                      # noqa: E402
from backend.metering import PRICES                  # noqa: E402

# Local engines cost nothing per page. Listed explicitly rather than left absent, because a
# missing price reports as "unpriced" and $0 has to be a stated fact, not an omission.
OCR = {"rapidocr": 0.0, "paddle": 0.0, "tesseract": 0.0, "markitdown": 0.0, "mock": 0.0,
       # Proprietary, per page, list price read 2026-08-22. Verify before quoting in a
       # submission — these are the two that can move the total by an order of magnitude.
       "azure": 0.0015, "vlm": None, "google": 0.0015}
SEARCH = {"serper": 0.001, "duckduckgo": 0.0, "mojeek": 0.0, "scrapling_ddg": 0.0}


def main() -> int:
    req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                 headers={"User-Agent": "VeriTrade-Research/0.2"})
    models = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]
    llm = {}
    for m in models:
        try:
            pin, pout = float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])
        except Exception:
            continue
        if pin < 0 or pout < 0:                      # router pseudo-models price as -1
            continue
        llm[m["id"]] = {"input_per_1m": round(pin * 1e6, 6),
                        "output_per_1m": round(pout * 1e6, 6)}
    out = {"source": "openrouter.ai/api/v1/models + list prices",
           "llm": llm, "ocr": OCR, "search": SEARCH}
    PRICES.parent.mkdir(parents=True, exist_ok=True)
    PRICES.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(llm)} model prices -> {PRICES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
