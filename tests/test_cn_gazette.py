"""China State Council Gazette lane (`backend/pipeline/adapter_cn_gazette.py`).

Every fixture under tests/fixtures/portals/cn_gazette/ is a real page saved from www.gov.cn on
2026-09-29: the gazette's own issue index (a slice: nine real issues), nine issue pages, nine
instrument texts, and the robots.txt of the four hosts the lane was chosen between. Nothing
here touches the network.

What is pinned, and why each matters:
  * the lane is ALLOWED to read what it reads, and the three full-text databases it does not
    use really do forbid crawling (robots fixtures) — the reason this lane exists at all;
  * which table-of-contents entries count as a legislative instrument, and under which name;
  * the text screen finds the panel's sectoral pillar-6 instruments and NOT unrelated ones;
  * the end-to-end call returns exactly those five, best first, and the cache makes a second
    run fetch no instrument text again;
  * a cold run is bounded in time and says what it left; an unreachable index or a robots
    refusal returns nothing rather than raising;
  * through `discovery.discover_live`, these instruments outrank cac.gov.cn's front-page rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import settings
from backend.pipeline import adapter_cn_gazette as G
from backend.pipeline import discovery, portal, robots
from backend.rdtii.indicators import get_indicators
from backend.schemas import DocFormat, Economy

FX = Path(__file__).parent / "fixtures" / "portals" / "cn_gazette"
SHIPPED_INTERVAL_S = G._MIN_INTERVAL_S      # read before any fixture patches it

# issue URL (from the index slice) -> fixture file
ISSUES = {
    "https://www.gov.cn/gongbao/2017/issue_6126/": "cn_gazette_issue_2017_9.html",
    "https://www.gov.cn/gongbao/2016/issue_5846/": "cn_gazette_issue_2016_31.html",
    "https://www.gov.cn/gongbao/2016/issue_5586/": "cn_gazette_issue_2016_18.html",
    "https://www.gov.cn/gongbao/2016/issue_5506/": "cn_gazette_issue_2016_14.html",
    "https://www.gov.cn/gongbao/2016/issue_5306/": "cn_gazette_issue_2016_5.html",
    "https://www.gov.cn/gongbao/2016/issue_5125/": "cn_gazette_issue_2016_1.html",
    "https://www.gov.cn/gongbao/2013/issue_3640/": "cn_gazette_issue_2013_18.html",
    "https://www.gov.cn/gongbao/2013/issue_3381/": "cn_gazette_issue_2013_4.html",
    "https://www.gov.cn/gongbao/2008/issue_1676/": "cn_gazette_issue_2008_35.html",
}
C = "https://www.gov.cn/gongbao/content/"
CONTENT = {
    C + "2017/content_5181095.htm": "cn_gazette_content_2017_content_5181095.htm",  # 网络借贷
    C + "2016/content_5129498.htm": "cn_gazette_content_2016_content_5129498.htm",  # 网约车
    C + "2013/content_2326559.htm": "cn_gazette_content_2013_content_2326559.htm",  # 征信业
    C + "2016/content_2979707.htm": "cn_gazette_content_2016_content_2979707.htm",  # 地图
    C + "2016/content_5074079.htm": "cn_gazette_content_2016_content_5074079.htm",  # 网络出版
    C + "2008/content_1175820.htm": "cn_gazette_content_2008_content_1175820.htm",  # 森林防火
    C + "2016/content_5041555.htm": "cn_gazette_content_2016_content_5041555.htm",  # 会计档案
    C + "2016/content_5086355.htm": "cn_gazette_content_2016_content_5086355.htm",  # 放射性物品
}
INDEX = FX / "cn_gazette_gbgl_slice.json"

P6_EXPECTED = [  # (name, url) in the order the lane must return them
    # weighted 4 (two localisation sentences each); tie -> same year -> the newer ISSUE first
    ("网络预约出租汽车经营服务管理暂行办法", C + "2016/content_5129498.htm"),
    ("网络出版服务管理规定", C + "2016/content_5074079.htm"),
    # weighted 3 (one localisation + one outbound); tie -> newer instrument first
    ("网络借贷信息中介机构业务活动管理暂行办法", C + "2017/content_5181095.htm"),
    ("征信业管理条例", C + "2013/content_2326559.htm"),
    # weighted 2 (one localisation clause: art.34, servers inside the territory)
    ("地图管理条例", C + "2016/content_2979707.htm"),
]


def _read(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, status: int, text: str = ""):
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")


class FakeGov:
    """Serves the fixtures by URL; anything else is a 404. Records every request."""

    def __init__(self, pages: dict[str, str] | None = None, index: str | None = None):
        self.pages = dict(pages if pages is not None else self._default_pages())
        if index is not None:
            self.pages[G.INDEX_URL] = index
        self.requests: list[str] = []

    @staticmethod
    def _default_pages() -> dict[str, str]:
        pages = {G.INDEX_URL: INDEX.read_text(encoding="utf-8")}
        pages.update({u: _read(f) for u, f in ISSUES.items()})
        pages.update({u: _read(f) for u, f in CONTENT.items()})
        return pages

    def get(self, url, **_kw):
        self.requests.append(url)
        body = self.pages.get(url)
        return _Resp(200, body) if body is not None else _Resp(404)


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    """No network, no sleeping, a private cache directory."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(G, "_MIN_INTERVAL_S", 0.0)     # pacing has its own test below


