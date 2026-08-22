"""India Code adapter — the DSpace REST API.

India is the one economy where provision boundaries come from the publisher rather than from
our own splitting heuristic, so these tests pin the metadata contract we depend on. Fixtures
are real API responses, trimmed: the suite stays offline, and a portal changing its schema
shows up as a deliberate edit here rather than as a live run that quietly returns nothing.
"""
import pytest

from backend.pipeline import adapter_india as A
from backend.schemas import Economy

# Real item, trimmed — DPDP Act 2023 s.16, the RDTII 6.4 answer for India.
S16 = {
    "uuid": "6387180a-0def-4f62-baca-0c092c1dc2a1",
    "handle": "123456789/512146",
    "name": "Processing of personal data outside India.",
    "metadata": {
        "dc.identifier.collection": [{"value": "SECTION"}],
        "dc.identifier.section_number": [{"value": "16"}],
        "dc.identifier.act_number": [{"value": "22"}],
        "dc.date.act_year": [{"value": "2023"}],
        "dc.identifier.act_year": [{"value": "2023"}],
        "dc.identifier.act_repealed": [{"value": "false"}],
        "dc.identifier.repealed": [{"value": "false"}],
        "dc.identifier.state_name": [{"value": "CENTRAL"}],
        "dc.title.act_name": [{"value": "The Digital Personal Data Protection Act, 2023."}],
        "dc.identifier.section_page_note": [{"value":
            '<span style="margin-left: 15px;"></span>(1) The Central Government may, by '
            "notification, restrict the transfer of personal&nbsp;data by a Data Fiduciary "
            "for processing to such country or territory outside India as may be so notified."}],
    },
}


def _variant(**md):
    item = {k: v for k, v in S16.items() if k != "metadata"}
    item["metadata"] = {**S16["metadata"], **{k: [{"value": v}] for k, v in md.items()}}
    return item


def test_section_text_is_the_statutes_own_words():
    """The Verbatim Snippet column IS the statute. Markup and entities go; nothing else may."""
    t = A.section_text(S16)
    assert t.startswith("(1) The Central Government may, by notification, restrict")
    assert "<span" not in t and "&nbsp;" not in t
    assert "personal data by a Data Fiduciary" in t      # the entity became a real space


def test_a_repealed_act_is_dropped():
    """A repealed instrument scores zero however well it reads, and the portal tells us."""
    assert A.is_in_force(S16)
    assert not A.is_in_force(_variant(**{"dc.identifier.act_repealed": "true"}))


def test_a_repealed_section_of_a_live_act_is_also_dropped():
    """Two separate flags, because an Act can stand while one section is repealed."""
    assert not A.is_in_force(_variant(**{"dc.identifier.repealed": "true"}))


def test_only_section_items_are_kept(monkeypatch):
    """ACT-level records carry no operative text, so citing one gives an act without a section
    — which the template says scores zero."""
    items = [S16, _variant(**{"dc.identifier.collection": "ACT"})]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(items))
    assert len(A.search_sections(None, "x")) == 1


def test_state_legislation_is_out_of_scope(monkeypatch):
    """RDTII scores the economy's Central law; keeping thirty states would multiply the corpus
    and none of it would be scoreable."""
    items = [S16, _variant(**{"dc.identifier.state_name": "KERALA"})]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(items))
    assert len(A.search_sections(None, "x")) == 1


def test_a_heading_with_no_body_cannot_support_a_citation(monkeypatch):
    items = [S16, _variant(**{"dc.identifier.section_page_note": ""})]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(items))
    assert len(A.search_sections(None, "x")) == 1


def _wrap(items):
    return {"_embedded": {"searchResult": {"_embedded": {
        "objects": [{"_embedded": {"indexableObject": i}} for i in items]}}}}


def test_discovered_doc_carries_the_citable_url_and_the_act_number(monkeypatch):
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap([S16]))
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache", lambda *a, **k: None)
    docs = A._search_in_dspace(None, {"name": "India Code"}, "transfer", Economy.IN, [],
                               log=lambda _m: None)
    assert len(docs) == 1
    d = docs[0]
    # A reviewer has to be able to open the Source URL — the API endpoint is not that.
    assert d.source_url == "https://indiacode.gov.in/handle/123456789/512146"
    assert "Section 16" in d.title and "Digital Personal Data Protection Act" in d.title
    assert d.law_number == "Act 22 of 2023"


def test_a_dead_api_returns_nothing_rather_than_raising(monkeypatch):
    """One failed query must not take the run down; discovery has other sources and other
    queries, and a raised exception here would lose all of them."""
    def boom(*a, **k):
        raise RuntimeError("502")
    monkeypatch.setattr(A, "_get", boom)
    logged = []
    assert A._search_in_dspace(None, {}, "q", Economy.IN, [], log=logged.append) == []
    assert logged and "India Code API failed" in logged[0]


def test_the_adapter_is_reachable_from_discovery_dispatch():
    """The dispatch table is in another module; a rename there would silently disable India."""
    from backend.pipeline.adapter_india import _search_in_dspace
    import inspect

    from backend.pipeline import discovery
    src = inspect.getsource(discovery)
    assert '"in_dspace"' in src and "_search_in_dspace" in src
    assert callable(_search_in_dspace)
