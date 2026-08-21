"""Is this instrument scoreable at all — or is it a draft, a repeal, or an amending act?

The final-round Indicator Reference states the rule plainly: a measure that is a draft, a bill,
a repealed instrument or an amending act scores ZERO regardless of what it says. The trap is
that all three read exactly like the real thing to every stage upstream of here. An amending
act is genuine legislation on the official portal, in force, using the indicator's own
vocabulary — "section 26 is amended by inserting … personal data … outside Singapore" — so it
retrieves well, grades well, and produces a confident row that scores nothing.

Three categories, and they are NOT the same error:

    DRAFT      a bill or consultation text. Not law yet. Cite it and the row is wrong today.
    REPEALED   was law, is not now. Cite it and the row is wrong today for the other reason.
    AMENDING   real law, but the wrong CITATION: an amending act edits a principal act, and
               the scoreable provision is the principal act's section as amended. This is the
               only one of the three where the underlying finding is right and just the
               reference is wrong — so it is the one worth telling a reviewer about rather
               than dropping, because the fix is to re-cite, not to discard.

Detection is on the instrument's NAME, deliberately. The title is where every jurisdiction
states this — "(Amendment) Act", "Bill", "Repeal Act", "Draft" — while body text says
"amended" constantly inside perfectly scoreable principal acts. Reading the body would flag
half of them.

Nothing here hardcodes a law: these are the drafting conventions of the instrument class,
which is what distinguishes this from a seed list of answers.
"""
from __future__ import annotations

import re
from enum import Enum

# Native-language equivalents matter because six of the nine live-test economies do not
# legislate in English, and an amending act in Chinese ("修正案") or Russian ("о внесении
# изменений") is exactly as unscoreable as one in English.
_AMENDING = re.compile(
    r"\(\s*amendment[^)]*\)"                       # "(Amendment) Act 2020", "(Amendment No. 2)"
    r"|\bamendment\s+(?:act|law|ordinance|decree|regulations?)\b"
    r"|\bact\s+to\s+amend\b|\blaw\s+on\s+amendments?\b"
    r"|о\s+внесении\s+изменени"                    # ru: "on the introduction of amendments"
    r"|修正案|修改决定"                              # zh: amendment / decision to amend
    r"|нэмэлт,?\s*өөрчлөлт"                        # mn: "additions and changes"
    r"|sửa\s+đổi,?\s*bổ\s+sung"                    # vi: "amending and supplementing"
    r"|perubahan\s+atas"                           # id: "amendment to"
    r"|pindaan",                                   # ms: "amendment"
    re.I)

_DRAFT = re.compile(
    r"\bbill\b|\bdraft\b|\bexposure\s+draft\b|\bconsultation\s+(?:paper|draft)\b"
    r"|\bproposed\s+(?:act|law|amendment)\b"
    r"|законопроект|草案|征求意见稿|dự\s+thảo|rancangan\s+undang|төсөл",
    re.I)

_REPEALED = re.compile(
    r"\brepeal(?:ed|ing)?\b|\brevocation\b|\brevoked\b|\bceased\s+to\s+have\s+effect\b"
    r"|утратил[аои]?\s+силу|废止|已废止|hết\s+hiệu\s+lực|dicabut",
    re.I)

# "Repeal" inside a principal act's own long title is normal drafting — the Personal Data
# Protection Act 2012 repeals earlier provisions and is still THE scoreable instrument. Only a
# title whose SUBJECT is repeal disqualifies it, so require the repeal word to lead.
_REPEAL_LED = re.compile(r"^\s*(?:the\s+)?[\w\s'\-]{0,40}\brepeal\b", re.I)


class Status(str, Enum):
    SCOREABLE = "scoreable"
    AMENDING = "amending"
    DRAFT = "draft"
    REPEALED = "repealed"


#: Statuses that must never reach the submission workbook as they stand.
UNSCOREABLE = (Status.AMENDING, Status.DRAFT, Status.REPEALED)

_NOTE = {
    Status.AMENDING: (
        "Amending act — RDTII scores the PRINCIPAL act as amended, not the amending "
        "instrument. Re-cite the principal act at the amended section."),
    Status.DRAFT: "Draft or bill — not in force, so it scores zero as a measure.",
    Status.REPEALED: "Repealed or revoked instrument — no longer in force, so it scores zero.",
}


def classify(law_name: str) -> Status:
    """The instrument class implied by a law's own title."""
    name = (law_name or "").strip()
    if not name:
        return Status.SCOREABLE
    if _DRAFT.search(name):
        return Status.DRAFT
    if _REPEALED.search(name) and _REPEAL_LED.search(name):
        return Status.REPEALED
    if _AMENDING.search(name):
        return Status.AMENDING
    return Status.SCOREABLE


def note_for(status: Status) -> str | None:
    """The sentence that goes into the row's Notes, or None when nothing is wrong."""
    return _NOTE.get(status)


def is_scoreable(law_name: str) -> bool:
    return classify(law_name) is Status.SCOREABLE
