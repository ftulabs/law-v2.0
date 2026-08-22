"""Cost accounting, counted as it happens.

The template requires cost "recorded per run and per engine during the live hour … without
manual arithmetic". Every test here pins one way a cost table can be quietly wrong, which is
worse than having no table: a number that looks measured and is not.
"""
import json

import pytest

from backend import metering
from backend.config import ROOT


@pytest.fixture
def meter():
    m = metering.start("test-run")
    yield m
    metering.stop()


PRICES = {
    "llm": {"m/one": {"input_per_1m": 1.0, "output_per_1m": 2.0}},
    "ocr": {"rapidocr": 0.0, "azure": 0.0015},
    "search": {"serper": 0.001},
}


def test_llm_cost_comes_from_real_token_counts(meter):
    meter.record_llm("m/one", prompt_tokens=1_000_000, completion_tokens=500_000, seconds=3)
    r = meter.report(PRICES)
    assert r["llm"][0]["cost_usd"] == pytest.approx(1.0 + 1.0)      # 1M in + 0.5M out at $2/M
    assert r["total_usd"] == pytest.approx(2.0)


def test_cost_is_keyed_by_the_engine_that_answered(meter):
    """C5b compares two engines over the same work, so one number for the run is not enough —
    and after a failover the model that answered is not always the one that was asked for."""
    meter.record_llm("m/one", 1_000_000, 0)
    meter.record_llm("m/two", 1_000_000, 0)
    models = {row["model"] for row in meter.report(PRICES)["llm"]}
    assert models == {"m/one", "m/two"}


def test_a_missing_price_reports_unpriced_not_zero(meter):
    """$0.00 is a claim; "we do not know" is not the same claim. A total that silently absorbs
    an unpriced component reads as complete when it is a floor."""
    meter.record_llm("m/unknown", 1_000_000, 0)
    r = meter.report(PRICES)
    assert r["llm"][0]["cost_usd"] is None
    assert r["total_is_complete"] is False
    assert "llm" in r["unpriced"]
    assert "floor" in meter.table().lower()


def test_a_priced_zero_is_a_real_zero(meter):
    """Local OCR genuinely costs nothing per page, and saying so is a measurement."""
    meter.record_ocr("rapidocr", pages=40)
    r = meter.report(PRICES)
    assert r["ocr"][0]["cost_usd"] == 0.0
    assert r["total_is_complete"] is True


def test_paid_ocr_would_dominate_the_bill_at_real_prices(meter):
    """Why OCR is metered at all, and why paid OCR is not the default.

    Run against the SHIPPED price table and the SHIPPED default model, on one ~50-page Act at
    the ~64 grading calls a document actually costs. Switching OCR to a paid service does not
    add a line to the bill — it becomes the largest line, several times the mapping cost. That
    inverts which component is worth optimising, so the assertion is that the inversion is
    real rather than something we assumed."""
    from backend.config import settings
    prices = json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))
    meter.record_ocr("azure", pages=50)
    meter.record_llm(settings.openrouter_model, 160_000, 45_000)
    r = meter.report(prices)
    ocr = next(x["cost_usd"] for x in r["ocr"])
    llm = next(x["cost_usd"] for x in r["llm"])
    assert ocr > 2 * llm, f"paid OCR ${ocr:.4f} vs mapping ${llm:.4f}"


def test_search_counts_billable_queries(meter):
    for _ in range(90):
        meter.record_search("serper")
    assert meter.report(PRICES)["search"][0]["cost_usd"] == pytest.approx(0.09)


def test_recording_outside_a_run_is_a_no_op():
    """tools/ scripts and the test suite must not need metering setup, and must not crash
    without it."""
    metering.stop()
    metering.record_llm("m/one", 10, 10)
    metering.record_ocr("rapidocr", 1)
    metering.record_search("serper")
    metering.record_fetch(100)
    metering.record_embedding(5)
    assert metering.current() is None


def test_concurrent_recording_does_not_lose_calls(meter):
    """Mapping runs sixteen calls at once; a lost increment understates the bill silently."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(lambda _: meter.record_llm("m/one", 10, 5), range(400)))
    assert meter.report(PRICES)["llm"][0]["calls"] == 400


def test_the_readme_table_is_generated_not_typed(meter):
    meter.record_ocr("rapidocr", pages=12)
    meter.record_llm("m/one", 100_000, 20_000)
    meter.record_search("serper")
    t = meter.table()
    assert "| Component | Engine used | Units | Measured cost |" in t
    assert "rapidocr" in t and "m/one" in t and "serper" in t
    assert "**Total**" in t


def test_the_shipped_price_file_covers_the_engines_we_default_to():
    """A price file that omits the default model reports every run as unpriced."""
    from backend.config import settings
    prices = json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))
    assert settings.openrouter_model in prices["llm"], settings.openrouter_model
    assert prices["ocr"][settings.ocr_provider] == 0.0


def test_a_worker_thread_records_into_the_same_meter(meter):
    """The defect this pins cost a run's entire cost table. Metering was held in a ContextVar,
    and a ThreadPoolExecutor worker starts with a FRESH context — so sixteen mapping threads
    recorded into meters nobody could read, and the run reported total_usd 0.0 with
    total_is_complete true. A confident zero is worse than a missing number."""
    from concurrent.futures import ThreadPoolExecutor

    def work(_):
        metering.record_llm("m/one", 100, 50)     # module-level call, as a provider makes it

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, range(32)))
    assert meter.report(PRICES)["llm"][0]["calls"] == 32


def test_a_run_that_spent_nothing_is_distinguishable_from_one_that_recorded_nothing(meter):
    """Both look like $0.00. The sample-corpus path genuinely spends nothing; a broken meter
    also reports nothing. `calls` is what tells them apart, so it has to be in the report."""
    r = meter.report(PRICES)
    assert r["llm"] == [] and r["total_usd"] == 0.0
    meter.record_llm("m/one", 0, 0)
    assert meter.report(PRICES)["llm"][0]["calls"] == 1
