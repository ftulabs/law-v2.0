"""Turn world-atlas topojson into the compact outline the globe component ships.

    curl -o world110m.json https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json
    python tools/build_geo_outline.py


Run once. The output is vendored into the repo on purpose: the previous globe pulled three.js
and NASA earth textures from a CDN at render time, so a judging machine without outbound
network — or behind a proxy that blocks jsdelivr — got a blank box with no error anywhere.
"""
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "world110m.json"
OUT = ROOT / "frontend" / "components" / "geo" / "world.json"

# ISO-3166 numeric ids used by world-atlas, for every economy VeriTrade covers.
# 626 = Timor-Leste, added 2026-08-28: it is on the panel's list and carries the difficulty
# bonus, and it was missing here because the economy itself was missing from the codebase.
# At 110m it is a real outline, not a dot — Natural Earth carries it.
NUMERIC = {
    "702": "SG", "036": "AU", "458": "MY", "156": "CN", "356": "IN", "496": "MN",
    "764": "TH", "704": "VN", "360": "ID", "398": "KZ", "418": "LA", "643": "RU",
    "626": "TL",
}


def decode_arcs(topo):
    scale, translate = topo["transform"]["scale"], topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append([x * scale[0] + translate[0], y * scale[1] + translate[1]])
        out.append(pts)
    return out


def ring(arcs, idxs):
    pts = []
    for i in idxs:
        seg = arcs[~i][::-1] if i < 0 else arcs[i]
        pts.extend(seg if not pts else seg[1:])
    return pts


def polygons(arcs, geom):
    if geom["type"] == "Polygon":
        return [[ring(arcs, r) for r in geom["arcs"]]]
    if geom["type"] == "MultiPolygon":
        return [[ring(arcs, r) for r in poly] for poly in geom["arcs"]]
    return []


def simplify(pts, tol):
    """Drop points closer than `tol` degrees. Enough for a globe two inches across, and it is
    the difference between a 400 KB asset and a 90 KB one."""
    if len(pts) < 4:
        return pts
    out = [pts[0]]
    for p in pts[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    out.append(pts[-1])
    return out if len(out) >= 4 else pts


def area(ring_pts):
    s = 0.0
    for i in range(len(ring_pts) - 1):
        x1, y1 = ring_pts[i]
        x2, y2 = ring_pts[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def main():
    topo = json.loads(SRC.read_text(encoding="utf-8"))
    arcs = decode_arcs(topo)
    land, ours = [], {}
    for geom in topo["objects"]["countries"]["geometries"]:
        iso = NUMERIC.get(str(geom.get("id")).zfill(3))
        for poly in polygons(arcs, geom):
            outer = simplify([[round(x, 2), round(y, 2)] for x, y in poly[0]], 0.6)
            if iso:
                # Never area-filtered. Singapore is 0.05 degrees across and would vanish, and
                # an economy silently missing from its own coverage map is the exact failure
                # this file exists to prevent.
                ours.setdefault(iso, []).append(outer)
            elif area(outer) >= 1.5:         # specks render as one pixel; drop them
                land.append(outer)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"land": land, "economies": ours}, separators=(",", ":")),
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"{OUT} — {len(land)} land rings, {len(ours)} economies, {kb:.0f} KB")
    for iso, rings in sorted(ours.items()):
        print(f"  {iso}: {len(rings)} ring(s), {sum(len(r) for r in rings)} points")


if __name__ == "__main__":
    main()
