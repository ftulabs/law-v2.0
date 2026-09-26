"""Native-language retrieval vocabulary for the RDTII indicators.

`indicators.py` holds English `query_terms`, which is all Round 1 needed — SG, AU and MY
publish in English. For Round 2 that assumption breaks: an English phrase like "shall not be
transferred" has zero lexical overlap with 不得向境外提供, so BM25 contributes nothing and the
hybrid ranker falls back to the dense signal alone at alpha=0.65 weighting against it.

These terms are added TO the English ones, never instead of them. Two reasons: an economy's
corpus is usually mixed (Chinese portals carry English translations, Indian statutes are
English, Mongolian PDFs quote treaty names in English), and keeping both means a wrong guess
here can only fail to match — it cannot displace a term that was working.

PROVENANCE — this matters, because a term nobody can source is a term nobody can check:

* `zh` phrases are quoted from the operative articles themselves and are verifiable:
  PIPL art.40 「应当在中华人民共和国境内存储」, art.38 「安全评估 / 标准合同 / 保护认证」,
  art.52 「个人信息保护负责人」, art.55 「个人信息保护影响评估」; Cybersecurity Law art.37
  「应当在境内存储」, art.21 「留存不少于六个月」, art.28 「技术支持和协助」.
* `mn` is a SEED vocabulary of the ordinary statutory words (хадгалах = store, дамжуулах =
  transfer, хориглох = prohibit, зөвшөөрөл = permission), NOT quoted provision text. It has
  not been validated against a crawled corpus yet. Run `tools/audit_native_terms.py` once
  Mongolian laws are in the corpus and replace anything that never fires — a term that
  matches nothing is dead weight, and one that matches everything is worse than dead.

Economies whose statutes are published in English (India) map to None and are unaffected.
"""
from __future__ import annotations

# Economy → language key below. None = statutes are published in English, nothing to add.
ECONOMY_QUERY_LANG: dict[str, str | None] = {
    "SG": None, "AU": None, "MY": None,      # English (MY's AGC portal is bilingual EN/MS)
    "IN": None,                              # Indian statutes are enacted and published in English
    "CN": "zh",
    "MN": "mn",
    # staged for later finals, unvalidated
    "TH": "th", "RU": "ru", "ID": "id",
    # Timor-Leste legislates in Portuguese and Tetum, often publishing the same instrument in
    # both. Portuguese is mapped because that is what the operative text is drafted in; a
    # Tetum block would be additive on the lexical side and is not written yet, so a
    # Tetum-only instrument currently retrieves on the dense stage alone.
    "TL": "pt",
}

