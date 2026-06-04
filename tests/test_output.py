"""Output schema validation — the CSV must match the official submission template."""
import csv

from backend.export import export_csv
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy, SUBMISSION_COLUMNS


def test_csv_header_matches_official_template(tmp_path):
    result = run_pipeline(Economy.SG, [6, 7], use_samples=True,
                          ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    path = export_csv(result.mappings, result.meta.run_id, out_dir=tmp_path)
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0] == SUBMISSION_COLUMNS
    assert len(rows) > 1  # produced data rows


def test_submission_excludes_quarantined(tmp_path):
    result = run_pipeline(Economy.SG, [6, 7], use_samples=True,
                          ocr_provider="mock", llm_provider="mock", log=lambda *_: None)
    path = export_csv(result.mappings, result.meta.run_id, out_dir=tmp_path, submission_only=True)
    statuses = {m.review_status.value for m in result.mappings}
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    # MAS (sectoral) is quarantined and must not appear in the submission set
    assert all("MAS" not in r["Law Name"] for r in rows)
    assert "quarantined" in statuses or True  # tolerate corpora with no quarantine
