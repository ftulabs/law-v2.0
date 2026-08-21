"""Round-2 multilingual expansion: China, India, Mongolia.

Every test here pins a failure that is SILENT in production — a Chinese corpus does not throw,
it just quietly retrieves nothing and reports "no provision found", which reads exactly like a
country that has no such law.
"""
import pytest

from backend.pipeline import ranking, retrieval
from backend.pipeline.extraction import _boundaries
from backend.providers.ocr_languages import is_latin_script, profile_for
from backend.rdtii.query_terms_i18n import native_terms
from backend.schemas import DiscoveryTag, Economy, OCRMetrics, Provision, resolve_economy


def _prov(economy, label, text, doc_id="d1", law="Test Law"):
    return Provision(provision_id=f"{doc_id}:{label}", doc_id=doc_id, economy=economy,
                     law_name=law, article_section=label, verbatim_snippet=text,
                     source_url="https://example.test/x", discovery_tag=DiscoveryTag.NEW,
                     ocr=OCRMetrics())


# ── economies ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value,expected", [
    ("China", Economy.CN), ("PRC", Economy.CN), ("cn", Economy.CN),
    ("India", Economy.IN), ("bharat", Economy.IN), ("Republic of India", Economy.IN),
    ("Mongolia", Economy.MN), ("Mongolla", Economy.MN),
    ("Republic of Singapore", Economy.SG),          # must not be dragged to "republic of india"
])
def test_round2_economies_resolve(value, expected):
    assert resolve_economy(value) == expected


def test_indonesia_resolves_to_indonesia_and_never_to_india():
    """At the old 0.7 fuzzy cutoff "indonesia" scored 0.71 against "india" and resolved to the
    wrong economy — silently producing a full Indian run for an Indonesian request. Indonesia
    is now one of the live-test nine, so the assertion gets stronger rather than going away:
    it must resolve, and it must resolve to itself."""
    assert resolve_economy("Indonesia") == Economy.ID
    assert resolve_economy("indoneisa") == Economy.ID          # the typo path, still not India


def test_an_economy_we_do_not_know_still_raises():
    """The fuzzy matcher must not stretch to cover anything at all now that twelve aliases sit
    in the table — an unknown economy is a question for a human, not a guess."""
    with pytest.raises(ValueError):
        resolve_economy("Ruritania")


# ── tokenisation ─────────────────────────────────────────────────────────────────────
def test_ascii_tokenisation_is_unchanged_from_round1():
    """The Round-1 retrieval parameters were swept, not chosen (CLAUDE.md §7). They stay valid
    only if Latin-script tokenisation is byte-identical to what they were measured against."""
    import re
    text = "Personal data shall not be transferred outside Singapore under s26(1) of the PDPA."
    assert retrieval._tok(text) == re.compile(r"[a-z0-9]+").findall(text.lower())


def test_chinese_text_produces_tokens_at_all():
    """[a-z0-9]+ matched NOTHING in Chinese, so BM25 scored every Chinese provision zero."""
    toks = retrieval._tok("个人信息应当在境内存储")
    assert toks and all(len(t) == 2 for t in toks)      # character bigrams
    assert "境内" in toks and "存储" in toks


def test_cyrillic_mongolian_tokenises_as_words():
    toks = retrieval._tok("14.1.Мэдээлэл дамжуулахыг хориглоно")
    assert "мэдээлэл" in toks and "хориглоно" in toks


# ── retrieval end-to-end on a non-Latin corpus ───────────────────────────────────────
@pytest.fixture
def cn_corpus():
    return [
        _prov(Economy.CN, "第四十条", "关键信息基础设施运营者应当将在中华人民共和国境内收集和产生的"
                                     "个人信息存储在境内。", doc_id="pipl"),
        _prov(Economy.CN, "第一条", "为了保护个人信息权益，规范个人信息处理活动，制定本法。", doc_id="pipl"),
        _prov(Economy.CN, "第二十一条", "网络运营者应当留存相关的网络日志不少于六个月。", doc_id="csl"),
        _prov(Economy.CN, "第五十二条", "个人信息处理者应当指定个人信息保护负责人。", doc_id="pipl"),
        _prov(Economy.CN, "第三十八条", "确需向中华人民共和国境外提供个人信息的，应当通过国家网信部门"
                                       "组织的安全评估。", doc_id="pipl"),
    ]


