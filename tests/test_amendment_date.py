"""'Last Amended' accuracy: each portal's own revision-history widget is the source of truth,
not a guess from the law's title/enactment year. Fixtures below are trimmed excerpts of REAL
fetched pages (SG: sso.agc.gov.sg/Act/PDPA2012; MY: lom.agc.gov.my/act-detail.php?act=709),
captured while diagnosing the reported "Last Amended is nonsense / often blank" bug.
"""
from backend.pipeline.discovery import (
    _au_latest_compilation, _my_parse_timeline_date, _sg_parse_timeline_date,
)

# Trimmed real SSO page: TWO 'global-vars' data-json blobs appear (verified live) — a
# page-wide config one first (no timelineItems), then the document-specific one whose
# docTimelineIdx points at the CURRENT entry. Item1 "/Date(1764864000000)/" = 2025-12-05 SGT
# (the epoch-ms is SG-local midnight, UTC+8 — converting via plain UTC lands a day early),
# matching the live page's own highlighted timeline point "05 Dec 2025 — Amended by Act 19 of 2025".
SG_HTML = (
    '<div class="global-vars" data-json=\'{"host":"sso.agc.gov.sg","rootPath":"https://sso.agc.gov.sg/"}\'>'
    '<div class="global-vars" data-json=\'{"tocSysId":"x","legisTitle":"Personal Data '
    'Protection Act 2012","docTimelineIdx":1,"provTimelineIdx":-1,"timelineItems":'
    '[{"Item1":"\\/Date(1609516800000)\\/","Item2":"/Act/PDPA2012/Historical/20210102","Item3":"a"},'
    '{"Item1":"\\/Date(1764864000000)\\/","Item2":"/Act/PDPA2012?ValidDate=20251205","Item3":"b"}],'
    '"validStartDate":"\\/Date(1764864000000)\\/"}\'>'
)

# Trimmed real MY act-detail timeline (Act 709, Personal Data Protection Act 2010).
MY_HTML = """
<li><a href="#0" data-date="11/06/2010" data-project-id="721" data-log-type="ORIGINAL" class="selected event_a">Jun 2010<br>Original</a></li>
<li><a href="#0" data-date="19/02/2023" data-project-id="1783545" data-log-type="SUBSIDIARY_LEGISLATION" class=" event_a">Feb 2023<br>Subsidiary<br>Legislation</a></li>
<li><a href="#0" data-date="16/10/2024" data-project-id="2430673" data-log-type="AMENDMENTS" class=" event_a">Oct 2024<br>Amendments</a></li>
<li><a href="#0" data-date="30/09/2025" data-project-id="3082378" data-log-type="SUBSIDIARY_LEGISLATION" class=" event_a">Sep 2025<br>Subsidiary<br>Legislation</a></li>
"""


def test_sg_timeline_picks_the_current_entry_not_the_first():
    assert _sg_parse_timeline_date(SG_HTML) == "2025-12-05"


def test_sg_timeline_returns_none_without_the_blob():
    assert _sg_parse_timeline_date("<html>no timeline here</html>") is None


def test_my_timeline_excludes_subsidiary_legislation_events():
    """The Act's own last AMENDMENT (Oct 2024) must win over a later but unrelated
    Subsidiary Legislation gazette notice (Sep 2025) — a different, subordinate instrument,
    not a change to this Act's own text."""
    assert _my_parse_timeline_date(MY_HTML) == "2024-10-16"


def test_my_timeline_falls_back_to_last_event_if_all_are_subsidiary():
    only_subsidiary = (
        '<a data-date="01/01/2020" data-project-id="1" data-log-type="SUBSIDIARY_LEGISLATION">x</a>'
        '<a data-date="01/01/2021" data-project-id="2" data-log-type="SUBSIDIARY_LEGISLATION">y</a>'
    )
    assert _my_parse_timeline_date(only_subsidiary) == "2021-01-01"


