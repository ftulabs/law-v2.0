# Crawling politely — robots.txt, rate limits, and what each portal actually says

On 15 October five tools read the same government sites within the same hour. A ministry
running this tool afterwards should not have to configure politeness to avoid being blocked.
So it is on by default and there is no flag a hurried operator can forget.

Summary table (rate limit, parallelism, file:line) lives in the
[README](../README.md#crawling-politely). This document is the part that did not fit: what the
portals actually say, and why the parser has to be exact rather than approximate.

---

## What changed, and why it was not cosmetic

Before 2026-08-21 nothing in this repository checked a `Disallow`. One module read robots.txt —
`corpus/regulator.py` — and read it to *harvest* the `Sitemap:` directive. Every fetch
succeeded, no test failed, and nothing anywhere was wrong in a way a run would surface.

It stopped being theoretical the moment the nine live-test portals were probed. Three of them
carry rules that bite precisely where the discovery lane wants to go.

| Portal | The rule | Why it matters |
| :--- | :--- | :--- |
| `publication.pravo.gov.ru` | `Disallow: /File`, `Disallow: /Search` | `/File` is where the document bodies live. The obvious route is the forbidden one |
| `adilet.zan.kz` | `Disallow: /*/search/`, `/*/list/docs/`, `/*/archive/`, `/*/origins/` | The listing paths are closed. This is a constraint on the **discovery adapter**, not just on fetch |
| `peraturan.bpk.go.id` | `Disallow: /` for nine **named** agents; wildcard group is `Allow: /` | Read crudely, we either lose an economy or break a promise — see below |

Russia's file also publishes `Sitemap: http://publication.pravo.gov.ru/sitemap.xml`. That is
both permitted and a better discovery surface than search, so the RU lane should be built on it.
The robots file is telling us the right way in, not only the wrong ones.

---

## The Indonesian case, in full

`peraturan.bpk.go.id/robots.txt`, read 2026-08-21:

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /

User-agent: Amazonbot
Disallow: /
User-agent: Applebot-Extended
Disallow: /
User-agent: Bytespider
Disallow: /
User-agent: CCBot
Disallow: /
User-agent: ClaudeBot
Disallow: /
User-agent: CloudflareBrowserRenderingCrawler
Disallow: /
User-agent: Google-Extended
Disallow: /
User-agent: GPTBot
Disallow: /
User-agent: meta-externalagent
Disallow: /
```

We had this host recorded as simply disallowed. **That was too broad.** The block names
Anthropic's general-purpose *web crawler*, which is not this pipeline. VeriTrade fetches as
`VeriTrade-Research/0.2` (`config.crawl_user_agent`) and therefore falls in the wildcard group,
whose signals it satisfies exactly: it *references* provisions and cites them with their source
URL (`use=reference`), and it trains no model on them (`ai-train=no`).

So the host is permitted to us and forbidden to a general AI crawler, and the entire difference
is which user-agent group the parser selects. Two rules follow, and neither is optional:

1. **Never fetch this host with an agent identifying as one of the named crawlers.** That
   includes browser-rendering services that announce themselves as
   `CloudflareBrowserRenderingCrawler`.
2. **Never use its text for training.**

The general lesson: a robots parser that greps for the word `Disallow` gets this wrong in one
direction (losing Indonesia, one of the nine) and a parser that only reads the `*` group gets it
wrong in the other (fetching as a blocked agent). Correct group selection is the whole thing.

---

## Rules implemented

`backend/pipeline/robots.py`, per RFC 9309.

**Group selection.** The **most specific** matching user-agent group wins; `*` is used only when
no named group matches. Matching is by longest product token, case-insensitive, against our
user-agent string. Consecutive `User-agent:` lines share one group of rules.

**Path matching.** Within the chosen group the **longest** matching rule wins, and on an
equal-length tie **Allow beats Disallow** — so `Allow: /docs/` genuinely carves an exception out
of `Disallow: /`. `*` and `$` wildcards are honoured; `$` anchors the end, so `Disallow: /*.pdf$`
blocks `/act.pdf` but not `/act.pdf?download=1`.

**Empty and absent.** An empty `Disallow:` grants everything — treating the empty string as a
path prefix would match every URL and silently block the whole host. An empty file grants. A
4xx means the file is absent, which is permission.

**Failure denies.** A 5xx or a network failure returns *unknown*, and unknown is treated as
disallowed. "The server could not tell us the rules" is not permission.

**Crawl-delay.** Read and honoured whenever it is **larger** than our own setting. Our
`crawl_delay_seconds` is a floor on politeness, not a ceiling; a host asking for more space gets
it.

**Checked before the cache, not only before the network.** A rule published after we already
downloaded a body still governs whether we may use that body. This is why the check sits at the
top of `fetch_to_cache`, above the TTL branch.

**Skips are logged.** `[fetch] SKIPPED by robots.txt: <url> (<reason>)`. A document missing from
a submission needs an explanation a judge can check, and silence is not one.

**Rules are cached per host for one hour**, so enforcement costs one extra request per portal
per run rather than one per document.

**Turning it off is possible and says so.** `CRAWL_RESPECT_ROBOTS=false` reports
`robots checking disabled` in the reason string, so a run that ignored robots cannot look like a
run that complied.

---

## TLS verification allowlist

Separate mechanism, same spirit — a narrow, named exception rather than a global switch.
`fetch._TLS_RELAXED_HOSTS` currently holds two hosts:

| Host | Why | Cost of not relaxing |
| :--- | :--- | :--- |
| `wb.flk.npc.gov.cn` | expired certificate; every Chinese statute PDF and DOCX lives there | the entire economy returns "No provision found" |
| `krisdika.go.th` | self-signed certificate; Thailand's own law library | Thailand has no primary portal at all |

It is defensible only because all four of these hold, and it must not be widened without them:

1. the documents are public statutes — nothing confidential is requested;
2. no credential, cookie or token is ever sent to these hosts;
3. fetched bytes are content-hashed (SHA-256) and stored, so a substituted body is detectable
   after the fact rather than trusted blindly;
4. the alternative is not "more secure", it is "this country cannot be processed".

Every use is logged, and it is an explicit host allowlist — never a global `verify=False`.

---

## Testing

`tests/test_robots.py` pins the behaviour against the **real** files these portals serve, quoted
and trimmed rather than fetched, so the suite stays offline and a portal changing its rules
shows up as a deliberate edit rather than as a test that silently starts passing for a new
reason.

Sixteen cases, each one a mistake that costs something real: an economy dropped because we were
too cautious, or a written promise broken because we were not cautious enough.