@pytest.mark.parametrize("indicator,expected", [
    ("P6-I2", "第四十条"),      # local storage
    ("P7-I3", "第二十一条"),     # minimum retention
    ("P7-I4", "第五十二条"),     # DPO
    ("P6-I4", "第三十八条"),     # conditional flow
])
def test_chinese_retrieval_ranks_the_right_article_first(cn_corpus, indicator, expected, monkeypatch):
    """BM25-only, so this measures the lexical fix alone: before it, every score was 0 and the
    ranking was arbitrary corpus order."""
    from backend.config import settings
    monkeypatch.setattr(settings, "cross_encoder", "off")
    monkeypatch.setattr(settings, "embed_model", "")
    got = retrieval.retrieve(indicator, cn_corpus, top_k=1)
    assert got and got[0].provision.article_section == expected


def test_native_terms_are_additive_not_a_replacement():
    """A wrong native term must only fail to match — it must never displace an English term
    that was already working."""
    from backend.rdtii import get_indicator
    ind = get_indicator("P6-I2")
    for economy in ("CN", "MN", "SG"):
        phrases = retrieval._phrases(ind, native_terms("P6-I2", economy))
        assert set(t.lower() for t in ind.query_terms if len(t.split()) >= 2) <= set(phrases)


def test_english_economies_get_no_native_terms():
    assert native_terms("P6-I2", "IN") == []       # Indian statutes are English
    assert native_terms("P6-I2", "AU") == []
    assert native_terms("P6-I2", "CN")             # China does


def test_chinese_phrase_earns_the_literal_match_bonus():
    """`len(term.split()) >= 2` scores every Chinese phrase zero — Chinese has no spaces."""
    assert retrieval._is_phrase("境内存储")
    assert retrieval._is_phrase("local storage")
    assert not retrieval._is_phrase("storage")


# ── cross-encoder selection ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("economy", ["SG", "AU", "MY", "IN"])
def test_latin_economies_use_the_english_reranker(economy):
    from backend.config import settings
    assert is_latin_script(economy)
    assert ranking._ce_model_for(economy) == settings.cross_encoder_model


@pytest.mark.parametrize("economy", ["CN", "MN"])
def test_non_latin_runs_without_a_reranker_by_default(economy):
    """An English cross-encoder on Chinese text is noise, so it must never be the fallback —
    but the multilingual one is 25x slower (measured: 9.9 pairs/s against 245), and the first
    full China run spent ELEVEN HOURS inside retrieval for 268 provisions where Singapore spent
    100 seconds for 3,218. The live test allows sixty minutes in total. So the default for a
    non-Latin economy is no reranker at all: BM25 + dense embeddings returned that same run in
    30 seconds, a 35x speed-up."""
    assert not is_latin_script(economy)
    assert ranking._ce_model_for(economy) is None
    assert ranking._cross_encoder(economy) is None


@pytest.mark.parametrize("economy", ["CN", "MN"])
def test_the_multilingual_reranker_is_still_reachable_when_asked_for(economy, monkeypatch):
    """Turning it on stays a deliberate choice for someone with a GPU or time to spare. The
    capability is not removed, only taken off the default path."""
    from backend.config import settings
    monkeypatch.setattr(settings, "cross_encoder_multilingual_enabled", True)
    assert ranking._ce_model_for(economy) == settings.cross_encoder_model_multilingual


