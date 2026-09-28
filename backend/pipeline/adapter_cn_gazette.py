"""China — State Council Gazette (国务院公报) lane, screened by FULL TEXT, not by title.

WHY THIS LANE EXISTS. Measured 2026-09-29: the panel's Round-2 database cites eleven Chinese
instruments for pillar 6, and the only other lane (`cn_portal`, cac.gov.cn) reached two of
them. The rest are SECTORAL rules from other issuers — the ride-hailing measures (Ministry of
Transport and six others), online lending (banking regulator), credit reporting and map
management (State Council), online publishing (press regulator). A cyberspace regulator's
website never lists them, and their titles carry no data vocabulary at all: 地图管理条例 and
网络预约出租汽车经营服务管理暂行办法 both score 0.0 on `portal.title_relevance`. The obligation
is in the TEXT — 地图管理条例 art.34 puts map-data servers inside the territory, the
ride-hailing measures art.27 keep platform data 在中国内地存储.

WHY THE GAZETTE, AND NOT A SEARCH ENGINE. The three national full-text databases —
flk.npc.gov.cn, sousuo.www.gov.cn and the rules library's sousuoht.www.gov.cn backend — each
publish `Disallow: /` for every user agent (checked 2026-09-29). www.gov.cn does not disallow
/gongbao/, and the gazette carries exactly the tiers the panel cites: 国务院令 (administrative
regulations) and the ministries' 部令 (departmental rules), in full text. Of the panel's
pillar-6 and pillar-7 citations that are not NPC statutes, it holds 网约车, 网络借贷, 征信业,
地图, 网络出版, 促进和规范数据跨境流动规定, 网络数据安全管理条例, 互联网信息服务管理办法,
会计档案管理办法, 互联网电子邮件服务管理办法 and more (measured over all 936 issues, 14,892
items). NPC STATUTES (PIPL, the Cybersecurity Law) are NOT in it — they reach the run through
`cn_portal`.

HOW, IN FOUR STEPS
  1. `/gongbao/gbgl.json` is the gazette's own issue index (the page's archive widget reads it):
     year → issue → issue URL. 2000 onward uses one page layout; that is what is read.
  2. Each issue page lists its items. An item is kept when it is a LEGISLATIVE instrument —
     a decree (…令（第N号）) or a notice issuing one (关于印发《X》的通知) — whose name ends in an
     instrument type (法/条例/办法/规定/规则/细则/规范/准则). Repeal and pure amendment decisions,
     approvals (批复), plans, notices and appointments are not. See `instrument_name`.
  3. Every kept instrument's text is SCREENED: how many sentences tie data to the territory
     (P6: kept in / processed in / servers in the territory, or data sent out of it) or carry
     a data-protection / retention / government-access duty (P7). See `screen`. This is the
     step that finds 地图管理条例 — no title rule can. Measured over the whole gazette
     (2026-09-29): 59 instruments screen positive for P6, nearly all data rules.
  4. Instruments with at least one screened sentence are returned, best first (at most
     `_MAX_RETURN`). One name published twice (re-issued after amendment) keeps its newest
     screened copy. The lane declares `adds_docs:` in sources.yaml, so its documents get their
     own slots instead of competing with cac.gov.cn's title-ranked rows for the shared 22.

COST, AND WHY IT IS PAID ONCE. Measured 2026-09-29 on the deploy host: 891 issues, 6,042
instruments, and a cold run spent 522 s in discovery fetching each text once (four at a time). Gazette pages never change after
publication, so each page's screen result is kept in `<cache_dir>/cn_gazette/screen.json`
keyed by `SCREEN_VERSION`, and every later run reads it: a warm run fetches only the index and
the newest issues. A cold run is also bounded by `_SCREEN_BUDGET_S` — it screens NEWEST FIRST
and says in the log how many it left for the next run, rather than holding a live run hostage.
Only the screen COUNTS are cached, never the text: the documents a run keeps are fetched again
by the normal fetch stage, like any other lane's.

NO HARDCODED NAMES. Nothing here names a law. Step 2 is a rule about instrument TYPES; step 3
is a rule about what a localisation / data-protection SENTENCE contains. Both were checked
against the panel's answers and against unrelated instruments (放射性物品运输安全监督管理办法,
森林防火条例, and customs rules whose GOODS 出境 — screen 0 for pillar 6) —
`tests/test_cn_gazette.py`.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from bs4 import BeautifulSoup

from ..config import settings
from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

INDEX_URL = "https://www.gov.cn/gongbao/gbgl.json"
#: Issue pages in the layout this module reads. Pre-2000 issues live under another path and
#: another layout; they are not read (the data-protection instruments the indicators ask about
#: are all later than that).
_ISSUE_URL_RE = re.compile(r"^https://www\.gov\.cn/gongbao/(\d{4})/issue_\d+/$")
_CONTENT_HREF_RE = re.compile(r"content_\d+\.html?$")

#: Bump when `screen`'s rules change: every cached count is then re-screened.
SCREEN_VERSION = 2
#: Wall-clock bound on screening in one call. A cold cache needs ~8 min at `_WORKERS`=4.
_SCREEN_BUDGET_S = 600.0
_WORKERS = 4
#: The newest issues are re-read every run (an index can list an issue before its page is
#: complete); older issue pages are immutable and read from the cache.
_FRESH_ISSUES = 3
#: At most this many instruments per call, best screen first. `discovery._cap` then trims the
#: union of all CN lanes to `discovery_max_docs`.
_MAX_RETURN = 40
_ISSUE_CACHE = "issues_v2.json"

# ── step 2: which gazette items are legislative instruments ──────────────────────────────────

_WS_RE = re.compile(r"[\s　\xa0]+")
#: The decree / announcement header: "…令（第631号）", "…令（2016年第60号）", "…令（〔2021〕第5号）",
#: "…公告（〔2008〕26号）".
_DECREE_RE = re.compile(r"(?:令|公告)[（(][^（）()]{0,20}号[）)]")
_ISSUED_RE = re.compile(r"(?:印发|发布)《([^》]+)》")
#: A cover document that wraps the instrument: "…关于印发X的通知", "…印发《X》的通知",
#: "…关于修改《X》的决定". Whatever the gazette prints AFTER it is the instrument itself.
_COVER_RE = re.compile(r"(?:关于|印发《).*?的(?:通知|决定|公告)")
_NAME_SUFFIX_RE = re.compile(
    r"(?:法|条例|办法|规定|规则|细则|规范|准则)(?:[（(][^（）()]{0,12}[）)])?$")
#: A second instrument name inside one entry: a suffix with more name text after it. A batch
#: amendment decision prints every rule it amends back to back ("海关总署关于修改部分规章的决定
#: 中华人民共和国海关…监管办法中华人民共和国海关…管理规定…"); its page is the decision, not
#: any of those rules. Measured over all 14,892 gazette entries (2026-09-29), a naive version
#: also rejected ~100 single names, so: 规范/规则 are left out (verbs and common nouns in
#: names — 促进和规范数据跨境流动规定, 网络交易平台规则监督管理办法); a suffix followed by a
#: connective is one name (…法实施细则, …准则——基本准则, 规范性文件, 行为准则与廉政规定), and so
#: is one closing a quoted title (违反《铁路安全管理条例》行政处罚实施办法).
_SECOND_NAME_RE = re.compile(
    r"(?:办法|规定|条例|细则|准则)(?:[（(][^（）()]{0,12}[）)])?"
    r"(?![（(]|实施|施行|补充|性|化|的|与|和|及|—|情况|行为|》)(?=.{4,})")


def _several_names(text: str) -> bool:
    return bool(_SECOND_NAME_RE.search(text))
#: Names that end in an instrument type yet are not one to cite.
_NOT_INSTRUMENT_RE = re.compile(r"废止|失效|批复|名录|目录|任免")


def instrument_name(item_text: str) -> str | None:
    """The instrument's own name from one gazette table-of-contents entry, or None when the
    entry is not a legislative instrument.

    The entry is the anchor text with every line break and indentation removed — issue pages
    wrap long issuer lists with <br> mid-word, so line structure cannot be trusted:
      中华人民共和国国务院令（第631号）征信业管理条例                    -> 征信业管理条例
      交通运输部…国家互联网信息办公室令（2016年第60号）网络预约…暂行办法 -> 网络预约…暂行办法
      财政部关于印发《政府非税收入管理办法》的通知政府非税收入管理办法   -> 政府非税收入管理办法
      交通运输部令（2013年第4号）关于修改《快递业务经营许可管理办法》的决定快递业务经营许可管理办法
                                                                   -> 快递业务经营许可管理办法
      中国人民银行令（〔2024〕第1号）中国人民银行关于修改《支付结算办法》的决定 -> None (the
                             decision alone; the revised text is not printed with it)
    """
    text = _WS_RE.sub("", item_text or "")
    if not text:
        return None
    decrees = list(_DECREE_RE.finditer(text))
    rest = text[decrees[-1].end():] if decrees else text
    cover = _COVER_RE.search(rest)
    if cover:
        # A notice/decision wrapping the instrument. The gazette prints the instrument's own
        # name after it when it prints the instrument; a notice naming it in 《》 is the same
        # instrument; a bare decision (amendment/repeal alone) is not one.
        tail = rest[cover.end():]
        issued = _ISSUED_RE.search(cover.group())
        if tail and not issued and _several_names(tail):
            return None                     # a batch decision: the page amends many rules
        if tail and issued and tail.startswith(issued.group(1)):
            # One notice issuing several instruments prints their names back to back
            # ("…《A》《B》的通知AB"); the 《》 gives the first name's boundary.
            name = issued.group(1)
        elif tail:
            name = tail
        elif issued and not cover.group().endswith("的决定"):
            name = issued.group(1)
        else:
            return None
    else:
        issued = _ISSUED_RE.search(rest)
        if issued and rest[issued.end():] in ("", issued.group(1)):
            name = issued.group(1)          # "…印发《X》X" with no 的通知 between
        elif _several_names(rest):
            return None                     # several instruments run together, no boundary
        else:
            name = rest
    name = name.lstrip("…．.·—-")
    # "关于" alone is not a reason to drop: 国务院关于经营者集中申报标准的规定 is a regulation.
    # A decision/notice/opinion is dropped by the suffix test below instead.
    if not name or _NOT_INSTRUMENT_RE.search(name):
        return None
    if not _NAME_SUFFIX_RE.search(name):
        return None
    return name


def parse_index(raw: str) -> list[tuple[int, str]]:
    """(year, issue URL) for every issue in `gbgl.json`, NEWEST FIRST.

    Issue numbers are sorted numerically within a year rather than trusted in file order."""
    data = json.loads(raw.lstrip("﻿"))
    values = data[0]["values"] if isinstance(data, list) else data["values"]
    out: list[tuple[int, int, str]] = []
    for year_label, issues in values.items():
        for issue_label, entry in (issues or {}).items():
            url = (entry or {}).get("gname") or ""
            m = _ISSUE_URL_RE.match(url)
            if not m:
                continue
            num = re.search(r"\d+", issue_label or "")
            out.append((int(m.group(1)), int(num.group()) if num else 0, url))
    out.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [(y, u) for y, _, u in out]


def issue_entries(html: str, issue_url: str) -> list[tuple[str, str]]:
    """(content URL, raw entry text) for every gazette item an issue page lists — the part of
    an issue page that is cached. Names are derived from it at READ time (`parse_issue`), so a
    change to `instrument_name` takes effect on a warm cache instead of waiting for pages that
    never change to be fetched again."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not _CONTENT_HREF_RE.search(href):
            continue
        url = urllib.parse.urljoin(issue_url, href)
        if "/gongbao/" not in url or url in seen:
            continue
        seen.add(url)
        out.append((url, a.get_text("")))
    return out


