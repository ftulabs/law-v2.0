"""robots.txt enforcement, against the real files the live-test portals serve.

The bodies quoted here were fetched on 2026-08-21 and trimmed; they are pinned rather than
downloaded so the suite stays offline and so a portal changing its rules shows up as a
deliberate edit here, not as a test that silently starts passing for a new reason.

Every case is one we would otherwise get wrong in a way that costs something real: a whole
economy dropped because we were too cautious, or a written promise broken because we were not
cautious enough.
"""
import pytest

from backend.config import settings
from backend.pipeline import robots

VERITRADE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 VeriTrade-Research/0.2")

# peraturan.bpk.go.id — named-agent blocks, wildcard allow.
INDONESIA = """
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /

User-agent: Amazonbot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: GPTBot
Disallow: /
"""

# publication.pravo.gov.ru — /File is where the documents live.
RUSSIA = """
User-agent: *
Disallow: /Error
Disallow: /Search
Disallow: /File
Sitemap: http://publication.pravo.gov.ru/sitemap.xml
"""

# adilet.zan.kz — listing and search paths closed, documents open.
KAZAKHSTAN = """
User-Agent: *
Disallow: /files/
Disallow: /rus/archive/
Disallow: /rus/search/
Disallow: /rus/list/docs/
Disallow: /kaz/search/
"""


# ── the case that would have cost us an economy ───────────────────────────────────────
def test_indonesia_permits_veritrade_and_blocks_claudebot():
    """The block names Anthropic's WEB CRAWLER, not this pipeline. Reading the file as
    "disallowed" — which is what we had recorded — throws away one of the nine for a rule that
    was never addressed to us. Reading it as "allowed for everyone" would break a promise."""
    r = robots.parse(INDONESIA)
    url = "https://peraturan.bpk.go.id/Details/123/uu-no-27-tahun-2022"
    assert r.allowed(url, VERITRADE_UA) is True
    assert r.allowed(url, "ClaudeBot/1.0") is False
    assert r.allowed(url, "GPTBot") is False


def test_the_most_specific_agent_group_wins_not_the_first_one():
    """`*` grants and `ClaudeBot` denies. A parser that takes the first matching group, or that
    ORs the groups together, gets one of the two answers wrong."""
    r = robots.parse(INDONESIA)
    assert r.allowed("https://x.test/a", "ClaudeBot") is False       # named beats wildcard
    assert r.allowed("https://x.test/a", "SomeOtherBot") is True     # falls back to wildcard


# ── the cases that would have broken a written promise ────────────────────────────────
def test_russia_blocks_the_path_the_documents_live_on():
    r = robots.parse(RUSSIA)
    assert r.allowed("http://publication.pravo.gov.ru/File/GetFile/00012026", VERITRADE_UA) is False
    assert r.allowed("http://publication.pravo.gov.ru/Search?q=x", VERITRADE_UA) is False
    assert r.allowed("http://publication.pravo.gov.ru/document/00012026", VERITRADE_UA) is True


def test_kazakhstan_closes_listings_but_leaves_documents_open():
    """So enumeration must not walk the listing paths — which is a design constraint on the
    discovery adapter, not merely a fetch-time rejection."""
    r = robots.parse(KAZAKHSTAN)
    assert r.allowed("https://adilet.zan.kz/rus/search/docs?q=data", VERITRADE_UA) is False
    assert r.allowed("https://adilet.zan.kz/rus/list/docs/all", VERITRADE_UA) is False
    assert r.allowed("https://adilet.zan.kz/rus/docs/Z2200000094", VERITRADE_UA) is True


# ── the matching rules themselves ─────────────────────────────────────────────────────
def test_longest_matching_path_wins():
    r = robots.parse("User-agent: *\nDisallow: /\nAllow: /docs/\n")
    assert r.allowed("https://x.test/docs/act.pdf") is True
    assert r.allowed("https://x.test/admin") is False


def test_allow_beats_disallow_on_an_equal_length_tie():
    r = robots.parse("User-agent: *\nDisallow: /a\nAllow: /a\n")
    assert r.allowed("https://x.test/a") is True


def test_wildcards_and_end_anchors_are_honoured():
    r = robots.parse("User-agent: *\nDisallow: /*.pdf$\n")
    assert r.allowed("https://x.test/law/act.pdf") is False
    assert r.allowed("https://x.test/law/act.pdf?download=1") is True   # $ anchors the end
    assert r.allowed("https://x.test/law/act.html") is True


def test_an_empty_disallow_grants_rather_than_denies_everything():
    """`Disallow:` with no value means "nothing is disallowed". Treating the empty string as a
    prefix would match every path and silently block the entire host."""
    r = robots.parse("User-agent: *\nDisallow:\n")
    assert r.allowed("https://x.test/anything") is True


def test_consecutive_user_agent_lines_share_one_group():
    r = robots.parse("User-agent: A\nUser-agent: B\nDisallow: /x\n")
    assert r.allowed("https://t.test/x", "A") is False
    assert r.allowed("https://t.test/x", "B") is False
    assert r.allowed("https://t.test/x", "C") is True


