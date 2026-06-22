"""RDTII 2.1 scoring rubric — Zone 3 (the OPTIONAL scoring layer).

The judges' "Scoring criteria" sheet assigns each MAPPED measure a Raw Score on a
0 → 1 scale where the number is a COMPLIANCE-COST / digital-trade-restrictiveness
grade, NOT a "did we find something" flag:

    0   = simplified / low compliance cost (no restrictive measure, OR a desirable
          horizontal framework that REDUCES trade friction — see the inverted indicators)
    0.5 = a measure that bites only a specific sector / specific data / non-personal data
    1   = heavily regulated / high compliance cost (a broad, all-sector or personal-data
          measure, or MORE THAN ONE sectoral measure in the 0.5 band)

⚠ TWO INVERTED INDICATORS. For 7.1 (comprehensive data-protection framework) and 7.2
(dedicated cybersecurity framework) the polarity FLIPS: the indicator titles in the
methodology are phrased as a *LACK* ("Lack of comprehensive legal framework…"), so
FINDING the good horizontal framework scores 0, a sectoral-only framework scores 0.5,
and NO framework scores 1. This is the single most common scoring error. The answer key
confirms it: SG/MY/AU all score 0 on 7.1 (each has a horizontal framework); SG & MY score
0 on 7.2 (Cybersecurity Act 2018 / Cyber Security Act 2024) while AU scores 0.5 (no single
dedicated horizontal cybersecurity law — guided by a strategy + SOCI Act + Privacy Act).

The text of every `criteria` tier below is quoted verbatim from the official
"Scoring criteria" sheet (Scoring_information_2.xlsx), mapped from Methodology
6.1..6.4 / 7.1..7.5 to our P6-I / P7-I ids. The per-economy answer key (the Database
country sheets) was used to validate each tier against worked examples.

Exceptions carried from the FAQ (Scoring_information_1.pdf):
  • Localisation indicators (6.x) and retention (7.3): do NOT score a measure that applies
    only to GOVERNMENT data.
  • 6.3 infrastructure: covers ONLY a requirement to ESTABLISH a server/data-centre locally
    for data-transfer purposes; ongoing duties on an already-established data centre, and
    pure licensing/registration, fall elsewhere (→ score 0 here, note it).
  • 7.1 "comprehensive" = applied HORIZONTALLY across all sectors; sectoral-only → 0.5.
  • 7.3 "minimum period" requires a SPECIFIED duration (day/month/year); if no duration is
    stated, mark the measure but score 0.
  • 7.5 scores 1 for any measure allowing government access WITHOUT a court order.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreTier:
    score: float          # 1 / 0.5 / 0
    criteria: str         # verbatim methodology wording


@dataclass(frozen=True)
class IndicatorRubric:
    indicator_id: str
    category: str                 # methodology "Category (Policy issue)"
    tiers: tuple[ScoreTier, ...]  # ordered high→low score
    inverted: bool = False        # 7.1 / 7.2: finding the good framework scores 0
    binary: bool = False          # only 1 / 0 (no 0.5 middle tier)
    note: str = ""                # scoring exception / guidance for the grader

    def prompt_block(self) -> str:
        lines = [f"INDICATOR {self.indicator_id} — {self.category}"]
        if self.inverted:
            lines.append("POLARITY: INVERTED — a desirable horizontal framework scores 0; "
                         "absence of any framework scores 1.")
        for t in self.tiers:
            lines.append(f"  score {t.score}: {t.criteria}")
        if self.note:
            lines.append(f"  NOTE: {self.note}")
        return "\n".join(lines)


_GOV_EXC = ("Exception: do NOT score a data-localization/retention measure that applies only "
            "to GOVERNMENT data (assign 0 and note it).")

RUBRICS: dict[str, IndicatorRubric] = {
    # ───────────────── Pillar 6 — Cross-border Data Policies ─────────────────
    "P6-I1": IndicatorRubric(
        "P6-I1", "Ban and local processing requirements",
        (
            ScoreTier(1.0, "Ban and/or local processing requirement for all sectors or personal "
                           "data, OR more than one measure in the 0.5 category"),
            ScoreTier(0.5, "Ban and/or local processing requirement applied to a specific sector, "
                           "specific data, non-personal data, or transfer is prohibited to one country"),
            ScoreTier(0.0, "No requirement (transfer remains possible; a conditional regime belongs "
                           "to P6-I4, not here)"),
        ),
        note=_GOV_EXC,
    ),
    "P6-I2": IndicatorRubric(
        "P6-I2", "Local storage requirements",
        (
            ScoreTier(1.0, "Local storage requirement for all sectors or personal data, OR more "
                           "than one measure in the 0.5 category"),
            ScoreTier(0.5, "Local storage requirement applied to a specific sector, specific data "
                           "or non-personal data"),
            ScoreTier(0.0, "No requirement"),
        ),
        note=_GOV_EXC,
    ),
    "P6-I3": IndicatorRubric(
        "P6-I3", "Infrastructure requirements",
        (
            ScoreTier(1.0, "Infrastructure requirement (a mandate to establish a local server / "
                           "data centre as a condition to transfer data or supply a service)"),
            ScoreTier(0.0, "No requirement"),
        ),
        binary=True,
        note=("Covers ONLY the requirement to ESTABLISH local infrastructure for data-transfer "
              "purposes. Ongoing duties on an already-established data centre, or pure licensing/"
              "registration, are NOT scored here → 0, add the info. " + _GOV_EXC),
    ),
    "P6-I4": IndicatorRubric(
        "P6-I4", "Conditional flow regimes",
        (
            ScoreTier(1.0, "Conditions for all sectors or personal data"),
            ScoreTier(0.5, "Conditions for specific data or non-personal data"),
            ScoreTier(0.0, "No condition"),
        ),
        note=_GOV_EXC,
    ),
    # ───────────────── Pillar 7 — Domestic Data Protection & Privacy ─────────────────
    "P7-I1": IndicatorRubric(
        "P7-I1", "Lack of comprehensive legal framework for data protection",
        (
            ScoreTier(1.0, "No data protection legal framework"),
            ScoreTier(0.5, "Data protection legal framework only for specific sectors (sectoral law)"),
            ScoreTier(0.0, "Comprehensive data protection framework (applied horizontally across all sectors)"),
        ),
        inverted=True,
        note="Comprehensive = horizontal across all sectors. A sectoral-only framework is 0.5.",
    ),
    "P7-I2": IndicatorRubric(
        "P7-I2", "Lack of dedicated legal framework for cybersecurity",
        (
            ScoreTier(1.0, "No cybersecurity legal framework"),
            ScoreTier(0.5, "Non-dedicated cybersecurity legal framework, and/or a dedicated "
                           "cybersecurity law only for specific sectors (sectoral law)"),
            ScoreTier(0.0, "Dedicated cybersecurity legal framework (horizontal)"),
        ),
        inverted=True,
        note="A dedicated, horizontal cybersecurity Act scores 0. Cyber measures scattered across "
             "general/sectoral laws (no single dedicated horizontal Act) score 0.5.",
    ),
    "P7-I3": IndicatorRubric(
        "P7-I3", "Minimum period of data retention requirements",
        (
            ScoreTier(1.0, "A minimum period of data retention is required, with a SPECIFIED "
                           "duration (e.g. 'retain for 5 years', '12 months')"),
            ScoreTier(0.0, "No data retention requirement, OR a retention rule with no specified "
                           "minimum duration"),
        ),
        binary=True,
        note=("The duration must be explicitly stated to score 1. A bare 'cease retaining when no "
              "longer needed' with no fixed period scores 0. " + _GOV_EXC),
    ),
    "P7-I4": IndicatorRubric(
        "P7-I4", "DPO / DPIA requirements",
        (
            ScoreTier(1.0, "DPO and DPIA, OR a DPO requirement only, applied to all sectors"),
            ScoreTier(0.5, "DPO and DPIA, OR a DPO requirement only, applied to a specific sector"),
            ScoreTier(0.0, "No requirement (e.g. a DPIA merely contemplated/recommended, not mandated)"),
        ),
    ),
    "P7-I5": IndicatorRubric(
        "P7-I5", "Requirements to allow government access to personal data",
        (
            ScoreTier(1.0, "Any measure that allows the government to access data WITHOUT a court order"),
            ScoreTier(0.0, "No measure (or access only under a court order/warrant)"),
        ),
        binary=True,
    ),
}


def get_rubric(indicator_id: str) -> IndicatorRubric | None:
    return RUBRICS.get(indicator_id)


# the discrete scores the grader is allowed to emit (binary indicators reject 0.5)
VALID_SCORES = (0.0, 0.5, 1.0)


def coerce_score(value, rubric: IndicatorRubric | None) -> float | None:
    """Snap a model-returned score to the nearest legal tier for the indicator.
    Returns None when the value is unusable (lets the caller fall back/skip)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    allowed = (0.0, 1.0) if (rubric and rubric.binary) else VALID_SCORES
    return min(allowed, key=lambda a: abs(a - v))