def _run(client, pillar=6, src=None, log=None):
    said: list[str] = []
    docs = G.search_cn_gazette(client, src or {"name": "State Council Gazette (国务院公报)"}, "",
                               Economy.CN, get_indicators(pillar), log=log or said.append)
    return docs, said


# ── 1. the lane is allowed to read what it reads ─────────────────────────────────────────────

def test_gov_cn_robots_allows_every_url_shape_the_lane_reads():
    rules = robots.parse(_read("robots_www.gov.cn.txt"))
    for url in (G.INDEX_URL, "https://www.gov.cn/gongbao/2016/issue_5846/",
                C + "2016/content_5129498.htm"):
        assert rules.allowed(url, "Mozilla/5.0 VeriTrade"), url


@pytest.mark.parametrize("host", ["flk.npc.gov.cn", "sousuo.www.gov.cn", "sousuoht.www.gov.cn"])
def test_the_full_text_databases_forbid_crawling_which_is_why_this_lane_exists(host):
    rules = robots.parse(_read(f"robots_{host}.txt"))
    assert not rules.allowed(f"https://{host}/search?q=x", "Mozilla/5.0 VeriTrade")


def test_a_robots_refusal_fetches_nothing_and_returns_nothing(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: False)
    client = FakeGov()
    docs, said = _run(client)
    assert docs == [] and client.requests == []
    assert any("issue index unreachable" in m for m in said), said


# ── 2. which entries are instruments, under which name ───────────────────────────────────────

