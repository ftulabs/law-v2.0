"""India Code's two-stage discovery, and the unit mismatch that made it look like it worked.

A pillar-6 run reported "18 documents -> 18 provisions" and mapped exactly one. Both numbers
were true and neither was an error, which is why nothing caught it: India Code publishes each
SECTION as its own record, so a "document" there is a provision, and `discovery_max_docs`
bought India eighteen provisions where it buys Singapore eighteen statutes.

Fixtures are shaped like real API responses. The suite stays offline; a portal changing its
schema shows up as a deliberate edit here rather than as a live run that quietly returns a
corpus of dairy-board and bonded-labour law.
"""
import collections

import pytest

from backend.pipeline import adapter_india as A
from backend.pipeline import discovery as D
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy


def _item(act, sec, heading, *, collection="SECTION", state="CENTRAL", body="Some text.",
          repealed="false"):
    return {
        "handle": f"123456789/{act[:3]}{sec}",
        "name": heading,
        "metadata": {
            "dc.identifier.collection": [{"value": collection}],
            "dc.identifier.section_number": [{"value": sec}],
            "dc.identifier.state_name": [{"value": state}],
            "dc.identifier.act_repealed": [{"value": repealed}],
            "dc.title.act_name": [{"value": act}],
            "dc.identifier.section_page_note": [{"value": body}],
        },
    }


def _wrap(items, total=None):
    return {"_embedded": {"searchResult": {
        "page": {"totalElements": total if total is not None else len(items)},
        "_embedded": {"objects": [{"_embedded": {"indexableObject": i}} for i in items]}}}}


# ── stage 1: a phrase must be sent as a phrase ────────────────────────────────────────────

@pytest.mark.parametrize("raw, expect", [
    ("cross-border transfer of personal data", '"cross-border transfer of personal data"'),
    ('"personal data" AND "outside India"', '"personal data" AND "outside India"'),
    ("cybersecurity", "cybersecurity"),
    ('dc.title.act_name:"X"', 'dc.title.act_name:"X"'),
])
def test_a_bare_query_is_quoted_and_a_structured_one_is_left_alone(raw, expect):
    """Unquoted, this engine matches a bag of words: `cross-border transfer of personal data`
    returns 71 items led by the Commercial Courts Act and the Andaman & Nicobar Police Manual.
    Quoted, the same idea returns the DPDP Act."""
    assert A.as_phrase(raw) == expect


def test_a_common_phrase_counts_for_less_than_a_rare_one():
    """`"transfer of personal data"` matches 4 items and every one is the DPDP Act;
    `"retain" AND "period" AND "records"` matches 2,709 and names eleven Acts, mostly tenancy
    and benami-property law. Without IDF the second outvotes the first."""
    assert A.phrase_weight(4) > A.phrase_weight(2709)
    assert 0.2 < A.phrase_weight(2709) < A.phrase_weight(4) <= 1.0


def test_stage_one_tallies_acts_and_ignores_state_and_repealed_records(monkeypatch):
    items = [_item("DPDP Act, 2023", "16", "Processing outside India"),
             _item("DPDP Act, 2023", "17", "Exemptions"),
             _item("IT Act, 2000", "43A", "Security practices"),
             _item("Kerala Act", "1", "x", state="KERALA"),
             _item("Dead Act", "1", "x", repealed="true"),
             _item("DPDP Act, 2023", "0", "cover", collection="ACT")]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(items, total=90))
    total, acts = A.phrase_acts(None, '"personal data"')
    assert total == 90
    assert acts == collections.Counter({"DPDP Act, 2023": 2, "IT Act, 2000": 1})


# ── stage 2: the whole Act, not the sections that happen to contain the phrase ─────────────

def test_stage_two_pages_until_the_act_is_exhausted(monkeypatch):
    """DSpace caps a page at 100 objects however large `size` is. The Information Technology
    Act 2000 has 125 sections across three pages; a single-page assumption loses 71 of them
    and raises nothing."""
    pages = [[_item("IT Act, 2000", str(n), f"s{n}") for n in range(0, 100)],
             [_item("IT Act, 2000", str(n), f"s{n}") for n in range(100, 125)],
             []]
    calls = []

    def fake_get(_client, _path, **params):
        calls.append(params.get("page"))
        page = params.get("page", 0)
        return _wrap(pages[page] if page < len(pages) else [], total=125)

    monkeypatch.setattr(A, "_get", fake_get)
    out = A.act_sections(None, "IT Act, 2000")
    assert len(out) == 125
    assert calls[:2] == [0, 1]


