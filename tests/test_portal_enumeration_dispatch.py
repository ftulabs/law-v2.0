"""A portal-enumerating adapter must be called once per source, not once per query term.

sg_sso, tl_gazette, la_gazette and th_law_api each walk their WHOLE portal on every call and
ignore `query` -- their own module docstrings say so ("`query` is deliberately unused",
"`query` is ignored"). Before this fix, `discovery.discover_live`'s dispatch called every
adapter once per query term regardless of that. For a source with no `queries`/`queries_p<N>`
override, that fallback is the generated generic query list -- 52 terms for pillar 6 (measured
live, see the module docstrings) -- so a single-call ~183.5s Timor-Leste crawl became 52 of
those: about two hours forty minutes for one economy, one pillar. It is also the likely cause
of Singapore's SSO throttle: SSO answers a burst with `202`/empty body, and 52 consecutive
full sort-window-union crawls is exactly the burst that exists to stop.

Driven entirely by a stub function -- no network, no real portal, no real adapter module.
"""
from backend.pipeline import discovery, portal
from backend.schemas import Economy


def _stub_source():
    return {
        "economy": "TL",
        "name": "stub enumerating portal",
        "adapter": "stub_enumerator",
        # Deliberately no `queries:`/`queries_p6:` override, so `_source_queries` falls back
        # to the generated ~52-term generic list -- the exact shape that produced the 2h40m
        # crawl this test exists to prevent a regression of.
    }


def test_portal_enumerating_adapter_is_called_once_per_source_not_once_per_term(monkeypatch):
    calls: list[str] = []

    def _stub(client, src, query, economy, indicators, log):
        calls.append(query)
        return [portal.make_doc(economy, "https://mj.gov.tl/x.pdf", "Stub Law",
                                 "stub enumerating portal")]

    try:
        portal.register("stub_enumerator", _stub, enumerates_portal=True)
    except TypeError:
        # Pre-fix `portal.register` does not know about `enumerates_portal` yet. Registering
        # plainly here means the dispatch below runs under exactly today's per-term behaviour
        # -- the failure this produces (52 calls, not 1) IS the defect this test pins.
        portal.register("stub_enumerator", _stub)

    try:
        monkeypatch.setattr(discovery, "load_sources", lambda: [_stub_source()])
        docs = discovery.discover_live(Economy.TL, pillar=6, max_docs=50,
                                        log=lambda *_: None)
        assert len(calls) == 1, (
            f"a portal-enumerating adapter must be called exactly once per source -- got "
            f"{len(calls)} calls: {calls[:5]}{'...' if len(calls) > 5 else ''}")
        assert len(docs) == 1
    finally:
        portal._REGISTRY.pop("stub_enumerator", None)
        enum_map = getattr(portal, "_ENUMERATES_PORTAL", None)
        if enum_map is not None:
            enum_map.pop("stub_enumerator", None)


def test_query_consuming_adapter_is_still_called_once_per_term(monkeypatch):
    """The round-robin merge exists so no single query monopolises the budget (its own
    comment records India returning 46 sections on one query and starving the rest of the
    pillar). An adapter that genuinely consumes `query` (the default -- no
    `enumerates_portal=True`) must keep being called per term, or that protection is lost."""
    calls: list[str] = []

    def _stub(client, src, query, economy, indicators, log):
        calls.append(query)
        return [portal.make_doc(economy, f"https://mj.gov.tl/{query}.pdf", "Stub Law",
                                 "stub query portal")]

    portal.register("stub_query_consumer", _stub)  # enumerates_portal defaults False

    try:
        src = _stub_source()
        src["adapter"] = "stub_query_consumer"
        src["queries_p6"] = ["alpha", "beta", "gamma"]
        monkeypatch.setattr(discovery, "load_sources", lambda: [src])
        discovery.discover_live(Economy.TL, pillar=6, max_docs=50, log=lambda *_: None)
        assert calls == ["alpha", "beta", "gamma"]
    finally:
        portal._REGISTRY.pop("stub_query_consumer", None)
        enum_map = getattr(portal, "_ENUMERATES_PORTAL", None)
        if enum_map is not None:
            enum_map.pop("stub_query_consumer", None)


def test_cn_portal_real_adapter_and_real_source_is_dispatched_once_not_per_term(monkeypatch):
    """2026-09-07 final review, Finding 1: `cn_portal` was registered WITHOUT
    `enumerates_portal=True`. `adapter_china._search_terms` fills its term list from
    `src["queries_p6"]`/`queries_p7` BEFORE appending the per-call `query` argument, then caps
    the result at `_SEARCH_MAX_TERMS` (6) -- and the real `data/sources.yaml` `cn_portal` entry
    carries 13 `queries_p6` terms and 13 `queries_p7` terms (measured by reading that file), so
    the cap is exhausted by config terms alone and the passed `query` is provably unreachable.
    Calling the adapter once per query term therefore repeated the identical front/section/
    aggregator httpx walk AND the identical six WAF-gated Scrapling searches against
    search.cac.gov.cn thirteen times over for zero additional coverage -- 78 WAF crossings for
    one pillar, against a portal this project's own docs call flaky and WAF-gated.

    Unlike the two stub-based tests above, this drives the REAL `cn_portal` registration
    (import-time `portal.register` call in `adapter_china.py`) against the REAL CN source entry
    from `data/sources.yaml` -- the specific gap the reviewer named: nothing previously
    exercised the actual adapters' registration, only a synthetic stub. The registered callable
    is swapped for a counting stand-in so no network call is made; `portal.enumerates_portal`
    is left exactly as `adapter_china.py` set it, so this fails if that classification
    regresses.
    """
    from backend.pipeline import adapter_china  # noqa: F401 -- runs the real portal.register()

    cn_sources = [s for s in discovery.load_sources()
                  if s.get("economy") == "CN" and s.get("adapter") == "cn_portal"]
    assert cn_sources, "data/sources.yaml must still carry a cn_portal entry for CN"
    src = cn_sources[0]
    assert len(src.get("queries_p6") or []) >= 6 and len(src.get("queries_p7") or []) >= 6, (
        "this test's premise -- that config terms alone exhaust the 6-term search cap before "
        "`query` is appended -- requires >=6 queries_p6 AND >=6 queries_p7 terms in the "
        "shipped data/sources.yaml entry")

    calls: list[str] = []

    def _counting(client, src, query, economy, indicators, log):
        calls.append(query)
        return []

    real_fn = portal.get_adapter("cn_portal")
    real_enumerates = portal.enumerates_portal("cn_portal")
    portal.register("cn_portal", _counting, enumerates_portal=real_enumerates)

    try:
        monkeypatch.setattr(discovery, "load_sources", lambda: [src])
        discovery.discover_live(Economy.CN, pillar=6, max_docs=50, log=lambda *_: None)
        assert len(calls) == 1, (
            f"cn_portal must be dispatched once per source, not once per query term -- got "
            f"{len(calls)} calls: {calls[:5]}{'...' if len(calls) > 5 else ''}")
    finally:
        portal.register("cn_portal", real_fn, enumerates_portal=real_enumerates)