@pytest.mark.parametrize("entry, name", [
    ("中华人民共和国国务院令（第631号）　　征信业管理条例", "征信业管理条例"),
    # a long issuer list wrapped mid-word by the page, decree number split across lines
    ("中华人民共和国交通运输部 中华人民共和国工业和信息化部 中华人民共和国公安部 中华人民共和国"
     "　商务部 国家工商行政管理总局 国家质量监督检验检疫总局 国家互联网信息办公室令（2016年"
     "　　第60号）　　网络预约出租汽车经营服务管理暂行办法", "网络预约出租汽车经营服务管理暂行办法"),
    ("中国证券监督管理委员会公告（〔2008〕26号）　证券公司集合资产管理业务实施细则（试行）",
     "证券公司集合资产管理业务实施细则（试行）"),
    ("财政部关于印发《政府非税收入管理办法》的通知　　政府非税收入管理办法", "政府非税收入管理办法"),
    ("财政部 国家网信办关于印发《会计师事务所数据安全管理暂行办法》的通知",
     "会计师事务所数据安全管理暂行办法"),
    ("高法院高检院公安部安全部司法部印发《关于依法保障律师执业权利的规定》的通知　关于依法保障律师执业权利的规定",
     "关于依法保障律师执业权利的规定"),
    ("国务院办公厅关于印发国家卫生和计划生育委员会主要职责内设机构和人员 编制规定的通知 "
     "国家卫生和计划生育委员会主要职责内设机构和人员编制规定",
     "国家卫生和计划生育委员会主要职责内设机构和人员编制规定"),
    ("教育部关于印发《中小学教师资格考试暂行办法》《中小学教师资格定期注册暂 行办法》的通知 "
     "中小学教师资格考试暂行办法 中小学教师资格定期注册暂行办法", "中小学教师资格考试暂行办法"),
    # an amendment decision followed by the revised instrument: the instrument
    ("中华人民共和国交通运输部令（2013年第4号） 关于修改《快递业务经营许可管理办法》的决定 快递业务经营许可管理办法",
     "快递业务经营许可管理办法"),
    ("国家质量监督检验检疫总局公告（2013年第143号） 质检总局关于发布《国境口岸卫生处理监督管理办法》的公告 "
     "国境口岸卫生处理监督管理办法", "国境口岸卫生处理监督管理办法"),
    # "关于" inside a real regulation's own name
    ("国务院关于经营者集中申报标准的规定", "国务院关于经营者集中申报标准的规定"),
    # one name that CONTAINS an instrument word, and an 实施细则 of a law
    ("中华人民共和国国务院令（第692号） 中华人民共和国反间谍法实施细则", "中华人民共和国反间谍法实施细则"),
    ("中华人民共和国国务院令（第1号）　征信业管理条例实施办法", "征信业管理条例实施办法"),
    # leader dots in front of a name
    ("………………　中华人民共和国外国人入境出境管理条例", "中华人民共和国外国人入境出境管理条例"),    # single names a naive "second name" rule rejected (measured over all 14,892 entries)
    ("国家互联网信息办公室令（第16号）　　促进和规范数据跨境流动规定", "促进和规范数据跨境流动规定"),
    ("网络交易平台规则监督管理办法", "网络交易平台规则监督管理办法"),
    ("违反《铁路安全管理条例》行政处罚实施办法", "违反《铁路安全管理条例》行政处罚实施办法"),
    ("关于实施《证券期货投资者适当性管理办法》的规定", "关于实施《证券期货投资者适当性管理办法》的规定"),
    ("国家质量监督检验检疫总局规范性文件管理办法", "国家质量监督检验检疫总局规范性文件管理办法"),
    ("建设项目环境影响评价行为准则与廉政规定", "建设项目环境影响评价行为准则与廉政规定"),
    # "…印发《X》X" with no 的通知 in between
    ("中共中央国务院印发《信访工作条例》信访工作条例", "信访工作条例"),
])
def test_instrument_name_reads_the_instrument_not_its_cover(entry, name):
    assert G.instrument_name(entry) == name


@pytest.mark.parametrize("entry", [
    "中国人民银行令（〔2024〕第1号）　　中国人民银行关于修改《支付结算办法》的决定",   # decision alone
    "中华人民共和国商务部令（2016年第2号） 商务部关于废止和修改部分规章和规范性文件的决定",
    "国务院关于建立完善守信联合激励和失信联合惩戒制度加快推进社会诚信建设的指导意见",
    "国务院关于《西藏自治区国土空间规划（2021—2035年）》的批复",
    "中华人民共和国国务院任免人员",
    "国家税务总局公告（2016年第10号） 国家税务总局关于更新税务行政许可事项目录的公告",
    "国务院关于印发“十三五”脱贫攻坚规划的通知 “十三五”脱贫攻坚规划",
    "同舟共济，继往开来 ——在中非合作论坛第八届部长级会议开幕式上的主旨演讲",
    "安全监管总局关于宣布失效一批安全生产文件的通知 宣布失效的安全生产文件目录",
    # a batch amendment decision: the page amends many rules and prints none of them
    "中华人民共和国海关总署令（第240号）海关总署关于修改部分规章的决定中华人民共和国海关对进出境旅客行李物品"
    "监管办法中华人民共和国海关对中国籍旅客进出境行李物品的管理规定",
    # several names run together with no boundary to cut at
    "………………质检总局出入境检验检疫电子报检管理办法（试行）出入境检验检疫电子转单管理办法",
    "信托公司管理办法信托公司股权管理暂行办法银行保险机构关联交易管理办法",
    "互联网诊疗管理办法（试行）互联网医院管理办法（试行）远程医疗服务管理规范（试行）",
    "不动产登记暂行条例实施细则不动产登记资料查询暂行办法",
    "",
])
def test_non_instruments_are_not_kept(entry):
    assert G.instrument_name(entry) is None


