"""FROZEN reference copy of the original scoring method, version 1.0.0 (kept unchanged for comparison).

This module is NOT used for stored scores. It exists so the application and the tests can show exactly how
version 1.1.0 differs from 1.0.0 (see /api/scores/comparison and docs/UPGRADES.md).

Original docstring:

Evidence-Aware Biomarker Confidence (evidence-support score), version 1.0.0.

Score = wP*P + wD*D + wT*T + wC*C   (default weights 0.35 / 0.25 / 0.25 / 0.15)

This is a transparent, explainable *evidence-support* (coverage) score for an
association recorded in this database. It is NOT a probability of clinical
validity and must never be presented as such.

The calculation is a pure function of its inputs (no clock, randomness or DB
access), so identical inputs + scoring version always give identical output.

Missing data policy
-------------------
* A component that cannot be observed is ``None`` (unknown), never 0.
* All four observed       -> status "complete", score = weighted sum.
* Observed weight >= min  -> status "provisional", score renormalised over the
                             observed weights:  sum(w_i x_i) / sum(w_i).
* Observed weight <  min  -> status "insufficient", overall score is None.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

SCORING_VERSION = "1.0.0"  # legacy

COMPONENTS = ("publication_support", "source_diversity", "evidence_type", "consistency")

# Evidence-type rubric (0-100). Higher = study design closer to direct human evidence.
# Proposed project parameters, documented in README section "Evidence scoring methodology".
EVIDENCE_TYPE_RUBRIC: dict[str, float] = {
    "meta_analysis": 100.0,
    "randomized_clinical_trial": 95.0,
    "clinical_guideline": 90.0,
    "clinical_trial": 85.0,
    "patient_cohort": 80.0,
    "genomic_profiling": 65.0,
    "experimental": 55.0,
    "review": 40.0,
    "computational_prediction": 20.0,
}

# Consistency annotation values -> agreement credit.
CONSISTENCY_CREDIT: dict[str, float] = {"supports": 1.0, "mixed": 0.5, "conflicting": 0.0}


@dataclass(frozen=True)
class EvidenceItem:
    """Minimal, DB-independent view of one evidence record."""

    publication_key: str | None  # PMID/DOI/publication_id; None when evidence is not a publication
    source_name: str | None
    evidence_type: str | None
    consistency: str | None


@dataclass(frozen=True)
class ScoreWeights:
    publication_support: float = 0.35
    source_diversity: float = 0.25
    evidence_type: float = 0.25
    consistency: float = 0.15

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def validate(self) -> None:
        if any(w < 0 for w in self.as_dict().values()):
            raise ValueError("Weights must be non-negative")
        if abs(sum(self.as_dict().values()) - 1.0) > 1e-6:
            raise ValueError("Weights must sum to 1.0")


@dataclass
class ScoreResult:
    publication_support: float | None
    source_diversity: float | None
    evidence_type: float | None
    consistency: float | None
    overall_score: float | None
    evidence_coverage: float  # fraction of total weight that was observed (0-1)
    score_status: str  # complete | provisional | insufficient
    missing_components: list[str] = field(default_factory=list)
    n_publications: int = 0
    n_sources: int = 0
    n_evidence: int = 0
    scoring_version: str = SCORING_VERSION
    method: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- components
def publication_support_score(n_publications: int, cap: int = 5) -> float | None:
    """P: diminishing returns on the number of DISTINCT publications.

    P = 100 * log2(1 + n) / log2(1 + cap), capped at 100.
    n=1 -> 38.7, n=2 -> 61.3, n=3 -> 77.4, n=4 -> 89.8, n>=5 -> 100 (cap=5).
    Zero recorded publications is reported as unknown: absence from this
    database is not evidence of absence in the literature.
    """
    if n_publications <= 0:
        return None
    return round(min(100.0, 100.0 * math.log2(1 + n_publications) / math.log2(1 + cap)), 2)


def source_diversity_score(n_sources: int) -> float | None:
    """D: distinct source databases, D = 100 * (1 - 0.5^n).

    1 source -> 50, 2 -> 75, 3 -> 87.5, 4 -> 93.75. Duplicate records from the
    same source count once (the caller passes the number of DISTINCT sources).
    """
    if n_sources <= 0:
        return None
    return round(100.0 * (1.0 - 0.5**n_sources), 2)


def evidence_type_score(types: Iterable[str | None]) -> float | None:
    """T: 0.7 * best rubric value + 0.3 * mean rubric value over DISTINCT typed categories.

    Rewards the strongest design present while giving some credit for breadth.
    Unknown / unlabelled evidence types are ignored; if none are labelled -> None.
    """
    values = sorted({EVIDENCE_TYPE_RUBRIC[t] for t in types if t in EVIDENCE_TYPE_RUBRIC})
    if not values:
        return None
    return round(0.7 * max(values) + 0.3 * (sum(values) / len(values)), 2)


def consistency_score(annotations: Iterable[str | None]) -> float | None:
    """C: share of curated annotations that agree. mixed = half credit.

    Only explicit curated annotations count; un-annotated evidence is ignored,
    and if there is no annotation at all the component is unknown (None).
    """
    credits = [CONSISTENCY_CREDIT[a] for a in annotations if a in CONSISTENCY_CREDIT]
    if not credits:
        return None
    return round(100.0 * sum(credits) / len(credits), 2)


# --------------------------------------------------------------------------- aggregate
def compute_score(
    items: list[EvidenceItem],
    weights: ScoreWeights | None = None,
    publication_cap: int = 5,
    min_coverage: float = 0.5,
) -> ScoreResult:
    weights = weights or ScoreWeights()
    weights.validate()

    pubs = {i.publication_key for i in items if i.publication_key}
    sources = {i.source_name.strip().lower() for i in items if i.source_name and i.source_name.strip()}

    components = {
        "publication_support": publication_support_score(len(pubs), publication_cap),
        "source_diversity": source_diversity_score(len(sources)),
        "evidence_type": evidence_type_score(i.evidence_type for i in items),
        "consistency": consistency_score(i.consistency for i in items),
    }
    w = weights.as_dict()
    observed = {k: v for k, v in components.items() if v is not None}
    missing = [k for k in COMPONENTS if components[k] is None]
    coverage = round(sum(w[k] for k in observed), 4)

    if not missing:
        status = "complete"
        overall = sum(w[k] * v for k, v in observed.items())
        method = "Weighted sum of all four observed components."
    elif coverage >= min_coverage and coverage > 0:
        status = "provisional"
        overall = sum(w[k] * v for k, v in observed.items()) / coverage
        method = (
            f"Provisional: renormalised over observed components ({coverage:.0%} of total weight). "
            f"Unknown: {', '.join(missing)}."
        )
    else:
        status = "insufficient"
        overall = None
        method = (
            f"Insufficient evidence metadata: only {coverage:.0%} of the total weight is observed "
            f"(minimum {min_coverage:.0%}). No overall score reported."
        )

    return ScoreResult(
        publication_support=components["publication_support"],
        source_diversity=components["source_diversity"],
        evidence_type=components["evidence_type"],
        consistency=components["consistency"],
        overall_score=None if overall is None else round(overall, 2),
        evidence_coverage=coverage,
        score_status=status,
        missing_components=missing,
        n_publications=len(pubs),
        n_sources=len(sources),
        n_evidence=len(items),
        method=method,
    )


def methodology() -> dict:
    """Machine-readable description of the scoring method (served at /api/scores/methodology)."""
    return {
        "scoring_version": SCORING_VERSION,
        "formula": "Score = wP*P + wD*D + wT*T + wC*C",
        "components": {
            "P": "Publication support: 100*log2(1+n)/log2(1+cap), n = DISTINCT publications, capped at 100.",
            "D": "Source diversity: 100*(1-0.5^n), n = DISTINCT source databases.",
            "T": "Evidence type: 0.7*max + 0.3*mean of rubric values of distinct labelled evidence types.",
            "C": "Consistency: 100 * (supports + 0.5*mixed) / annotated evidence. Unannotated = unknown.",
        },
        "evidence_type_rubric": EVIDENCE_TYPE_RUBRIC,
        "missing_data": (
            "Unknown components are stored as NULL. If some are unknown but the observed weight is at least "
            "the minimum coverage, a PROVISIONAL score is renormalised over observed weights. Otherwise the "
            "association is marked INSUFFICIENT and no overall score is reported."
        ),
        "disclaimer": (
            "Evidence-support score summarises the evidence recorded in this database. It is not a probability "
            "of clinical validity and does not indicate that a biomarker is clinically approved, safe or effective."
        ),
    }
