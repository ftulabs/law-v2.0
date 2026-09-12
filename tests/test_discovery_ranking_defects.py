"""Four discovery defects found on 2026-09-11/12, each pinned by the evidence that found it.

They are grouped here because they share one shape: NOTHING RAISED. Each produced a full run,
a complete CSV and a plausible-looking document set, and each was only visible by reading what
discovery actually returned and asking whether those were laws about the right subject in the
right country.

  1. TRUNCATE-BEFORE-RANK. The round-robin merge took candidates in the order an adapter
     returned them and stopped at `max_docs * 3`. Singapore Statutes Online returns all 524
     current Acts in ALPHABETICAL order, so the run kept sixty-six A-titles and discarded
     everything after them — the Personal Data Protection Act included, which the adapter had
     just scored 0.9035 against the 0.6000 of the Acts that survived it.

  2. TITLE SCORED WITH BODY PHRASES. Six adapters ranked a title with `discovery._score`,
     which counts an indicator's `query_terms` — operative provision phrases, all forty-three
     of pillar 6's being multi-word. No title contains one, so the topical term read 0.000 for
     every candidate and the score collapsed to the adapter's constant base weight. A constant
     sort key is a no-op, which is what fed defect 1.

  3. OFF-HOST WEB RESULTS. `site:` is a request the engine may ignore, and a degraded engine
     ignores it. A Russia pillar-6 run returned fifteen documents of which ZERO were on a
     Russian government host: an advert for a VPN subscription, Wikipedia, cloudflare.com,
     Vietnam's own 91/2025/QH15, and Singapore's regulator.

  4. NON-MEASURES RANKED AS MEASURES. `rdtii/instrument.py` had recognised commentary, drafts
     and repeals since Round 2, but only the exporter asked it — after fetch, OCR, splitting
     and grading. A China pillar-6 run spent all twenty-two of its slots on articles ABOUT the
     Personal Information Protection Law and reached the grader with one statute.
"""
from __future__ import annotations

import pytest

from backend.pipeline import discovery, portal
from backend.rdtii import instrument
from backend.rdtii.indicators import get_indicators
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy


def _doc(title: str, score: float = 0.0, url: str | None = None,
         economy: str = "SG") -> DiscoveredDoc:
    url = url or f"https://sso.agc.gov.sg/Act/{abs(hash(title)) % 10**6}"
    return DiscoveredDoc(
        doc_id=portal.doc_id(economy, url), economy=Economy(economy), title=title,
        source_url=url, portal="test", fmt=DocFormat.HTML, relevance_score=score,
        discovery_tag=DiscoveryTag.NEW)


# ── 1. title relevance ───────────────────────────────────────────────────────────────────────

def test_a_relevant_act_outranks_an_irrelevant_one_on_title_alone():
    """The measurement that started this: both of these scored 0.000 under `_score`."""
    inds = get_indicators(6)
    pdpa = portal.title_relevance("Personal Data Protection Act 2012", inds, economy="SG")
    birds = portal.title_relevance("Animals and Birds Act 1965", inds, economy="SG")
    assert pdpa > birds, f"PDPA {pdpa} did not beat Animals and Birds {birds}"
    assert birds == 0.0


def test_the_old_scorer_really_could_not_tell_them_apart():
    """Guards the PREMISE. If `_score` ever starts separating titles, the fix above is no
    longer load-bearing and this file should be revisited rather than quietly kept."""
    inds = get_indicators(6)
    assert discovery._score("Personal Data Protection Act 2012", inds) == \
           discovery._score("Animals and Birds Act 1965", inds)


@pytest.mark.parametrize("economy, relevant, irrelevant", [
    ("CN", "中华人民共和国个人信息保护法", "中华人民共和国种子法"),
    ("TH", "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒", "พระราชบัญญัติกองทุนยุติธรรม พ.ศ. 2558"),
    ("LA", "ກົດໝາຍວ່າດ້ວຍ ຄວາມປອດໄພໄຊເບີ", "ກົດໝາຍວ່າດ້ວຍ ການປູກຝັງ"),
    ("ID", "Undang-undang Nomor 27 Tahun 2022 — Pelindungan Data Pribadi",
           "Undang-undang Nomor 4 Tahun 2021 — Pengesahan ASEAN Agreement"),
    ("TL", "Lei da Proteção de Dados Pessoais", "Lei dos Símbolos Nacionais"),
])
def test_native_title_vocabulary_separates_relevant_from_irrelevant(economy, relevant, irrelevant):
    """One case per non-English economy, because each has its own script and its own way of
    failing. Laos is the reason this is parametrised rather than written once: it had no entry
    in `ECONOMY_QUERY_LANG` at all, so every Lao title scored 0.0000 including the Cybersecurity
    Law, and a single English-only test would never have shown it."""
    inds = get_indicators(6) + get_indicators(7)
    hit = portal.title_relevance(relevant, inds, economy=economy)
    miss = portal.title_relevance(irrelevant, inds, economy=economy)
    assert hit > miss, f"{economy}: {relevant!r} scored {hit}, {irrelevant!r} scored {miss}"


