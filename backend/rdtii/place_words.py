"""Words that put data or equipment INSIDE or OUTSIDE a country, in every language we grade.

Why this exists. Three of the four pillar-6 indicators turn on a place: 6.2 and 6.3 need the
data or the server to be inside the country, 6.4 needs the data to go to another country, and
6.1 needs it stopped from leaving. The second-pass check asks the checker to QUOTE those words,
and on the Mongolia pillar-6 run of 2026-09-29 it quoted words that merely sit near the topic:
"хадгалах хугацаа болон байршил" ("storage period and location": a policy must STATE a location,
none is fixed), "Улсын мэдээллийн санд" ("in the State database"), "бусдад дамжуулж болно"
("may transfer to others": no foreign destination), and a list of armed-forces units for "the
words placing that infrastructure inside the country". Each quote was really in the snippet, so
the check passed. A quote that names no country, territory, border or abroad cannot show a place,
and that is a question of vocabulary the code can answer without asking a model again.

Matching is a casefolded substring test, so declined forms reach their stem: Монгол Улсаас,
Монгол Улсын and Монгол Улсад all contain "монгол улс"; территории and территорию contain
"территори". Words are chosen to be SPECIFIC, not topical: Mongolian "дотоод" alone also means
"internal" (a unit's internal operations) and "Улсын" alone means "State" (a State database), so
neither is on the list; the locative "дотоодод" is.
"""
from __future__ import annotations

PLACE_WORDS: tuple[str, ...] = (
    # English: every economy writes some statutes in it
    "outside", "overseas", "abroad", "foreign", "another country", "other country",
    "third country", "cross-border", "cross border", "beyond the", "territory", "territorial",
    "country", "countries", "jurisdiction", "in-country", "domestic", "locally",
    "registered office",
    "singapore", "australia", "malaysia", "india", "china", "mongolia", "thailand", "russia",
    "indonesia", "lao", "timor",
    # Malay
    "luar negara", "dalam negara",
    # Chinese
    "境内", "境外", "国内", "国外", "外国", "本国", "我国", "中华人民共和国", "中国", "出境", "跨境",
    # Mongolian
    "монгол улс", "нутаг дэвсгэр", "гадаад улс", "гадаадад", "гадаадын", "гадаад руу",
    "хилийн чанад", "улсын хил", "дотоодод",
    # Russian
    "территори", "российск", "россии", "за пределы", "за пределами", "иностран", "трансгранич",
    "зарубеж",
    # Thai
    "ราชอาณาจักร", "ประเทศไทย", "ต่างประเทศ", "ในประเทศ",
    # Indonesian
    "wilayah", "luar negeri", "dalam negeri", "negara lain",
    # Lao
    "ລາວ", "ຕ່າງປະເທດ", "ພາຍໃນປະເທດ", "ອານາເຂດ",
    # Portuguese (Timor-Leste)
    "território", "estrangeiro", "fora do país", "no país",
)


def names_place(text: str | None) -> bool:
    """True when `text` contains a word placing something inside or outside a country."""
    if not text:
        return False
    low = text.casefold()
    return any(w in low for w in PLACE_WORDS)