def _named(entries) -> list[tuple[str, str]]:
    out = []
    for url, text in entries:
        name = instrument_name(text)
        if name:
            out.append((url, name))
    return out


def parse_issue(html: str, issue_url: str) -> list[tuple[str, str]]:
    """(content URL, instrument name) for every legislative instrument an issue page lists."""
    return _named(issue_entries(html, issue_url))


# ── step 3: what the text says ───────────────────────────────────────────────────────────────

_SENTENCE_SPLIT = re.compile(r"[。；;\n]")
# PILLAR 6 — two sentence shapes, both about DATA and the national territory:
#   LOCALISATION  a storage/processing act tied to the territory: 存放地图数据的服务器设在中华人民
#                 共和国境内; 在中国境内采集的信息的整理、保存和加工，应当在中国境内进行;
#                 应当在中国内地存储 (the ride-hailing measures never say 境内).
#   OUTBOUND      data leaving it: 向境外组织或者个人提供信息, 数据出境, 不得外流, 跨境传输.
# "出境" alone is NOT enough, and that was measured: SCREEN_VERSION 1 counted any sentence with
# a territory word, a data word and an act, and 176 instruments passed — customs rules led
# (出境运输工具…向海关传输预配舱单电子数据: the goods and the vehicle leave, not the data) and
# pushed the panel's own sectoral answers out of the run. Here 出境/外流 count only with data as
# their subject. Version 2 passes 59, nearly all of them data rules.
# A localisation sentence weighs TWO, an outbound one ONE: localisation is the core of 6.1–6.3,
# and a single such clause (地图管理条例 art.34) must not rank below two passing mentions.
_P6_DATA = re.compile(r"个人信息|数据|信息|服务器|存储设备|资料")
_P6_LOCAL = re.compile(
    r"(?:存储|储存|存放|保存|处理|设在|设置在|位于)[^。；，,]{0,14}(?:境内|中国内地)"
    r"|(?:境内|中国内地)[^。；，,]{0,10}(?:存储|储存|存放|保存|处理)")