NATIVE_QUERY_TERMS: dict[str, dict[str, list[str]]] = {
    "zh": {
        "P6-I1": ["不得向境外提供", "禁止出境", "不得出境", "应当在境内处理", "境内处理"],
        "P6-I2": ["应当在中华人民共和国境内存储", "应当在境内存储", "境内存储", "本地存储",
                  "存储于境内", "在境内保存"],
        "P6-I3": ["服务器应当设在境内", "境内服务器", "数据中心", "关键信息基础设施",
                  "基础设施应当位于"],
        "P6-I4": ["确需向境外提供", "数据出境安全评估", "安全评估", "个人信息保护认证",
                  "标准合同", "经批准", "取得个人单独同意"],
        "P7-I1": ["个人信息保护法", "个人信息处理者", "处理个人信息", "个人信息权益",
                  "处理个人信息的原则"],
        "P7-I2": ["网络安全法", "网络安全等级保护", "关键信息基础设施安全保护",
                  "网络安全事件应急预案", "数据安全法"],
        "P7-I3": ["留存不少于六个月", "保存期限", "留存期限", "不少于", "保存不少于",
                  "最短保存期限"],
        "P7-I4": ["个人信息保护负责人", "个人信息保护影响评估", "事前风险评估",
                  "个人信息保护主管人员"],
        "P7-I5": ["技术支持和协助", "公安机关", "国家安全机关", "依法要求提供",
                  "有权调取", "配合国家机关"],
    },
    "mn": {
        # SEED vocabulary — see PROVENANCE above. Mongolian is agglutinative, so these are
        # kept as stems: BM25 tokenises "дамжуулахыг" whole and will not match "дамжуулах",
        # which is exactly why the audit tool exists.
        "P6-I1": ["хориглоно", "хориглох", "дамжуулахыг хориглоно", "гадаад улсад дамжуулах"],
        "P6-I2": ["нутаг дэвсгэрт хадгалах", "хадгалах", "хадгалалт", "дотоодод хадгалах"],
        "P6-I3": ["сервер", "дэд бүтэц", "мэдээллийн систем", "нутаг дэвсгэрт байрлах"],
        "P6-I4": ["зөвшөөрөл", "зөвшөөрснөөс бусад", "олон улсын гэрээ", "мэдээлэл дамжуулах"],
        "P7-I1": ["хувь хүний мэдээлэл хамгаалах", "мэдээлэл хамгаалах тухай хууль",
                  "мэдээлэл боловсруулах"],
        "P7-I2": ["кибер аюулгүй байдал", "мэдээллийн аюулгүй байдал", "кибер халдлага"],
        "P7-I3": ["хадгалах хугацаа", "хугацаанд хадгална", "жилээс доошгүй", "устгах"],
        "P7-I4": ["эрсдэлийн үнэлгээ", "мэдээлэл хамгаалах ажилтан", "үнэлгээ хийх"],
        "P7-I5": ["эрх бүхий байгууллага", "төрийн байгууллага", "шаардах эрхтэй",
                  "хууль сахиулах байгууллага"],
    },
    "pt": {
        # SEED vocabulary — see PROVENANCE above. Portuguese, as used in Timor-Leste's own
        # legal drafting (European Portuguese forms, not Brazilian: "protecção"/"proteção"
        # both occur in the gazette because the 1990 orthographic agreement was adopted
        # unevenly, so BOTH spellings are listed where they differ).
        #
        # Two things make Portuguese cheap to add and easy to get wrong. Cheap: it is Latin
        # script, so BM25 tokenises it as words with no segmenter. Easy to get wrong: article
        # references are written "Artigo 1.º" with U+00BA, and NFKC rewrites that to "1.o" —
        # see the TL note in providers/ocr_languages.py. Nothing here depends on that, but a
        # citation matcher does.
        "P6-I1": ["é proibida a transferência", "proibida a transferência internacional",
                  "não podem ser transferidos", "tratados em território nacional",
                  "tratamento em território nacional"],
        "P6-I2": ["armazenados em território nacional", "conservados em território nacional",
                  "armazenamento em território nacional", "manter em território nacional",
                  "base de dados localizada"],
        "P6-I3": ["servidores localizados em território nacional", "centro de dados",
                  "infra-estrutura", "infraestrutura", "servidor localizado"],
        "P6-I4": ["transferência internacional de dados", "consentimento do titular",
                  "nível adequado de protecção", "nível adequado de proteção",
                  "autorização prévia", "cláusulas contratuais"],
        "P7-I1": ["protecção de dados pessoais", "proteção de dados pessoais",
                  "tratamento de dados pessoais", "titular dos dados", "dados pessoais"],
        "P7-I2": ["segurança cibernética", "cibersegurança", "segurança da informação",
                  "incidente de segurança"],
        "P7-I3": ["prazo de conservação", "conservados pelo prazo", "prazo mínimo",
                  "período de conservação"],
        "P7-I4": ["encarregado de protecção de dados", "encarregado de proteção de dados",
                  "avaliação de impacto", "avaliação de impacto sobre a protecção de dados"],
        "P7-I5": ["autoridade judiciária", "autoridades competentes",
                  "acesso pelas autoridades", "investigação criminal", "ordem judicial"],
    },
    # th / ru / id were mapped in ECONOMY_QUERY_LANG above with NO block here, so from their
    # first live run until 2026-09-26 their lexical side matched English terms against Thai,
    # Cyrillic and Indonesian text — near-zero BM25 on every provision, ranking by the dense
    # stage alone. Measured cost: Thailand's PDPA มาตรา 28 (cross-border transfer, the 6.4
    # answer) was extracted as its own article and still never reached the 6.4 shortlist; its
    # retrieval score was 0.28. These are SEED vocabularies written from the operative wording
    # of each economy's own statutes — drafting phrases, never law titles — and carry the same
    # caveat as "mn": validate with tools/audit_native_terms.py before trusting them.
    "th": {
        # Thai is unsegmented; retrieval indexes it as character bigrams (retrieval._tok), so a
        # phrase matches wherever its characters run together — no word segmenter needed.
        "P6-I1": ["ห้ามส่งหรือโอน", "ห้ามโอนข้อมูล", "ประมวลผลภายในราชอาณาจักร",
                  "ภายในราชอาณาจักร"],
        "P6-I2": ["จัดเก็บไว้ในราชอาณาจักร", "เก็บรักษาไว้ในราชอาณาจักร", "ในราชอาณาจักร",
                  "ศูนย์ข้อมูลในประเทศ"],
        "P6-I3": ["ศูนย์ข้อมูล", "เครื่องแม่ข่าย", "ระบบคอมพิวเตอร์ตั้งอยู่ในราชอาณาจักร"],
        "P6-I4": ["ส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ", "ไปยังต่างประเทศ",
                  "มาตรฐานการคุ้มครองข้อมูลส่วนบุคคลที่เพียงพอ", "ได้รับความยินยอม",
                  "องค์การระหว่างประเทศ"],
        "P7-I1": ["ข้อมูลส่วนบุคคล", "เจ้าของข้อมูลส่วนบุคคล", "ผู้ควบคุมข้อมูลส่วนบุคคล",
                  "การเก็บรวบรวม ใช้ หรือเปิดเผย"],
        "P7-I2": ["การรักษาความมั่นคงปลอดภัยไซเบอร์", "ภัยคุกคามทางไซเบอร์",
                  "โครงสร้างพื้นฐานสำคัญทางสารสนเทศ", "ความมั่นคงปลอดภัยไซเบอร์"],
        "P7-I3": ["เก็บรักษาข้อมูลจราจรทางคอมพิวเตอร์", "ไม่น้อยกว่า", "เก็บรักษาไว้ไม่น้อยกว่า",
                  "ระยะเวลาการเก็บรักษา"],
        "P7-I4": ["เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล", "ประเมินผลกระทบ",
                  "การประเมินความเสี่ยง"],
        "P7-I5": ["พนักงานเจ้าหน้าที่", "พนักงานสอบสวน", "มีหนังสือเรียก", "ให้ส่งข้อมูล",
                  "เข้าถึงข้อมูล", "โดยไม่ต้องมีหมาย"],
    },
    "ru": {
        # Inflected: BM25 matches the surface form, so the forms listed are the ones statutes
        # actually print (genitive "персональных данных" far more than nominative).
        "P6-I1": ["запрещается передача", "не допускается", "за пределы территории Российской Федерации"],
        "P6-I2": ["баз данных, находящихся на территории Российской Федерации",
                  "находящихся на территории Российской Федерации", "обеспечить запись, систематизацию, накопление, хранение",
                  "хранение на территории Российской Федерации"],
        "P6-I3": ["на территории Российской Федерации", "технических средств",
                  "центров обработки данных"],
        "P6-I4": ["трансграничная передача персональных данных",
                  "трансграничной передачи персональных данных", "иностранных государств",
                  "адекватной защиты прав субъектов персональных данных",
                  "уведомить уполномоченный орган"],
        "P7-I1": ["персональных данных", "субъекта персональных данных",
                  "обработка персональных данных", "оператор"],
        "P7-I2": ["критической информационной инфраструктуры", "безопасности критической",
                  "компьютерных атак", "компьютерных инцидентов", "защиты информации"],
        "P7-I3": ["хранить", "в течение", "не менее", "срок хранения", "хранению"],
        "P7-I4": ["лицо, ответственное за организацию обработки персональных данных",
                  "ответственного за организацию обработки", "оценки вреда"],
        "P7-I5": ["оперативно-розыскной деятельности", "органам, осуществляющим оперативно-розыскную",
                  "по запросу", "предоставлять", "органов федеральной службы безопасности"],
    },
    "id": {
        # Latin script, space-segmented; Indonesian drafting is highly formulaic ("wajib …",
        # "dalam wilayah Negara Republik Indonesia"), which is what makes a seed list useful.
        "P6-I1": ["dilarang mentransfer", "tidak boleh dikirim ke luar", "wajib diproses di dalam negeri"],
        "P6-I2": ["wajib ditempatkan dalam wilayah", "di wilayah Indonesia", "dalam wilayah hukum Negara Republik Indonesia",
                  "melakukan penyimpanan", "disimpan di wilayah"],
        "P6-I3": ["pusat data", "pusat pemulihan bencana", "wajib menempatkan pusat data",
                  "di wilayah Indonesia"],
        "P6-I4": ["transfer Data Pribadi", "ke luar wilayah hukum Negara Republik Indonesia",
                  "tingkat Pelindungan Data Pribadi yang setara", "persetujuan Subjek Data Pribadi",
                  "pengiriman Data Pribadi"],
        "P7-I1": ["Pelindungan Data Pribadi", "Subjek Data Pribadi", "Pengendali Data Pribadi",
                  "pemrosesan Data Pribadi"],
        "P7-I2": ["keamanan siber", "Badan Siber dan Sandi Negara", "insiden siber",
                  "keamanan informasi", "infrastruktur informasi vital"],
        "P7-I3": ["wajib menyimpan", "paling singkat", "jangka waktu penyimpanan",
                  "retensi", "paling sedikit"],
        "P7-I4": ["penilaian dampak Pelindungan Data Pribadi", "pejabat atau petugas yang melaksanakan fungsi Pelindungan Data Pribadi",
                  "wajib menunjuk"],
        "P7-I5": ["aparat penegak hukum", "atas permintaan", "memberikan akses",
                  "penyidik", "wajib memberikan"],
    },
}


def native_terms(indicator_id: str, economy: str | None) -> list[str]:
    """Extra query terms for this indicator in the economy's statutory language."""
    lang = ECONOMY_QUERY_LANG.get((economy or "").upper())
    if not lang:
        return []
    return NATIVE_QUERY_TERMS.get(lang, {}).get(indicator_id, [])


def has_native_terms(economy: str | None) -> bool:
    lang = ECONOMY_QUERY_LANG.get((economy or "").upper())
    return bool(lang and NATIVE_QUERY_TERMS.get(lang))
