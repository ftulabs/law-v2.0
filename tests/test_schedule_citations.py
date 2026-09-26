"""Schedule paragraphs, legislative history and bare Part headings in SSO-style statutes.

Measured 2026-09-25: 17 of Singapore's 59 PDPA rows for 7.1 cited "Section 1", "Section 2" …
for paragraphs of the First to Ninth Schedules, and the Law Revision Commission's legislative
history became "Section 1" rows ("Act 26 of 2012 — Bill: 24/2012, First Reading …")."""
from backend.pipeline.extraction import extract_provisions
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics

BODY = "\n".join(
    f"Heading {n}\n{n}.—(1) An organisation must comply with the duty numbered {n} in respect "
    f"of personal data in its possession, and a person who fails to do so shall be guilty of an "
    f"offence under this Act." for n in range(1, 30))
TEXT = (
    BODY
    + "\nPART 9\nPROVIDERS OF ESSENTIAL SERVICE [Act 19 of 2024 wef 31/10/2025]\n"
    + "Duty of provider\n30.—(1) A provider must notify the Commissioner of every incident within "
      "the prescribed period after becoming aware of it.\n"
    + "FIRST SCHEDULE\nSections 17(1) and (2)\nCOLLECTION WITHOUT CONSENT\n"
    + "1.—(1) The collection of personal data about an individual is necessary for any purpose "
      "which is clearly in the interests of the individual.\n"
    + "FIRST SCHEDULE — continued\n"
    + "2. The collection of personal data is necessary to respond to an emergency that threatens "
      "the life of the individual.\n"
    + "SECOND SCHEDULE\n1. The disclosure of personal data to a public agency for the purposes "
      "of policy formulation, where the agency so requests in writing.\n"
    + "LEGISLATIVE HISTORY\nPERSONAL DATA PROTECTION ACT 2012\n"
    + "1. Act 26 of 2012 — Personal Data Protection Act 2012 Bill : 24/2012 First Reading : "
      "10 September 2012 Second Reading : 15 October 2012.\n")


def _labels():
    doc = DiscoveredDoc(doc_id="SG-t", economy=Economy.SG, title="Personal Data Protection Act 2012",
                        source_url="https://sso.agc.gov.sg/Act/PDPA2012", portal="x",
                        fmt=DocFormat.PDF_TEXT)
    return [(p.article_section, p.verbatim_snippet) for p in extract_provisions(doc, TEXT, OCRMetrics())]


def test_schedule_paragraphs_are_cited_as_paragraphs_of_their_schedule():
    labels = [a for a, _ in _labels()]
    assert "First Schedule, paragraph 1" in labels
    assert "First Schedule, paragraph 2" in labels
    assert "Second Schedule, paragraph 1" in labels
    assert labels.count("Section 1") == 1                  # the real s1 only


def test_running_schedule_header_does_not_enter_the_snippet():
    assert not any("continued" in s for _, s in _labels())


def test_legislative_history_is_not_a_provision():
    assert not any("First Reading" in s for _, s in _labels())


def test_a_part_heading_with_no_sentence_is_not_a_provision():
    labels = [a for a, _ in _labels()]
    assert not any(a.upper().startswith("PART") for a in labels)
    assert "Section 30" in labels
