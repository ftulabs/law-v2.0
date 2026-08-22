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

**Polarity.** Nine of these are framed as an absence — "Lack of a copyright framework",
"Lack of an independent telecom authority". For those the evidence to find is the framework
ITSELF, and finding it means the economy scores 0 (unrestricted). That is the same inversion
`rdtii/scoring_rubric.py` already documents for 7.1 and 7.2, so `INVERTED` below names them
and each `legal_test` says so in words — a grader reading only the test must not conclude that
finding a good law is a null result.

These are our reading of the Methodology's scoring criteria, not the panel's own wording, and
they have not been validated against an answer key. `docs/round2-expansion.md` records that
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
     "measure on an ICT-related good (semiconductors, network equipment, handsets, cables, "
     "displays, servers). The instrument is usually a ministerial determination or gazette "
     "notice naming the product and the duty rate, not a statute. The enabling ACT alone is "
     "not a measure — a customs or trade-remedies act that merely creates the power to "
     "investigate scores nothing; the measure is the imposition.",
     ["anti-dumping duty", "countervailing duty", "safeguard measure", "provisional duty",
      "dumping margin", "injury to the domestic industry", "trade remedies investigation",
      "definitive duty is imposed on imports of"]),

    # ───────────────────────── Pillar 2 — Public Procurement ────────────────────────────────
    ("2.1", 2, "Foreign exclusions from public procurement of ICT",
     "Does the law exclude foreign firms from public procurement of ICT goods or digital services?",
     "The operative rule EXCLUDES, or empowers exclusion of, foreign suppliers from public "
     "procurement of ICT goods or digital services — by nationality, by requiring local "
     "registration or incorporation as a condition of bidding, or by reserving contracts for "
     "domestic firms. Distinguish from 2.3 (limitations WITHIN bidding that disadvantage a "
     "foreign bidder who is nonetheless allowed to bid) and from 3.5 (commercial presence to "
     "supply the market generally, not to bid). A bare legal BASIS to exclude, never exercised, "
     "scores lower than an actual exclusion — but it is still the provision to cite.",
     ["shall be reserved for", "only local suppliers", "registered domestic supplier",
      "eligible bidders shall be", "national preference", "foreign supplier shall not",
      "incorporated in", "government procurement", "restricted tender"]),

    ("2.2", 2, "Source code, encryption and trade-secret requirements in procurement",
     "Must a supplier surrender source code, encryption keys or trade secrets to win a contract?",
     "The operative rule requires a supplier — as a condition of a public contract, "
     "certification or market access — to DISCLOSE, deposit, escrow or transfer source code, "
     "algorithms, encryption keys or trade secrets to the state or a designated body. "
     "Distinguish from 4.9 (mandatory disclosure of trade secrets generally, outside "
     "procurement) and from 11.4 (deviation from international encryption standards, which is "
     "about which cryptography is permitted rather than who must hand it over).",
     ["source code shall be", "deposit the source code", "escrow", "provide the encryption key",
      "technical documentation shall be submitted", "disclose the algorithm",
      "surrender of intellectual property", "as a condition of procurement"]),

    ("2.3", 2, "Limitations in procurement bidding",
     "Does the law disadvantage foreign bidders within the bidding process?",
     "The operative rule DISCRIMINATES against a foreign bidder who is permitted to bid: a "
     "price preference for domestic offers, a local-content or local-partner condition in the "
     "tender, bid documents in the national language only, or an in-country reference "
     "requirement. Distinguish from 2.1 (outright exclusion from bidding) and 10.3 (local "
     "content as a general trade measure rather than a tender condition).",
     ["price preference", "margin of preference", "domestic content", "local partner",
      "bid security", "prior experience in the country", "tender documents shall be in",
      "preference shall be given to"]),

    # ───────────────────────── Pillar 3 — Foreign Direct Investment ─────────────────────────
    ("3.1", 3, "Foreign equity limits in digital-trade sectors",
     "Does the law cap foreign shareholding in a sector relevant to digital trade?",
     "The operative rule CAPS foreign ownership at a stated percentage (or bans it outright) in "
     "a sector relevant to digital trade — telecommunications, data processing, cloud, "
     "e-commerce, online media, payments. The cap is a number: '49 per cent', 'majority shall "
     "be held by nationals'. Distinguish from 5.2 (the same test but SPECIFICALLY telecom) and "
     "12.01 (specifically e-commerce): cite the sector-specific indicator where one exists.",
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
     "Must directors, managers or key personnel be nationals or residents?",
     "The operative rule requires a stated proportion of the BOARD, the managing director, the "
     "legal representative or another key officer to be a national of, or resident in, the "
     "economy. Note the overlap with data-protection law: a requirement that the data "
     "protection officer be locally resident is BOTH this indicator and 7.4 — cite it once "
     "under each where the run covers both pillars.",
     ["shall be a citizen of", "ordinarily resident in", "majority of the directors shall be",
      "the managing director shall be", "resident representative", "at least one director who is a resident"]),

    ("3.4", 3, "Screening of investment and acquisitions",
     "Is foreign investment or acquisition subject to government screening or approval?",
     "The operative rule subjects a foreign investment, acquisition or change of control to "
     "PRIOR REVIEW, notification, approval or a national-interest / national-security test. The "
     "strongest evidence is a screening mechanism actually used to block a transaction. "
     "Exception per the Methodology: anti-trust review of competition effects is NOT this "
     "indicator — the test must turn on foreignness or national interest, not market share.",
     ["prior approval of the", "notify the authority before acquiring", "national interest test",
      "national security review", "foreign investment review", "significant action",
      "change of control shall be approved", "screening mechanism"]),

    ("3.5", 3, "Commercial presence requirements for cross-border services",
     "Must a supplier establish locally in order to serve the market from abroad?",
     "The operative rule requires a foreign supplier to ESTABLISH a local entity, branch, "
     "representative office or registered agent in order to supply a digital-trade service to "
     "customers in the economy. Distinguish from 12.8 (local presence for ONLINE service "
     "providers specifically) and from 6.3 (local servers or data centres — infrastructure, "
     "not corporate presence).",
     ["shall establish a branch", "local presence", "registered office in",
      "representative office", "shall be incorporated locally", "appoint a local agent",
      "may not supply services unless established"]),

    # ───────────────────────── Pillar 4 — Intellectual Property Rights ──────────────────────
    ("4.01", 4, "Patent application issues",
     "Does patent application law treat local and foreign applicants differently, or restrict what is patentable in software?",
     "The operative rule creates a DIFFERENTIAL between local and foreign applicants (a local "
     "agent mandate, a first-filing obligation, differential fees or terms) or excludes "
     "software, business methods or computer-implemented inventions from patentability. Note "
     "the code: this is 4.01, a different indicator from 4.1 (trade secrets). Written as text, "
     "never as a number — 4.01 read as a float becomes 4.1.",
     ["shall not be patentable", "computer program as such", "local patent agent",
      "first filing", "foreign applicant shall", "compulsory licence",
      "working requirement", "business method"]),

    ("4.1", 4, "Lack of an effective trade-secrets framework",
     "Is there a legal framework protecting trade secrets, with effective remedies?",
     "The evidence is a provision establishing protection for UNDISCLOSED INFORMATION / trade "
     "secrets — a definition, a cause of action for misappropriation, and remedies (injunction, "
     "damages). A general unfair-competition or contract rule with no trade-secret cause of "
     "action is a WEAKER framework, which is itself the finding. Distinguish from 4.9 (a rule "
     "COMPELLING disclosure of trade secrets, a restriction rather than an absence)."
     + _INVERTED_NOTE,
     ["trade secret", "undisclosed information", "confidential business information",
      "misappropriation", "unfair competition", "injunction and damages",
      "reasonable steps to keep it secret"]),

    ("4.2", 4, "Patent enforcement — civil and administrative procedures and remedies",
     "Are there civil and administrative procedures, remedies and provisional measures for patent infringement?",
     "The evidence is a provision giving a patent holder CIVIL or ADMINISTRATIVE recourse: "
     "infringement proceedings, injunctions, damages, and provisional measures (preliminary "
     "injunction, seizure, preservation of evidence). Absence of provisional measures is a "
     "distinct and lesser finding from absence of the whole regime. Distinguish from 4.3 "
     "(other enforcement issues — border measures, criminal sanctions, standing, delay)."
     + _INVERTED_NOTE,
     ["infringement of a patent", "preliminary injunction", "provisional measures",
      "preservation of evidence", "damages shall be awarded", "civil proceedings",
      "administrative enforcement", "seizure of infringing goods"]),

    ("4.3", 4, "Patent enforcement — other issues",
     "Are there other restrictions on patent enforcement (border measures, criminal sanctions, standing, delay)?",
     "The operative rule RESTRICTS enforcement other than through civil/administrative "
     "procedure: no border/customs measures for patents, no criminal sanction, restricted "
     "standing (e.g. only a locally registered holder may sue), mandatory pre-litigation "
     "administrative steps, or statutory delays. Distinguish from 4.2, which is the civil and "
     "administrative remedy set itself.",
     ["customs may suspend release", "border measures", "criminal liability for infringement",
      "only the registered proprietor may", "shall first apply to the administrative authority",
      "limitation period", "standing to sue"]),

    ("4.5", 4, "Lack of a copyright framework and exceptions",
     "Is there a copyright framework, and does it contain the exceptions digital trade relies on?",
     "The evidence is a copyright statute AND its EXCEPTIONS — quotation, temporary and "
     "incidental copying, private study, text-and-data mining, reverse engineering for "
     "interoperability. A framework with no digital exceptions is a partial finding, not a "
     "full one. Distinguish from 4.6 (enforcement of copyright online) and 8.1 (intermediary "
     "safe harbour for copyright infringement by users)."
     + _INVERTED_NOTE,
     ["copyright subsists in", "fair dealing", "fair use", "permitted acts", "exceptions and limitations",
      "temporary reproduction", "text and data mining", "interoperability", "moral rights"]),

    ("4.6", 4, "Online copyright enforcement — procedures, remedies and provisional measures",
     "Are there civil and administrative remedies and provisional measures for online copyright infringement?",
     "The evidence is a provision giving a rights holder recourse against ONLINE infringement: "
     "notice-and-takedown, site blocking or disabling orders, statutory damages, provisional "
     "measures, or an administrative complaint route. Distinguish from 8.1, which is the "
     "INTERMEDIARY's liability shield seen from the intermediary's side; the same section often "
     "supports both, and each cites its own limb."
     + _INVERTED_NOTE,
     ["notice and takedown", "expeditiously remove", "disable access to", "blocking order",
      "statutory damages", "online service provider shall", "injunction against an intermediary",
      "repeat infringer"]),

    ("4.9", 4, "Mandatory disclosure of trade secrets, source code or algorithms",
     "Does the law compel disclosure of source code, algorithms or other trade secrets?",
     "The operative rule COMPELS a firm to disclose, deposit or transfer source code, an "
     "algorithm, a model or another trade secret to the state, a regulator, a certification "
     "body or a local partner — as a condition of market access, licensing, certification, "
     "audit or investment. Distinguish from 2.2 (the same demand made specifically as a public "
     "PROCUREMENT condition) and from 8.4 (monitoring obligations, which compel surveillance of "
     "users rather than disclosure of technology).",
     ["source code", "algorithm shall be filed", "shall submit the technical documentation",
      "security assessment of the algorithm", "algorithm filing", "technology transfer",
      "provide access to the underlying model", "shall disclose to the competent authority"]),

    # ───────────────────────── Pillar 5 — Telecom Regulations & Competition ─────────────────
    ("5.1", 5, "Lack of passive infrastructure sharing",
     "Must operators share passive infrastructure — ducts, poles, towers, sites?",
     "The evidence is an obligation to SHARE PASSIVE infrastructure (ducts, dark fibre, poles, "
     "masts, towers, rooftops, in-building facilities), whether mandatory for all operators or "
     "imposed only on an operator with significant market power. Voluntary or commercially "
     "negotiated sharing with no obligation is the weaker case. Distinguish from 5.4 "
     "(functional/accounting separation, an organisational remedy rather than a physical one)."
     + _INVERTED_NOTE,
     ["infrastructure sharing", "passive infrastructure", "ducts and poles", "co-location",
      "site sharing", "shall grant access to", "significant market power", "tower sharing"]),

    ("5.2", 5, "Foreign equity limits in the telecom sector",
     "Does the law cap foreign shareholding in telecommunications?",
     "The operative rule CAPS foreign ownership in telecommunications at a stated percentage, "
     "or bans it. This is the telecom-specific case of 3.1: where a provision is telecom-only, "
     "cite it here; a horizontal cap that happens to cover telecom belongs to 3.1.",
     ["foreign equity in a licensee", "shall not exceed", "telecommunications licensee",
      "foreign shareholding", "majority Mongolian/national ownership", "per cent of the shares"]),

    ("5.3", 5, "Government shareholding in telecom companies",
     "Does the state hold shares in telecom operators?",
     "The evidence is a provision or instrument establishing STATE OWNERSHIP of a telecom "
     "operator — an act incorporating a state carrier, a golden-share or special-share power, "
     "or a statutory minimum government holding. A privatisation act that RETAINS a state stake "
     "is evidence; one that removes it entirely is the opposite finding.",
     ["shares held by the Government", "State-owned enterprise", "special share",
      "golden share", "the Government shall retain", "public corporation",
      "wholly owned by the State"]),

    ("5.4", 5, "Lack of functional or accounting separation",
     "Is an incumbent required to separate its wholesale and retail arms, functionally or in its accounts?",
     "The evidence is an obligation on a dominant or vertically integrated operator to keep "
     "SEPARATE ACCOUNTS, or to separate functions/structure, for its network and service arms. "
     "Accounting separation alone is a partial finding; functional or structural separation is "
     "the full one. Distinguish from 5.1 (physical sharing)."
     + _INVERTED_NOTE,
     ["accounting separation", "functional separation", "structural separation",
      "separate accounts shall be maintained", "cost accounting", "vertically integrated operator",
      "wholesale and retail"]),

    ("5.5", 5, "Licensing requirements for telecom operators",
     "Is a licence required to operate, and are its conditions strict or discriminatory?",
     "The operative rule requires a LICENCE, concession or authorisation to provide telecom or "
     "network services, and its conditions bind: nationality or local-establishment tests, "
     "discretionary refusal, capital or coverage obligations, licence fees, or a limited number "
     "of licences. A light-touch general authorisation with a notification is the weaker case. "
     "Distinguish from 9.4 (licensing of ONLINE CONTENT providers, VPN and cloud) and 12.3 "
     "(licensing of e-commerce providers).",
     ["licence to operate a telecommunications network", "shall not provide services without a licence",
      "general authorisation", "licence conditions", "spectrum licence",
      "the authority may refuse to grant", "licence fee", "class licence"]),

    ("5.7", 5, "Lack of an independent telecom authority",
     "Is there a telecom regulator independent of government and of operators?",
     "The evidence is the provision ESTABLISHING the regulator and its independence: separate "
     "legal personality, fixed-term appointments with protected removal, its own budget, "
     "decisions not subject to ministerial direction, and separation from any state-owned "
     "operator. A regulator that is a department of the ministry, or whose decisions the "
     "minister may overturn, is the weaker finding."
     + _INVERTED_NOTE,
     ["shall be an independent", "body corporate", "shall not be subject to the direction of any person",
      "term of office", "may be removed only", "the Commission shall determine",
      "regulatory authority is established", "appeal against a decision of the authority"]),

    # ───────────────────────── Pillar 8 — Internet Intermediary Liability ───────────────────
    ("8.1", 8, "Lack of safe harbour for copyright infringement",
     "Is an intermediary shielded from liability for users' copyright infringement?",
     "The evidence is a LIABILITY SHIELD for a network, hosting, caching or search provider in "
     "respect of copyright material transmitted or stored for a user — typically conditional on "
     "no actual knowledge and on expeditious removal once notified. A sectoral shield covering "
     "only some intermediaries is the partial case. Distinguish from 8.2 (a shield for OTHER "
     "unlawful content) and 4.6 (the rights holder's remedy)."
     + _INVERTED_NOTE,
     ["shall not be liable", "safe harbour", "mere conduit", "caching", "hosting",
      "actual knowledge", "expeditiously remove", "network service provider",
      "no general obligation to monitor"]),

    ("8.2", 8, "Lack of safe harbour for other illegal activities",
     "Is an intermediary shielded from liability for users' unlawful content generally?",
     "The evidence is a liability shield covering unlawful content OTHER than copyright — "
     "defamation, obscenity, hate speech, fraud, unlawful goods — for a provider that merely "
     "transmits or hosts. A shield conditioned on compliance with removal orders still counts; "
     "a regime imposing PRIMARY liability on the intermediary is the opposite finding and "
     "belongs here as the evidence for it."
     + _INVERTED_NOTE,
     ["shall not be liable for", "third-party information", "intermediary", "due diligence",
      "upon receiving actual knowledge", "conduit", "exemption from liability",
      "unlawful content"]),

    ("8.3", 8, "User identity requirements",
     "Must users identify themselves to connect to the internet or use an online service?",
     "The operative rule requires REAL IDENTITY: identity verification or registration to buy a "
     "SIM, obtain an internet connection, register a domain, open a platform account, or post "
     "content — including national-ID, biometric or mobile-number binding, and cybercafé "
     "logbook rules. Distinguish from 8.4 (monitoring of what a user does, rather than "
     "establishing who they are) and 7.5 (state ACCESS to the resulting data).",
     ["real identity", "identity verification", "registration of subscribers",
      "national identity card", "SIM card registration", "shall verify the identity of users",
      "register with their real names", "cyber cafe", "log of users"]),

    ("8.4", 8, "Monitoring requirements",
     "Must an intermediary monitor user activity or proactively remove content?",
     "The operative rule imposes a duty to MONITOR user activity, filter or proactively detect "
     "and remove content, retain traffic logs for inspection, or install technical means "
     "enabling monitoring. Distinguish from 7.3 (a retention rule stated as a minimum PERIOD), "
     "9.1 (blocking or filtering ordered against specific content) and 8.3 (identifying users).",
     ["shall monitor", "proactively detect", "automated filtering", "technical measures to prevent",
      "shall remove within", "keep records of user activity", "traffic data shall be retained",
      "report to the authority"]),

    # ───────────────────────── Pillar 9 — Content Access ────────────────────────────────────
    ("9.1", 9, "Blocking or filtering commercial web content",
     "May the state block or filter access to websites or online services?",
     "The operative rule EMPOWERS or REQUIRES blocking, filtering or disabling access to online "
     "content, a site, an app or a service — by an authority, a court, or an ISP under "
     "direction. Blocking is the stronger case, filtering the weaker. Exception per the "
     "Methodology: measures aimed at ILLEGAL content of a purely non-commercial kind (child "
     "abuse material) are not scored — the indicator concerns COMMERCIAL content.",
     ["block access to", "shall be blocked", "filtering", "disable access", "take down the website",
      "direct an internet service provider", "prohibited content", "banned application",
      "restrict access to the platform"]),

    ("9.3", 9, "Online advertising requirements",
     "Does the law restrict online advertising?",
     "The operative rule RESTRICTS online advertising: a prohibition or prior-approval regime "
     "for certain advertisements, a local-agency or local-production requirement, a data-driven "
     "or targeted-advertising ban, or a licence for advertising platforms. Exception per the "
     "Methodology: rules that merely protect consumers from misleading advertising are not "
     "scored — the restriction has to bite on the ability to advertise.",
     ["advertisement shall not", "prior approval of the advertisement", "advertising licence",
      "targeted advertising is prohibited", "advertisement published through the internet",
      "the advertiser shall be established in", "advertising of prohibited goods"]),

    ("9.4", 9, "Licensing requirements for online content providers and applications",
     "Must an online content provider, social platform, VPN or cloud service hold a licence?",
     "The operative rule requires a LICENCE, permit, registration or authorisation to operate an "
     "online content service, social media platform, news portal, streaming service, VPN, cloud "
     "or app — including registration with a local representative as a condition of operating. "
     "Distinguish from 5.5 (telecom NETWORK operator licensing), 12.3 (e-commerce providers) "
     "and 12.8 (local presence with no licence attached).",
     ["licence for online content", "internet content provider", "registration of the platform",
      "shall obtain a permit to provide", "VPN service", "cloud service licence",
      "online news service", "social media platform shall register", "electronic service provider licence"]),

    # ───────────────────────── Pillar 10 — Non-technical NTMs ───────────────────────────────
    ("10.1", 10, "Import ban on ICT goods and online services",
     "Does the law ban the import of ICT goods or the supply of an online service?",
     "The operative rule PROHIBITS importation of an ICT good (network equipment, servers, "
     "handsets, encryption devices) or bans an online service or application outright. A ban on "
     "more than one good or service is the stronger case. Distinguish from 10.2 (restrictions "
     "short of a ban: quotas, permits, conditions) and 9.1 (blocking access to content rather "
     "than prohibiting the product).",
     ["shall not be imported", "prohibited goods", "import prohibition", "banned equipment",
      "the application shall be prohibited", "prohibited list", "no person shall import"]),

    ("10.2", 10, "Other import restrictions on ICT goods and online services",
     "Are ICT imports restricted short of a ban — by quota, permit, licence or condition?",
     "The operative rule RESTRICTS but does not prohibit: an import quota, an import licence or "
     "permit, a pre-shipment inspection, a designated port of entry, a state-trading monopoly, "
     "or a certification condition on entry. Distinguish from 11.3 (product screening and "
     "testing as a conformity requirement) — where the barrier is technical conformity, cite "
     "11.3; where it is a trade formality, cite here.",
     ["import licence", "import permit", "quota", "prior authorisation to import",
      "pre-shipment inspection", "designated port", "shall be imported only through",
      "import of telecommunications equipment"]),

    ("10.3", 10, "Local content requirements",
     "Must a product or service incorporate a minimum share of local content?",
     "The operative rule requires a stated proportion of LOCAL CONTENT — domestic components, "
     "local manufacturing, local software, local hosting, local personnel or local language — "
     "as a condition of sale, licence, investment or tax treatment. Distinguish from 2.3 "
     "(local content as a TENDER condition), 6.2/6.3 (local storage or infrastructure for "
     "DATA) and 12.8 (local presence).",
     ["local content", "domestic component", "percentage of local", "manufactured locally",
      "TKDN", "shall use domestically produced", "local software", "national language"]),

    ("10.4", 10, "Export restrictions on ICT goods and online services",
     "Are exports of ICT goods or online services restricted?",
     "The operative rule RESTRICTS export: an export licence or permit, a control list covering "
     "encryption or dual-use ICT items, an export ban, or a technology-transfer restriction "
     "applied on the way out. Note the frequent overlap with data policy — an export control on "
     "cryptography is this indicator; a control on TRANSFERRING DATA abroad is pillar 6.",
     ["export licence", "export control list", "dual-use", "shall not be exported",
      "cryptographic equipment", "export permit", "technology export catalogue",
      "controlled technology"]),

    # ───────────────────────── Pillar 11 — Standards and Procedures ─────────────────────────
    ("11.1", 11, "Lack of transparent technical standards",
     "Is standard-setting open, published and open to foreign participation?",
     "The evidence is the provision governing HOW technical standards are made: whether the "
     "standards body admits foreign participants, whether drafts are published for comment, "
     "whether standards are freely available, and whether international standards are adopted "
     "as a default. A closed body, or standards available only on payment in the national "
     "language, is the finding."
     + _INVERTED_NOTE,
     ["national standards body", "public consultation on the draft standard",
      "shall be based on international standards", "notification to the WTO",
      "membership of the technical committee", "standards shall be published",
      "adoption of international standards"]),

    ("11.2", 11, "Self-certification limitations for product safety",
     "May a supplier self-declare conformity, or is third-party certification compulsory?",
     "The operative rule determines whether a Supplier's Declaration of Conformity (SDoC) is "
     "ACCEPTED for radio, EMC/EMI or electrical safety, or whether third-party certification by "
     "a designated (often local) body is compulsory. Not accepting SDoC at all is the strongest "
     "case; accepting it only from local bodies is the middle case. Distinguish from 11.3 "
     "(testing of the product itself) and 11.4 (encryption standards).",
     ["declaration of conformity", "self-declaration", "accredited certification body",
      "type approval", "conformity assessment", "recognised laboratory",
      "certificate of conformity issued by", "mutual recognition"]),

    ("11.3", 11, "Product screening and testing requirements",
     "Must ICT products be tested or screened in-country before sale?",
     "The operative rule requires TESTING, screening, registration or approval of an ICT product "
     "before it may be sold or connected — in-country testing, sample submission, a local "
     "laboratory, or a security review of equipment. Distinguish from 11.2 (who may certify) "
     "and 10.2 (import formalities); where the requirement is a SECURITY review of network "
     "equipment it may also support 7.2.",
     ["shall be tested", "testing in a laboratory located in", "type approval certificate",
      "product registration", "security review of network equipment",
      "samples shall be submitted", "shall not be connected to the network unless approved"]),

    ("11.4", 11, "Deviation from international encryption standards",
     "Does the law require national cryptography instead of international standards?",
     "The operative rule mandates NATIONAL or proprietary cryptographic algorithms, key lengths "
     "or modules in place of international standards (ISO, IEC, ITU, FIPS, AES, TDES, ECC), "
     "requires approval of cryptography before use, or requires key escrow. Distinguish from "
     "2.2 and 4.9 (compelled disclosure of keys or source code) — this indicator is about which "
     "cryptography is PERMITTED.",
     ["commercial cryptography", "approved algorithm", "national cryptographic standard",
      "key length shall not exceed", "encryption products shall be approved",
      "key escrow", "SM2 SM4", "use of encryption requires a licence"]),

    # ───────────────────────── Pillar 12 — Online Sales and Transactions ────────────────────
    ("12.01", 12, "Foreign equity limits in the e-commerce sector",
     "Does the law cap foreign shareholding in e-commerce?",
     "The operative rule CAPS or bans foreign ownership of an e-commerce business, marketplace "
     "or online retail platform. This is the e-commerce case of 3.1; note the code is 12.01, "
     "written as text — read as a number it becomes 12.1, a different indicator.",
     ["foreign equity", "e-commerce", "marketplace", "online retail", "shall not exceed",
      "negative investment list", "foreign-invested enterprise"]),

    ("12.2", 12, "Online purchase and delivery limitations",
     "Does the law limit what may be bought online, in what quantity, or how it is delivered?",
     "The operative rule LIMITS online purchase or delivery: a ban on selling certain goods "
     "online, a quantity or value ceiling per transaction or per person, a restriction on "
     "cross-border delivery, or a mandate to use a designated logistics or postal operator. "
     "Exception per the Methodology: limitations that merely mirror an offline restriction on "
     "the same product (alcohol, pharmaceuticals) are not scored here.",
     ["shall not be sold online", "maximum quantity", "per transaction limit",
      "cross-border e-commerce goods", "designated logistics", "delivery shall be through",
      "positive list of goods"]),

    ("12.3", 12, "Licensing scheme for e-commerce providers",
     "Must an e-commerce provider hold a licence or register?",
     "The operative rule requires a LICENCE, permit or registration to operate an e-commerce "
     "business or marketplace (B2B or B2C). Exception per the Methodology: an ordinary business "
     "registration that every company must complete is not an e-commerce licence. Distinguish "
     "from 9.4 (online CONTENT providers) and 12.8 (local presence).",
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
     "Does the law impose national payment standards that deviate from international ones?",
     "The operative rule mandates a NATIONAL payment scheme, switch, QR standard or message "
     "format in place of an international one, or requires routing through a domestic switch. "
     "Distinguish from 12.4.6 (a mandated INTERMEDIARY as an institution) — this limb is about "
     "the technical standard.",
     ["national payment switch", "domestic routing of transactions", "QR code standard",
      "national card scheme", "shall comply with the national standard",
      "interoperability standard issued by the central bank"]),

    ("12.4.4", 12, "Online payment — licensing requirements",
     "Must a payment service provider be licensed?",
     "The operative rule requires a LICENCE, authorisation or registration to provide payment, "
     "e-money, wallet or payment-gateway services — including a capital requirement or a local "
     "incorporation condition attached to that licence. Distinguish from 12.3 (licensing the "
     "e-commerce seller rather than the payment provider).",
     ["payment service provider licence", "e-money issuer", "payment institution",
      "shall not carry on payment services without", "minimum paid-up capital",
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
      "monopoly of the settlement system"]),

    ("12.4.7", 12, "Online payment — other restrictions",
     "Are there other restrictions on online payment not covered by the other 12.4 limbs?",
     "The residual limb. Use it only when the operative rule restricts online payment and does "
     "NOT match 12.4.1–12.4.6: for example a ban on a payment instrument (cryptocurrency, "
     "prepaid card), a mandatory settlement delay, a merchant-category prohibition, or a "
     "surcharge rule. State in the rationale which limbs were considered and why they do not fit.",
     ["prohibited means of payment", "virtual currency shall not be used",
      "settlement period", "merchant category", "surcharge", "prepaid instrument",
      "cash on delivery shall"]),

    ("12.5", 12, "Low de minimis",
     "Is the de minimis threshold for duty- or tax-free imports low?",
     "The evidence is the DE MINIMIS value below which an imported consignment is free of duty "
     "or tax — a number with a currency, usually in a customs act, tariff schedule or ministerial "
     "notification. A low or zero threshold is the restrictive finding. This is one of the few "
     "indicators where the citation is a figure rather than an obligation.",
     ["de minimis", "consignments not exceeding", "duty-free threshold",
      "value of the goods does not exceed", "low-value consignment", "exempt from customs duty"]),

    ("12.6", 12, "Customs duties on electronic transmissions",
     "Does the economy impose customs duties on electronic transmissions?",
     "The operative rule IMPOSES a customs duty, tariff or equivalent border charge on "
     "ELECTRONIC TRANSMISSIONS — downloaded software, digital media, streamed content. "
     "Distinguish carefully from a domestic VAT/GST or digital services tax on the same supply: "
     "an internal tax applied equally to domestic supply is NOT a customs duty on transmission, "
     "and conflating them is the most common error on this indicator.",
     ["customs duty on electronic transmission", "digital goods imported", "tariff on software",
      "moratorium on customs duties", "electronically transmitted goods",
      "import duty on digital products"]),

    ("12.7", 12, "Domain name requirements",
     "Are there restrictive conditions on registering or holding a domain name?",
     "The operative rule conditions registration or retention of a domain — local presence or "
     "nationality of the registrant, use of a local registrar, mandatory ccTLD use, real-name "
     "verification, or state power to suspend or revoke a name. Note the overlap: real-name "
     "verification also supports 8.3; cite the limb that matches the words used.",
     ["domain name registration", "registrant shall be", "local registrar",
      "shall have a presence in", "ccTLD", "the registry may suspend",
      "real name registration of the domain", "domain name management"]),

    ("12.8", 12, "Local presence requirements for online service providers",
     "Must an online service provider establish or appoint a representative locally?",
     "The operative rule requires an online service provider, platform or app to ESTABLISH "
     "locally or appoint a local representative, agent or point of contact — often as a "
     "condition of serving users in the economy, and often paired with a registration duty. "
     "Distinguish from 3.5 (commercial presence for cross-border services generally), 9.4 "
     "(a licence rather than mere presence) and 6.3 (local servers, not corporate presence).",
     ["shall appoint a representative in", "local point of contact", "shall establish an office",
      "electronic system operator shall register", "legal representative in the territory",
      "designated contact person", "presence requirement"]),

    ("12.9", 12, "Lack of a legal framework for online consumer protection",
     "Is there a consumer-protection framework covering online transactions?",
     "The evidence is a framework protecting consumers in ONLINE transactions: pre-contractual "
     "disclosure, a right of withdrawal or cooling-off period, rules on unfair terms, redress "
     "and dispute resolution, and enforcement by an authority. A general consumer act with "
     "nothing specific to distance or electronic contracting is the partial finding. Distinguish "
     "from 7.1 (data protection, a different protective framework)."
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
