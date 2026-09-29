"""The other ten pillars — RDTII 2.1 indicators outside 6 and 7.

The final-round brief says the sealed test may name "a pillar you have not worked on". Until
now that was a guaranteed blank: `indicators.py` coded nine indicators, and the remaining
fifty-two existed only as titles and scoring criteria in `data/rdtii/indicator_reference.json`
— enough to *score* an answer, nothing to *find* one with. Retrieval needs `query_terms` and
the grader needs a `legal_test`; without them a run over pillar 9 returns "No provision found"
for every indicator and looks exactly like an economy with no content-access law.

Two decisions worth stating, because both could reasonably have gone the other way.

**The nine stay separate and frozen.** `INDICATORS` still holds only pillars 6 and 7. Those
definitions were tuned against the panel's own Round-1 answer key and the retrieval parameters
were swept against them (`docs/retrieval-redesign.md`); folding fifty-two more into the same
list would change `get_indicators(None)`, which `backend/eval/*` uses to build the evaluation
corpus, and silently re-baseline every measurement we have. So this module is a second
registry and `get_indicators(pillar)` reads from it only for pillars outside 6 and 7. The
honest summary is: **the nine are measured, the fifty-two are declared.**

**The ID is the numeric code.** Elsewhere the internal form is `P6-I4`. It cannot express
this set: `4.01` and `4.1` are different indicators that both collapse to `P4-I1`, and
`12.4.1` has three components. `rdtii/codes.py` already passes a numeric code through
unchanged, so using it here costs nothing at the export boundary and removes a whole class of
collision.

**Polarity.** Eleven of these score highest when a framework is ABSENT — nine by title ("Lack of
a copyright framework", "Lack of an independent telecom authority") and 4.2/4.6, whose scoring
gives 0 when civil/administrative remedies AND provisional measures both exist. For those the
evidence to find is the framework
ITSELF, and finding it means the economy scores 0 (unrestricted). That is the same inversion
`rdtii/scoring_rubric.py` already documents for 7.1 and 7.2, so `INVERTED` below names them
and each `legal_test` says so in words — a grader reading only the test must not conclude that
finding a good law is a null result.

**Not every in-scope indicator lives in statute text.** The non-regulatory indicators (1.1-1.3,
2.4, 4.4, 4.7, 4.8, 5.6, 6.5, 9.2, 12.10-12.13) come from WITS, V-Dem and treaty-status pages
and are deliberately absent here. Three that ARE here are scored on enforcement or practice —
3.4 (a screening mechanism actually used to block), 5.3 (the state's shareholding, found in
market reports and SOE lists) and 9.1 (instances of blocking/filtering) — so a statute gives
only part of the answer, and their legal_test says so rather than letting a grader treat a
missing provision as a clean result.

These are our reading of the Methodology's scoring criteria and the RDTII 2.1 guide (page
numbers cited are the guide's PRINTED page numbers), not the panel's own wording, and they
have not been validated against an answer key. `docs/round2-expansion.md` records that
distinction; the frontend reports it per pillar rather than presenting all twelve as equal.
"""
from __future__ import annotations

from ..schemas import Indicator

#: Indicators whose score rises when the framework is ABSENT. Finding the law is a real result
#: — it is the evidence that the economy scores 0 — and must not be discarded as a non-answer.
INVERTED = frozenset({"4.1", "4.2", "4.5", "4.6", "5.1", "5.4", "5.7",
                      "8.1", "8.2", "11.1", "12.9"})

#: Official pillar names, from the Methodology sheet of the panel's own Database.
PILLAR_NAMES = {
    1: "Tariffs and Trade Defence",
    2: "Public Procurement",
    3: "Foreign Direct Investment",
    4: "Intellectual Property Rights",
    5: "Telecom Regulations & Competition",
    6: "Cross-border Data Policies",
    7: "Domestic Data Protection & Privacy",
    8: "Internet Intermediary Liability",
    9: "Content Access",
    10: "Non-technical NTMs",
    11: "Standards and Procedures",
    12: "Online Sales and Transactions",
}

_INVERTED_NOTE = (" POLARITY: this indicator is framed as an ABSENCE. The evidence to find is "
                  "the framework itself; finding it is what shows the economy is unrestricted. "
                  "Cite the provision that establishes (or conspicuously fails to establish) it.")