def test_parse_index_is_newest_first_and_skips_foreign_urls():
    raw = json.loads(INDEX.read_text(encoding="utf-8"))
    raw[0]["values"]["2016年"]["第99号"] = {"gname": "https://example.org/not-an-issue/"}
    out = G.parse_index("﻿" + json.dumps(raw, ensure_ascii=False))
    assert [u for _, u in out] == list(ISSUES)          # ISSUES is written newest first
    assert [y for y, _ in out] == [2017, 2016, 2016, 2016, 2016, 2016, 2013, 2013, 2008]


def test_parse_issue_on_real_pages():
    rows = G.parse_issue(_read("cn_gazette_issue_2013_4.html"),
                         "https://www.gov.cn/gongbao/2013/issue_3381/")
    assert rows[0] == (C + "2013/content_2326559.htm", "征信业管理条例")
    assert all(u.startswith(C + "2013/content_") for u, _ in rows)

    rows = G.parse_issue(_read("cn_gazette_issue_2016_31.html"),
                         "https://www.gov.cn/gongbao/2016/issue_5846/")
    assert (C + "2016/content_5129498.htm", "网络预约出租汽车经营服务管理暂行办法") in rows

    rows = dict(G.parse_issue(_read("cn_gazette_issue_2017_9.html"),
                              "https://www.gov.cn/gongbao/2017/issue_6126/"))
    assert rows[C + "2017/content_5181095.htm"] == "网络借贷信息中介机构业务活动管理暂行办法"

    names = [n for _, n in G.parse_issue(_read("cn_gazette_issue_2016_18.html"),
                                         "https://www.gov.cn/gongbao/2016/issue_5586/")]
    assert "放射性物品运输安全监督管理办法" in names
    assert not [n for n in names if n.endswith(("意见", "批复", "通知", "公告", "决定"))]
    # footer links (content_… on /home/ and /zhengce/) are not gazette items
    assert all("/gongbao/content/" in u for u, _ in G.parse_issue(
        _read("cn_gazette_issue_2016_1.html"), "https://www.gov.cn/gongbao/2016/issue_5125/"))


# ── 3. the text screen ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fixture, p6, local, p7", [
    ("cn_gazette_content_2013_content_2326559.htm", 3, 1, 2),    # 征信业管理条例 (panel 6.1)
    ("cn_gazette_content_2016_content_2979707.htm", 2, 1, 3),    # 地图管理条例 (panel 6.2/6.3)
    ("cn_gazette_content_2016_content_5074079.htm", 4, 2, 1),    # 网络出版服务管理规定 (6.3)
    ("cn_gazette_content_2016_content_5129498.htm", 4, 2, 7),    # 网约车 (6.1/6.2/6.3/7.3)
    ("cn_gazette_content_2017_content_5181095.htm", 3, 1, 2),    # 网络借贷 (panel 6.1)
    ("cn_gazette_content_2016_content_5041555.htm", 0, 0, 12),   # 会计档案管理办法 (7.3)
    ("cn_gazette_content_2008_content_1175820.htm", 0, 0, 0),    # 森林防火条例 (unrelated)
    ("cn_gazette_content_2016_content_5086355.htm", 0, 0, 0),    # 放射性物品运输… (unrelated)
])
def test_screen_counts_on_real_texts(fixture, p6, local, p7):
    """Exact counts: a change to the screen rules must show up here, and must bump
    SCREEN_VERSION so every cached count is recomputed."""
    assert G.screen(G._text_of(_read(fixture))) == {"p6": p6, "p6_local": local, "p7": p7}