_P6_OUT = re.compile(
    r"(?:向|往|到|至|给)境外[^。；，,]{0,8}(?:提供|传输|传送|转移|发送)"
    r"|(?:提供|传输|传送|转移|发送)(?:给|至|到)?境外"
    r"|(?:数据|信息|资料)[^。；，,]{0,6}(?:出境|外流)"
    r"|跨境(?:传输|提供|流动|转移)")
_P6_OUT_DATA = re.compile(r"个人信息|数据|信息|资料")
# PILLAR 7 — a sentence carrying one of the pillar's duties over data:
#   protection/processing of personal information (7.1, 7.4), cybersecurity (7.2),
#   a retention period (7.3), a state organ obtaining data (7.5).
_P7_RULES: tuple[tuple[re.Pattern, re.Pattern], ...] = (
    (re.compile(r"个人信息"), re.compile(r"保护|处理|泄露|负责人|影响评估|安全")),
    (re.compile(r"网络安全"), re.compile(r"保护|义务|措施|等级|事件")),
    (re.compile(r"数据|信息|记录|日志|档案|资料|凭证"),
     re.compile(r"(?:保存|留存|保管)[^。；]{0,20}(?:不少于|期限|[0-9一二三四五六七八九十]+(?:年|个月))")),
    (re.compile(r"数据|信息|资料"),
     re.compile(r"(?:公安机关|国家安全机关|主管部门|有关部门)[^。；]{0,30}"
                r"(?:调取|查询|查阅|技术支持|协助)")),
)


