"""Literal-phrase bonus looks at the WHOLE provision for native-language economies, and keeps
the measured 2,048-character window for SG/AU/MY (see retrieval._phrase_text)."""
from backend.pipeline.retrieval import _phrase_bonus
from backend.rdtii.indicators import INDICATORS
from backend.rdtii.query_terms_i18n import native_terms
from backend.schemas import Economy, Provision

IND = {i.indicator_id: i for i in INDICATORS}


def _prov(economy, text):
    return Provision(provision_id="x#p1", doc_id="x", economy=economy, law_name="L",
                     article_section="Статья 18", verbatim_snippet=text, source_url="u")


def test_a_russian_phrase_past_the_embedding_window_and_behind_no_break_spaces_counts():
    tail = ("5. При сборе персональных данных оператор обязан обеспечить обработку; обработка с "
            "использованием баз\xa0данных, находящихся за\xa0пределами территории Российской "
            "Федерации, не\xa0допускаются.")
    text = "1. Оператор обязан предоставить сведения. " * 80 + tail      # tail beyond 2,048 chars
    assert len(text) - len(tail) > 2048
    assert _phrase_bonus(IND["P6-I2"], [_prov(Economy.RU, text)],
                         native_terms("P6-I2", "RU"))[0] > 0


def test_english_economies_keep_the_measured_window():
    text = "An organisation must comply with this Part. " * 60 + "kept at the registered office"
    assert _phrase_bonus(IND["P6-I2"], [_prov(Economy.SG, text)])[0] == 0