@pytest.mark.parametrize("sentence, p6", [
    # localisation sentences weigh 2
    ("互联网地图服务单位应当将存放地图数据的服务器设在中华人民共和国境内。", 2),
    ("网约车平台公司所采集的个人信息和生成的业务数据，应当在中国内地存储和使用。", 2),
    ("征信机构在中国境内采集的信息的整理、保存和加工，应当在中国境内进行。", 2),
    # outbound sentences weigh 1
    ("上述信息和数据不得外流。", 1),
    ("征信机构向境外组织或者个人提供信息，应当遵守法律、行政法规的有关规定。", 1),
    ("关键信息基础设施运营者向境外提供个人信息的，应当进行安全评估。", 1),
    # SCREEN_VERSION 1 counted these — customs sentences where goods and vehicles leave
    ("出境运输工具预计载有旅客的，舱单传输人应当在1小时以前向海关传输预配舱单电子数据。", 0),
    ("小型船舶出境前，船舶负责人应当通过公共数据信息平台向海关发送舱单电子数据。", 0),
    ("产地检验检疫机构与口岸检验检疫机构应当及时交流出境水生动物信息。", 0),
    ("境外投资者应当依法办理登记手续。", 0),        # territory, no data
    ("经营者应当妥善存储用户数据。", 0),            # data + storage, no territory
    ("国家鼓励数据开发利用。", 0),
])
def test_p6_needs_data_tied_to_the_territory_in_one_sentence(sentence, p6):
    assert G.screen(sentence)["p6"] == p6


@pytest.mark.parametrize("sentence, p7", [
    ("会计档案的保管期限为永久、定期两类，定期保管期限最低为10年。", 1),
    ("网约车平台公司应当记录驾驶员、约车人在其服务平台发布的信息内容，保存期限不少于2年。", 1),
    ("公安机关依法调取数据的，网络运营者应当予以协助。", 1),
    ("处理个人信息应当遵循合法、正当、必要原则，保护个人信息安全。", 1),
    ("森林防火工作实行各级人民政府行政首长负责制。", 0),
])
def test_p7_duty_sentences(sentence, p7):
    assert G.screen(sentence)["p7"] == p7


def test_score_scale_sits_between_cac_noise_and_cac_statutes():
    """Above a cac.gov.cn row with no topic signal (0.68), below the statutes cac.gov.cn finds
    by name (网络安全法 0.93): with a 0.95 ceiling the gazette pushed the Cybersecurity Law out
    of a live run on 2026-09-29."""
    assert G.score(0) == 0.0
    assert 0.68 < G.score(1) < G.score(2) < G.score(6) == G.score(60) == 0.90 < 0.93


# ── 4. end to end over the fixtures ──────────────────────────────────────────────────────────

def test_pillar6_returns_exactly_the_panels_sectoral_instruments_best_first():
    docs, said = _run(FakeGov(), pillar=6)
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED
    for d in docs:
        assert d.law_name == d.title
        assert d.economy is Economy.CN and d.fmt is DocFormat.HTML
        assert d.doc_id == portal.doc_id("CN", d.source_url)
        assert d.relevance_score > 0.68
    assert docs[0].relevance_score >= docs[-1].relevance_score
    assert any("9 issues" in m for m in said), said


def test_pillar7_ranks_the_retention_rule_first():
    docs, _ = _run(FakeGov(), pillar=7)
    assert docs[0].title == "会计档案管理办法"
    assert {"网络预约出租汽车经营服务管理暂行办法", "征信业管理条例"} <= {d.title for d in docs}
    assert "森林防火条例" not in {d.title for d in docs}


def test_second_run_reads_no_instrument_text_again():
    first = FakeGov()
    _run(first)
    screened = [u for u in first.requests if u in CONTENT]
    assert sorted(screened) == sorted(CONTENT)             # every fixture text was screened once

    second = FakeGov()
    docs, said = _run(second)
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED
    assert not [u for u in second.requests if u in CONTENT]
    # only the index and the newest issues are re-read; older issue pages come from the cache
    assert [u for u in second.requests if u in ISSUES] == list(ISSUES)[:G._FRESH_ISSUES]
    assert any("screened 0 new" in m for m in said), said


def test_a_better_name_rule_reaches_cached_issues_without_refetching_them(monkeypatch):
    """Issue pages never change, so they are cached — but the NAMES read from them are derived
    at read time. A rule change must take effect on a warm cache."""
    _run(FakeGov())
    real = G.instrument_name
    monkeypatch.setattr(G, "instrument_name",
                        lambda text: None if "征信" in (text or "") else real(text))
    again = FakeGov()
    docs, _ = _run(again)
    assert "征信业管理条例" not in {d.title for d in docs}
    assert [u for u in again.requests if u in ISSUES] == list(ISSUES)[:G._FRESH_ISSUES]