def screen(text: str) -> dict[str, int]:
    """{"p6": weighted P6 sentences, "p6_local": localisation sentences, "p7": P7 sentences}
    for one instrument's text. See the comments on the patterns above."""
    p6 = local = p7 = 0
    for s in _SENTENCE_SPLIT.split(text or ""):
        if len(s) < 6:
            continue
        if _P6_LOCAL.search(s) and _P6_DATA.search(s):
            p6 += 2
            local += 1
        elif _P6_OUT.search(s) and _P6_OUT_DATA.search(s):
            p6 += 1
        if any(obj.search(s) and duty.search(s) for obj, duty in _P7_RULES):
            p7 += 1
    return {"p6": p6, "p6_local": local, "p7": p7}


def _text_of(html: str) -> str:
    from .ocr import _html_to_text          # the SAME text the extraction stage will read
    return _html_to_text(html)


def score(hits: int) -> float:
    """Relevance on the scale the other CN lane uses (cac.gov.cn rows sit at 0.60–0.99).

    Floor 0.70: one screened sentence is a stronger signal than a cac.gov.cn row whose title
    matched nothing (0.68, its `search` base weight — the 2026 action plans). Ceiling 0.90:
    below the statutes cac.gov.cn finds by name (网络安全法 0.93, 数据出境安全评估办法 0.99),
    which this gazette never prints. Measured 2026-09-29: with a 0.95 ceiling the gazette
    outranked the Cybersecurity Law and the run lost it. Measured 2026-09-29 on pillar 6: 地图管理条例 1, 征信业管理条例 2, 网络借贷… 2,
    网络出版服务管理规定 2, 网络预约出租汽车… 2."""
    if hits <= 0:
        return 0.0
    return round(0.70 + 0.20 * min(1.0, hits / 6.0), 4)


# ── cache ────────────────────────────────────────────────────────────────────────────────────

def _cache_dir():
    d = settings.cache_path / "cn_gazette"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(name: str) -> dict:
    try:
        return json.loads((_cache_dir() / name).read_text(encoding="utf-8"))
    except Exception:                          # noqa: BLE001 -- absent/corrupt cache = cold run
        return {}


def _save(name: str, data: dict) -> None:
    p = _cache_dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ── entry point ──────────────────────────────────────────────────────────────────────────────

def _pillars(indicators: list) -> list[int]:
    ps = sorted({getattr(i, "pillar", None) for i in indicators} & {6, 7})
    return ps or [6, 7]


