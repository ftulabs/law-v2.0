"""Which OpenRouter upstream providers answer the SAME prompt the same way twice.

`config.openrouter_provider_order` pins the upstream provider because on OpenRouter one model
id is served by a dozen companies on different hardware, quantisations and kernels, and which
one answers decides the verdict on a borderline provision. That pin is only defensible if the
provider in it was MEASURED to be reproducible, and the measurement will drift as they change
their serving stacks — so this is the tool that re-takes it.

    python tools/probe_provider_determinism.py
    python tools/probe_provider_determinism.py --runs 6 --providers DeepInfra,Parasail

It grades one deliberately BORDERLINE provision (Mongolia's Personal Data Protection Law
article 8 against P6-I4 — a consent rule that reads onto a conditional-transfer indicator
without plainly satisfying it) N times per provider and reports how many distinct verdicts
came back. A provider is usable for a submission only at 1.

Reference measurement, 2026-08-27, 4 runs each:

    DeepInfra     1 verdict    ~2.4 s
    Parasail      2 verdicts   ~12 s
    Alibaba       4 verdicts   ~13 s
    DigitalOcean  3 verdicts   ~37 s
    SiliconFlow   3 verdicts   ~65 s
    StreamLake    1 verdict + 3 errors

Note what the unpinned column of that run showed: four calls served by the SAME provider still
split two-two. Continuous batching changes the numerics per request, so `temperature=0` alone
never made this reproducible and never could — it makes sampling greedy over logits that are
themselves not fixed.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings                                    # noqa: E402
from backend.pipeline.mapping import SYSTEM, _user_prompt              # noqa: E402
from backend.rdtii import get_indicators                               # noqa: E402
from backend.schemas import Economy, OCRMetrics                        # noqa: E402

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: The probe case. A provision every provider agrees on measures nothing — determinism is only
#: ever lost where the judgement is close, so the probe has to be close too.
PROBE_LAW = "16390288615991"          # ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ
PROBE_ARTICLE = "8 "                  # article 8 — consent of the data subject
PROBE_INDICATOR = "P6-I4"             # conditional cross-border transfer regime

DEFAULT_PROVIDERS = ("DeepInfra", "SiliconFlow", "Parasail", "DigitalOcean",
                     "StreamLake", "Alibaba")


def _probe_prompt() -> str:
    """The real grading prompt for the probe provision, fetched live."""
    import httpx                                                       # noqa: PLC0415

    from backend.pipeline.adapter_mongolia import _doc, export_law, export_text  # noqa: PLC0415
    from backend.pipeline.extraction import extract_provisions          # noqa: PLC0415

    client = httpx.Client(timeout=90, follow_redirects=True,
                          headers={"User-Agent": settings.crawl_user_agent})
    title, body = export_law(client, PROBE_LAW)
    doc = _doc(PROBE_LAW, title, Economy.MN, "legalinfo.mn", len(body))
    provs = extract_provisions(doc, export_text(body), OCRMetrics())
    prov = next(p for p in provs if p.article_section.startswith(PROBE_ARTICLE))
    ind = {i.indicator_id: i for i in get_indicators(6)}[PROBE_INDICATOR]
    return _user_prompt(ind, prov)


def _ask(user: str, provider: str, model: str, key: str) -> tuple:
    body = {
        "model": model, "temperature": 0, "max_tokens": settings.openrouter_max_tokens,
        "provider": {"order": [provider], "allow_fallbacks": False},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.monotonic()
    data = json.loads(urllib.request.urlopen(req, timeout=180).read())
    elapsed = time.monotonic() - t0
    text = data["choices"][0]["message"]["content"] or "{}"
    m = re.search(r"\{.*\}", text, re.S)
    out = json.loads(m.group(0)) if m else {}
    # The verdict, not the prose: two answers that decide the same way but word the rationale
    # differently are the same answer for a submission's purposes.
    return (bool(out.get("satisfies_target")), out.get("legal_match"),
            out.get("better_sibling")), elapsed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=4, help="calls per provider (default 4)")
    ap.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS))
    ap.add_argument("--model", default=settings.openrouter_model)
    args = ap.parse_args()

    key = settings.openrouter_api_key
    if not key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 2

    print(f"model={args.model}  runs={args.runs}  probe={PROBE_LAW} art {PROBE_ARTICLE.strip()}"
          f" vs {PROBE_INDICATOR}\n")
    user = _probe_prompt()
    rows = []
    for name in [p.strip() for p in args.providers.split(",") if p.strip()]:
        seen: collections.Counter = collections.Counter()
        lat: list[float] = []
        for _ in range(args.runs):
            try:
                verdict, elapsed = _ask(user, name, args.model, key)
                seen[verdict] += 1
                lat.append(elapsed)
            except Exception as e:                 # noqa: BLE001 — an outage is a result too
                seen[("ERROR", type(e).__name__, None)] += 1
        errors = sum(n for v, n in seen.items() if v[0] == "ERROR")
        distinct = len([v for v in seen if v[0] != "ERROR"])
        mean = f"{sum(lat) / len(lat):.1f}s" if lat else "—"
        rows.append((distinct, errors, name, mean, dict(seen)))
        verdict_word = "REPRODUCIBLE" if distinct == 1 and not errors else "varies"
        print(f"  {name:14} {verdict_word:13} {distinct} distinct verdict(s), "
              f"{errors} error(s), mean {mean}")

    usable = [r for r in rows if r[0] == 1 and r[1] == 0]
    print("\nUsable for a submission (one verdict, no errors), fastest first:")
    if usable:
        for _, _, name, mean, _ in sorted(usable, key=lambda r: r[3]):
            print(f"  {name}  ({mean})")
        print(f"\nSet OPENROUTER_PROVIDER_ORDER={usable[0][2]} "
              f"(currently {settings.openrouter_provider_order})")
    else:
        print("  NONE — do not submit results from this model until one is reproducible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