def test_cache_from_an_older_screen_version_is_recomputed(monkeypatch):
    _run(FakeGov())
    monkeypatch.setattr(G, "SCREEN_VERSION", G.SCREEN_VERSION + 1)
    again = FakeGov()
    docs, _ = _run(again)
    assert sorted(u for u in again.requests if u in CONTENT) == sorted(CONTENT)
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED


def test_a_cold_run_out_of_time_says_what_it_left_and_the_next_run_finishes():
    docs, said = _run(FakeGov(), src={"name": "g", "screen_budget_s": 0})
    assert docs == []
    assert any("left for the next run" in m for m in said), said
    docs, _ = _run(FakeGov())
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED


def test_an_unreachable_text_is_not_cached_as_zero():
    client = FakeGov()
    url = C + "2016/content_2979707.htm"                   # 地图管理条例
    del client.pages[url]
    docs, _ = _run(client)
    assert "地图管理条例" not in {d.title for d in docs}
    docs, _ = _run(FakeGov())                              # the page is back
    assert "地图管理条例" in {d.title for d in docs}


def test_unreachable_or_broken_index_returns_nothing():
    client = FakeGov()
    del client.pages[G.INDEX_URL]
    docs, said = _run(client)
    assert docs == [] and any("index unreachable" in m for m in said)
    docs, said = _run(FakeGov(index="<html>not json</html>"))
    assert docs == [] and any("index unreadable" in m for m in said)


def _synthetic_index(*issue_urls: str) -> str:
    """Issues numbered in the order given: the LAST url is the newest issue."""
    issues = {f"第{i}号": {"gname": u} for i, u in enumerate(issue_urls, 1)}
    return json.dumps([{"values": {"2020年": issues}}], ensure_ascii=False)


def _issue_page(*items: tuple[str, str]) -> str:
    lis = "".join(f'<li><a href="../../content/2020/{h}">{t}</a></li>' for h, t in items)
    return f"<html><body><ul>{lis}</ul></body></html>"


def test_one_name_in_two_issues_keeps_the_newest_screened_copy():
    new_issue, old_issue = ("https://www.gov.cn/gongbao/2020/issue_2/",
                            "https://www.gov.cn/gongbao/2020/issue_1/")
    law = "中华人民共和国国务院令（第1号）　　数据管理条例"
    pages = {
        G.INDEX_URL: _synthetic_index(old_issue, new_issue),
        new_issue: _issue_page(("content_2.htm", law)),
        old_issue: _issue_page(("content_1.htm", law)),
        C + "2020/content_2.htm": "<p>第一条　个人信息应当在境内存储。</p>",
        C + "2020/content_1.htm": "<p>第一条　个人信息应当在境内存储。</p><p>第二条　数据不得出境。</p>",
    }
    docs, _ = _run(FakeGov(pages=pages))
    assert [(d.title, d.source_url) for d in docs] == [("数据管理条例", C + "2020/content_2.htm")]


def test_a_newer_copy_that_screens_zero_does_not_hide_an_older_positive_one():
    new_issue, old_issue = ("https://www.gov.cn/gongbao/2020/issue_2/",
                            "https://www.gov.cn/gongbao/2020/issue_1/")
    law = "中华人民共和国国务院令（第1号）　　数据管理条例"
    pages = {
        G.INDEX_URL: _synthetic_index(old_issue, new_issue),
        new_issue: _issue_page(("content_2.htm", law)),
        old_issue: _issue_page(("content_1.htm", law)),
        C + "2020/content_2.htm": "<p>第一条　本条例自公布之日起施行。</p>",
        C + "2020/content_1.htm": "<p>第一条　个人信息应当在境内存储。</p>",
    }
    docs, _ = _run(FakeGov(pages=pages))
    assert [(d.title, d.source_url) for d in docs] == [("数据管理条例", C + "2020/content_1.htm")]


