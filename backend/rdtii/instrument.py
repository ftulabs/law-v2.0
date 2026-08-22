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


# An official portal publishes more than law. cac.gov.cn carries the Cyberspace
# Administration's press Q&A about a measure ("《数据出境安全评估办法》答记者问") and expert
# commentary on it ("《中华人民共和国数据安全法》解读") on the same site, in the same template,
# using the measure's exact vocabulary — so they retrieve at the top of the list and grade
# well. In a China pillar-7 run three such pages produced confident mappings; every one of
# them cited "(document)" rather than an article, because a press release has no articles to
# cite. That absent citation is the tell, and it is what this pattern is written from.
#
# NOT included, on purpose: "guidance", "guideline", "standard", "specification", "code of
# practice". Those ARE the cited instrument in several of the panel's own answers (Singapore's
# PDPC advisory guidelines, China's GB/T 39335 personal-information impact-assessment guide).
# Blocking them to catch a press release would cost real evidence.
_COMMENTARY = re.compile(
    r"答记者问"                                    # zh: "answering reporters' questions"
    r"|政策问答|法规问答"                            # zh: policy / regulatory Q&A
    r"|解读"                                       # zh: interpretation, incl. 专家解读/权威解读
    r"|新闻发布会|记者会"                            # zh: press conference
    r"|行业动态|新闻中心"                            # zh: industry news, newsroom
    r"|\bpress\s+(?:release|conference|statement)\b"
    r"|\bfrequently\s+asked\s+questions\b|\bFAQs?\b"
    r"|\bexplanatory\s+(?:note|memorandum)\b"
    r"|\bfact\s*sheet\b|\bnews\s+release\b"
    r"|\bcommentary\s+on\b"
    r"|разъяснени"                                 # ru: "clarifications"
    r"|тайлбар,?\s*зөвлөмж",                       # mn: "explanation / recommendation"
    re.I)


class Status(str, Enum):
    SCOREABLE = "scoreable"
    AMENDING = "amending"
    DRAFT = "draft"
    REPEALED = "repealed"
    COMMENTARY = "commentary"


#: Statuses that must never reach the submission workbook as they stand.
UNSCOREABLE = (Status.AMENDING, Status.DRAFT, Status.REPEALED, Status.COMMENTARY)

_NOTE = {
    Status.AMENDING: (
        "Amending act — RDTII scores the PRINCIPAL act as amended, not the amending "
        "instrument. Re-cite the principal act at the amended section."),
    Status.DRAFT: "Draft or bill — not in force, so it scores zero as a measure.",
    Status.REPEALED: "Repealed or revoked instrument — no longer in force, so it scores zero.",
    Status.COMMENTARY: (
        "Press release, Q&A or commentary published alongside a measure — not the measure "
        "itself. Re-cite the instrument it explains, at the article that carries the rule."),
}


def classify(law_name: str) -> Status:
    """The instrument class implied by a law's own title."""
    name = (law_name or "").strip()
    if not name:
        return Status.SCOREABLE
    if _COMMENTARY.search(name):
        return Status.COMMENTARY
    if _DRAFT.search(name):
        return Status.DRAFT
    if _reports_on_an_instrument(name):
        return Status.COMMENTARY
    if _REPEALED.search(name) and _REPEAL_LED.search(name):
        return Status.REPEALED
    if _AMENDING.search(name):
        return Status.AMENDING
    return Status.SCOREABLE


#: A Chinese instrument named inside 《》 with a REPORTING VERB around it: the page is an
#: article about the measure, not the measure. 《》 is the giveaway — a Chinese measure's own
#: title never quotes itself, so 网络安全审查办法 is the measure and
#: 国家互联网信息办公室等十三部门修订发布《网络安全审查办法》 is the news item announcing it.
#: Both were reaching the submission, the second with the site's navigation menu as its
#: Verbatim Snippet.
_QUOTED_INSTRUMENT = re.compile(r"《[^》]{2,60}》")
_REPORTING_VERB = re.compile(r"发布|公布|签署|印发|出台|下载|施行|实施")


def _reports_on_an_instrument(name: str) -> bool:
    """True for a page ABOUT a named instrument rather than the instrument itself.

    Deliberately not a standalone rejection. `extraction` drops a document only when it is
    commentary AND carries no article numbering, so a promulgating notice whose body actually
    IS the measure — 国务院关于印发《…》的通知 with its 第一条…第N条 attached — still passes: it
    has boundaries, so the pair does not hold. Being reported-about is a suspicion; being
    reported-about with nothing citable in it is the finding.
    """
    if not _QUOTED_INSTRUMENT.search(name or ""):
        return False
    stripped = _QUOTED_INSTRUMENT.sub("", name).strip("　 ")
    if not stripped:
        return False            # the title IS the quoted instrument, just wearing brackets
    return bool(_REPORTING_VERB.search(stripped))


def note_for(status: Status) -> str | None:
    """The sentence that goes into the row's Notes, or None when nothing is wrong."""
    return _NOTE.get(status)


def is_scoreable(law_name: str) -> bool:
    return classify(law_name) is Status.SCOREABLE
