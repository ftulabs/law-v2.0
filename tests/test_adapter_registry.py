"""Every adapter named in sources.yaml must resolve, and every economy must have a lane.

This is the seam where a typo costs an economy its entire discovery in silence: an unknown
adapter name falls through to `_search_one`, which needs a `search_url_template` these
entries do not have, and the lane quietly returns nothing.
"""
import pytest

from backend.pipeline import discovery, portal
from backend.schemas import LIVE_TEST_POOL

# Importing the adapter modules is what runs their portal.register(...) calls.
from backend.pipeline import (adapter_china, adapter_indonesia, adapter_laos,  # noqa: F401
                              adapter_singapore, adapter_thailand, adapter_timor)


def _named_adapters():
    return {s.get("adapter") for s in discovery.load_sources()
            if s.get("adapter") and s.get("adapter") != "websearch"}


def test_every_adapter_named_in_sources_yaml_resolves():
    unresolved = [a for a in _named_adapters()
                  if portal.get_adapter(a) is None and a not in discovery._ADAPTERS]
    assert not unresolved, f"sources.yaml names adapters nothing implements: {unresolved}"


@pytest.mark.parametrize("economy", sorted(LIVE_TEST_POOL))
def test_every_economy_has_at_least_one_portal_native_lane(economy):
    """Russia is the documented exception: its fetch route is solved but discovery injects
    its rows client-side, and Phase 3 owns it. Every other economy must be able to reach its
    own portal without a search engine."""
    if economy == "RU":
        pytest.skip("RU discovery is unsolved by design — see the design spec, Phase 3")
    native = [s for s in discovery.load_sources()
              if s.get("economy") == economy
              and s.get("adapter") and s.get("adapter") != "websearch"]
    assert native, f"{economy} has no portal-native lane — a dead search engine costs it everything"


def test_no_lane_is_configured_on_the_npc_database():
    """flk.npc.gov.cn's API returns "download": 0. Discovery-only entries may mention it;
    no ADAPTER may be built on it."""
    for s in discovery.load_sources():
        if "flk.npc.gov.cn" in (s.get("base_url") or "") or "flk.npc.gov.cn" in (s.get("site") or ""):
            assert s.get("adapter") in (None, "websearch"), (
                "flk.npc.gov.cn must not carry a portal adapter — the operator refused")
