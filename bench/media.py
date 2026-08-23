"""Teaser assets for the project page, drawn from the records.

A project page has a slot at the top for the thing that shows the result at a
glance. The convention fills it with a video; this project has no video, and
faking one would be worse than leaving it empty. What it has is a finding that
is genuinely easier to see moving than still: three of the four configurations
leave two economies at exactly zero, and the fourth does not.

So the teaser is an animated bar chart, one frame per condition, read straight
out of `bench/out/metrics.json`. No number in it is typed here -- the same rule
the paper and the site run on. Rerun after `ledger metrics`:

    .venv-bench/bin/python -m bench.media
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

METRICS = ROOT / "bench" / "out" / "metrics.json"
OUT_DIR = ROOT / "assets" / "media"

FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

ECONOMIES = [("SG", "Singapore", "Latin"), ("AU", "Australia", "Latin"),
             ("MY", "Malaysia", "Latin"), ("IN", "India", "Latin"),
             ("CN", "China", "Han"), ("MN", "Mongolia", "Cyrillic")]

# The four frames, in the order the ablation reads: neither treatment, each
# alone, then both.
FRAMES = [
    ("ascii_only", "english", "Monolingual tokeniser, English vocabulary"),
    ("script_aware", "english", "Script-aware tokeniser, English vocabulary"),
    ("ascii_only", "english_plus_native", "Monolingual tokeniser, + native vocabulary"),
    ("script_aware", "english_plus_native", "Script-aware tokeniser, + native vocabulary"),
]

W, H = 1200, 620
PANEL_W, PANEL_H = 560, 520
INK, MUTED, RULE = (26, 30, 33), (95, 107, 118), (225, 229, 233)
BAR_LATIN, BAR_HIT, BAR_ZERO = (47, 111, 178), (40, 140, 90), (208, 90, 70)


def _cells() -> "dict[tuple[str, str, str], float]":
    """(economy, tokeniser, terms) -> reachability, from metrics.json only."""
    if not METRICS.is_file():
        raise SystemExit("no metrics at %s -- run `ledger metrics` first" % METRICS)
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    out = {}
    for cell in payload["cells"]:
        cfg = cell["config"]
        stats = (cell.get("metrics") or {}).get("reachable") or {}
        if stats.get("mean") is None:
            continue
        out[(cfg["economy"], cfg["tokeniser"], cfg["terms"])] = float(stats["mean"])
    return out


def _frame(draw_mod, values, tokeniser, terms, caption):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    title = ImageFont.truetype(str(FONT_BOLD), 34)
    sub = ImageFont.truetype(str(FONT), 22)
    lab = ImageFont.truetype(str(FONT), 19)
    num = ImageFont.truetype(str(FONT_BOLD), 21)
    small = ImageFont.truetype(str(FONT), 16)

    d.text((60, 38), "Can the indicator vocabulary reach the law at all?",
           font=title, fill=INK)
    d.text((60, 84), caption, font=sub, fill=MUTED)

    top, bottom, left = 150, H - 118, 60
    plot_h = bottom - top
    d.line([(left, bottom), (W - 60, bottom)], fill=(150, 160, 170), width=2)
    for i in range(5):
        v = i / 4.0
        y = bottom - v * plot_h
        d.line([(left, y), (W - 60, y)], fill=RULE, width=1)
        d.text((left - 46, y - 10), "%.2f" % v, font=small, fill=MUTED)

    slot = (W - 60 - left) / len(ECONOMIES)
    bw = slot * 0.46
    for i, (code, name, script) in enumerate(ECONOMIES):
        value = values.get((code, tokeniser, terms), 0.0)
        cx = left + slot * (i + 0.5)
        y = bottom - value * plot_h
        colour = BAR_LATIN if script == "Latin" else (BAR_HIT if value > 0.01 else BAR_ZERO)
        if value > 0.001:
            d.rectangle([cx - bw / 2, y, cx + bw / 2, bottom], fill=colour)
        else:
            # A zero bar draws nothing, so the zero is stated instead. It is the
            # result, not an absence of one.
            d.line([(cx - bw / 2, bottom), (cx + bw / 2, bottom)], fill=BAR_ZERO, width=5)
        d.text((cx, y - 30), "%.3f" % value, font=num,
               fill=colour if value > 0.001 else BAR_ZERO, anchor="ma")
        d.text((cx, bottom + 12), name, font=lab, fill=INK, anchor="ma")
        d.text((cx, bottom + 38), script, font=small,
               fill=MUTED if script == "Latin" else BAR_ZERO, anchor="ma")

    d.text((60, H - 34), "share of the expert panel's cited instruments a query can reach  ·  "
                         "every value from bench/out/metrics.json",
           font=small, fill=MUTED)
    return img


def _panel(values, tokeniser, terms, caption):
    """One teaser panel: the six economies under one condition, compactly.

    Four of these sit in a row at the top of the project page, labelled (a) to
    (d), so the reader sees the whole ablation before reading a word of it. The
    order is the order the argument runs in: neither treatment, each alone, both.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (PANEL_W, PANEL_H), "white")
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(str(FONT_BOLD), 26)
    lab = ImageFont.truetype(str(FONT), 21)
    num = ImageFont.truetype(str(FONT_BOLD), 20)

    d.text((PANEL_W // 2, 20), caption, font=head, fill=INK, anchor="ma")

    top, bottom, left, right = 76, PANEL_H - 92, 34, PANEL_W - 22
    plot_h = bottom - top
    d.line([(left, bottom), (right, bottom)], fill=(150, 160, 170), width=2)
    for i in range(3):
        y = bottom - (i / 2.0) * plot_h
        d.line([(left, y), (right, y)], fill=RULE, width=1)

    slot = (right - left) / len(ECONOMIES)
    bw = slot * 0.54
    for i, (code, name, script) in enumerate(ECONOMIES):
        value = values.get((code, tokeniser, terms), 0.0)
        cx = left + slot * (i + 0.5)
        y = bottom - value * plot_h
        colour = BAR_LATIN if script == "Latin" else (BAR_HIT if value > 0.01 else BAR_ZERO)
        if value > 0.001:
            d.rectangle([cx - bw / 2, y, cx + bw / 2, bottom], fill=colour)
        else:
            d.line([(cx - bw / 2, bottom), (cx + bw / 2, bottom)], fill=BAR_ZERO, width=5)
        d.text((cx, y - 27), "%.2f" % value, font=num,
               fill=colour if value > 0.001 else BAR_ZERO, anchor="ma")
        d.text((cx, bottom + 14), code, font=lab,
               fill=INK if script == "Latin" else BAR_ZERO, anchor="ma")
    return img


def build(out_dir: Path = OUT_DIR) -> None:
    try:
        from PIL import ImageDraw
    except ImportError:
        raise SystemExit("Pillow is required: .venv-bench/bin/pip install Pillow")

    values = _cells()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = [_frame(ImageDraw, values, tok, terms, cap) for tok, terms, cap in FRAMES]

    # The last frame holds four times as long: it is the one with the answer in
    # it, and a loop that flashes past the answer teaches nothing.
    durations = [1400, 1400, 1400, 4200]
    gif = out_dir / "teaser.gif"
    frames[0].save(str(gif), save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    still = out_dir / "teaser.png"
    frames[-1].save(str(still), "PNG", optimize=True)

    # The four panels of the teaser row, one per condition.
    labels = ["Monolingual, English", "Script-aware, English",
              "Monolingual, + native", "Script-aware, + native"]
    for letter, (tok, terms, _), label in zip("abcd", FRAMES, labels):
        _panel(values, tok, terms, label).save(
            str(out_dir / ("panel_%s.png" % letter)), "PNG", optimize=True)

    favicon = out_dir / "favicon.svg"
    favicon.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#1a1e21"/>'
        '<rect x="13" y="30" width="8" height="21" fill="#2f6fb2"/>'
        '<rect x="27" y="22" width="8" height="29" fill="#2f6fb2"/>'
        '<rect x="41" y="47" width="8" height="4" fill="#d05a46"/>'
        '<circle cx="45" cy="24" r="4.5" fill="none" stroke="#d05a46" stroke-width="2.5"/>'
        "</svg>\n", encoding="utf-8")

    print("[media]   %s (%d frames), %s, 4 panels, %s"
          % (gif.relative_to(ROOT), len(frames),
             still.relative_to(ROOT), favicon.relative_to(ROOT)))


if __name__ == "__main__":
    build()
