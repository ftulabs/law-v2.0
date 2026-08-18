"""Coordination for several Claude Code sessions editing this repo at once.

Why a directory and not one shared file: three sessions appending to a single SESSIONS.md
would conflict on every write. Here each session owns exactly one file, `.sessions/<id>.json`,
so writes never collide and `git` can merge the directory trivially.

A claim is a list of path prefixes plus what the session is doing. Claims are advisory — they
make collisions VISIBLE, they do not lock anything. Real isolation is a branch per session.

    python tools/session_claim.py claim  --id retrieval --paths backend/eval backend/corpus \
                                         --branch feat/precompute-corpus --what "L4-L6 corpus"
    python tools/session_claim.py list
    python tools/session_claim.py check  --paths backend/pipeline/retrieval.py
    python tools/session_claim.py release --id retrieval
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / ".sessions"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    out = []
    if DIR.exists():
        for f in sorted(DIR.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                d["_file"] = f.name
                out.append(d)
            except Exception:  # noqa: BLE001
                pass
    return out


def _overlap(a: str, b: str) -> bool:
    a, b = a.strip("/"), b.strip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def cmd_claim(a) -> int:
    DIR.mkdir(exist_ok=True)
    others = [c for c in _load() if c.get("id") != a.id and c.get("status") == "active"]
    clashes = [(c, p, q) for c in others for p in c.get("paths", []) for q in a.paths
               if _overlap(p, q)]
    rec = {"id": a.id, "branch": a.branch, "what": a.what, "paths": a.paths,
           "status": "active", "claimed_at": _now(), "updated_at": _now(),
           "pid": os.getpid()}
    (DIR / f"{a.id}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"claimed [{a.id}] on branch {a.branch}: {', '.join(a.paths)}")
    if clashes:
        print("\n!! OVERLAPPING ACTIVE CLAIMS:")
        for c, p, q in clashes:
            print(f"   [{c['id']}] branch={c.get('branch')} owns {p}  <->  you asked for {q}")
            print(f"       doing: {c.get('what', '')}")
        return 2
    return 0


def cmd_list(a) -> int:
    claims = _load()
    if not claims:
        print("no active sessions registered")
        return 0
    for c in claims:
        mark = "*" if c.get("status") == "active" else " "
        print(f"{mark} [{c['id']:14}] branch={str(c.get('branch')):26} {c.get('status')}")
        print(f"    since {c.get('claimed_at')}  |  {c.get('what', '')}")
        for p in c.get("paths", []):
            print(f"      - {p}")
    return 0


def cmd_check(a) -> int:
    hits = [(c, p, q) for c in _load() if c.get("status") == "active"
            for p in c.get("paths", []) for q in a.paths if _overlap(p, q)]
    if not hits:
        print("clear — no active claim covers those paths")
        return 0
    for c, p, q in hits:
        print(f"CLAIMED by [{c['id']}] (branch {c.get('branch')}): {p} covers {q}")
        print(f"   doing: {c.get('what', '')}")
    return 2


def cmd_release(a) -> int:
    f = DIR / f"{a.id}.json"
    if not f.exists():
        print(f"no claim named {a.id}")
        return 1
    d = json.loads(f.read_text(encoding="utf-8"))
    d["status"] = "released"
    d["updated_at"] = _now()
    f.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"released [{a.id}]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claim")
    c.add_argument("--id", required=True)
    c.add_argument("--paths", nargs="+", required=True)
    c.add_argument("--branch", default="")
    c.add_argument("--what", default="")
    sub.add_parser("list")
    k = sub.add_parser("check")
    k.add_argument("--paths", nargs="+", required=True)
    r = sub.add_parser("release")
    r.add_argument("--id", required=True)
    a = ap.parse_args()
    return {"claim": cmd_claim, "list": cmd_list, "check": cmd_check,
            "release": cmd_release}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