def test_pillar6_ties_prefer_a_localisation_clause():
    """Two instruments at the same weighted count: the one whose count comes from a
    localisation sentence ranks first, whatever the year."""
    issue = "https://www.gov.cn/gongbao/2020/issue_1/"
    pages = {
        G.INDEX_URL: _synthetic_index(issue),
        issue: _issue_page(("content_1.htm", "国务院令（第1号）　甲管理办法"),
                           ("content_2.htm", "国务院令（第2号）　乙管理办法")),
        C + "2020/content_1.htm": "<p>第一条　数据不得出境。</p><p>第二条　信息不得外流。</p>",
        C + "2020/content_2.htm": "<p>第一条　服务器应当设在中华人民共和国境内并存储数据。</p>",
    }
    docs, _ = _run(FakeGov(pages=pages))
    assert [d.title for d in docs] == ["乙管理办法", "甲管理办法"]


# ── 5. wiring ────────────────────────────────────────────────────────────────────────────────

def test_registered_as_a_portal_enumerator():
    assert portal.get_adapter("cn_gazette") is G.search_cn_gazette
    assert portal.enumerates_portal("cn_gazette") is True


def test_sources_yaml_carries_the_lane_for_china():
    cn = [s for s in discovery.load_sources() if s.get("economy") == "CN"]
    gaz = [s for s in cn if s.get("adapter") == "cn_gazette"]
    assert len(gaz) == 1
    assert gaz[0].get("base_url", "").startswith("https://www.gov.cn/gongbao")
    # both portal lanes are present; cn_portal still brings the NPC statutes
    assert {"cn_portal", "cn_gazette"} <= {s.get("adapter") for s in cn}


def test_through_discovery_the_gazette_instruments_outrank_cac_front_page_rows(monkeypatch):
    """The real `discover_live` merge, cap and non-measure drop, with cac.gov.cn replaced by a
    stub returning what it returned on 2026-09-29: one statute, recent action plans at its
    0.68 search weight, and commentary."""
    fake = FakeGov()

    def _cac(client, src, query, economy, indicators, log):
        mk = lambda u, t, s: portal.make_doc(economy, u, t, "cac", score=s)   # noqa: E731
        rows = [mk("https://www.cac.gov.cn/law.htm", "中华人民共和国网络安全法", 0.93)]
        rows += [mk(f"https://www.cac.gov.cn/plan{i}.htm",
                    f"促进网信企业高质量发展行动计划（2026-2030年）第{i}批", 0.68) for i in range(12)]
        rows += [mk(f"https://www.cac.gov.cn/n{i}.htm", f"专家解读｜数据出境第{i}问", 0.95)
                 for i in range(40)]
        return rows

    def _gazette(client, src, query, economy, indicators, log):
        return G.search_cn_gazette(fake, src, query, economy, indicators, log)

    real = portal.get_adapter("cn_gazette")
    portal.register("stub_cac", _cac, enumerates_portal=True)
    portal.register("cn_gazette", _gazette, enumerates_portal=True)
    try:
        monkeypatch.setattr(discovery, "load_sources", lambda: [
            {"economy": "CN", "name": "cac", "adapter": "stub_cac", "queries_p6": ["x"]},
            {"economy": "CN", "name": "gazette", "adapter": "cn_gazette"},
        ])
        docs = discovery.discover_live(Economy.CN, pillar=6, max_docs=6, log=lambda _m: None)
    finally:
        portal.register("cn_gazette", real, enumerates_portal=True)
        portal._REGISTRY.pop("stub_cac", None)
        getattr(portal, "_ENUMERATES_PORTAL", {}).pop("stub_cac", None)
    titles = [d.title for d in docs]
    assert titles[0] == "中华人民共和国网络安全法"
    assert titles[1:] == [n for n, _ in P6_EXPECTED]
    assert not [t for t in titles if "行动计划" in t or "解读" in t]


def test_a_screened_lane_adds_its_own_slots_to_the_default_budget(monkeypatch):
    """`adds_docs:` grows the DEFAULT budget only; an explicit `max_docs` is exact."""
    def _many(client, src, query, economy, indicators, log):
        # fifty distinct instrument names ("甲子数据管理办法" …), each a citable measure
        return [portal.make_doc(economy, f"https://www.gov.cn/gongbao/content/x{i}.htm",
                                f"{'甲乙丙丁戊己庚辛壬癸'[i % 10]}{'子丑寅卯辰'[i // 10]}数据管理办法",
                                "g", score=0.8) for i in range(50)]

    portal.register("stub_many", _many, enumerates_portal=True)
    try:
        monkeypatch.setattr(settings, "discovery_max_docs", 5)
        monkeypatch.setattr(discovery, "load_sources", lambda: [
            {"economy": "CN", "name": "g", "adapter": "stub_many", "adds_docs": 7}])
        assert len(discovery.discover_live(Economy.CN, pillar=6, log=lambda _m: None)) == 12
        assert len(discovery.discover_live(Economy.CN, pillar=6, max_docs=5,
                                           log=lambda _m: None)) == 5
        monkeypatch.setattr(discovery, "load_sources", lambda: [
            {"economy": "CN", "name": "g", "adapter": "stub_many"}])
        assert len(discovery.discover_live(Economy.CN, pillar=6, log=lambda _m: None)) == 5
    finally:
        portal._REGISTRY.pop("stub_many", None)
        getattr(portal, "_ENUMERATES_PORTAL", {}).pop("stub_many", None)


