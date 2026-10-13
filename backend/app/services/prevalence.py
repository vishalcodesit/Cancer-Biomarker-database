"""Population-level genomic context (TCGA PanCancer Atlas via cBioPortal) and prevalence-aware curation priority.

Novel element of the upgrade: literature evidence (the evidence-support score) is placed next to how common the
biomarker actually is in tumours, so the database can show
  * which common alterations are thinly supported by the curated evidence (curation priority), and
  * which rare alterations are strongly supported (established but niche targets).

All frequencies are computed from raw counts. A cancer with several cohorts (NSCLC = TCGA LUAD + TCGA LUSC) is
pooled by summing altered and profiled counts. A Wilson score interval quantifies sampling uncertainty.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.services.scores import current_score

ALTERATION_FOR_BASIS = {
    "somatic_mutation": "somatic_mutation",
    "somatic_mutation_upper_bound": "somatic_mutation",
    "amplification": "amplification",
    "deep_deletion": "deep_deletion",
}

# Curation priority = gap_severity * (1 + PREVALENCE_WEIGHT * min(frequency, PREVALENCE_CAP)).
# A gap in an alteration seen in 50% of tumours counts three times as much as the same gap with no prevalence data.
PREVALENCE_WEIGHT = 4.0
PREVALENCE_CAP = 0.5


@dataclass
class Pooled:
    altered: int = 0
    profiled: int = 0
    cohorts: list[str] = field(default_factory=list)

    @property
    def frequency(self) -> float:
        return self.altered / self.profiled if self.profiled else 0.0


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (well behaved for small k and for k = 0)."""
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def load_counts(db: Session) -> dict[tuple[int, int, str], Pooled]:
    """(gene_id, cancer_id, alteration_type) -> counts pooled over the cancer's cohorts."""
    rows = db.execute(
        select(m.GenomicPrevalence.gene_id, m.Cohort.cancer_id, m.GenomicPrevalence.alteration_type,
               m.GenomicPrevalence.altered_cases, m.GenomicPrevalence.profiled_cases, m.Cohort.study_id)
        .join(m.Cohort, m.Cohort.cohort_id == m.GenomicPrevalence.cohort_id)
    ).all()
    pooled: dict[tuple[int, int, str], Pooled] = defaultdict(Pooled)
    for gene_id, cancer_id, atype, altered, profiled, study in rows:
        p = pooled[(gene_id, cancer_id, atype)]
        p.altered += altered
        p.profiled += profiled
        p.cohorts.append(study)
    return dict(pooled)


def describe(p: Pooled) -> dict:
    lo, hi = wilson_interval(p.altered, p.profiled)
    return {"altered_cases": p.altered, "profiled_cases": p.profiled, "frequency": round(p.frequency, 4),
            "ci95_low": round(lo, 4), "ci95_high": round(hi, 4), "cohorts": sorted(p.cohorts)}


def association_prevalence(assoc: m.BiomarkerCancer, counts: dict) -> dict | None:
    """TCGA frequency of the alteration that defines this biomarker, in this association's cancer type."""
    b = assoc.biomarker
    if not b.prevalence_basis or len(b.genes) != 1:
        return None
    gene = b.genes[0]
    atype = ALTERATION_FOR_BASIS[b.prevalence_basis]
    p = counts.get((gene.gene_id, assoc.cancer_id, atype))
    if p is None:
        return None
    return {"gene_symbol": gene.official_symbol, "alteration_type": atype, "basis": b.prevalence_basis,
            "upper_bound": b.prevalence_basis.endswith("upper_bound"), **describe(p),
            "source": "cBioPortal, TCGA PanCancer Atlas"}


def curation_priority(gap_severity: int, frequency: float | None) -> float:
    return round(gap_severity * (1 + PREVALENCE_WEIGHT * min(frequency or 0.0, PREVALENCE_CAP)), 2)


def _assoc_map(db: Session, ids: list[int] | None = None) -> dict[int, m.BiomarkerCancer]:
    q = select(m.BiomarkerCancer).options(
        selectinload(m.BiomarkerCancer.biomarker).selectinload(m.Biomarker.genes),
        selectinload(m.BiomarkerCancer.cancer),
        selectinload(m.BiomarkerCancer.scores),
    )
    if ids is not None:
        q = q.where(m.BiomarkerCancer.association_id.in_(ids))
    return {a.association_id: a for a in db.scalars(q).all()}


