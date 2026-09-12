"""The India lane returned nothing for weeks and the suite stayed green. This stops that.

`adapter_india.act_name()` read `dc.title.act_name`. India Code publishes
`dc.identifier.act_name`. `_md` returns "" for a key that is absent, so `act_name()` returned ""
for every hit, `phrase_acts` skipped every one of them ("if name:"), `_search_in_dspace` logged
"no in-force Central sections" for every query, and the whole economy silently fell through to
the web-search lanes — whose top results were India Code's own navigation pages ("India Code:
Browsing DSpace") and, on 2026-09-11, a university ordinance about the title of Professor
Emeritus. Nothing raised. The CSV said "No provision found", which is what an economy with no
such law would also say.

The reason no test caught it is the interesting part, and it is why this file exists: the
fixtures in `test_india_two_stage.py` and `test_adapter_india.py` were hand-written from the
same assumption as the code. They asserted that the adapter reads the key the fixtures
contain — a closed loop that cannot fail. A mock can only ever confirm the author's belief
about the API; it cannot contradict it.

So the fixture here is not hand-written. It is the portal's own answer, captured live, kept as
data, and compared against the constant the adapter uses. If India Code renames the field, this
test goes red with the real key in the failure message instead of an economy going quietly
empty.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.pipeline import adapter_india as A

FIXTURE = Path(__file__).parent / "fixtures" / "india_code_search_item_keys.json"


def _captured() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_field_the_adapter_reads_is_one_the_portal_actually_publishes():
    keys = _captured()["metadata_keys"]
    assert A.ACT_NAME_FIELD in keys, (
        f"{A.ACT_NAME_FIELD!r} is not among the keys India Code returned on "
        f"{_captured()['_captured']}. Keys it did return: {keys}")


def test_the_key_that_caused_the_outage_is_confirmed_absent():
    """Pinned so the fix cannot be quietly reverted to something that reads as plausible."""
    assert "dc.title.act_name" not in _captured()["metadata_keys"]


def test_act_name_reads_a_real_value_out_of_a_real_response():
    """End-to-end over the captured shape: the accessor, not just the constant."""
    item = {"metadata": {A.ACT_NAME_FIELD: [{"value": "The Digital Personal Data Protection Act, 2023."}]}}
    assert A.act_name(item) == "The Digital Personal Data Protection Act, 2023"


def test_an_item_missing_the_act_name_yields_nothing_rather_than_a_wrong_name():
    """`phrase_acts` drops a nameless hit on purpose; this pins the shape it drops on."""
    assert A.act_name({"metadata": {}}) == ""
    assert A.act_name({}) == ""


def test_the_stage_two_query_uses_the_same_field_as_the_metadata_read():
    """The outage had TWO halves — the metadata read AND the Solr field in the stage-2 query
    (`dc.title.act_name:"…"` returned 0 hits live, `dc.identifier.act_name:"…"` returned 50).
    Fixing one and not the other would leave the economy just as empty, so they are one
    constant now and this asserts they stay one."""
    src = (Path(__file__).parents[1] / "backend" / "pipeline" / "adapter_india.py").read_text(
        encoding="utf-8")
    assert 'query = \'%s:"%s"\' % (ACT_NAME_FIELD' in src, (
        "the stage-2 query no longer builds its field name from ACT_NAME_FIELD")
