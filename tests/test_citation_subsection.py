"""Citation granularity (Article/Section column): a section's label must reflect the
SPECIFIC subsection the grader actually relied on for THIS mapping — not a subsection
guessed once at extraction time (the old "(1)" bug, always wrong when the operative rule
sits elsewhere) and not an invented one either. No subsection identified => cite the whole
section, matching the verbatim snippet (which is always the full section text).
"""
from backend.pipeline import mapping
from backend.rdtii import get_indicators
from backend.schemas import Economy, OCRMetrics, Provision

SNIPPET = (
    "26 Cross-border disclosure of personal information\n"
    "(1) An entity may disclose personal information to an overseas recipient.\n"
    "(2) The entity must take reasonable steps before disclosure unless an exception applies.\n"
    "(3) The exceptions in this section do not apply to sensitive information.\n"
)


def _prov():
    return Provision(provision_id="p1", doc_id="d", economy=Economy.AU,
                     law_name="Privacy Act 1988", article_section="Section 26",
                     verbatim_snippet=SNIPPET, source_url="u", ocr=OCRMetrics())


class _FakeLLM:
    name = "fake"
    model_version = "fake-1"

    def __init__(self, subsection):
        self.subsection = subsection

    def complete_json(self, system, user):
        return {"relevant": True, "legal_match": 0.9, "scope_alignment": 1.0,
                "subsection": self.subsection, "rationale": "x"}


def _map_one(subsection):
    inds = get_indicators(6)[:1]
    out = mapping.map_provisions(run_id="t", provisions=[_prov()], pillar=6, indicators=inds,
                                 llm=_FakeLLM(subsection), top_k=5, log=lambda *_: None)
    return out[0]


def test_valid_subsection_present_in_snippet_is_appended():
    m = _map_one("(2)")
    assert m.article_section == "Section 26(2)"


def test_hallucinated_subsection_not_in_snippet_falls_back_to_whole_section():
    # the section only goes up to (3) — a model claiming (9) must not be trusted verbatim
    m = _map_one("(9)")
    assert m.article_section == "Section 26"


def test_null_subsection_cites_the_whole_section():
    m = _map_one(None)
    assert m.article_section == "Section 26"


def test_malformed_subsection_string_falls_back_to_whole_section():
    m = _map_one("see subsection 2")
    assert m.article_section == "Section 26"