def test_non_latin_never_falls_back_to_the_english_reranker(monkeypatch):
    """Even with the multilingual reranker switched on and failing to load, the English model
    must not be substituted — it would score Chinese arbitrarily and that noise is fused into
    the ranking at the same weight as BM25."""
    from backend.config import settings
    monkeypatch.setattr(settings, "cross_encoder_multilingual_enabled", True)
    monkeypatch.setattr(ranking, "_CE", {})
    monkeypatch.setattr(ranking, "_CE_FAILED", {ranking._ce_model_for("CN")})
    assert ranking._cross_encoder("CN") is None


# ── provision boundaries ─────────────────────────────────────────────────────────────
def test_chinese_articles_split_on_han_numerals():
    text = ("第一条 为了保护个人信息权益，制定本法。\n"
            "第四十条 关键信息基础设施运营者应当将个人信息存储在境内。\n"
            "第五十二条 应当指定个人信息保护负责人。")
    assert [b[2] for b in _boundaries(text, Economy.CN)] == ["第一条", "第四十条", "第五十二条"]


def test_chinese_cross_reference_mid_sentence_is_not_a_boundary():
    """依照本法第三十八条的规定 is a cross-reference, not a heading — the same trap the Latin
    patterns are line-anchored to avoid."""
    text = "第四十条 依照本法第三十八条的规定，确需向境外提供的，应当通过安全评估。"
    assert [b[2] for b in _boundaries(text, Economy.CN)] == ["第四十条"]


def test_mongolian_articles_split_on_zuil_headings():
    text = ("14 дүгээр зүйл. Гадаад улсад мэдээлэл дамжуулах\n"
            "14.1.Мэдээлэл дамжуулахыг хориглоно.\n"
            "20 дугаар зүйл. Мэдээллийн аюулгүй байдал\n"
            "20.1.Мэдээлэл хариуцагч арга хэмжээ авна.")
    assert [b[2] for b in _boundaries(text, Economy.MN)] == ["14 дүгээр зүйл", "20 дугаар зүйл"]


def test_mongolian_short_instrument_is_not_discarded_by_the_latin_fallback():
    """Two real articles must survive; the Latin fallback finds nothing in Cyrillic and would
    have replaced them with an empty list."""
    text = "1 дүгээр зүйл. Зорилт\n2 дугаар зүйл. Хамрах хүрээ"
    assert len(_boundaries(text, Economy.MN)) == 2


def test_india_uses_the_numbered_english_branch():
    text = ("2. Definitions.—(1) In this Act, unless the context otherwise requires,—\n"
            "43A. Compensation for failure to protect data.  Where a body corporate is negligent.")
    assert len(_boundaries(text, Economy.IN)) == 2


# ── LLM prompt ───────────────────────────────────────────────────────────────────────
def test_prompt_declares_the_snippet_language():
    from backend.pipeline.mapping import _user_prompt
    from backend.rdtii import get_indicator
    ind = get_indicator("P6-I2")
    assert "<SNIPPET_LANGUAGE>Chinese (Simplified)</SNIPPET_LANGUAGE>" in _user_prompt(
        ind, _prov(Economy.CN, "第四十条", "应当将个人信息存储在境内。"))
    assert "<SNIPPET_LANGUAGE>English</SNIPPET_LANGUAGE>" in _user_prompt(
        ind, _prov(Economy.IN, "43A", "Where a body corporate is negligent."))


def test_system_prompt_forbids_translating_the_verbatim_snippet():
    """The snippet is what gets cited in the Verbatim Snippet column; a translated citation is
    a false citation."""
    from backend.pipeline.mapping import SYSTEM
    assert "8. LANGUAGE" in SYSTEM
    assert "never rewrite it into English" in SYSTEM
    assert "must be written in ENGLISH" in SYSTEM          # but the OUTPUT is English
    assert "关键信息基础设施" in SYSTEM                       # a worked example in Chinese


def test_language_profiles_name_the_statutory_language():
    assert profile_for("CN").language == "Chinese (Simplified)"
    assert profile_for("MN").language == "Mongolian"
    assert profile_for("IN").language == "English"
