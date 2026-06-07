"""JS single-page-app shell guard.

legislation.gov.au (AU) serves its law text via Angular — a static fetch returns only
the site chrome. Without a guard, that chrome is extracted as a bogus, non-verbatim
"provision" and mapped to an indicator. These tests pin the detector + the guard so AU
shells yield ZERO provisions (clean) rather than navigation garbage.
"""
import tempfile
from pathlib import Path

from backend.pipeline.ocr import get_document_text, is_js_app_shell
from backend.pipeline import extraction
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, OCRMetrics

# An Angular shell: framework marker present, body is only site chrome (no law text).
SPA_SHELL = """<!doctype html><html lang="en"><head><title>Privacy Act 1988</title></head>
<body ng-version="17.0.0">
<a href="#maincontent">Skip to main</a>
<div>Text Details Authorises Downloads All versions Interactions</div>
<div>Order print copy Save this title to My Account Set up an alert</div>
<div>Table of contents Enter text to search</div>
<router-outlet></router-outlet>
</body></html>"""

# A real (server-rendered) law page: no SPA marker, has section structure.
REAL_LAW_HTML = """<html><body>
<h1>Personal Data Protection Act</h1>
<p>Section 26. Transfer of personal data outside Singapore</p>
<p>(1) An organisation must not transfer any personal data to a country outside Singapore
except in accordance with requirements prescribed under this Act.</p>
<p>Section 27. Other matters</p>
<p>(2) The Commission may issue guidelines.</p>
</body></html>"""


def test_detector_flags_unrendered_spa():
    assert is_js_app_shell(SPA_SHELL)


def test_detector_keeps_real_law_html():
    assert not is_js_app_shell(REAL_LAW_HTML)


def test_detector_keeps_spa_marker_page_that_has_rendered_content():
    # an SPA framework can still serve rendered law text (e.g. after browser render);
    # presence of section markers means it is NOT an empty shell.
    rendered = SPA_SHELL.replace("<router-outlet></router-outlet>",
                                 "<p>Section 5. Application</p><p>(1) This Act applies...</p>")
    assert not is_js_app_shell(rendered)


def _doc(html, fmt=DocFormat.HTML):
    f = Path(tempfile.mkdtemp()) / "doc.html"
    f.write_text(html, encoding="utf-8")
    return DiscoveredDoc(doc_id="d1", economy=Economy.AU, title="Privacy Act 1988",
                         source_url="https://www.legislation.gov.au/C2004A03712/latest/text",
                         portal="AU", fmt=fmt, discovery_tag=DiscoveryTag.NEW, local_path=str(f))


def test_get_document_text_suppresses_shell():
    text, metrics = get_document_text(_doc(SPA_SHELL))
    assert text == "" and metrics.notes == "js_app_shell"
    # and extraction therefore yields zero provisions (no nav-chrome garbage)
    assert extraction.extract_provisions(_doc(SPA_SHELL), text, metrics) == []


def test_get_document_text_keeps_real_html():
    text, metrics = get_document_text(_doc(REAL_LAW_HTML))
    assert "transfer any personal data" in text.lower()
    assert metrics.notes is None
    assert len(extraction.extract_provisions(_doc(REAL_LAW_HTML), text, metrics)) >= 1
