"""Evidence-gap analysis: flags associations whose recorded evidence is thin, narrow, inappropriate or inconsistent.

Version 2 (upgrade):
* Context-only records (no publication and no study design, e.g. KEGG disease-map membership) are no longer
  counted as sources and no longer raise "untyped_evidence". In version 1 every one of the 34 untyped flags was
  caused by these deliberately untyped rows, and 57 of 58 associations were flagged.
* New flag "role_evidence_mismatch": the strongest recorded study design does not match what the claimed
  role needs (for example a predictive claim supported only by laboratory or genomic-profiling studies).
* Each flag has a severity; associations get a summed gap_severity so the list can be ranked.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.services.scores import current_score, supports_role

GAP_FLAGS = {
    "no_evidence": "No supporting evidence records are stored for this association.",
    "role_evidence_mismatch": "None of the recorded study designs is of the kind the claimed role requires "
    "(see role_evidence_expectations).",
    "inconsistent": "Documented mixed or conflicting evidence exists.",
    "few_publications": "Fewer than the threshold number of distinct supporting publications.",
    "single_source": "All supporting evidence comes from a single source database.",
    "low_score": "Evidence-support score below the threshold, or no score could be computed.",
    "untyped_evidence": "At least one supporting evidence record has no specified study design.",
    "no_consistency_annotation": "No evidence record carries a curated consistency annotation.",
    "incomplete_metadata": "Evidence or publication records are missing provenance fields "
    "(source record ID, source URL, retrieval date, or publication year/journal).",
}

# Severity points per flag (proposed project parameters, used only to rank the curation work list).
GAP_SEVERITY = {
    "no_evidence": 5,
    "role_evidence_mismatch": 4,
    "inconsistent": 3,
    "few_publications": 2,
    "single_source": 2,
    "low_score": 2,
    "untyped_evidence": 1,
    "no_consistency_annotation": 1,
    "incomplete_metadata": 1,
}

_CLINICAL = ("meta_analysis", "randomized_clinical_trial", "clinical_trial", "clinical_guideline")
_PATIENT_OUTCOME = _CLINICAL + ("patient_cohort",)

# Which study designs can support each role. A heuristic adapted from the logic of evidence hierarchies
# (FDA-NIH BEST role definitions; AMP/ASCO/CAP evidence levels): it is a curation aid, not a standard.
ROLE_EVIDENCE_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    # benefit from a specific therapy needs interventional evidence or a guideline
    "predictive": _CLINICAL,
    # association with outcome needs outcome data collected in patients
    "prognostic": _PATIENT_OUTCOME,
    # detection or molecular classification can be shown by patient cohorts or tumour genomic profiling
    "diagnostic": _PATIENT_OUTCOME + ("genomic_profiling",),
    # inherited risk estimates come from family, case-control or population cohorts
    "risk": _PATIENT_OUTCOME,
    # tracking disease over time needs longitudinal patient data
    "monitoring": _PATIENT_OUTCOME,
}


def _incomplete(ev: m.Evidence) -> list[str]:
    missing = [f for f in ("source_record_id", "source_url", "retrieved_at") if getattr(ev, f) is None]
    if ev.publication is not None:
        missing += [f"publication.{f}" for f in ("publication_year", "journal") if getattr(ev.publication, f) is None]
    return missing


def analyse_association(assoc: m.BiomarkerCancer, min_publications: int = 2, min_score: float = 50.0) -> dict:
    all_evidence = assoc.evidence
    evidence = [e for e in all_evidence if supports_role(e)]
    pubs = {e.publication_id for e in evidence if e.publication_id is not None}
    sources = {e.source_name.strip().lower() for e in evidence}
    score = current_score(assoc)
    flags: list[str] = []
    details: dict[str, object] = {}

    if not evidence:
        flags.append("no_evidence")
    typed = {e.evidence_type for e in evidence if e.evidence_type}
    expected = ROLE_EVIDENCE_EXPECTATIONS.get(assoc.biomarker_role, ())
    if typed and not typed & set(expected):
        flags.append("role_evidence_mismatch")
        details["recorded_designs"] = sorted(typed)
        details["designs_expected_for_role"] = list(expected)
    if len(pubs) < min_publications:
        flags.append("few_publications")
    if len(sources) == 1:
        flags.append("single_source")
    untyped = [e.evidence_id for e in evidence if e.evidence_type is None]
    if untyped:
        flags.append("untyped_evidence")
        details["untyped_evidence_ids"] = untyped
    if evidence and all(e.consistency_annotation is None for e in evidence):
        flags.append("no_consistency_annotation")
    incomplete = {e.evidence_id: _incomplete(e) for e in all_evidence if _incomplete(e)}
    if incomplete:
        flags.append("incomplete_metadata")
        details["incomplete_fields"] = sorted({f for fs in incomplete.values() for f in fs})
    conflicting = [e for e in evidence if e.consistency_annotation in ("mixed", "conflicting")]
    if conflicting:
        flags.append("inconsistent")
        details["inconsistent_evidence"] = [
            {"evidence_id": e.evidence_id, "annotation": e.consistency_annotation, "summary": e.evidence_summary}
            for e in conflicting
        ]
    if score is None or score.overall_score is None or score.overall_score < min_score:
        flags.append("low_score")

    flags.sort(key=lambda f: -GAP_SEVERITY[f])
    return {
        "association_id": assoc.association_id,
        "biomarker_id": assoc.biomarker_id,
        "biomarker_name": assoc.biomarker.name,
        "biomarker_code": assoc.biomarker.biomarker_code,
        "cancer_id": assoc.cancer_id,
        "cancer_name": assoc.cancer.name,
        "biomarker_role": assoc.biomarker_role,
        "source_status": assoc.source_status,
        "n_evidence": len(evidence),
        "n_context_records": len(all_evidence) - len(evidence),
        "n_publications": len(pubs),
        "n_sources": len(sources),
        "overall_score": score.overall_score if score else None,
        "score_status": score.score_status if score else None,
        "evidence_coverage": score.evidence_coverage if score else None,
        "flags": flags,
        "gap_count": len(flags),
        "gap_severity": sum(GAP_SEVERITY[f] for f in flags),
        "details": details,
    }


def gap_analysis(
    db: Session,
    cancer_id: int | None = None,
    role: str | None = None,
    flag: str | None = None,
    min_publications: int = 2,
    min_score: float = 50.0,
    sort: str = "gap_severity",
    order: str = "desc",
) -> list[dict]:
    q = select(m.BiomarkerCancer).options(
        selectinload(m.BiomarkerCancer.biomarker),
        selectinload(m.BiomarkerCancer.cancer),
        selectinload(m.BiomarkerCancer.evidence).selectinload(m.Evidence.publication),
        selectinload(m.BiomarkerCancer.scores),
    )
    if cancer_id is not None:
        q = q.where(m.BiomarkerCancer.cancer_id == cancer_id)
    if role is not None:
        q = q.where(m.BiomarkerCancer.biomarker_role == role)
    rows = [analyse_association(a, min_publications, min_score) for a in db.scalars(q).all()]
    if flag:
        rows = [r for r in rows if flag in r["flags"]]
    else:
        rows = [r for r in rows if r["flags"]]
    return sort_rows(rows, sort, order)


def sort_rows(rows: list[dict], sort: str, order: str) -> list[dict]:
    reverse = order == "desc"
    if sort in ("overall_score", "curation_priority", "tcga_frequency"):
        # Unknown values always sort last regardless of direction.
        known = sorted((r for r in rows if r.get(sort) is not None), key=lambda r: r[sort], reverse=reverse)
        return known + [r for r in rows if r.get(sort) is None]
    if sort in ("n_publications", "n_sources", "gap_count", "gap_severity"):
        return sorted(rows, key=lambda r: (r[sort], r["biomarker_name"]), reverse=reverse)
    return sorted(rows, key=lambda r: (r["biomarker_name"], r["cancer_name"]), reverse=reverse)


def gap_summary(rows: list[dict]) -> dict[str, int]:
    return {f: sum(1 for r in rows if f in r["flags"]) for f in GAP_FLAGS}