def with_curation_priority(db: Session, rows: list[dict]) -> list[dict]:
    """Add TCGA frequency and a prevalence-weighted curation priority to gap-analysis rows."""
    counts = load_counts(db)
    assocs = _assoc_map(db, [r["association_id"] for r in rows])
    for r in rows:
        prev = association_prevalence(assocs[r["association_id"]], counts)
        r["tcga_frequency"] = prev["frequency"] if prev else None
        r["prevalence_basis"] = prev["basis"] if prev else None
        r["curation_priority"] = curation_priority(r["gap_severity"], r["tcga_frequency"])
    return rows


QUADRANTS = {
    "established": "Common in tumours and well supported by the recorded evidence.",
    "under_curated": "Common in tumours but thinly supported here: highest curation priority.",
    "niche_supported": "Rare in tumours yet well supported (for example a specific actionable variant).",
    "rare_thin": "Rare in tumours and thinly supported.",
}


def discordance(db: Session, score_threshold: float = 75.0, common_threshold: float = 0.10) -> dict:
    """Evidence-vs-prevalence map: one point per association that has both a score and a TCGA frequency."""
    counts = load_counts(db)
    items, not_applicable = [], 0
    for a in _assoc_map(db).values():
        prev = association_prevalence(a, counts)
        s = current_score(a)
        if prev is None or s is None or s.overall_score is None:
            not_applicable += 1
            continue
        common = prev["frequency"] >= common_threshold
        strong = s.overall_score >= score_threshold
        quadrant = ("established" if strong else "under_curated") if common else ("niche_supported" if strong else "rare_thin")
        items.append({"association_id": a.association_id, "biomarker_id": a.biomarker_id,
                      "biomarker_name": a.biomarker.name, "biomarker_code": a.biomarker.biomarker_code,
                      "cancer_name": a.cancer.name, "biomarker_role": a.biomarker_role,
                      "overall_score": s.overall_score, "score_status": s.score_status,
                      "quadrant": quadrant, **prev})
    items.sort(key=lambda r: (r["quadrant"], -r["frequency"]))
    return {"score_threshold": score_threshold, "common_threshold": common_threshold,
            "quadrant_descriptions": QUADRANTS,
            "quadrant_counts": {q: sum(1 for r in items if r["quadrant"] == q) for q in QUADRANTS},
            "n_plotted": len(items), "n_not_applicable": not_applicable, "items": items,
            "caveats": [
                "Frequencies are gene-level and cohort-wide (TCGA PanCancer Atlas), not subtype-specific.",
                "For variant-specific biomarkers (marked upper bound) the gene-level frequency over-estimates the "
                "frequency of the exact variant.",
                "TCGA profiled mostly untreated primary tumours, so acquired-resistance alterations are excluded.",
                "Protein, RNA, germline, fusion and signature biomarkers have no gene-level TCGA frequency here.",
            ]}


def gene_prevalence(db: Session, gene_id: int) -> list[dict]:
    """Per cancer (pooled over cohorts) and per alteration type, for the gene detail page."""
    cancers = {c.cancer_id: c.name for c in db.scalars(select(m.Cancer)).all()}
    out = []
    for (gid, cid, atype), p in load_counts(db).items():
        if gid == gene_id:
            out.append({"cancer_id": cid, "cancer_name": cancers[cid], "alteration_type": atype, **describe(p)})
    return sorted(out, key=lambda r: (r["cancer_name"], r["alteration_type"]))


def cancer_top_altered(db: Session, cancer_id: int, limit: int = 12) -> list[dict]:
    genes = {g.gene_id: g.official_symbol for g in db.scalars(select(m.Gene)).all()}
    rows = [{"gene_id": gid, "gene_symbol": genes[gid], "alteration_type": atype, **describe(p)}
            for (gid, cid, atype), p in load_counts(db).items() if cid == cancer_id and p.altered > 0]
    return sorted(rows, key=lambda r: -r["frequency"])[:limit]


def cohorts(db: Session) -> list[dict]:
    return [{"cohort_id": c.cohort_id, "study_id": c.study_id, "name": c.name, "cancer_id": c.cancer_id,
             "cancer_name": c.cancer.name, "source_name": c.source_name, "n_samples_mutation": c.n_samples_mutation,
             "n_samples_cna": c.n_samples_cna, "citation": c.citation, "source_url": c.source_url,
             "retrieved_at": c.retrieved_at}
            for c in db.scalars(select(m.Cohort).options(selectinload(m.Cohort.cancer)).order_by(m.Cohort.study_id))]
