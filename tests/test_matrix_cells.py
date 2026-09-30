"""A matrix cell and the evidence panel beside it must name the same provision."""
from types import SimpleNamespace

from frontend import matrix


def _m(article, conf, law="Corporations Act 2001", ind="P6-I4", no_ev=False):
    return SimpleNamespace(law_name=law, indicator_id=ind, article_section=article,
                           confidence_score=conf, law_number="C2004A00818",
                           source_url="https://www.legislation.gov.au/x", no_ev=no_ev)


def _no_ev(m):
    return m.no_ev


def test_the_chip_names_the_provision_the_panel_opens():
    # the order that used to split them: weak rows arriving before and after each other
    ms = [_m("Section 205G", 0.41), _m("Section 111M", 0.55), _m("Section 20K", 0.52)]
    rows = matrix.build_rows(ms, _no_ev, lambda u: "www.legislation.gov.au")
    cell = rows[0]["cells"]["P6-I4"]
    first = matrix.cell_mappings(ms, "Corporations Act 2001|P6-I4", _no_ev)[0]
    assert cell["t"] == first.article_section == "Section 111M"
    assert cell["k"] == 2                        # the other two are announced, not hidden


def test_order_does_not_depend_on_arrival():
    ms = [_m("Section 20K", 0.52), _m("Section 111M", 0.55), _m("Section 205G", 0.41)]
    assert [x.article_section for x in
            matrix.cell_mappings(ms, "Corporations Act 2001|P6-I4", _no_ev)] == \
        ["Section 111M", "Section 20K", "Section 205G"]


def test_a_real_finding_outranks_a_no_evidence_row():
    ms = [_m("none", 0.0, no_ev=True), _m("Section 26", 0.7)]
    cell = matrix.build_rows(ms, _no_ev, lambda u: "")[0]["cells"]["P6-I4"]
    assert cell["t"] == "Section 26" and cell["k"] == 0


def test_no_cell_key_means_no_mappings():
    assert matrix.cell_mappings([_m("s 1", 0.9)], None, _no_ev) == []