def test_stage_two_rejects_a_longer_act_whose_name_merely_contains_the_query(monkeypatch):
    """`dc.title.act_name:"…"` is a phrase match, so a longer title can come back with it."""
    items = [_item("IT Act, 2000", "1", "a"),
             _item("IT Act, 2000 (Amendment) Act, 2008", "1", "b")]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(items))
    out = A.act_sections(None, "IT Act, 2000")
    assert [A.act_name(i) for i in out] == ["IT Act, 2000"]


def test_the_adapter_returns_a_whole_act_not_just_the_matching_sections(monkeypatch):
    """The defect in one line: a phrase search returns the handful of sections containing the
    phrase, and that was mistaken for the Act."""
    act_items = [_item("DPDP Act, 2023", str(n), f"s{n}") for n in range(1, 45)]
    hit_items = [act_items[15]]

    def fake_get(_client, _path, **params):
        q = params.get("query", "")
        return _wrap(act_items if q.startswith("dc.title.act_name:") else hit_items,
                     total=len(act_items) if q.startswith("dc.title") else 19)

    monkeypatch.setattr(A, "_get", fake_get)
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache", lambda *a, **k: None)
    docs = A._search_in_dspace(None, {"name": "India Code"}, '"personal data" AND "outside India"',
                               Economy.IN, [], log=lambda _m: None)
    assert len(docs) == 44
    assert {d.law_name for d in docs} == {"DPDP Act, 2023"}


def test_every_section_of_one_act_shares_one_score(monkeypatch):
    """The score ranks LAWS. Sections of one Act competing against each other on separate
    scores is what let a run keep section 7 of an Act and drop section 16 of the same Act."""
    act_items = [_item("DPDP Act, 2023", str(n), f"s{n}") for n in range(1, 6)]
    monkeypatch.setattr(A, "_get", lambda *a, **k: _wrap(act_items, total=19))
    monkeypatch.setattr("backend.pipeline.fetch.seed_cache", lambda *a, **k: None)
    docs = A._search_in_dspace(None, {}, '"x"', Economy.IN, [], log=lambda _m: None)
    assert len({d.relevance_score for d in docs}) == 1


# ── the budget: what one unit of `discovery_max_docs` buys ─────────────────────────────────

def _doc(law, sec, score):
    return DiscoveredDoc(
        doc_id=f"IN:{law}:{sec}", economy=Economy.IN, title=f"{law} — Section {sec}",
        law_name=law, source_url=f"https://indiacode.gov.in/handle/{law}/{sec}",
        portal="India Code", fmt=DocFormat.HTML, relevance_score=score,
        discovery_tag=DiscoveryTag.NEW)


def test_a_section_unit_source_spends_the_budget_on_laws():
    """Three Acts of forty sections each is THREE documents' worth of budget, not 120."""
    docs = [_doc(f"Act {a}", s, 10 - a) for a in range(5) for s in range(40)]
    kept = D._cap(docs, max_docs=3, section_unit=True)
    assert len({d.law_name for d in kept}) == 3
    assert len(kept) == 120
    assert D._budget_used(kept, section_unit=True) == 3


def test_an_admitted_law_keeps_all_of_its_sections():
    """A half-harvested Act is worse than a missing one: the indicator it answers can sit in
    the half that was cut, and the run still reports evidence for that law."""
    docs = [_doc("Act A", s, 5.0) for s in range(40)] + [_doc("Act B", s, 4.0) for s in range(40)]
    kept = D._cap(docs, max_docs=1, section_unit=True)
    assert {d.law_name for d in kept} == {"Act A"}
    assert len(kept) == 40


def test_an_ordinary_source_is_capped_exactly_as_before():
    docs = [_doc(f"Act {a}", 0, 10 - a) for a in range(30)]
    assert len(D._cap(docs, max_docs=18, section_unit=False)) == 18
    assert D._budget_used(docs, section_unit=False) == 30


def test_the_india_lane_declares_its_unit_in_yaml():
    """The code reads `unit: section` rather than testing `economy == IN`, so the declaration
    has to actually be there or the cap silently reverts to counting provisions."""
    from backend.pipeline.discovery import load_sources
    india = [s for s in load_sources() if s.get("adapter") == "in_dspace"]
    assert india and india[0].get("unit") == "section"
    assert india[0].get("queries_p6") and india[0].get("queries_p7")


def test_the_india_query_pack_is_phrases_not_law_names():
    """The generated pack's name fragments (`companies act`, `labour act`) are built for a
    name-only portal. Fired at this full-text engine they returned the Indian Reserve Forces
    Act 1888 and the Bonded Labour System (Abolition) Act."""
    from backend.pipeline.discovery import load_sources
    india = [s for s in load_sources() if s.get("adapter") == "in_dspace"][0]
    for q in india["queries_p6"] + india["queries_p7"]:
        assert '"' in q, f"{q!r} is not a phrase query"