def test_rules_before_any_user_agent_line_are_ignored():
    r = robots.parse("Disallow: /\nUser-agent: *\nAllow: /\n")
    assert r.allowed("https://t.test/a") is True


def test_an_empty_file_allows_everything():
    assert robots.parse("").allowed("https://t.test/a") is True


# ── failure modes ─────────────────────────────────────────────────────────────────────
def test_an_unreadable_robots_file_denies_rather_than_grants():
    """"The server could not tell us the rules" is not permission. A 4xx means the file is
    absent, which IS permission; a 5xx or a network failure is not."""
    r = robots.Robots(unknown=True)
    assert r.allowed("https://t.test/a") is False


def test_crawl_delay_is_read_so_a_host_can_ask_for_more_space():
    r = robots.parse("User-agent: *\nCrawl-delay: 10\nDisallow: /x\n")
    assert r.delay_for(VERITRADE_UA) == 10.0


def test_our_delay_is_a_floor_and_the_hosts_larger_ask_wins(monkeypatch):
    from backend.pipeline import fetch
    monkeypatch.setattr(settings, "crawl_delay_seconds", 2.0)
    monkeypatch.setattr(settings, "crawl_respect_robots", True)
    parsed = robots.parse("User-agent: *\nCrawl-delay: 7\n")
    monkeypatch.setattr(robots, "for_url", lambda url: parsed)
    slept = []
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(fetch, "_last_request", {"h": fetch.time.monotonic()})
    fetch._polite_wait("h", "https://h/x")
    assert slept and slept[0] > 6.0          # the host's 7s, not our 2s


# ── the fetcher actually asks ─────────────────────────────────────────────────────────
def test_fetch_refuses_a_disallowed_url_before_touching_the_network(monkeypatch):
    """Pinned because a politeness claim that lives only in a module nothing calls is worse
    than no claim: the README states it as fact and a reviewer can check the code."""
    from backend.pipeline import fetch
    monkeypatch.setattr(settings, "crawl_respect_robots", True)
    monkeypatch.setattr(robots, "for_url", lambda url: robots.parse("User-agent: *\nDisallow: /\n"))
    called = []
    monkeypatch.setattr(fetch, "_httpx_fetch", lambda *a, **k: called.append(1))
    monkeypatch.setattr(fetch, "_scrapling_fetch", lambda *a, **k: called.append(1))
    logged: list[str] = []
    assert fetch.fetch_to_cache("https://blocked.test/act.pdf", log=logged.append) is None
    assert not called
    assert any("robots" in m.lower() for m in logged)


def test_disabling_the_check_is_possible_and_says_so(monkeypatch):
    monkeypatch.setattr(settings, "crawl_respect_robots", False)
    ok, why = robots.allowed("https://anything.test/x")
    assert ok and "disabled" in why


# ── unreachable robots.txt, and the one narrow way past it ───────────────────────────
def test_a_persistently_unreachable_host_can_be_overridden_only_by_a_written_decision(monkeypatch):
    """The strict rule cost us an entire economy, correctly and unhelpfully.

    indiacode.gov.in serves its DSpace API but its web front end returns 502 for everything,
    robots.txt included — so "5xx means disallow" skipped every Indian document. RFC 9309
    §2.3.1.4 provides for proceeding when unavailability persists, and this is that provision
    made explicit: an entry with a date and the evidence behind it, logged on every use.
    """
    monkeypatch.setattr(settings, "crawl_respect_robots", True)
    monkeypatch.setattr(robots, "for_url",
                        lambda url: robots.Robots(unknown=True, source=url + "/robots.txt"))
    ok, why = robots.allowed("https://indiacode.gov.in/handle/123456789/512146")
    assert ok
    assert "RFC 9309" in why and "2026-08-22" in why


def test_the_override_does_not_apply_to_any_other_host(monkeypatch):
    monkeypatch.setattr(settings, "crawl_respect_robots", True)
    monkeypatch.setattr(robots, "for_url",
                        lambda url: robots.Robots(unknown=True, source=url + "/robots.txt"))
    ok, why = robots.allowed("https://some-other-portal.example/doc")
    assert not ok and "disallowed" in why


def test_the_override_cannot_rescue_a_host_that_actually_says_no(monkeypatch):
    """It rescues UNKNOWN, never DENIED. A site that answers with Disallow is obeyed even if it
    happens to be on the list — otherwise the table would quietly become a bypass."""
    monkeypatch.setattr(settings, "crawl_respect_robots", True)
    monkeypatch.setattr(robots, "for_url",
                        lambda url: robots.parse("User-agent: *\nDisallow: /\n"))
    ok, _ = robots.allowed("https://indiacode.gov.in/handle/1")
    assert not ok


def test_every_override_entry_carries_its_justification():
    """An exception nobody has to justify stops being a decision."""
    for host, entry in robots.UNREACHABLE_OVERRIDE.items():
        assert entry.get("since") and entry.get("reason") and entry.get("evidence"), host
        assert len(entry["evidence"]) > 60, f"{host}: evidence is too thin to review"