# ── 2. truncate-before-rank ──────────────────────────────────────────────────────────────────

def test_a_high_scoring_candidate_survives_an_alphabetical_portal(monkeypatch):
    """The Singapore failure in miniature: the wanted Act sits far down an alphabetical index,
    past the point the merge used to stop at."""
    filler = [_doc(f"A{i:04d} Filler Act 1900") for i in range(300)]
    wanted = _doc("Personal Data Protection Act 2012", score=0.9035)
    bucket = filler + [wanted]          # exactly as SSO returns it: alphabetical, wanted late

    monkeypatch.setattr(discovery, "load_sources",
                        lambda: [{"economy": "SG", "adapter": "stub_portal", "name": "stub"}])
    monkeypatch.setattr(discovery, "discover_websearch", lambda *a, **kw: [])
    portal.register("stub_portal", lambda *a, **kw: list(bucket), enumerates_portal=True)

    docs = discovery.discover_live(Economy("SG"), 6, log=lambda _m: None)
    assert any(d.title == "Personal Data Protection Act 2012" for d in docs), (
        "the highest-scoring Act was discarded by arrival order before anything was sorted")
    assert docs[0].title == "Personal Data Protection Act 2012"


# ── 3. off-host web results ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, allowed", [
    ("http://publication.pravo.gov.ru/Document/View/0001", True),
    ("https://publication.pravo.gov.ru/x", True),
    ("https://www.publication.pravo.gov.ru/x", True),
    ("https://duckduckgo.com/ad", False),
    ("https://en.wikipedia.org/wiki/Data_localization", False),
    ("https://www.cloudflare.com/learning/", False),
    ("https://thuvienphapluat.vn/91-2025-QH15", False),      # Vietnam's law, not Russia's
    ("https://www.pdpc.gov.sg/guide", False),                # Singapore's regulator
])
def test_only_the_declared_official_host_is_accepted(url, allowed):
    """Every one of these URLs is from the real Russia pillar-6 result set of 2026-09-11."""
    assert discovery._on_official_host(url, "publication.pravo.gov.ru") is allowed


def test_a_lane_with_no_known_host_returns_nothing_rather_than_searching_the_open_web(monkeypatch):
    """Russia had no `OFFICIAL_PORTAL` entry, which is HOW the lane came to run unscoped. An
    unattributable result is worse than no result, so the lane declines."""
    said = []
    monkeypatch.setattr("backend.pipeline.websearch.OFFICIAL_PORTAL", {})
    out = discovery.discover_websearch(Economy("RU"), 6, 22, site=None, base_url=None,
                                       log=said.append)
    assert out == []
    assert any("no official host known" in m for m in said), said


# ── 4. non-measures ──────────────────────────────────────────────────────────────────────────

def test_commentary_about_a_law_is_dropped_at_discovery_not_at_export():
    """Titles from the real China pillar-6 result set. Each NAMES the statute it discusses, so
    no keyword scorer can separate them from it — only the instrument class can."""
    docs = [
        _doc("中华人民共和国个人信息保护法", 0.93, url="https://www.cac.gov.cn/a", economy="CN"),
        _doc("数据出境安全评估办法", 0.99, url="https://www.cac.gov.cn/b", economy="CN"),
        _doc("专家解读｜个人信息保护法治的中国方案", 0.85, url="https://www.cac.gov.cn/c", economy="CN"),
        _doc("“《个人信息保护法》实施一周年实践与展望”高峰论坛在京举行", 0.85,
             url="https://www.cac.gov.cn/d", economy="CN"),
        _doc("国家互联网信息办公室关于《数据出境安全评估办法（征求意见稿）》公开征求意见的通知",
             0.99, url="https://www.cac.gov.cn/e", economy="CN"),
        _doc("中央网信办举办“网络法治讲堂”活动", 0.68, url="https://www.cac.gov.cn/f", economy="CN"),
    ]
    kept = {d.title for d in discovery._drop_unscoreable(docs, lambda _m: None)}
    assert kept == {"中华人民共和国个人信息保护法", "数据出境安全评估办法"}


