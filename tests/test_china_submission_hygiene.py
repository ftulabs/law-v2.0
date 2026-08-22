"""What reached a China pillar-7 submission that should not have, and what did not that should.

Four defects, all silent, all visible only by reading the exported CSV:

  * two consultation DRAFTS were cited as evidence, at confidence 1.00 and 0.83. The row even
    carried the warning "Draft or bill — not in force, so it scores zero as a measure" — the
    classifier was right and nothing acted on it.
  * news pages ABOUT a measure were cited as the measure, with the site's navigation menu
    ("登录 注册 繁體版 EN 首页 …") as the Verbatim Snippet.
  * the Last Amended column was empty for every Chinese row.
  * Discovery Tag said NEW for all 51 rows, including PIPL — a law the panel's own database
    cites. See tests/test_baseline_multiscript.py.
"""
import pytest

from backend.pipeline.extraction import _stated_amendment_date
from backend.rdtii import instrument
from backend.rdtii.instrument import Status


# ── a page about a measure is not the measure ─────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "国家互联网信息办公室等十三部门修订发布《网络安全审查办法》",   # CAC "revises and issues"
    "李强签署国务院令公布《网络数据安全管理条例》",                 # "Li Qiang signs … promulgating"
    "数据安全所需日志留存时间不得少于六个月 《重庆市数据安全管理条例》9月1日起施行",
    "点击下载《个人信息保护影响评估报告（模板）》",                 # "click to download … (template)"
])
def test_a_news_item_about_an_instrument_is_commentary(name):
    assert instrument.classify(name) is Status.COMMENTARY


@pytest.mark.parametrize("name", [
    "中华人民共和国网络安全法",
    "网络安全审查办法",
    "网络数据安全管理条例(中华人民共和国国务院令第790号)",
    # The title IS the quoted instrument — brackets, no reporting verb.
    "《中华人民共和国数据安全法》",
    "Personal Data Protection Act 2012",
])
def test_a_measure_is_not_mistaken_for_a_news_item(name):
    assert instrument.classify(name) is Status.SCOREABLE


def test_a_consultation_draft_stays_a_draft_not_commentary():
    """Order matters: these carry 《》 too, and calling them commentary would lose the reason
    they are excluded — a draft scores zero because it is not in force, which is a different
    fact from being a press page."""
    for name in ["国家互联网信息办公室关于《互联网信息服务管理办法（修订草案征求意见稿）》再次公开征求意见的通知",
                 "国家互联网信息办公室关于《互联网应用程序个人信息收集使用规定（征求意见稿）》公开征求意见的通知"]:
        assert instrument.classify(name) is Status.DRAFT


# ── an instrument with no legal force is not evidence ─────────────────────────────────────

class _M:
    """Minimal stand-in: the filter reads only these two fields."""

    def __init__(self, law_name, indicator_id="P7-I3"):
        self.law_name = law_name
        self.indicator_id = indicator_id


def test_drafts_and_repealed_rows_are_dropped_amending_rows_are_kept():
    from backend.pipeline.orchestrator import _drop_instruments_with_no_force

    rows = [_M("中华人民共和国网络安全法"),
            _M("国家互联网信息办公室关于《互联网信息服务管理办法（修订草案征求意见稿）》公开征求意见的通知"),
            _M("Personal Data Protection (Amendment) Act 2020"),
            _M("Personal Data Protection Act 2012")]
    kept = _drop_instruments_with_no_force(rows, log=lambda _m: None)
    names = [m.law_name for m in kept]
    assert "中华人民共和国网络安全法" in names
    assert "Personal Data Protection Act 2012" in names
    # An amending act's finding is real — only its citation names the wrong instrument.
    assert "Personal Data Protection (Amendment) Act 2020" in names
    assert not any("征求意见稿" in n for n in names)


def test_the_drop_is_reported_rather_than_silent():
    from backend.pipeline.orchestrator import _drop_instruments_with_no_force

    logged = []
    _drop_instruments_with_no_force([_M("《X办法（征求意见稿）》公开征求意见的通知")], logged.append)
    assert any("draft" in m for m in logged)


# ── Last Amended, from the law's own legislative history ──────────────────────────────────

@pytest.mark.parametrize("head, expect", [
    # Adopted 2016, amended 2025 — the amendment is what "Last Amended" means.
    ("中华人民共和国网络安全法\n（2016年11月7日第十二届全国人民代表大会常务委员会第二十四次会议通过　"
     "根据2025年10月28日第十四届全国人民代表大会常务委员会第十八次会议《关于修改〈中华人民共和国"
     "网络安全法〉的决定》修正）", "2025-10-28"),
    # Never amended: the adoption date is the honest answer, and is what the panel records.
    ("中华人民共和国个人信息保护法\n（2021年8月20日第十三届全国人民代表大会常务委员会第三十次会议通过）",
     "2021-08-20"),
    # Amended twice — the latest wins.
    ("某法\n（2000年1月1日通过　根据2010年5月4日…修正　根据2019年4月23日…修正）", "2019-04-23"),
])
def test_a_chinese_law_states_its_own_dates(head, expect):
    assert _stated_amendment_date(head, "CN") == expect


def test_only_the_head_is_read():
    """A law quoting another law's amendment history deeper in its text would otherwise
    overwrite its own date with that one."""
    head = "某法\n（2021年8月20日通过）\n" + "第一条 " + ("填充。" * 900) + "根据2024年1月1日…修正"
    assert _stated_amendment_date(head, "CN") == "2021-08-20"


def test_no_date_is_invented_where_the_convention_does_not_apply():
    assert _stated_amendment_date("（2016年11月7日通过）", "SG") is None
    assert _stated_amendment_date("Personal Data Protection Act 2012", "CN") is None
    assert _stated_amendment_date("", "CN") is None
