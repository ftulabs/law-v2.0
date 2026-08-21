"""robots.txt, enforced — not merely read for its Sitemap line.

Until now the only code that touched robots.txt was `corpus/regulator.py`, and it read the
file to HARVEST the `Sitemap:` directive. Nothing anywhere checked a `Disallow`. That is a
compliance gap rather than a bug in the ordinary sense: every fetch succeeded, no test failed,
and the README section the final round requires — "robots.txt respected | yes | file:line" —
could not have been filled in honestly.

It also stopped being theoretical the moment the live-test nine were probed. Three of those
portals carry rules that bite exactly where we want to go:

  publication.pravo.gov.ru   Disallow: /File   ← where the document bodies live
  adilet.zan.kz              Disallow: /*/search/, /*/list/docs/, /*/archive/
  peraturan.bpk.go.id        Disallow: / for nine NAMED agents (ClaudeBot, GPTBot, CCBot …)
                             while the wildcard group is Allow: / with
                             Content-Signal: search=yes, ai-train=no, use=reference

The last one is why matching has to be done properly rather than by searching the file for the
word "Disallow". VeriTrade sends `VeriTrade-Research/0.2` and falls in the wildcard group, so
it is permitted where a general-purpose AI crawler is not — and the difference is entirely in
which group the parser selects. Getting that wrong in the cautious direction loses an economy;
getting it wrong in the other direction breaks a promise we make in writing.

Rules implemented, per RFC 9309:
  * the MOST SPECIFIC matching user-agent group wins, and `*` is used only if no named group
    matches. Group selection is by longest matching product token, case-insensitive.
  * within the chosen group, the LONGEST matching path rule wins, and Allow beats Disallow on
    an equal-length tie — so `Allow: /docs/` genuinely carves an exception out of
    `Disallow: /`.
  * `*` and `$` wildcards in paths are honoured.
  * an empty `Disallow:` grants, an empty file grants, and a 4xx grants. A 5xx or a network
    failure DENIES, because "the server could not tell us the rules" is not permission.
  * `Crawl-delay` is read and reported, so a host asking for more space than our default gets
    it instead of being overridden by our own setting.

One deliberate non-goal: this never fetches on the caller's behalf and never raises. It
answers a question. The fetcher decides what to do with the answer, and logs it.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from ..config import settings

_CACHE: dict[str, "Robots"] = {}          # host → parsed rules
_TTL_SECONDS = 3600.0


@dataclass
class Rule:
    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        return bool(_compile(self.pattern).match(path))

    @property
    def weight(self) -> int:
        """Longest-match wins; a trailing $ counts as the character it anchors."""
        return len(self.pattern)


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass
class Robots:
    groups: list[Group] = field(default_factory=list)
    fetched_at: float = 0.0
    #: True when we could not read the file for a reason that is not "it is absent".
    unknown: bool = False
    source: str = ""

    def _group_for(self, user_agent: str) -> Group | None:
        """The most specific group whose product token appears in our user agent."""
        ua = user_agent.lower()
        best: tuple[int, Group] | None = None
        star: Group | None = None
        for g in self.groups:
            for a in g.agents:
                if a == "*":
                    star = star or g
                elif a and a in ua and (best is None or len(a) > best[0]):
                    best = (len(a), g)
        return best[1] if best else star

    def allowed(self, url: str, user_agent: str | None = None) -> bool:
        if self.unknown:
            return False                       # no rules readable → not permission
        ua = user_agent or settings.crawl_user_agent
        group = self._group_for(ua)
        if group is None:
            return True                        # a file that names no applicable group grants
        path = _path_of(url)
        winner: Rule | None = None
        for r in group.rules:
            if not r.pattern:                  # "Disallow:" with an empty value grants all
                continue
            if r.matches(path) and (
                    winner is None
                    or r.weight > winner.weight
                    # equal length: Allow wins, so an exception can be carved out of Disallow: /
                    or (r.weight == winner.weight and r.allow and not winner.allow)):
                winner = r
        return winner.allow if winner else True

    def delay_for(self, user_agent: str | None = None) -> float | None:
        group = self._group_for(user_agent or settings.crawl_user_agent)
        return group.crawl_delay if group else None


def _path_of(url: str) -> str:
    p = urlparse(url)
    path = unquote(p.path) or "/"
    return f"{path}?{p.query}" if p.query else path


_RE_CACHE: dict[str, re.Pattern] = {}


def _compile(pattern: str) -> re.Pattern:
    """robots path pattern → regex. Only * and $ are special; everything else is literal."""
    if pattern in _RE_CACHE:
        return _RE_CACHE[pattern]
    anchored_end = pattern.endswith("$")
    body = pattern[:-1] if anchored_end else pattern
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    _RE_CACHE[pattern] = re.compile(rx + ("$" if anchored_end else ""))
    return _RE_CACHE[pattern]


def parse(text: str) -> Robots:
    """Parse a robots.txt body. Tolerant by design: an unreadable line is skipped, never fatal."""
    robots, group, expecting_agent = Robots(), None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name, value = field_name.strip().lower(), value.strip()
        if field_name == "user-agent":
            # Consecutive User-agent lines share one group of rules.
            if group is None or not expecting_agent:
                group = Group()
                robots.groups.append(group)
            group.agents.append(value.lower())
            expecting_agent = True
            continue
        if group is None:                       # a rule before any User-agent line: ignore
            continue
        expecting_agent = False
        if field_name in ("allow", "disallow"):
            group.rules.append(Rule(allow=(field_name == "allow"), pattern=value))
        elif field_name == "crawl-delay":
            try:
                group.crawl_delay = float(value)
            except ValueError:
                pass
    return robots


def _fetch(base: str) -> Robots:
    url = base.rstrip("/") + "/robots.txt"
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=15,
                          headers={"User-Agent": settings.crawl_user_agent}) as c:
            r = c.get(url)
    except Exception:
        # Could not ask. Treat as unknown rather than as permission — but see `for_url`, which
        # degrades to ALLOW when robots enforcement is switched off entirely.
        return Robots(unknown=True, fetched_at=time.monotonic(), source=url)
    if r.status_code >= 500:
        return Robots(unknown=True, fetched_at=time.monotonic(), source=url)
    if r.status_code >= 400:
        return Robots(fetched_at=time.monotonic(), source=url)      # absent → everything allowed
    out = parse(r.text)
    out.fetched_at, out.source = time.monotonic(), url
    return out


def for_url(url: str) -> Robots:
    """Cached rules for the URL's host. One fetch per host per hour."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    cached = _CACHE.get(base)
    if cached and (time.monotonic() - cached.fetched_at) < _TTL_SECONDS:
        return cached
    _CACHE[base] = _fetch(base)
    return _CACHE[base]


def allowed(url: str, user_agent: str | None = None) -> tuple[bool, str]:
    """(may we fetch it, why). The reason string is written into the run log verbatim, because
    a document missing from a submission needs an explanation a judge can check."""
    if not settings.crawl_respect_robots:
        return True, "robots checking disabled (CRAWL_RESPECT_ROBOTS=false)"
    rules = for_url(url)
    if rules.unknown:
        return False, f"robots.txt unreadable at {rules.source} — treating as disallowed"
    if rules.allowed(url, user_agent):
        return True, ""
    return False, (f"disallowed by {rules.source} for user-agent "
                   f"{(user_agent or settings.crawl_user_agent).split()[-1]}")


def clear_cache() -> None:
    _CACHE.clear()