def test_an_amending_act_is_kept_because_a_later_stage_owns_that_decision():
    """`orchestrator._drop_unscoreable_rows` keeps amending acts deliberately (the finding is
    right, only the citation needs re-pointing) and Malaysia depends on it, because AGC
    publishes dated reprints so an amendment newer than the reprint is real evidence. Dropping
    them here would silently reverse a decision made two layers down."""
    docs = [_doc("Personal Data Protection (Amendment) Act 2024", 0.9,
                 url="https://lom.agc.gov.my/x", economy="MY")]
    assert instrument.classify(docs[0].title) is instrument.Status.AMENDING
    assert len(discovery._drop_unscoreable(docs, lambda _m: None)) == 1


def test_a_real_measure_is_never_mistaken_for_commentary():
    """The guard on the guard. Guidance documents ARE the cited instrument in several of the
    panel's own answers, so over-blocking costs real evidence."""
    for name in ("中华人民共和国网络安全法", "数据出境安全评估办法", "网络安全审查办法",
                 "个人信息保护影响评估指南", "Personal Data Protection Act 2012",
                 "Cybersecurity Act 2018", "Advisory Guidelines on Key Concepts in the PDPA"):
        assert instrument.classify(name) is instrument.Status.SCOREABLE, name


# ── 5. the four families that survived the first China pass ─────────────────────────────────
#
# Titles below are VERBATIM from a live China run on both pillars, 2026-09-12, after the first
# round of commentary patterns had already dropped 55 of 66 pillar-6 candidates and 41 of 63 on
# pillar 7. What was left was not noise in general — it was four specific shapes, each a
# STRUCTURAL property of a Chinese government feed rather than a keyword to chase.

@pytest.mark.parametrize("title, why", [
    ("一图读懂｜《数据安全技术 电子产品信息清除技术要求》强制性国家标准", "column masthead"),
    ("E法同行 兴辽治宁｜“知E行法”普法小剧场② 数据安全法五周年篇", "column masthead"),
    ("《中华人民共和国网络安全法》修改后有哪些变化？", "the title is a question"),
    ("网络安全法施行6周年！重温习近平总书记重要论述", "anniversary piece"),
    ("关于对派拓公司在华销售产品启动网络安全审查的公告", "enforcement against a named company"),
    ("网络安全审查办公室关于对“滴滴出行”启动网络安全审查的公告", "enforcement"),
    ("北京市网信办对三家企业未履行数据安全保护义务作出行政处罚", "administrative penalty"),
    ("国家网信办依法集中查处一批侵害个人信息权益的违法违规App", "enforcement sweep"),
    ("国家网信办发布近期网络安全、数据安全、个人信息保护相关执法典型案例", "case digest"),
    ("吉林省白城市委网信办认真组织开展《中华人民共和国数据安全法》等法律法规专题培训活动",
     "a training session ABOUT the law"),
    ("网络安全如何保障，习近平这些话指明路径", "leadership commentary"),
    ("提升数据安全治理效能（新知新觉）", "newspaper column"),
    ("《个人信息出境安全评估办法》体现“以人为本”的数据治理理念", "opinion piece about a measure"),
    ("2025年人工智能技术赋能网络安全应用测试结果发布", "test results"),
    ("中国个人信息保护报告（2025年）", "an annual report, not a measure"),
])
def test_these_are_not_measures(title, why):
    assert instrument.classify(title) in instrument.UNSCOREABLE, f"{why}: {title}"


@pytest.mark.parametrize("title", [
    # Every one of these was in the same run's output and IS citable.
    "数据出境安全评估办法",
    "中华人民共和国个人信息保护法",
    "中华人民共和国网络安全法",
    "中华人民共和国数据安全法",
    "个人信息出境标准合同办法",
    "网络数据安全管理条例",
    "粤港澳大湾区（内地、香港）个人信息跨境流动标准合同实施指引",
    "关于开展个人信息保护负责人信息报送工作的公告",
    # And these are the near-misses the patterns must not take with them.
    "网络安全审查办法",                    # the REVIEW MEASURES, not a review being opened
    "数据安全技术 电子产品信息清除技术要求",  # the standard itself, without its 一图读懂 wrapper
    "个人信息保护影响评估指南",
    "关键信息基础设施安全保护条例",
    "中华人民共和国密码法",
])
def test_and_these_still_are(title):
    """The guard on the guard. 'Enforcement' patterns that also catch 网络安全审查办法 would
    delete the very Measures the enforcement is carried out under."""
    assert instrument.classify(title) is instrument.Status.SCOREABLE, title
