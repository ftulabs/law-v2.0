"""Title-shaped vocabulary: what a law RELEVANT TO PILLARS 6 AND 7 IS CALLED.

WHY THIS MODULE EXISTS. Discovery ranks candidates before any body is fetched, so the only
text it has is a TITLE. Until 2026-09-11 six portal adapters (SG, TL, LA, TH, ID, CN) ranked
that title with `discovery._score`, which measures how many of an indicator's `query_terms`
appear in the text. Those terms are OPERATIVE PROVISION phrases — "with the consent of the
individual", "data shall be stored in" — and every one of pillar 6's forty-three is a phrase of
several words. A title is three to ten words and contains none of them. Measured on Singapore
Statutes Online, pillar 6:

    _score("Personal Data Protection Act 2012", pillar-6 indicators) -> 0.000
    _score("Animals and Birds Act 1965",        pillar-6 indicators) -> 0.000

Both scored 0.4000 once the adapter's base weight was added — as did all 524 current Acts. A
constant key makes `list.sort` a no-op (it is stable), so the order that survived into
`discovery._cap`'s trim to `discovery_max_docs` was SSO's own browse order, which is
alphabetical: the run kept twenty-two Acts beginning with "A" and dropped the PDPA, the
Cybersecurity Act and the Companies Act. Nothing raised, and the CSV said "No provision found".

So a title needs title vocabulary. `keywords.INDICATOR_SEARCH_TERMS[...]["name"]` already holds
exactly that for English — "personal data protection act", "companies act", "criminal procedure
code" — written as CONTIGUOUS TITLE SUBSTRINGS for AU's name-only OData API. `name_fragments`
below reuses it rather than restating it, and this module adds the one thing it lacks: NATIVE
title fragments for the economies that do not legislate in English.

WHAT THIS MODULE DELIBERATELY DOES NOT DO is decide whether a candidate is a law at all. That
question — press release, draft, repeal, amending act, commentary — is already answered by
`backend/rdtii/instrument.py`, from the same signal (the title) and with the same reasoning; a
second opinion here would only be a weaker one, free to disagree with it. Discovery calls
`instrument.classify` directly, and that is also where the China defect is handled: a pillar-6
run on 2026-09-11 returned twenty-two candidates containing ONE statute, the other twenty-one
being commentary, forum reports and drafts that each NAME the statute they discuss and so
scored exactly as highly as it did.

NOTHING HERE NAMES A SPECIFIC LAW AS THE ANSWER. These are law-TYPE names and drafting
conventions — the same rule `keywords.py` already documents for its English fragments. A
jurisdiction with no data-protection act simply matches nothing, which is the correct outcome.
"""
from __future__ import annotations

import re
import unicodedata