def test_my_timeline_returns_none_without_any_events():
    assert _my_parse_timeline_date("<html>no timeline here</html>") is None


def test_au_latest_compilation_uses_the_documents_feed_start_date(monkeypatch):
    """Verified against the live page: legislation.gov.au's own 'Latest version'/'Compilation
    date' matches the OData /v1/documents feed's 'start' field exactly — NOT makingDate or
    asMadeRegisteredAt from /v1/titles (those are the original-enactment/early-registration
    timestamps the old code used, explaining the reported nonsense AU dates)."""
    import backend.pipeline.discovery as disco

    class _Resp:
        def json(self):
            return {"value": [
                {"start": "2026-06-04T00:00:00", "isAuthorised": True},
                {"start": "2025-06-10T00:00:00", "isAuthorised": True},
            ]}

    monkeypatch.setattr(disco, "_au_compilation_cache", {})
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp())
    pdf, start, never_amended = _au_latest_compilation("C2004A03712")
    assert start == "2026-06-04"
    assert pdf == "https://www.legislation.gov.au/C2004A03712/2026-06-04/2026-06-04/text/original/pdf"
    assert never_amended is False


def test_au_never_amended_act_reports_original(monkeypatch):
    """Judges' Q&A: a never-amended law reads "Original", never a blank or the registration
    date. On legislation.gov.au the as-made-only shape (verified live on C2026A00001) is
    compilationNumber '0' with registerId equal to the title id — amended acts return
    C-prefixed compilations with a running number instead."""
    import backend.pipeline.discovery as disco

    class _Resp:
        def json(self):
            return {"value": [{"start": "2026-01-21T00:00:00", "isAuthorised": True,
                               "compilationNumber": "0", "registerId": "C2026A00001"}]}

    monkeypatch.setattr(disco, "_au_compilation_cache", {})
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp())
    _, start, never_amended = _au_latest_compilation("C2026A00001")
    assert never_amended is True
    assert start == "2026-01-21"      # the date stays available for the PDF URL


def test_sg_single_timeline_entry_means_never_amended():
    """One timeline entry = the text never changed since enactment → "Original"."""
    single = (
        '<div class="global-vars" data-json=\'{"legisTitle":"X","docTimelineIdx":0,'
        '"timelineItems":[{"Item1":"\\/Date(1609516800000)\\/","Item2":"/Act/X","Item3":"a"}]}\'>'
    )
    assert _sg_parse_timeline_date(single) == "Original"


def test_my_timeline_with_only_original_event_reports_original():
    """A MY act whose own-text history is just the ORIGINAL gazettal (subsidiary-legislation
    events are other instruments) has never been amended → "Original"."""
    html = (
        '<a data-date="11/06/2010" data-project-id="1" data-log-type="ORIGINAL">x</a>'
        '<a data-date="19/02/2023" data-project-id="2" data-log-type="SUBSIDIARY_LEGISLATION">y</a>'
    )
    assert _my_parse_timeline_date(html) == "Original"


def test_format_last_amended_passes_original_through():
    from backend.pipeline.mapping import _format_last_amended
    assert _format_last_amended("Original", "Some Act 2026") == "Original"
    # unchanged behaviour for real dates and fallbacks
    assert _format_last_amended("2025-12-05", "X") == "December 2025"
    assert _format_last_amended(None, "Privacy Act 1988") == "1988"


def test_au_latest_compilation_caches_by_title_id(monkeypatch):
    import backend.pipeline.discovery as disco
    calls = {"n": 0}

    class _Resp:
        def json(self):
            calls["n"] += 1
            return {"value": [{"start": "2025-01-01T00:00:00", "isAuthorised": True}]}

    monkeypatch.setattr(disco, "_au_compilation_cache", {})
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp())
    _au_latest_compilation("C2020A00001")
    _au_latest_compilation("C2020A00001")
    assert calls["n"] == 1