def search_cn_gazette(client, src: dict, query: str, economy: Economy, indicators: list,
                      log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point (`PortalEnumerator` signature). `query` is unused — the lane
    enumerates the gazette and screens text; see the module docstring."""
    portal_name = src.get("name", "State Council Gazette (国务院公报)")
    budget = float(src.get("screen_budget_s", _SCREEN_BUDGET_S))
    workers = int(src.get("workers", _WORKERS))
    started = time.monotonic()

    resp = portal.portal_get(client, src.get("index_url", INDEX_URL), log)
    if resp is None:
        log("[cn_gazette] issue index unreachable — lane skipped")
        return []
    try:
        issues = parse_index(resp.text)
    except Exception as exc:                  # noqa: BLE001
        log(f"[cn_gazette] issue index unreadable ({type(exc).__name__}) — lane skipped")
        return []
    min_year = int(src.get("min_year", 2000))
    issues = [(y, u) for y, u in issues if y >= min_year]

    # Step 2 — issue pages (cached except the newest few).
    # v2 holds raw entries (v1 held names parsed by the rule of the day, so a better rule never
    # reached a cached issue — measured 2026-09-29: 6,042 names where the new rule gives 6,311).
    issue_cache = _load(_ISSUE_CACHE)
    fresh = {u for _, u in issues[:_FRESH_ISSUES]}
    todo = [u for _, u in issues if u in fresh or u not in issue_cache]
    lock = threading.Lock()

    def _read_issue(u: str):
        r = portal.portal_get(client, u, log, tries=2)
        return u, (issue_entries(r.text, u) if r is not None else None)

    unread = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for u, rows in ex.map(_read_issue, todo):
            if rows is None:
                unread += 1
                continue
            issue_cache[u] = rows
    if todo:
        _save(_ISSUE_CACHE, issue_cache)
    items: list[tuple[int, str, str]] = []           # (year, url, name), newest issue first
    seen_urls: set[str] = set()
    for y, u in issues:
        for url, name in _named(issue_cache.get(u, [])):
            if url not in seen_urls:
                seen_urls.add(url)
                items.append((y, url, name))
    log(f"[cn_gazette] {len(issues)} issues ({len(todo)} read now, {unread} unreadable) -> "
        f"{len(items)} legislative instruments")

    # Step 3 — screen texts not yet screened, newest first, within the budget.
    screened = _load("screen.json")
    todo_urls = [u for _, u, _ in items
                 if (screened.get(u) or {}).get("v") != SCREEN_VERSION]
    done = failed = 0
    out_of_time = False

    def _screen_one(u: str):
        if time.monotonic() - started > budget:
            return u, "timeout"
        r = portal.portal_get(client, u, log, tries=2)
        if r is None:
            return u, None
        rec = screen(_text_of(r.text))
        rec["v"] = SCREEN_VERSION
        return u, rec

    if todo_urls:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for u, rec in ex.map(_screen_one, todo_urls):
                if rec == "timeout":
                    out_of_time = True
                    continue
                if rec is None:
                    failed += 1                    # not cached: tried again next run
                    continue
                with lock:
                    screened[u] = rec
                    done += 1
                    if done % 250 == 0:
                        _save("screen.json", screened)
        _save("screen.json", screened)
    left = len(todo_urls) - done - failed
    log(f"[cn_gazette] screened {done} new instrument text(s), {failed} unreachable"
        + (f", {left} left for the next run (time budget {budget:.0f}s)" if out_of_time else ""))

    # Step 4 — rank. Newest screened copy per name; a copy that screens 0 does not shadow an
    # older one that screens higher (an amendment page can print only the changed articles).
    pillars = _pillars(indicators)
    best: dict[str, tuple[int, int, int, str]] = {}     # name -> (hits, local, year, url)
    for y, u, name in items:
        rec = screened.get(u)
        if not rec or rec.get("v") != SCREEN_VERSION:
            continue
        hits = sum(int(rec.get(f"p{p}", 0)) for p in pillars)
        if hits <= 0:
            continue
        if name not in best:                              # items are newest first
            best[name] = (hits, int(rec.get("p6_local", 0)) if 6 in pillars else 0, y, u)
    # Ties break toward a localisation clause, then toward the newer instrument.
    ranked = sorted(best.items(), key=lambda kv: kv[1][:3], reverse=True)
    docs = [portal.make_doc(economy, u, name, portal_name, law_name=name, score=score(hits))
            for name, (hits, _local, _y, u) in ranked[:_MAX_RETURN]]
    log(f"[cn_gazette] {len(best)} instrument(s) screen positive for pillar(s) "
        f"{'/'.join(map(str, pillars))}; returning {len(docs)}")
    return docs


# enumerates_portal=True: the lane reads the whole gazette index and ignores `query`, so
# discovery must call it once per source, not once per query term.
portal.register("cn_gazette", search_cn_gazette, enumerates_portal=True)