# ── 1. Native TITLE fragments ────────────────────────────────────────────────────────────────
#
# Keyed by the language codes `query_terms_i18n.ECONOMY_QUERY_LANG` already uses, so an economy
# maps to its vocabulary through the table that exists rather than a second one that could
# disagree with it. Values are lowercase substrings of a law's OWN NAME, not of its body.
NATIVE_NAME_FRAGMENTS: dict[str, list[str]] = {
    # Chinese titles are written without spaces, so these match as plain substrings.
    "zh": [
        "个人信息保护",      # personal information protection
        "数据安全",          # data security
        "网络安全",          # cybersecurity / network security
        "数据出境",          # outbound data transfer
        "关键信息基础设施",  # critical information infrastructure
        "电子商务",          # electronic commerce
        "电子签名",          # electronic signature
        "电信条例", "电信业务",   # telecommunications
        "征信业",            # credit reporting
        "保守国家秘密",      # protection of state secrets
        "反电信网络诈骗",    # anti-telecom-fraud
        "密码法", "商用密码",     # cryptography
        "刑法", "刑事诉讼",       # criminal code / criminal procedure
        "档案法",            # archives (record retention)
        "会计法",            # accounting (record retention)
        "国家安全法",        # national security
    ],
    "th": [
        "ข้อมูลส่วนบุคคล",        # personal data
        "ความมั่นคงปลอดภัยไซเบอร์",  # cybersecurity
        "ธุรกรรมทางอิเล็กทรอนิกส์",   # electronic transactions
        "คอมพิวเตอร์",            # computer(-related crime)
        "โทรคมนาคม",             # telecommunications
        "ข่าวสารของราชการ",       # official information
        "การบัญชี",               # accounting
        "อาญา",                  # criminal
    ],
    # Lao fragments are kept SHORT on purpose. The first draft guessed whole compound names
    # ("ອາຊະຍາກຳທາງໄຊເບີ", cybercrime) and scored 0.0000 against the gazette's real title for
    # the Cybersecurity Law, which is "ກົດໝາຍວ່າດ້ວຍ ຄວາມປອດໄພໄຊເບີ" — the two share only the
    # root ໄຊເບີ. Measured 2026-09-12 against the live index: every entry below is a root the
    # portal's own titles actually contain.
    "lo": [
        "ໄຊເບີ",             # cyber
        "ຂໍ້ມູນ",             # data / information
        "ອີເລັກໂຕຣນິກ", "ເອເລັກໂຕຣນິກ",   # electronic (both transliterations appear)
        "ໂທລະຄົມ",           # telecom
        "ການສື່ສານ",          # communications
        "ອາຍາ",              # criminal
        "ບັນຊີ",              # accounting / records
        "ສະຖິຕິ",            # statistics
        "ລັດວິສາຫະກິດ",       # state enterprise (record-keeping duties)
    ],
    "id": [
        "pelindungan data pribadi", "perlindungan data pribadi",
        "informasi dan transaksi elektronik",
        "keamanan siber", "keamanan dan ketahanan siber",
        "telekomunikasi",
        "penyelenggaraan sistem dan transaksi elektronik",
        "keterbukaan informasi publik",
        "rahasia dagang",
        "dokumen perusahaan",        # corporate record retention
        "hukum acara pidana", "kitab undang-undang hukum pidana",
    ],
    # Timor-Leste legislates in Portuguese; Tetum titles reuse the Portuguese nouns closely
    # enough that the distinctive stems below hit both.
    "pt": [
        "protecao de dados", "proteccao de dados", "dados pessoais",
        "telecomunicacoes",
        "comercio electronico", "transaccoes electronicas",
        "cibersegur",              # ciberseguranca / ciberseguranca
        "criminal", "processo penal", "codigo penal",
        "arquivo",                 # archives / retention
        "sociedades comerciais",   # companies
        "seguranca nacional",
    ],
    "ru": [
        "персональных данных", "персональные данные",
        "информации, информационных технологиях",
        "информационной безопасности",
        "связи",                   # communications
        "электронной подписи",
        "коммерческой тайне",
        "государственной тайне",
        "бухгалтерском учете",     # accounting records
        "уголовно-процессуальный", "уголовный кодекс",
    ],
    # Mongolian titles are handled by `adapter_mongolia._relevance`, which already ranks on the
    # portal's own declined forms; an entry here would be a second, weaker opinion.
}

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Case-folded, accent-stripped, punctuation-free — so a fragment matches a real title.

    Accents are stripped because Timor-Leste publishes the same instrument as "Protecção",
    "Proteccao" and "Protecao" depending on the year and the typesetter, and a fragment that
    only matches one spelling silently misses the other two. CJK and Thai/Lao text is
    unaffected by the fold, and those fragments match as plain substrings.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _WS.sub(" ", _PUNCT.sub(" ", text.casefold())).strip()


def name_fragments(indicators) -> list[str]:
    """The English title fragments for these indicators, from `keywords.py` — not restated here.

    Falls back to nothing (rather than to the indicators' own `query_terms`) for a pillar with
    no hand-written name pack: an operative phrase in a title-matching position is exactly the
    mistake this module exists to correct.
    """
    from .keywords import INDICATOR_SEARCH_TERMS
    out: list[str] = []
    for ind in indicators or []:
        pack = INDICATOR_SEARCH_TERMS.get(getattr(ind, "indicator_id", ""))
        if pack:
            out.extend(pack.get("name", []))
    return out


#: Economy -> the language its laws are TITLED in.
#:
#: This deliberately does NOT simply reuse `query_terms_i18n.ECONOMY_QUERY_LANG`, and Laos is
#: why. That table maps an economy to a key in `NATIVE_QUERY_TERMS`, so an economy with no
#: verified statutory PHRASES is absent from it entirely — Lao PDR has no entry at all. Reading
#: it here meant `native_fragments("LA")` returned [] and every Lao title scored 0.0000,
#: including "ກົດໝາຍວ່າດ້ວຍ ຄວາມປອດໄພໄຊເບີ" (the Cybersecurity Law). The two questions are not
#: the same one: "do we have verified provision phrases for this language" and "what language
#: are this economy's law TITLES in" have different answers, so they get different tables, and
#: the fallback below keeps them in step wherever they do agree.
TITLE_LANG: dict[str, str | None] = {
    "SG": None, "AU": None, "MY": None, "IN": None,     # legislate in English
    "CN": "zh", "TH": "th", "LA": "lo", "ID": "id", "TL": "pt", "RU": "ru",
    "MN": None,                    # ranked by `adapter_mongolia._relevance`; see the table above
}


def native_fragments(economy: str | None) -> list[str]:
    """Native-language title fragments for an economy."""
    if not economy:
        return []
    code = economy.upper()
    if code in TITLE_LANG:
        lang = TITLE_LANG[code]
    else:
        from .query_terms_i18n import ECONOMY_QUERY_LANG
        lang = ECONOMY_QUERY_LANG.get(code)
    return NATIVE_NAME_FRAGMENTS.get(lang or "", [])
