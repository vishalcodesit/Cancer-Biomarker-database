"""Bridge between the database and the pure scoring module (app.scoring)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app import scoring_legacy
from app.config import Settings, get_settings
from app.scoring import SCORING_VERSION, EvidenceItem, ScoreResult, ScoreWeights, compute_score


def weights_from_settings(settings: Settings) -> ScoreWeights:
    return ScoreWeights(
        publication_support=settings.score_weight_publication,
        source_diversity=settings.score_weight_source_diversity,
        evidence_type=settings.score_weight_evidence_type,
        consistency=settings.score_weight_consistency,
    )


def supports_role(ev: m.Evidence) -> bool:
    """An evidence record supports the biomarker role only if it cites a publication or declares a study design.

    Records with neither (for example KEGG disease-map membership) are context: they stay in the database
    for provenance and are shown in the UI, but they are not an independent supporting source.
    """
    return ev.publication_id is not None or ev.evidence_type is not None


def evidence_items(assoc: m.BiomarkerCancer) -> list[EvidenceItem]:
    items = []
    for ev in assoc.evidence:
        pub = ev.publication
        key = None
        if pub is not None:
            # De-duplicate studies on their identifier, not on the evidence row.
            key = f"pmid:{pub.pmid}" if pub.pmid else f"doi:{(pub.doi or '').lower()}"
        items.append(EvidenceItem(key, ev.source_name, ev.evidence_type, ev.consistency_annotation, supports_role(ev)))
    return items


def score_association(assoc: m.BiomarkerCancer, settings: Settings | None = None) -> ScoreResult:
    settings = settings or get_settings()
    return compute_score(
        evidence_items(assoc),
        weights=weights_from_settings(settings),
        publication_cap=settings.score_publication_cap,
        min_coverage=settings.score_min_coverage,
        breadth_discount=settings.score_breadth_discount,
    )


def legacy_score_association(assoc: m.BiomarkerCancer, settings: Settings | None = None) -> scoring_legacy.ScoreResult:
    """The same association scored with the frozen 1.0.0 method (for the version comparison only)."""
    settings = settings or get_settings()
    items = [scoring_legacy.EvidenceItem(i.publication_key, i.source_name, i.evidence_type, i.consistency)
             for i in evidence_items(assoc)]
    w = weights_from_settings(settings)
    return scoring_legacy.compute_score(
        items,
        weights=scoring_legacy.ScoreWeights(w.publication_support, w.source_diversity, w.evidence_type, w.consistency),
        publication_cap=settings.score_publication_cap,
        min_coverage=settings.score_min_coverage,
    )


def _load_all(db: Session) -> list[m.BiomarkerCancer]:
    return db.scalars(
        select(m.BiomarkerCancer).options(
            selectinload(m.BiomarkerCancer.evidence).selectinload(m.Evidence.publication),
            selectinload(m.BiomarkerCancer.scores),
            selectinload(m.BiomarkerCancer.biomarker),
            selectinload(m.BiomarkerCancer.cancer),
        )
    ).all()


def recompute_all(db: Session, settings: Settings | None = None) -> int:
    """Recalculate and upsert EvidenceScore rows for every association (current scoring version)."""
    settings = settings or get_settings()
    assocs = _load_all(db)
    for assoc in assocs:
        res = score_association(assoc, settings)
        row = next((s for s in assoc.scores if s.scoring_version == SCORING_VERSION), None)
        if row is None:
            row = m.EvidenceScore(association_id=assoc.association_id, scoring_version=SCORING_VERSION)
            db.add(row)
        row.publication_support_score = res.publication_support
        row.source_diversity_score = res.source_diversity
        row.evidence_type_score = res.evidence_type
        row.consistency_score = res.consistency
        row.overall_score = res.overall_score
        row.evidence_coverage = res.evidence_coverage
        row.score_status = res.score_status
        row.missing_components = ",".join(res.missing_components) or None
        row.n_publications = res.n_publications
        row.n_sources = res.n_sources
        row.calculated_at = m.utcnow()
    db.commit()
    return len(assocs)


def version_comparison(db: Session, settings: Settings | None = None) -> dict:
    """Score every association with 1.0.0 and 1.1.0 and report what changed and why."""
    settings = settings or get_settings()
    rows = []
    for a in _load_all(db):
        old, new = legacy_score_association(a, settings), score_association(a, settings)
        delta = None if old.overall_score is None or new.overall_score is None else round(new.overall_score - old.overall_score, 2)
        reasons = []
        if old.n_sources != new.n_sources:
            reasons.append(f"context-only source(s) no longer counted ({old.n_sources} -> {new.n_sources} sources)")
        if old.evidence_type != new.evidence_type:
            reasons.append(f"evidence-type component {old.evidence_type} -> {new.evidence_type}")
        rows.append({
            "association_id": a.association_id, "biomarker_name": a.biomarker.name, "biomarker_code": a.biomarker.biomarker_code,
            "cancer_name": a.cancer.name, "biomarker_role": a.biomarker_role,
            "score_v1_0_0": old.overall_score, "status_v1_0_0": old.score_status,
            "score_v1_1_0": new.overall_score, "status_v1_1_0": new.score_status,
            "delta": delta, "reasons": reasons,
        })
    ranked_old = _ranks({r["association_id"]: r["score_v1_0_0"] for r in rows})
    ranked_new = _ranks({r["association_id"]: r["score_v1_1_0"] for r in rows})
    for r in rows:
        r["rank_v1_0_0"], r["rank_v1_1_0"] = ranked_old.get(r["association_id"]), ranked_new.get(r["association_id"])
    deltas = [r["delta"] for r in rows if r["delta"] is not None]
    return {
        "from_version": scoring_legacy.SCORING_VERSION, "to_version": SCORING_VERSION,
        "n_associations": len(rows), "n_changed": sum(1 for d in deltas if abs(d) >= 0.005),
        "mean_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "items": sorted(rows, key=lambda r: (r["delta"] is None, -(abs(r["delta"] or 0)))),
    }


def _ranks(scores: dict[int, float | None]) -> dict[int, int]:
    """Competition ranking (1 = highest score); unscored associations are not ranked."""
    known = sorted(((s, k) for k, s in scores.items() if s is not None), key=lambda t: -t[0])
    out, prev, rank = {}, None, 0
    for i, (s, k) in enumerate(known, start=1):
        if s != prev:
            rank, prev = i, s
        out[k] = rank
    return out


def score_to_dict(row: m.EvidenceScore | None) -> dict | None:
    if row is None:
        return None
    return {
        "publication_support": row.publication_support_score,
        "source_diversity": row.source_diversity_score,
        "evidence_type": row.evidence_type_score,
        "consistency": row.consistency_score,
        "overall_score": row.overall_score,
        "evidence_coverage": row.evidence_coverage,
        "score_status": row.score_status,
        "missing_components": row.missing_components.split(",") if row.missing_components else [],
        "n_publications": row.n_publications,
        "n_sources": row.n_sources,
        "scoring_version": row.scoring_version,
        "calculated_at": row.calculated_at,
    }


def current_score(assoc: m.BiomarkerCancer) -> m.EvidenceScore | None:
    return next((s for s in assoc.scores if s.scoring_version == SCORING_VERSION), None)
