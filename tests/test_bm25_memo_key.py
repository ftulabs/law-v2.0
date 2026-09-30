"""The memoised BM25 index must follow the TEXT, not only the provision ids."""
from backend.pipeline import retrieval
from backend.schemas import Economy, Provision


def _corpus(text):
    return [Provision(provision_id="SG-abc#p1", doc_id="SG-abc", economy=Economy.SG,
                      law_name="Act", article_section="Section 1", verbatim_snippet=text,
                      source_url="https://sso.agc.gov.sg/Act/X")]


def test_same_ids_new_text_is_a_new_index():
    """A re-fetched, amended document keeps every provision id (they come from the URL)."""
    assert retrieval._corpus_key(_corpus("personal data must be stored")) != \
        retrieval._corpus_key(_corpus("personal data may be transferred"))
    _, old = retrieval._corpus_and_bm25(_corpus("personal data must be stored"))
    _, new = retrieval._corpus_and_bm25(_corpus("personal data may be transferred"))
    assert old is not new


def test_same_corpus_is_built_once():
    a = retrieval._corpus_and_bm25(_corpus("same words"))
    b = retrieval._corpus_and_bm25(_corpus("same words"))
    assert a is b