def test_sources_yaml_gives_the_gazette_lane_its_own_slots():
    gaz = [s for s in discovery.load_sources() if s.get("adapter") == "cn_gazette"][0]
    assert int(gaz.get("adds_docs") or 0) >= G._MAX_RETURN - 10



# ── 6. politeness: one request at a time, one per second ─────────────────────────────────────

class _Clock:
    """A fake monotonic clock: time passes only when the code sleeps (or a request is made)."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += max(0.0, s)


def test_requests_are_sequential_and_at_least_one_second_apart(monkeypatch):
    """Every request start, INCLUDING portal_get's retry of a failed page, is at least one
    second after the previous one. Retries are spaced by `crawl_delay_seconds`, so this runs
    with its shipped value, not the zero the other tests use."""
    clock = _Clock()
    monkeypatch.setattr(G, "_MIN_INTERVAL_S", 1.0)
    monkeypatch.setattr(settings, "crawl_delay_seconds", type(settings)().crawl_delay_seconds)
    monkeypatch.setattr(portal.time, "sleep", clock.sleep)
    monkeypatch.setattr(G.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(G.time, "sleep", clock.sleep)
    starts: list[float] = []

    class Timed(FakeGov):
        def get(self, url, **kw):
            starts.append(clock.now)
            clock.now += 0.3                          # the request itself takes 0.3 s
            return super().get(url, **kw)

    client = Timed()
    docs, _ = _run(client, src={"name": "g", "screen_budget_s": 10_000})
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED
    assert len(starts) == len(client.requests) > 10
    # each request takes 0.3 s, so start-to-start must be at least 1.3 s
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= 1.3 - 1e-9, gaps


def test_the_budget_also_bounds_reading_issue_pages(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(G, "_MIN_INTERVAL_S", 1.0)
    monkeypatch.setattr(G.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(G.time, "sleep", clock.sleep)
    client = FakeGov()
    docs, said = _run(client, src={"name": "g", "screen_budget_s": 3.5})
    # index at t=0, issues at t=1,2,3,4 (the budget is checked before the one-second wait);
    # at t=4 > 3.5 it stops: no sixth request, no text screened
    assert client.requests[0] == G.INDEX_URL
    assert len(client.requests) == 5
    assert not [u for u in client.requests if u in CONTENT]
    assert docs == []
    assert any("left for the next run" in m for m in said), said
    # a later call carries on from the cache and finishes
    monkeypatch.setattr(G, "_MIN_INTERVAL_S", 0.0)
    docs, _ = _run(FakeGov(), src={"name": "g", "screen_budget_s": 10_000})
    assert [(d.title, d.source_url) for d in docs] == P6_EXPECTED


def test_warm_runs_without_a_budget_over_both_pillars(monkeypatch):
    seen = {}

    def _capture(client, src, query, economy, indicators, log):
        seen["budget"] = src.get("screen_budget_s")
        seen["pillars"] = {i.pillar for i in indicators}
        seen["adapter"] = src.get("adapter")
        return []

    monkeypatch.setattr(G, "search_cn_gazette", _capture)
    G.warm(log=lambda _m: None)
    assert seen == {"budget": float("inf"), "pillars": {6, 7}, "adapter": "cn_gazette"}


def test_the_shipped_retry_delay_keeps_retries_at_or_under_one_request_per_second():
    from backend.config import Settings
    assert Settings().crawl_delay_seconds >= SHIPPED_INTERVAL_S == 1.0