# (code, pillar, title, description, legal_test, query_terms)
_SPEC: list[tuple[str, int, str, str, str, list[str]]] = [
    # ───────────────────────── Pillar 1 — Tariffs and Trade Defence ─────────────────────────
    ("1.4", 1, "Trade defence measures on ICT goods",
     "Does the economy impose anti-dumping, countervailing or safeguard duties on ICT goods?",
     "The operative rule IMPOSES an anti-dumping duty, a countervailing duty or a safeguard "
     "measure, currently in force, on an ICT good (ITA I/II and the proposed ITA III list: "
     "semiconductors, network equipment, handsets, cables, printed circuit boards, "
     "loudspeakers) or an ICT-RELATED good — a component or input of ICT manufacturing such as "
     "connection terminals, aluminium alloy strip, power transformers, stainless-steel tubes, "
     "glass-fibre material — imported from an economy in the region. Raw materials (rare "
     "earths, lithium, cobalt, silicon) are NOT covered. Only ACTIVE measures count: an "
     "investigation not yet concluded, or a terminated duty, scores nothing. The instrument is "
     "usually a ministerial determination, gazette notice or WTO notification (G/ADP/N/1) "
     "naming the product and the rate, not a statute; the enabling trade-remedies ACT alone "
     "is not a measure. Each measure scores 0.25, up to 1 (RDTII 2.1 guide p.16-17).",
     ["anti-dumping duty", "countervailing duty", "safeguard measure", "provisional duty",
      "dumping margin", "injury to the domestic industry", "trade remedies investigation",
      "definitive duty is imposed on imports of"]),

    # ───────────────────────── Pillar 2 — Public Procurement ────────────────────────────────
    ("2.1", 2, "Foreign exclusions from public procurement of ICT",
     "Does the law exclude foreign firms from public procurement of ICT goods or digital services?",
     "The operative rule EXCLUDES foreign suppliers from public procurement of ICT goods or "
     "online services: foreign firms may not bid at all; a named economy, group or company is "
     "banned from tenders (e.g. a ban on procuring foreign messenger services); government "
     "entities must buy hardware or software only from local suppliers; foreign firms may bid "
     "only when no domestic supplier is available; or foreign firms may bid only in "
     "partnership with a domestic one. Score 1 for a general exclusion or two or more "
     "specific ones, 0.5 for one specific (group of) firm(s). A bare legal BASIS that merely "
     "empowers the government to exclude scores 0 — cite it only as the reference rule. "
     "Distinguish from 2.3 (limitations WITHIN bidding for a foreign bidder who is allowed to "
     "bid) and 3.5 (commercial presence to supply the market generally, not to bid). A ban "
     "that applies only to government users may be this indicator or an import ban (10.1) — "
     "decide by whether it operates through procurement (RDTII 2.1 guide p.19; coder FAQ "
     "p.11).",
     ["shall be reserved for", "only local suppliers", "registered domestic supplier",
      "eligible bidders shall be", "foreign supplier shall not",
      "only when no domestic supplier", "in partnership with a domestic",
      "government procurement", "restricted tender"]),

    ("2.2", 2, "Source code, encryption and trade-secret requirements in procurement",
     "Must a supplier surrender source code or trade secrets, or use a specific encryption, to win a public contract?",
     "PUBLIC PROCUREMENT ONLY. Two limbs. (a) Score 1: as a condition of participating in or "
     "winning a tender, a supplier must SURRENDER source code, encryption keys or other trade "
     "secrets, or transfer ownership of / exclusive rights to IP such as patented technology — "
     "e.g. providers of custom software for public electronic systems must submit source code "
     "and documentation, or software must be lodged with source code in a government "
     "procurement register. (b) Score 0.5: bidders must use a SPECIFIC encryption standard to "
     "win the tender. The same demand made OUTSIDE procurement belongs to 4.9 (disclosure) or "
     "11.4 (encryption standards), not here (RDTII 2.1 guide p.19-20).",
     ["source code shall be", "deposit the source code", "escrow", "provide the encryption key",
      "technical documentation shall be submitted", "public electronic system",
      "transfer of intellectual property rights", "as a condition of procurement",
      "encryption shall be used", "government procurement"]),

    ("2.3", 2, "Limitations in procurement bidding",
     "Does the law limit participation in public procurement through quotas, preferences or local-content conditions?",
     "The operative rule LIMITS participation in public procurement without excluding foreign "
     "bidders outright: (a) a quota or set-aside, (b) a preference for certain suppliers, or "
     "(c) a price preference / margin of preference — triggered by the supplier's nationality, "
     "by another status (SME, women-owned, indigenous), or by a percentage of local content in "
     "the supplies. Score 1 for a measure that directly discriminates against FOREIGN bidders "
     "(or two or more of the 0.5 kind, or procurement rules that are not publicly available); "
     "0.5 for a limitation applied to all bidders alike, such as a local-content or "
     "performance-based condition or an SME set-aside; 0 where there is only a legal basis to "
     "impose limitations. A target price is ordinary procurement practice unless it differs "
     "for domestic and foreign bidders. Distinguish from 2.1 (outright exclusion) and 10.3 "
     "(local content in the COMMERCIAL market, not a tender condition) (RDTII 2.1 guide p.20; "
     "coder FAQ p.11).",
     ["price preference", "margin of preference", "domestic content", "local content",
      "reserved for micro and small enterprises", "procurement quota",
      "locally produced goods", "preference shall be given to"]),

    # ───────────────────────── Pillar 3 — Foreign Direct Investment ─────────────────────────
    ("3.1", 3, "Foreign equity limits in digital-trade sectors",
     "Does the law cap foreign shareholding in a sector relevant to digital trade?",
     "The operative rule CAPS foreign ownership at a stated percentage (or bans it outright), "
     "in private companies or SOEs, either horizontally or in a sector relevant to digital "
     "trade — computer and data-processing services, internet services, manufacture of "
     "telecom equipment, online media, broadcasting, payments. The cap is a number: '49 per "
     "cent', 'majority shall be held by nationals'. Score 1 for a ban in any sector or a "
     "minority-only cap in more than one sector; 0.8 minority-only in one sector; 0.5 a "
     "controlling stake allowed but capped, or caps only in SOEs. EXCLUDED: a cap written "
     "specifically for telecommunications (5.2) or e-commerce (12.01). A HORIZONTAL cap (a "
     "negative list, a foreign business act) is recorded here only, even where it also covers "
     "telecom; broadcasting caps belong here, not in pillar 5 (RDTII 2.1 guide p.25; coder "
     "FAQ p.11).",
     ["foreign equity shall not exceed", "per cent of the paid-up capital",
      "majority shareholding shall be held by", "foreign investment is prohibited in",
      "negative list", "at least 51%", "aggregate foreign shareholding"]),

    ("3.2", 3, "Joint venture requirements",
     "Must a foreign investor operate through a joint venture with a local partner?",
     "The operative rule requires a foreign investor to form a JOINT VENTURE, partnership or "
     "cooperative arrangement with a domestic entity as a condition of investing or operating. "
     "Distinguish from 3.1: a JV mandate is a structural requirement even where no percentage "
     "cap is stated, though the two frequently appear in one provision.",
     ["joint venture", "in partnership with a local", "equity joint venture",
      "shall establish a joint venture", "cooperation with a domestic enterprise",
      "local partner is required"]),

    ("3.3", 3, "Nationality or residency requirements for directors or managers",
     "Must at least one director or manager be a national or resident?",
     "The operative rule requires at least one member of the BOARD OF DIRECTORS or at least "
     "one MANAGER to be a national of, or resident/domiciled in, the economy — e.g. 'at least "
     "one director who is ordinarily resident', positions of director or manager reserved for "
     "nationals, an ISP's managers must be citizens. Any such requirement scores 1. "
     "Residency or nationality rules for officers who are NOT directors or managers do not "
     "count — so a locally resident data protection officer or a local contact person is not "
     "this indicator (see 7.4 / 12.8) (RDTII 2.1 guide p.26 and fn.10).",
     ["shall be a citizen of", "ordinarily resident in", "majority of the directors shall be",
      "the managing director shall be", "manager shall be a citizen",
      "at least one director who is a resident", "domicile in"]),

    ("3.4", 3, "Screening of investment and acquisitions",
     "Is foreign investment or acquisition subject to government screening or approval?",
     "The operative rule creates a SCREENING mechanism that lets the government review, "
     "approve, condition or block a foreign investment or M&A in a sector relevant to digital "
     "trade — prior approval or an investment certificate, a national-security / public-order "
     "review, a national-interest test, or an economic-benefit test (employment, technology "
     "contribution, local capacity-building). Score 0.25 for one mechanism, 0.5 for two or "
     "more, 1 where a mechanism has actually been USED to block an investment in a relevant "
     "sector. Exception: merger control for competition (anti-trust) purposes is not scored "
     "unless it discriminates. This is a PRACTICE-scored indicator: the statute shows the "
     "mechanism, but a blocking case is usually found in decisions or official announcements, "
     "not in statute text — absence of a blocking provision is not evidence of no block "
     "(RDTII 2.1 guide p.26-27; coder guide p.8).",
     ["prior approval of the", "notify the authority before acquiring", "national interest test",
      "national security review", "foreign investment review", "significant action",
      "change of control shall be approved", "screening mechanism"]),

    ("3.5", 3, "Commercial presence requirements for cross-border services",
     "Must a supplier establish locally in order to serve the market from abroad?",
     "The operative rule requires a foreign service provider to ESTABLISH a commercial presence "
     "(GATS Mode 3) — a locally incorporated company, subsidiary, branch or representative "
     "office with a physical or operational presence — in order to supply a service in a "
     "sector relevant to digital trade: e.g. a foreign company doing business must incorporate "
     "or register a branch; significant social media companies must open a permanent office; "
     "online-game providers must set up a local company to be licensed. Any such requirement "
     "scores 1. NOT this indicator: a mere business-registration duty with no physical or "
     "operational presence, or the appointment of a local agent/contact point only (that is "
     "12.8, Mode 1). Where one law requires both a local entity and a local representative, "
     "classify it here, as the stronger obligation. Distinguish from 6.3 (local servers or "
     "data centres) (RDTII 2.1 guide p.27-28, p.88).",
     ["shall establish a branch", "commercial presence", "shall be incorporated in",
      "representative office", "shall be incorporated locally", "permanent registered office",
      "may not supply services unless established", "register a branch"]),

    # ───────────────────────── Pillar 4 — Intellectual Property Rights ──────────────────────
    ("4.01", 4, "Patent application issues",
     "Does the patent APPLICATION process discriminate against foreign applicants or impose burdensome procedures?",
     "The operative rule RESTRICTS the patent application process. Score 1: a requirement "
     "that foreign / non-resident applicants appoint a local agent or representative, other "
     "differential treatment of foreign applicants, or discriminatory rejection of "
     "applications. Score 0.5: procedural burdens applied to all — a requirement to file "
     "locally (or obtain a secrecy/confidentiality examination) before filing abroad, "
     "mandatory translation into the official language, a requirement that foreign patents be "
     "re-registered locally to be valid, a non-transparent or discretionary process, or high "
     "filing/registration fees. What is patentable is not this indicator, and compulsory "
     "licensing is an enforcement matter (4.3) that TRIPS permits. Note the code: this is "
     "4.01, a different indicator from 4.1 (trade secrets). Written as text, never as a "
     "number — 4.01 read as a float becomes 4.1 (RDTII 2.1 guide p.29-30).",
     ["patent agent", "residing outside shall be represented", "registered patent attorney",
      "file a patent application in a foreign country", "confidentiality examination",
      "translation into the official language", "foreign applicant shall",
      "registration of foreign patents"]),

    ("4.1", 4, "Lack of an effective trade-secrets framework",
     "Is there a legal framework protecting trade secrets, with effective remedies?",
     "The evidence is a provision establishing EFFECTIVE protection for UNDISCLOSED "
     "INFORMATION / trade secrets (TRIPS art.39) — protection against unauthorised "
     "acquisition, use or disclosure, and an action for misappropriation with remedies "
     "(injunction, damages, where applicable criminal sanctions). Any form counts: a dedicated "
     "act, clauses in an IP, competition or civil law, or — in common-law economies — the "
     "breach-of-confidence doctrine in case law, which is effective protection even with no "
     "statute (so an empty statute search is not a finding of absence there). Score 0 "
     "effective protection; 0.5 narrow or partially enforced provisions; 1 none. Distinguish "
     "from 4.9 (a rule COMPELLING disclosure) (RDTII 2.1 guide p.37-38)."
     + _INVERTED_NOTE,
     ["trade secret", "undisclosed information", "confidential business information",
      "misappropriation", "breach of confidence", "unfair competition",
      "injunction and damages", "reasonable steps to keep it secret"]),

    ("4.2", 4, "Patent enforcement — civil and administrative procedures and remedies",
     "Are there civil and administrative procedures, remedies and provisional measures for patent infringement?",
     "The evidence is a provision giving a patent holder (a) CIVIL or ADMINISTRATIVE "
     "procedures and remedies for infringement (TRIPS arts.42-49: proceedings, injunctions, "
     "damages, destruction of infringing goods) and (b) PROVISIONAL MEASURES (TRIPS art.50: "
     "preliminary injunction, seizure or detention of suspected goods, preservation of "
     "evidence). General laws count — a Civil Code or Civil Procedure Code supplying "
     "provisional measures is evidence. Score 0 with both, 0.5 with only one, 1 with neither. "
     "Distinguish from 4.3 (restrictions on enforcement) (RDTII 2.1 guide p.30-31)."
     + _INVERTED_NOTE,
     ["infringement of a patent", "preliminary injunction", "provisional measures",
      "preservation of evidence", "damages shall be awarded", "civil proceedings",
      "administrative enforcement", "seizure of infringing goods"]),

    ("4.3", 4, "Patent enforcement — other issues",
     "Are there other restrictions on the enforcement of patent rights?",
     "The operative rule RESTRICTS a patent holder's ability to enforce: terms of protection "
     "or enforcement rights that differ for foreign applicants, state intervention that "
     "curtails the holder's rights, or a requirement to appoint a local agent for "
     "enforcement matters (a low-impact example). Score 1 when the restriction is pervasive "
     "(all circumstances and sectors) or there are two or more limited ones; 0.5 for one "
     "measure limited to a specific case or sector, or of low impact. NOT restrictions: the "
     "exceptions TRIPS allows — art.30 limited exceptions, and art.31/31bis compulsory "
     "licences or government use for public health, emergency or extreme urgency with "
     "adequate remuneration. Distinguish from 4.2, which asks whether civil/administrative "
     "remedies and provisional measures exist at all (RDTII 2.1 guide p.31; coder FAQ p.12).",
     ["patentee shall not", "rights of the patentee shall be restricted",
      "foreign patentee", "term of the patent", "shall appoint an agent",
      "the Government may use the patented invention", "standing to sue"]),

    ("4.5", 4, "Lack of a copyright framework and exceptions",
     "Is there a copyright framework, and what kind of exceptions does it adopt?",
     "The evidence is a copyright statute AND the TYPE of its EXCEPTIONS. Score 0: clear "
     "exceptions following a FAIR USE (open, multi-factor, case-by-case) or FAIR DEALING "
     "(listed purposes such as research, private study, criticism, review, news reporting, "
     "plus a fairness test) model. Score 0.5: exceptions exist but are not an explicit fair "
     "use/fair dealing regime — a bare Berne three-step test, or a closed list of narrow "
     "exceptions (e.g. only non-commercial education, research or personal use). Score 1: no "
     "copyright framework or no exceptions. Cite the exceptions provision, not just the grant "
     "of copyright. Distinguish from 4.6 (enforcement remedies) and 8.1 (intermediary safe "
     "harbour) (RDTII 2.1 guide p.33). Coder FAQ p.12 adds that a demonstrably high piracy "
     "rate scores 1 despite a law — a practice fact no statute shows."
     + _INVERTED_NOTE,
     ["copyright subsists in", "fair dealing", "fair use", "permitted acts",
      "exceptions and limitations", "does not conflict with a normal exploitation",
      "shall not constitute an infringement of copyright", "for the purpose of research or private study",
      "criticism or review"]),

    ("4.6", 4, "Online copyright enforcement — procedures, remedies and provisional measures",
     "Are there civil and administrative remedies and provisional measures for online copyright infringement?",
     "The evidence is a provision giving a COPYRIGHT holder (a) CIVIL or ADMINISTRATIVE "
     "procedures and remedies for infringement, including online infringement (TRIPS "
     "arts.42-49: proceedings, injunctions, damages, an administrative complaint route, "
     "notice-and-takedown or disabling orders) and (b) PROVISIONAL MEASURES (TRIPS art.50: "
     "interim injunctions, seizure, preservation of evidence). General laws count — a Civil "
     "Procedure Code supplying provisional measures is evidence. Score 0 with both, 0.5 with "
     "only one, 1 with neither. Distinguish from 8.1, which is the INTERMEDIARY's liability "
     "shield; the same section often supports both, and each cites its own limb (RDTII 2.1 "
     "guide p.34)."
     + _INVERTED_NOTE,
     ["notice and takedown", "expeditiously remove", "disable access to", "blocking order",
      "statutory damages", "online service provider shall", "injunction against an intermediary",
      "repeat infringer"]),

    ("4.9", 4, "Mandatory disclosure of trade secrets, source code or algorithms",
     "Does the law compel disclosure of source code, algorithms or other trade secrets?",
     "The operative rule COMPELS a firm to disclose, deposit or transfer source code, an "
     "algorithm or another trade secret to the state, a regulator or a panel — as a condition "
     "of market access or licensing, in proceedings, or under a national-security power. NOT "
     "scored when the law protects the disclosed information against unfair commercial use "
     "and further disclosure (TRIPS art.39.3). Without such safeguards: 0.5 for a requirement "
     "of limited scope (specific products or circumstances, e.g. a national-security "
     "disclosure power over certain companies); 1 for a requirement covering a whole sector or "
     "all sectors, or more than one measure. EXCLUDED here: disclosure demanded in public "
     "PROCUREMENT (2.2) and disclosure tied to ENCRYPTION products (11.4). Distinguish from 8.4 "
     "(surveillance of users, not disclosure of technology) (RDTII 2.1 guide p.37).",
     ["source code", "algorithm shall be filed", "shall submit the technical documentation",
      "security assessment of the algorithm", "algorithm filing", "technology transfer",
      "provide access to the underlying model", "shall disclose to the competent authority"]),

    # ───────────────────────── Pillar 5 — Telecom Regulations & Competition ─────────────────
    ("5.1", 5, "Lack of passive infrastructure sharing",
     "Must operators share passive infrastructure — ducts, poles, towers, sites?",
     "The evidence is an obligation on telecom operators to SHARE PASSIVE (non-electronic, "
     "physical) infrastructure — buildings, sites, network cabinets, masts/towers, poles, "
     "ducts, trays. Sharing of ACTIVE (electronic) network elements — antennas, RAN, backhaul, "
     "core network — is not this indicator. Score 0: sharing is mandated (at least one "
     "obligation). Score 0.5: not mandated but practised commercially or under a voluntary "
     "co-location framework, or mandated only case by case / upon request. Score 1: no "
     "obligation. Distinguish from 5.4 (functional/accounting separation, an organisational "
     "remedy rather than a physical one) (RDTII 2.1 guide p.41-42)."
     + _INVERTED_NOTE,
     ["infrastructure sharing", "passive infrastructure", "ducts and poles", "co-location",
      "site sharing", "shall grant access to", "significant market power", "tower sharing"]),

    ("5.2", 5, "Foreign equity limits in the telecom sector",
     "Does the law cap foreign shareholding in telecommunications?",
     "The operative rule CAPS foreign ownership in telecommunications (basic and value-added "
     "services, including VoIP), in private operators or SOEs, at a stated percentage, or bans "
     "it. Score 1 for a ban or minority-only caps in more than one measure; 0.8 minority stake "
     "only; 0.5 a controlling stake allowed but capped, or caps only in SOEs. This is the "
     "telecom-specific case of 3.1: where a provision is telecom-only, cite it here; a "
     "horizontal cap that happens to cover telecom belongs to 3.1, and broadcasting caps "
     "belong to 3.1 (RDTII 2.1 guide p.25 fn.9, p.40, p.42).",
     ["foreign equity in a licensee", "shall not exceed", "telecommunications licensee",
      "foreign shareholding", "majority national ownership", "per cent of the shares"]),

    ("5.3", 5, "Government shareholding in telecom companies",
     "Does the state hold shares in telecom operators?",
     "The evidence is the PERCENTAGE of shares the government (domestic, or a foreign "
     "government's SOE) holds in each telecom operator. Score 1 if any operator is more than "
     "50% government-owned, or two or more operators are 1-50% owned; 0.5 if one operator is "
     "1-50% owned; 0 if none. This is a PRACTICE-scored indicator: the figures normally come "
     "from telecom market reports, the regulator's annual updates, the ministry's SOE list or "
     "operators' own websites, not from statute text. A statute helps only where it fixes "
     "ownership — an act reserving networks to the state, incorporating a state carrier, or "
     "a golden/special share — and a privatisation act that RETAINS a stake is evidence. Not "
     "foreign equity caps (5.2) (RDTII 2.1 guide p.42-43; coder guide p.8, FAQ p.12).",
     ["shares held by the Government", "State-owned enterprise", "special share",
      "golden share", "the Government shall retain", "public corporation",
      "wholly owned by the State"]),

    ("5.4", 5, "Lack of functional or accounting separation",
     "Is an incumbent required to separate its wholesale and retail arms, functionally or in its accounts?",
     "The evidence is an obligation on an operator with SIGNIFICANT MARKET POWER to keep "
     "SEPARATE ACCOUNTS for different services (costs, revenue, assets per regulated "
     "service), and/or to separate FUNCTIONS (operational or structural separation of "
     "network and retail units), including a regulator's power to impose it on SMP operators. "
     "Score 0 when BOTH accounting and functional separation are mandated; 0.25 functional "
     "only; 0.5 accounting only; 1 neither. Distinguish from 5.1 (physical sharing) (RDTII "
     "2.1 guide p.43-44)."
     + _INVERTED_NOTE,
     ["accounting separation", "functional separation", "structural separation",
      "separate accounts shall be maintained", "cost accounting", "vertically integrated operator",
      "wholesale and retail"]),

    ("5.5", 5, "Licensing requirements for telecom operators",
     "Is a telecom licence subject to strict or discriminatory conditions?",
     "The operative rule sets a LICENCE for telecom services or facilities whose conditions are "
     "STRICT: discriminatory against foreign firms, or a significant barrier to entry for all — "
     "mandatory performance requirements, a separate licence for value-added services, a cap "
     "on the number of licences, minimum capital or share-offering requirements (e.g. an "
     "obligatory IPO), revenue-sharing with the regulator on top of fees, administrative "
     "allocation of spectrum instead of auction. Score 1 for any strict scheme; a licence "
     "with ordinary conditions and fees scores 0. Licences for online/digital service "
     "providers (ICPs, VPN, cloud, data centres, broadcasting — coder FAQ puts ISP-type digital "
     "service licences there too) are 9.4; e-commerce licences are 12.3 (RDTII 2.1 guide "
     "p.44; coder FAQ p.12, p.14).",
     ["licence to operate a telecommunications network", "shall not provide services without a licence",
      "value-added telecommunications service licence", "licence conditions", "spectrum",
      "number of licences", "minimum paid-up capital", "revenue share", "network facilities licence"]),

    ("5.7", 5, "Lack of an independent telecom authority",
     "Is there a telecom regulator independent of government and of operators?",
     "The evidence is the provision ESTABLISHING the telecom regulator and its duties and "
     "powers, read for independence from operators AND from government. Functional: it "
     "decides without approval from government bodies or operators (any override is clearly "
     "defined and limited), applies procedures equally to all including SOEs, and is not "
     "subject to political direction — it may sit under or report to a ministry and still be "
     "independent. Institutional/financial: legally separate from, and owning no, telecom "
     "operator; a dedicated, stable budget (levies or appropriation); control of its own "
     "staff. Binary: 0 if independent, 1 if not (RDTII 2.1 guide p.46; coder FAQ p.13)."
     + _INVERTED_NOTE,
     ["shall be an independent", "body corporate", "shall not be subject to the direction of any person",
      "term of office", "may be removed only", "the Commission shall determine",
      "regulatory authority is established", "appeal against a decision of the authority"]),

    # ───────────────────────── Pillar 8 — Internet Intermediary Liability ───────────────────
    ("8.1", 8, "Lack of safe harbour for copyright infringement",
     "Is an intermediary shielded from liability for users' copyright infringement?",
     "The evidence is a LIABILITY SHIELD for an internet intermediary (ISP, host, cache, "
     "platform) in respect of copyright-infringing material of its users — typically "
     "conditional on no actual knowledge and on removal once notified. Score 0 for a "
     "HORIZONTAL framework; 0.5 for a SECTORAL one (e.g. only in a telecom or e-commerce law); "
     "1 for none. A general e-commerce-law shield for hosting/caching that does not mention "
     "copyright still applies to it. Distinguish from 8.2 (a shield for OTHER unlawful "
     "content — one law often gives both, cite it under each) and 4.6 (the rights holder's "
     "remedy) (RDTII 2.1 guide p.64-65)."
     + _INVERTED_NOTE,
     ["shall not be liable", "safe harbour", "mere conduit", "caching", "hosting",
      "actual knowledge", "expeditiously remove", "network service provider",
      "no general obligation to monitor"]),

    ("8.2", 8, "Lack of safe harbour for other illegal activities",
     "Is an intermediary shielded from liability for users' unlawful content generally?",
     "The evidence is a liability shield covering unlawful content OTHER than copyright — "
     "defamation, privacy, harmful communications, fraud, unlawful goods — for a provider that "
     "merely transmits or hosts, unless it contributed or had notice. Score 0 for a "
     "HORIZONTAL framework; 0.5 for a SECTORAL one; 1 for none. A shield conditioned on "
     "removal once aware still counts; a regime imposing PRIMARY liability on the "
     "intermediary is the opposite finding and belongs here as the evidence for it (RDTII 2.1 "
     "guide p.65-66)."
     + _INVERTED_NOTE,
     ["shall not be liable for", "third-party information", "intermediary", "due diligence",
      "upon receiving actual knowledge", "conduit", "exemption from liability",
      "unlawful content"]),

    ("8.3", 8, "User identity requirements",
     "Must users identify themselves to connect to the internet or use an online service?",
     "The operative rule requires an internet intermediary to VERIFY AND RECORD accurate "
     "personal information of its users (name, ID number, address, biometrics) as a condition "
     "of access to its network or service. Score 1 where it applies to connecting to the "
     "internet or using online services (ISP subscriptions, platform or messaging accounts, "
     "traceability of the first originator, cybercafé ID logs); 0.5 where it applies only to "
     "SIM-card registration. Distinguish from 8.4 (monitoring what users do), 7.5 (state "
     "ACCESS to the data) and 7.3 (how long it is kept) — a rule that makes providers both "
     "collect and retain registration data can be cited under each (RDTII 2.1 guide p.66-67).",
     ["real identity", "identity verification", "registration of subscribers",
      "national identity card", "SIM card registration", "shall verify the identity of users",
      "register with their real names", "cyber cafe", "log of users"]),

    ("8.4", 8, "Monitoring requirements",
     "Must an intermediary monitor user activity, or remove or block illegal content?",
     "The operative rule requires an internet intermediary to (a) MONITOR users' activities or "
     "content — explicitly, or indirectly by installing software, algorithms or moderation "
     "tools to detect prohibited content, inspecting users' activity, checking or "
     "fact-verifying content before or after publication — and/or (b) REMOVE or BLOCK content "
     "deemed illegal (e.g. within 24 hours of notice) to avoid liability. Score 1 for any "
     "requirement that includes removing/blocking; 0.5 for active monitoring with no legal "
     "obligation to remove or block. A mere duty to retain logs is not monitoring (see 7.3). "
     "Distinguish from 9.1 (the state blocking or filtering commercial websites or content) "
     "and 8.3 (identifying users) (RDTII 2.1 guide p.67; coder FAQ p.13).",
     ["shall monitor", "proactively detect", "content moderation", "technical measures to prevent",
      "shall remove within", "remove or block access", "verify the content",
      "report to the authority"]),

    # ───────────────────────── Pillar 9 — Content Access ────────────────────────────────────
    ("9.1", 9, "Blocking or filtering commercial web content",
     "May the state block or filter access to websites or online services?",
     "The operative rule EMPOWERS or REQUIRES blocking or filtering of COMMERCIAL web content, "
     "by the government or by intermediaries at its direction — typically on broad "
     "public-interest, public-order or national-security grounds. BLOCKING denies access to a "
     "whole website (any technique: IP, DPI, URL, DNS) and scores 1 per measure; FILTERING "
     "limits access to certain content on a site and scores 0.5. NOT scored: blocking or "
     "filtering of political content, criminal content (child sexual abuse material), "
     "age-restricted content, defamation or other non-commercial content, or of "
     "IP-infringing content. This is a PRACTICE-scored indicator — it asks whether there have "
     "been INSTANCES of blocking/filtering; a statute supplies the legal basis, but the "
     "instances are found in orders and official announcements, not statute text. Distinguish "
     "from 8.4 (an intermediary's own monitoring/removal duty) (RDTII 2.1 guide p.69-70; "
     "coder guide p.8, FAQ p.14).",
     ["block access to", "shall be blocked", "filtering", "disable access", "take down the website",
      "direct an internet service provider", "prohibited content", "banned application",
      "restrict access to the platform"]),

    ("9.3", 9, "Online advertising requirements",
     "Does the law restrict online advertising?",
     "The operative rule LIMITS advertising online — e.g. mandatory language(s) or prior "
     "approval of advertisements, a ban on comparative advertising, a quota of free social "
     "advertising imposed on ad distributors with reporting duties, a ban on showing prices in "
     "foreign currency, a ban on targeted advertising. Scope: rules for online advertising, or "
     "for advertising generally where the law is silent on medium; rules applying ONLY to "
     "offline advertising (billboards) are excluded. NOT scored: consumer-protection rules "
     "(misleading or false advertising, consent-type rules) and restrictions on advertising "
     "specific products for health or safety (weapons, drugs, tobacco, alcohol, medicine). "
     "Each limiting requirement scores 1 (RDTII 2.1 guide p.21, p.71; coder FAQ p.14).",
     ["advertisement shall not", "prior approval of the advertisement", "advertising licence",
      "targeted advertising is prohibited", "advertisement published through the internet",
      "advertisements shall be in the state language", "comparative advertising",
      "social advertising", "prices in foreign currency"]),

    ("9.4", 9, "Licensing requirements for online content providers and applications",
     "Must an online content provider, social platform, VPN or cloud service hold a licence?",
     "The operative rule requires a LICENCE to operate an online content provider or digital "
     "service — social media, news/media and broadcasting services, streaming, VPN, cloud "
     "computing, data centres, IoT services, apps. Score 1 for a STRICT scheme — conditions "
     "such as commercial presence, nationality or residency, excessive paid-up capital, or "
     "technical mandates (government-approved systems, local data storage, local numbering, "
     "proprietary technology) — or for more than one licensing requirement; 0.5 for a single "
     "ordinary licensing scheme. Excluded: telecom facility/service licences (5.5) and "
     "e-commerce licences (12.3) — but a platform licence covering both online services and "
     "marketplaces is cited under 9.4 AND 12.3. A data-centre LICENCE is here, not 6.3 "
     "(which is only a mandate to locate infrastructure locally). Local presence with no "
     "licence attached is 12.8 (RDTII 2.1 guide p.11, p.71-72; coder FAQ p.12-14).",
     ["licence for online content", "internet content provider", "registration of the platform",
      "shall obtain a permit to provide", "VPN service", "cloud service licence",
      "online news service", "social media platform shall register", "electronic service provider licence",
      "data centre licence", "broadcasting licence"]),

    # ───────────────────────── Pillar 10 — Non-technical NTMs ───────────────────────────────
    ("10.1", 10, "Import ban on ICT goods and online services",
     "Does the law ban the import of ICT goods or the supply of an online service?",
     "The operative rule PROHIBITS importation of an ICT good (network equipment, servers, "
     "handsets, encryption devices) or bans an online service or application outright — "
     "whether the ban targets ICT specifically or is a broader ban that sweeps ICT in. Score "
     "0.5 for one ban on a single product or service; 1 for more than one ban, or one ban "
     "covering several products/services. Raw materials used to make ICT goods (rare earths) "
     "are not covered. A ban applying only to government users may be this or 2.1 — decide by "
     "whether it operates as an import ban or through procurement. Distinguish from 10.2 "
     "(restrictions short of a ban) and 9.1 (blocking access to content rather than "
     "prohibiting the product) (RDTII 2.1 guide p.9, p.74; coder FAQ p.11, p.14).",
     ["shall not be imported", "prohibited goods", "import prohibition", "banned equipment",
      "the application shall be prohibited", "prohibited list", "no person shall import"]),

    ("10.2", 10, "Other import restrictions on ICT goods and online services",
     "Are ICT imports restricted short of a ban — by quota, permit, licence or condition?",
     "The operative rule RESTRICTS imports of ICT goods or online services short of a ban and "
     "other than a local-content rule. Score 1 for a trade-blocking measure (an import quota), "
     "for two or more cost-adding measures, or where the rules are not publicly available. "
     "Score 0.5 for one cost-adding measure: a non-automatic import licence, permit, "
     "authorisation or registration of ICT goods (including regulator approval of equipment "
     "before it may be used or connected), labelling requirements, import controls, or "
     "import reserved to licensed entities. Where the requirement is conformity CERTIFICATION "
     "or TESTING itself, cite 11.2/11.3 as well (RDTII 2.1 guide p.75).",
     ["import licence", "import permit", "quota", "prior authorisation to import",
      "pre-shipment inspection", "designated port", "shall be imported only through",
      "import of telecommunications equipment"]),

    ("10.3", 10, "Local content requirements",
     "Must a product or service incorporate a minimum share of local content?",
     "The operative rule requires the use of domestically manufactured goods or domestically "
     "supplied services in producing or selling ICT goods or online services in the "
     "COMMERCIAL market — a minimum local-content percentage for devices (TV receivers, "
     "set-top boxes, phones), a share of locally produced content for OTT services, or local "
     "sourcing as a condition of investment or licensing. Score 0.5 for an LCR at product "
     "level (HS-6/HS-8, e.g. smartphones); 1 for two or more product-level LCRs or one at "
     "sectoral/horizontal level (HS-4/HS-2, e.g. telephony equipment). Excluded: LCRs in "
     "public procurement (2.3); local storage or infrastructure for DATA (6.2/6.3); local "
     "presence (12.8) (RDTII 2.1 guide p.75-76).",
     ["local content", "domestic component", "percentage of local", "manufactured locally",
      "TKDN", "shall use domestically produced", "locally produced content",
      "sourced from domestic"]),

    ("10.4", 10, "Export restrictions on ICT goods and online services",
     "Are exports of ICT goods or online services restricted?",
     "The operative rule RESTRICTS export of ICT goods (ITA I/II/III list) or online services: "
     "an export ban, an export licence or permit (e.g. for strategic / dual-use items such as "
     "computers, telecom equipment, information-security products, radio transmitters), or "
     "another limit on the quantity exported. Any such measure scores 1. Raw materials are "
     "not covered. Note the frequent overlap with data policy — an export control on "
     "cryptography is this indicator; a control on TRANSFERRING DATA abroad is pillar 6 "
     "(RDTII 2.1 guide p.76; coder FAQ p.14).",
     ["export licence", "export control list", "dual-use", "shall not be exported",
      "cryptographic equipment", "export permit", "technology export catalogue",
      "controlled technology"]),

    # ───────────────────────── Pillar 11 — Standards and Procedures ─────────────────────────
    ("11.1", 11, "Lack of transparent technical standards",
     "Is standard-setting open to foreign participation and transparent?",
     "The evidence is the provision governing HOW technical standards in digital-trade "
     "sectors are made, read for two things: (a) whether stakeholders, INCLUDING FOREIGN "
     "businesses, may participate in the standard-setting bodies, and (b) whether there is a "
     "transparent public-consultation or notification mechanism inviting comment on drafts. "
     "Binary: 1 if foreigners are excluded or restricted (e.g. telecom equipment standards "
     "set 'without foreign participation') or standard-setting is not transparent; 0 "
     "otherwise (RDTII 2.1 guide p.78-79)."
     + _INVERTED_NOTE,
     ["national standards body", "public consultation on the draft standard",
      "comments on the draft", "notification to the WTO",
      "membership of the technical committee", "standards shall be published",
      "foreign participation"]),

    ("11.2", 11, "Self-certification limitations for product safety",
     "May a supplier self-declare conformity, or is third-party certification compulsory?",
     "The operative rule determines how ICT products show CONFORMITY with domestic radio, "
     "EMC/EMI or electrical-safety standards. Score 0: a Supplier's Declaration of Conformity "
     "(SDoC) is accepted from foreign businesses for at least some ICT products. Score 0.5: "
     "no SDoC, but certificates from conformity assessment bodies in other economies are "
     "accepted (e.g. under the ASEAN EE MRA or APEC TEL MRA — members score 0.5 or less). "
     "Score 1: neither SDoC nor foreign third-party certification is recognised and local "
     "testing is required, or there is no framework accepting SDoC at all. Certification is "
     "about the mark/certificate; additional TESTING is 11.3. Distinguish from 11.4 "
     "(encryption standards) (RDTII 2.1 guide p.79; coder FAQ p.14-15).",
     ["declaration of conformity", "self-declaration", "accredited certification body",
      "type approval", "conformity assessment", "recognised laboratory",
      "certificate of conformity issued by", "mutual recognition"]),

    ("11.3", 11, "Product screening and testing requirements",
     "Must imported ICT products undergo additional screening or testing, in-country, before sale?",
     "The operative rule requires imported ICT products to undergo ADDITIONAL screening or "
     "testing beyond standard conformity assessment before entering the market — often "
     "justified by national security: in-country security testing of telecom equipment by "
     "designated labs, mandatory local testing of samples by the national standards body "
     "before clearance or certification. Score 1 where testing must be done domestically, "
     "including by in-country designated or accredited bodies, for any product without "
     "accepting third-party results; 0.5 where third-party test results are accepted (for at "
     "least some products). Ordinary EMC/EMI or product-safety testing is not the target. "
     "Distinguish from 11.2 (certification/marking) and 10.2 (import licensing formalities) "
     "(RDTII 2.1 guide p.80 and fn.48; coder FAQ p.15).",
     ["shall be tested", "testing in a laboratory located in", "security testing",
      "designated testing laboratory", "security review of network equipment",
      "samples shall be submitted", "test reports issued by", "prior to sale, import or use"]),

    ("11.4", 11, "Deviation from international encryption standards",
     "Does the law require national cryptography instead of international standards?",
     "The operative rule sets encryption requirements that DEVIATE from ISO/IEC standards "
     "(ISO/IEC 18033 encryption, 11770 key management): (a) a domestic or other algorithm "
     "not listed in ISO/IEC 18033 (listed: AES, TDEA, Camellia, SEED, MISTY1, CAST-128, "
     "HIGHT); (b) block sizes below the 18033 minimums; (c) symmetric keys shorter than 128 "
     "bits; (d) key management outside ISO/IEC 11770; or (e) disclosure of source code, "
     "encryption keys or other trade secrets to certify an encryption product, beyond ISO "
     "19790/24759 validation. Any such measure scores 1. NOT this indicator: a registration or "
     "licence to use, import or distribute encryption that carries none of those conditions "
     "(that is pillar 9 or 10). Encryption-related disclosure belongs here, not 4.9; a "
     "specific encryption demanded to win a TENDER is 2.2 (RDTII 2.1 guide p.37, p.80-81).",
     ["commercial cryptography", "cryptographic algorithm", "national cryptographic standard",
      "key length", "block size", "key management", "SM2 SM4",
      "source code of the encryption", "certification of encryption products"]),

    # ───────────────────────── Pillar 12 — Online Sales and Transactions ────────────────────
    ("12.01", 12, "Foreign equity limits in the e-commerce sector",
     "Does the law cap foreign shareholding in e-commerce?",
     "The operative rule CAPS or bans foreign ownership of an e-commerce business, marketplace "
     "or (online) retail trade enterprise — e.g. retail trade reserved to nationals below a "
     "capital threshold. Score 1 if only a minority stake (or none) is allowed; 0.5 if a "
     "controlling stake is allowed but capped; 0 if no cap. SOE-only caps are not scored here. "
     "Caps in other digital sectors are 3.1, telecom caps 5.2. This is the e-commerce case of "
     "3.1; note the code is 12.01, written as text — read as a number it becomes 12.1, a "
     "different indicator (RDTII 2.1 guide p.84).",
     ["foreign equity", "e-commerce", "marketplace", "retail trade", "shall not exceed",
      "negative investment list", "foreign-invested enterprise"]),

    ("12.2", 12, "Online purchase and delivery limitations",
     "Does the law cap how much a consumer may buy online, or restrict how goods bought online are delivered?",
     "The operative rule LIMITS online purchases or the delivery of goods bought online: a "
     "cap on the number or value of goods a consumer may import or buy through e-commerce "
     "(per shipment, per month, per year); a limit on delivery applied to the delivery company "
     "(e.g. foreign postal operators barred from intercity delivery and required to use local "
     "companies); or a restriction on how, where or when consumers may receive deliveries. "
     "At least one such requirement scores 1. NOT covered: taxes, customs duties or fees on "
     "online purchases (see 12.5/12.6); product restrictions for consumer protection "
     "(alcohol, tobacco, pharmaceuticals); FDI measures on delivery companies (pillar 3) "
     "(RDTII 2.1 guide p.84).",
     ["maximum quantity", "per shipment", "maximum value", "per month",
      "cross-border e-commerce goods", "foreign postal operator", "delivery shall be through",
      "courier services"]),

    ("12.3", 12, "Licensing scheme for e-commerce providers",
     "Must an e-commerce provider hold a licence or register?",
     "The operative rule requires a LICENCE, permit, acknowledgement certificate or specific "
     "registration to operate an e-commerce business or marketplace (B2B or B2C) — including "
     "one triggered by transaction-volume thresholds, or a duty to register commercial "
     "websites. Any one scores 1. Not captured: licences for other aspects of e-commerce "
     "such as online payment (12.4.4) or delivery; general company incorporation is not an "
     "e-commerce licence. A platform licence covering both marketplaces and online services "
     "is cited under 12.3 AND 9.4. Distinguish from 12.8 (local presence) (RDTII 2.1 guide "
     "p.11, p.85).",
     ["e-commerce licence", "shall register as an e-commerce operator",
      "operating permit for online trading", "platform operator shall obtain",
      "electronic commerce business licence", "registration with the ministry of trade"]),

    ("12.4.1", 12, "Online payment — mandated local bank account",
     "Must online payments settle through a local bank or account?",
     "The operative rule requires payment for online transactions to be made or settled through "
     "a bank, account or institution ESTABLISHED IN the economy. The other 12.4 limbs cover "
     "currency (12.4.2), standards (12.4.3), licensing (12.4.4), ceilings (12.4.5), mandated "
     "intermediaries (12.4.6) and anything else (12.4.7): cite the limb that matches the "
     "operative words, not the general one.",
     ["settlement through a local bank", "account opened with a bank licensed in",
      "domestic bank account", "funds shall be held in", "settled domestically"]),

    ("12.4.2", 12, "Online payment — mandated currency",
     "Must international online payments be made in a particular currency?",
     "The operative rule mandates or restricts the CURRENCY of an online or cross-border "
     "payment — a national-currency requirement, a foreign-exchange approval, or a ban on "
     "pricing in foreign currency. Distinguish from 12.4.1, which is about where the money "
     "sits, not what it is denominated in.",
     ["shall be denominated in", "national currency", "foreign exchange approval",
      "may not quote prices in foreign currency", "repatriation of proceeds",
      "exchange control"]),

    ("12.4.3", 12, "Online payment — deviation from national standards",
     "Does the law impose national payment-SECURITY standards that deviate from international ones?",
     "The operative rule mandates a national standard for PAYMENT SECURITY (card, chip, "
     "authentication, encryption or data-security requirements for electronic payments) that "
     "deviates from international standards. The test is flexible: a law that references any "
     "recognised international standard — ISO/IEC, PCI DSS or similar — is not a deviation. "
     "Distinguish from 12.4.6 (a mandated INTERMEDIARY, e.g. routing through a national "
     "switch) — this limb is about the security standard itself (RDTII 2.1 guide p.85 and "
     "fn.52).",
     ["payment security standard", "national standard for payment", "PCI DSS",
      "national card scheme", "shall comply with the national standard",
      "security requirements for electronic payment", "chip card standard"]),

    ("12.4.4", 12, "Online payment — licensing requirements",
     "Is a payment-service licence subject to restrictive conditions?",
     "The operative rule attaches RESTRICTIVE CONDITIONS to the licence for payment, e-money, "
     "wallet or payment-gateway services — local incorporation, nationality restrictions, or "
     "limits on the types or number of licences obtainable. A licence with ordinary "
     "prudential conditions is not enough on its own; cite the condition. Distinguish from "
     "12.3 (licensing the e-commerce seller rather than the payment provider) (RDTII 2.1 "
     "guide p.85).",
     ["payment service provider licence", "e-money issuer", "payment institution",
      "shall not carry on payment services without", "shall be incorporated in",
      "number of licences",
      "authorisation of the central bank", "payment gateway"]),

    ("12.4.5", 12, "Online payment — ceiling on the maximum amount",
     "Is there a cap on the value of an online or e-money transaction?",
     "The operative rule sets a MAXIMUM amount for an online payment, an e-money balance, a "
     "wallet top-up, a daily or monthly total, or a cross-border transfer. The evidence is a "
     "number. A threshold that merely triggers reporting or enhanced due diligence is NOT a "
     "ceiling — that is an AML rule, not a limit on the transaction.",
     ["shall not exceed", "maximum balance", "daily limit", "transaction limit",
      "per month", "ceiling on the amount", "wallet balance"]),

    ("12.4.6", 12, "Online payment — mandated specific intermediaries",
     "Must payments pass through a designated intermediary?",
     "The operative rule requires an online payment to be processed by a DESIGNATED or "
     "state-approved intermediary — a national clearing house, a monopoly processor, or a "
     "registered agent. Distinguish from 12.4.3 (a mandated technical standard) and 12.4.1 (a "
     "mandated local account).",
     ["shall be processed through", "designated clearing house", "national payment corporation",
      "authorised intermediary", "only through institutions approved by",
      "monopoly of the settlement system", "routed through the national switch"]),

    ("12.4.7", 12, "Online payment — other restrictions",
     "Are there other restrictions on online payment not covered by the other 12.4 limbs?",
     "The residual limb. Use it only when the operative rule restricts online or electronic "
     "payment (or credit) services and does NOT match 12.4.1–12.4.6: for example a mandatory "
     "settlement delay, a merchant-category prohibition, or a restriction on a prepaid "
     "instrument. Rules on CRYPTOCURRENCIES are not listed under 12.4 at all (the guide "
     "excludes them) — do not map them here. State in the rationale which limbs were "
     "considered and why they do not fit (RDTII 2.1 guide p.85-86).",
     ["prohibited means of payment", "settlement period", "merchant category",
      "surcharge", "prepaid instrument", "electronic payment shall not"]),

    ("12.5", 12, "Low de minimis",
     "Is the de minimis threshold for duty- or tax-free imports low?",
     "The evidence is the DE MINIMIS value below which an imported consignment is free of duty "
     "or tax at the border — a number with a currency, usually in a customs act, tariff "
     "schedule or ministerial notification. Convert at the IMF US$ rate (coder FAQ: as of 31 "
     "August). Score 1 if there is no de minimis rule; 0.5 if it is below US$200; 0 if it is "
     "US$200 or more. This is one of the few indicators where the citation is a figure rather "
     "than an obligation (RDTII 2.1 guide p.86; coder FAQ p.15).",
     ["de minimis", "consignments not exceeding", "duty-free threshold",
      "value of the goods does not exceed", "low-value consignment", "exempt from customs duty"]),

    ("12.6", 12, "Customs duties on electronic transmissions",
     "Does the economy impose customs duties on electronic transmissions?",
     "The operative rule IMPOSES, or creates the legal MECHANISM to impose, a customs duty or "
     "border charge on ELECTRONIC TRANSMISSIONS — imports/exports of software, electronic "
     "data, multimedia delivered electronically. Score 1 where duties are actually levied; "
     "0.5 where a legal mechanism exists even at a 0% rate (e.g. intangible goods classified "
     "under their own HS heading, such as 99.01); 0 where none (RDTII 2.1 guide p.86). "
     "Distinguish carefully from a domestic VAT/GST or digital services tax on the same supply: "
     "an internal tax applied equally to domestic supply is NOT a customs duty on transmission, "
     "and conflating them is the most common error on this indicator.",
     ["customs duty on electronic transmission", "digital goods imported", "tariff on software",
      "moratorium on customs duties", "electronically transmitted goods",
      "import duty on digital products"]),

    ("12.7", 12, "Domain name requirements",
     "Are there presence or local-domain requirements for commercial domain names?",
     "The operative rule sets requirements on COMMERCIAL domain names (all commercial ccTLDs "
     "and sub-domains; not .gov/.mil/.edu/.org). Score 1: a physical presence (residence, "
     "registered office or branch) is required to register or use the local ccTLD, or "
     "businesses must use a local domain name to engage in e-commerce or operate a licensed "
     "site (e.g. online newspapers and social networks must use '.vn'). Score 0.5: a foreign "
     "registrant must appoint a local representative or administrative contact. Real-name "
     "verification or suspension powers alone are not what this indicator scores (RDTII 2.1 "
     "guide p.87).",
     ["domain name registration", "registrant shall be", "administrative contact",
      "shall have a presence in", "ccTLD", "representative in the country",
      "shall use the national domain name", "domain name management"]),

    ("12.8", 12, "Local presence requirements for online service providers",
     "Must a foreign online service provider appoint a local representative, agent or contact point to serve the market remotely?",
     "The operative rule requires a foreign ONLINE service provider, as a precondition for "
     "supplying services across borders (GATS Mode 1) WITHOUT establishing an office, to have "
     "a local agent, legal representative, liaison officer, contact point or post box — e.g. "
     "registered electronic system operators must appoint a domiciled liaison officer; "
     "foreign IT providers without an office must designate a local privacy agent; large "
     "foreign social networks must appoint a local representative. Any such requirement "
     "scores 1. NOT this indicator: registered-office / registered-agent rules under "
     "corporate law (they apply only once a company is established); a requirement to "
     "incorporate or open a branch (3.5) — where one law demands both an entity and a "
     "representative, classify it as 3.5. Distinguish from 9.4 (a licence) and 6.3 (local "
     "servers) (RDTII 2.1 guide p.87-88).",
     ["shall appoint a representative in", "local point of contact", "liaison officer",
      "electronic system operator shall register", "legal representative in the territory",
      "designated contact person", "local agent", "without a physical office"]),

    ("12.9", 12, "Lack of a legal framework for online consumer protection",
     "Is there a consumer-protection framework covering online transactions?",
     "The evidence is a consumer-protection law APPLICABLE to online purchases. It need not be "
     "specific to e-commerce: a general consumer act that applies across sectors extends to "
     "online transactions and is sufficient, as is a separate e-commerce regulation "
     "(distance-contract disclosure, cooling-off, unfair terms, redress). Binary: 0 if such a "
     "law applies to online purchases; 1 if there is none, or the regime covers only offline "
     "transactions. Distinguish from 7.1 (data protection, a different protective framework) "
     "(RDTII 2.1 guide p.10, p.88)."
     + _INVERTED_NOTE,
     ["consumer protection", "distance contract", "cooling-off period", "right of withdrawal",
      "unfair contract term", "pre-contractual information", "redress",
      "electronic contract", "consumer dispute resolution"]),
]

INDICATORS_WIDE: list[Indicator] = [
    Indicator(indicator_id=code, pillar=pillar, title=title, description=description,
              legal_test=legal_test, scope="national", query_terms=terms)
    for code, pillar, title, description, legal_test, terms in _SPEC
]

#: Pillars this module covers. 6 and 7 are deliberately absent — they live in `indicators.py`
#: and are measured; nothing here may shadow them.
WIDE_PILLARS = frozenset(i.pillar for i in INDICATORS_WIDE)


def get_wide(pillar: int) -> list[Indicator]:
    return [i for i in INDICATORS_WIDE if i.pillar == pillar]
