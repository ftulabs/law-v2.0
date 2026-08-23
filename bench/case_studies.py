"""Worked examples: one instrument, one indicator, four conditions, token by token.

The aggregate result says an economy is unreachable. It does not show *why*, and
"why" is the part a reader has to be able to check. These case studies walk three
instruments through the same code the benchmark measures and print what the
tokeniser actually produced at each step, so the mechanism is inspectable rather
than asserted.

One instrument per script: a Chinese statute, a Mongolian statute, and a
Singaporean one as the control that works under every condition.

**Why the native text is rendered as an image.** This TeX installation has no CJK
package and no T2A Cyrillic encoding, so pdflatex cannot typeset either script.
The alternative -- transliterating -- is not available to us: the pipeline's own
rule is that statutory text is carried, never rewritten, because a translated
snippet is a false citation. So the glyphs are rasterised from the source string
with a font that covers the script, and what appears in the PDF is the statute's
own text rather than a romanisation of it.

Everything here is deterministic and offline. Run it with:

    .venv-bench/bin/python -m bench.case_studies
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rdtii import get_indicator                            # noqa: E402
from bench import corpus                                           # noqa: E402
from bench.tasks.retrieval import TOKENISERS, _query_text          # noqa: E402

OUT_DIR = ROOT / "paper" / "cases"

# Fonts that cover the scripts the case studies use. Chosen by coverage, not by
# taste: a font without the glyph renders a tofu box, which would be worse than
# not showing the text at all.
FONT_CJK = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc")
FONT_CYRILLIC = Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")
FONT_LATIN = FONT_CYRILLIC

CONDITIONS = [
    ("ascii_only", "english", "Monolingual, English terms"),
    ("script_aware", "english", "Script-aware, English terms"),
    ("ascii_only", "english_plus_native", "Monolingual, {}+ native terms"),
    ("script_aware", "english_plus_native", "Script-aware, {}+ native terms"),
]


@dataclass(frozen=True)
class Case:
    economy: str
    indicator_id: str
    match: str          # substring identifying the instrument in the corpus
    english_name: str   # what the panel called it, for the caption
    caption: str


CASES = [
    Case("CN", "P6-I2", "个人信息保护法",
         "Personal Information Protection Law of the PRC",
         "The panel's own answer for local storage, and the article the shipped "
         "grading prompt uses as its worked example."),
    Case("MN", "P7-I1", "ХҮНИЙ ХУВИЙН",
         "Law on Personal Data Protection",
         "Recovered into its own script by the portal-id join; the panel recorded "
         "it under an English name only."),
    Case("SG", "P7-I1", "Personal Data Protection Act",
         "Personal Data Protection Act 2012",
         "The control. Latin script throughout, so no condition changes anything."),
]


def _font_for(text: str) -> Path:
    script = corpus.script_of(text)
    if script == "Han":
        return FONT_CJK
    if script == "Cyrillic":
        return FONT_CYRILLIC
    return FONT_LATIN


def render(text: str, path: Path, size: int = 34) -> bool:
    """Rasterise one string. Returns False if no font covers it."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    font_path = _font_for(text)
    if not font_path.is_file():
        return False
    font = ImageFont.truetype(str(font_path), size)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font)
    pad = 6
    img = Image.new("RGB", (box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad), "white")
    ImageDraw.Draw(img).text((pad - box[0], pad - box[1]), text, font=font, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), "PNG", optimize=True)
    return True


def _tex(text: str) -> str:
    out = []
    for ch in str(text):
        if ch in "&%$#_{}":
            out.append("\\" + ch)
        elif ch == "~":
            out.append("\\textasciitilde{}")
        elif ch == "^":
            out.append("\\textasciicircum{}")
        elif ch == "\\":
            out.append("\\textbackslash{}")
        else:
            out.append(ch)
    return "".join(out)


def _token_cell(tokens: "list[str]", limit: int = 4) -> str:
    """Render a token list for the table.

    Latin tokens are shown as themselves. Non-Latin ones cannot be typeset in
    this TeX installation, so they are counted -- and counted *separately* from
    the Latin ones, because a mixed-script query is the interesting case and
    reporting one total for it would hide which half is doing the work.

    An empty cell says so in words. A blank in a table reads as an omission, and
    here the emptiness is the finding.
    """
    if not tokens:
        return "\\emph{none}"
    latin = [t for t in tokens if corpus.script_of(t) == "Latin"]
    other = len(tokens) - len(latin)
    shown = ", ".join("\\texttt{%s}" % _tex(t) for t in latin[:limit])
    if len(latin) > limit:
        shown += ", \\ldots\\ (%d)" % len(latin)
    if other:
        shown = (shown + " + " if shown else "") + "%d non-Latin" % other
    return shown or "\\emph{none}"


def build(out_dir: Path = OUT_DIR) -> Path:
    instruments, gold = corpus.load_reference()
    lines = [
        "% generated by bench/case_studies.py -- do not edit",
        "% Rerun:  .venv-bench/bin/python -m bench.case_studies",
        "",
    ]
    rendered = 0

    for n, case in enumerate(CASES, start=1):
        docs = [d for d in instruments
                if d.economy == case.economy and case.match in d.text]
        if not docs:
            raise SystemExit(
                "case %s/%s: no instrument matching %r in the reference corpus"
                % (case.economy, case.indicator_id, case.match)
            )
        doc = docs[0]
        indicator = get_indicator(case.indicator_id)
        script = corpus.script_of(doc.text)

        slug = "case%d_%s" % (n, case.economy.lower())
        img = out_dir / ("%s_title.png" % slug)
        has_img = render(doc.text, img)
        rendered += int(has_img)

        lines += [
            "\\subsection{%s --- %s (%s script)}"
            % (_tex(case.economy), _tex(case.indicator_id), _tex(script)),
            "",
            "\\textbf{Instrument.} %s. %s" % (_tex(case.english_name), _tex(case.caption)),
            "",
        ]
        if has_img:
            lines += [
                "\\noindent\\textbf{As the portal publishes it:}\\\\[2pt]",
                "\\noindent\\includegraphics[height=13pt]{cases/%s}" % img.name,
                # A blank line, so the table below starts its own paragraph.
                # Without it the tabular is set beside the image and runs off
                # the right margin.
                "",
            ]
        else:
            lines += ["\\textbf{Title.} \\texttt{%s}" % _tex(doc.text), ""]

        lines += [
            "\\vspace{2pt}",
            "\\noindent\\begin{tabular}{@{}p{3.5cm}p{3.6cm}p{3.4cm}r@{}}",
            "\\toprule",
            "Condition & Query tokens & Title tokens & Overlap \\\\",
            "\\midrule",
        ]
        for tok_name, terms, label in CONDITIONS:
            tok = TOKENISERS[tok_name]
            use_native = terms == "english_plus_native"
            q = tok(_query_text(indicator, case.economy, use_native))
            d = tok(doc.text)
            overlap = set(q) & set(d)
            lines.append("%s & %s & %s & %s \\\\" % (
                _tex(label.replace("{}", "")),
                _token_cell(q),
                _token_cell(d),
                "\\textbf{%d}" % len(overlap) if overlap else "\\textbf{0}",
            ))
        lines += [
            "\\bottomrule",
            "\\end{tabular}",
            "",
        ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "cases.tex"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[cases]   %s -- %d case(s), %d title image(s)" % (path, len(CASES), rendered))
    return path


if __name__ == "__main__":
    build()
