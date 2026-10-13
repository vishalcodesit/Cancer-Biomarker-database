"""Associations, evidence-support scores, gap analysis, analytics, dashboard and CSV import/export."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.common import ERROR_RESPONSES, bad_request, csv_response, not_found
from app.database import get_db
from app.scoring import methodology
from app.security import require_admin
from app.services import analytics, gaps, importer, prevalence, queries as qs, scores
from app.vocab import BIOMARKER_ROLES, BIOMARKER_TYPES, CONSISTENCY_VALUES, EVIDENCE_TYPES, SOURCE_STATUSES

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)

RoleParam = Literal[BIOMARKER_ROLES]  # type: ignore[valid-type]
TypeParam = Literal[BIOMARKER_TYPES]  # type: ignore[valid-type]
EvidenceTypeParam = Literal[EVIDENCE_TYPES]  # type: ignore[valid-type]
GapFlag = Literal[tuple(gaps.GAP_FLAGS)]  # type: ignore[valid-type]
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("/meta/vocabularies", tags=["Meta"], summary="Controlled vocabularies used by the schema")
def vocabularies():
    return {"biomarker_types": BIOMARKER_TYPES, "biomarker_roles": BIOMARKER_ROLES,
            "evidence_types": EVIDENCE_TYPES, "consistency_values": CONSISTENCY_VALUES,
            "source_statuses": SOURCE_STATUSES, "gap_flags": gaps.GAP_FLAGS,
            "import_entities": importer.ENTITY_ORDER}


@router.get("/dashboard/stats", tags=["Dashboard"], summary="Statistics computed from database records")
def dashboard(cancer_id: int | None = Query(None, ge=1), role: RoleParam | None = None,
              evidence_type: EvidenceTypeParam | None = None, db: Session = Depends(get_db)):
    return qs.dashboard_stats(db, cancer_id, role, evidence_type)


# --------------------------------------------------------------------------- associations & scores
@router.get("/associations", tags=["Evidence & scores"], summary="List biomarker-cancer associations")
def list_associations(cancer_id: int | None = None, biomarker_id: int | None = None, role: RoleParam | None = None,
                      score_status: Literal["complete", "provisional", "insufficient"] | None = None,
                      db: Session = Depends(get_db)):
    return qs.list_associations(db, cancer_id=cancer_id, biomarker_id=biomarker_id, role=role,
                                score_status=score_status)


@router.get("/associations/{association_id}", tags=["Evidence & scores"],
            summary="Association with evidence, stored score and live score explanation")
def get_association(association_id: int, db: Session = Depends(get_db)):
    a = qs.association_detail(db, association_id)
    if a is None:
        raise not_found("Association", association_id)
    live = scores.score_association(a)
    gap = prevalence.with_curation_priority(db, [gaps.analyse_association(a)])[0]
    return {**qs.association_dict(a, counts=prevalence.load_counts(db)), "score_explanation": live.to_dict(),
            "legacy_score_v1_0_0": scores.legacy_score_association(a).overall_score, "gap_analysis": gap}


@router.get("/scores/methodology", tags=["Evidence & scores"], summary="Evidence-support scoring method")
def score_methodology():
    from app.config import get_settings
    s = get_settings()
    return {**methodology(), "weights": scores.weights_from_settings(s).as_dict(),
            "publication_cap": s.score_publication_cap, "min_coverage": s.score_min_coverage,
            "breadth_discount": s.score_breadth_discount}


@router.get("/scores/comparison", tags=["Evidence & scores"],
            summary="Every association scored with the original 1.0.0 method and the current 1.1.0 method")
def score_comparison(db: Session = Depends(get_db)):
    return scores.version_comparison(db)


@router.post("/scores/recompute", tags=["Evidence & scores"], summary="Recalculate all stored scores",
             dependencies=[Depends(require_admin)])
def recompute(db: Session = Depends(get_db)):
    return {"associations_scored": scores.recompute_all(db)}


# --------------------------------------------------------------------------- gaps
@router.get("/gaps", tags=["Evidence gaps"], summary="Evidence-gap analysis")
def get_gaps(cancer_id: int | None = None, role: RoleParam | None = None, flag: GapFlag | None = None,
             min_publications: int = Query(2, ge=1, le=20), min_score: float = Query(50, ge=0, le=100),
             sort: Literal["gap_severity", "curation_priority", "gap_count", "overall_score", "tcga_frequency",
                           "n_publications", "n_sources", "name"] = "gap_severity",
             order: Literal["asc", "desc"] = "desc", db: Session = Depends(get_db)):
    all_rows = prevalence.with_curation_priority(db, gaps.gap_analysis(db, cancer_id, role, None, min_publications, min_score))
    all_rows = gaps.sort_rows(all_rows, sort, order)
    rows = [r for r in all_rows if flag in r["flags"]] if flag else all_rows
    return {"summary": gaps.gap_summary(all_rows), "flag_descriptions": gaps.GAP_FLAGS,
            "severity": gaps.GAP_SEVERITY, "role_evidence_expectations": gaps.ROLE_EVIDENCE_EXPECTATIONS,
            "n_associations": qs.count_associations(db, cancer_id, role),
            "total": len(rows), "items": rows}


# --------------------------------------------------------------------------- analytics
@router.get("/analytics/catalogue", tags=["Analytics"], summary="Documented SQL query catalogue")
def analytics_catalogue():
    return analytics.catalogue()


@router.get("/analytics/{report_key}", tags=["Analytics"], summary="Run a catalogue report (parameterized SQL)")
def run_analytics(report_key: str, request: Request, db: Session = Depends(get_db)):
    try:
        return analytics.run_report(db, report_key, dict(request.query_params))
    except KeyError:
        raise not_found("Report", report_key)
    except analytics.ReportError as exc:
        raise bad_request(str(exc))


# --------------------------------------------------------------------------- export
@router.get("/export/{dataset}", tags=["Import & export"], summary="Export a dataset as CSV")
def export(
    dataset: Literal["biomarkers", "publications", "associations", "gaps", "analytics"],
    request: Request,
    q: str | None = None,
    cancer_id: int | None = None,
    biomarker_id: int | None = None,
    biomarker_type: TypeParam | None = None,
    role: RoleParam | None = None,
    evidence_type: EvidenceTypeParam | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    flag: GapFlag | None = None,
    report: str | None = None,
    db: Session = Depends(get_db),
):
    if dataset == "biomarkers":
        items, _ = qs.list_biomarkers(db, q=q, cancer_id=cancer_id, biomarker_type=biomarker_type, role=role,
                                      sort="name", order="asc", offset=None, limit=None)
        return csv_response(items, "biomarkers.csv")
    if dataset == "publications":
        items, _ = qs.list_publications(db, q=q, biomarker_id=biomarker_id, cancer_id=cancer_id, year_from=year_from,
                                        year_to=year_to, evidence_type=evidence_type, offset=None, limit=None)
        cols = ["publication_id", "pmid", "doi", "title", "authors", "publication_year", "journal", "source_url",
                "biomarkers", "cancers", "evidence_types", "source_names"]
        return csv_response(items, "publications.csv", cols)
    if dataset == "associations":
        rows = []
        for a in qs.list_associations(db, cancer_id=cancer_id, biomarker_id=biomarker_id, role=role, score_status=None):
            s = a["score"] or {}
            rows.append({"association_id": a["association_id"], "biomarker": a["biomarker"]["name"],
                         "cancer": a["cancer"]["name"], "role": a["biomarker_role"],
                         "source_status": a["source_status"], "n_publications": a["n_publications"],
                         "overall_score": s.get("overall_score"), "score_status": s.get("score_status"),
                         "publication_support": s.get("publication_support"),
                         "source_diversity": s.get("source_diversity"), "evidence_type": s.get("evidence_type"),
                         "consistency": s.get("consistency"), "evidence_coverage": s.get("evidence_coverage"),
                         "missing_components": s.get("missing_components"),
                         "scoring_version": s.get("scoring_version")})
        return csv_response(rows, "associations_scores.csv")
    if dataset == "gaps":
        rows = prevalence.with_curation_priority(db, gaps.gap_analysis(db, cancer_id, role, flag))
        rows = gaps.sort_rows(rows, "curation_priority", "desc")
        cols = ["association_id", "biomarker_code", "biomarker_name", "cancer_name", "biomarker_role",
                "n_evidence", "n_publications", "n_sources", "overall_score", "score_status",
                "evidence_coverage", "gap_count", "gap_severity", "tcga_frequency", "curation_priority", "flags"]
        return csv_response(rows, "evidence_gaps.csv", cols)
    # analytics
    if not report:
        raise bad_request("Parameter 'report' is required for analytics export")
    try:
        res = analytics.run_report(db, report, dict(request.query_params))
    except KeyError:
        raise not_found("Report", report)
    except analytics.ReportError as exc:
        raise bad_request(str(exc))
    return csv_response(res["rows"], f"{report}.csv", res["columns"])


# --------------------------------------------------------------------------- import
@router.post("/import/{entity}", tags=["Import & export"], summary="Validate and import a curated CSV file")
async def import_csv(entity: str, request: Request, file: UploadFile = File(...),
                     dry_run: bool = Query(True, description="Validate only; do not write"),
                     db: Session = Depends(get_db)):
    if entity not in importer.ROW_MODELS:
        raise not_found("Import entity", entity)
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise bad_request("Only .csv files are accepted")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise bad_request("File exceeds the 5 MB limit")
    try:
        df = importer.read_csv_bytes(content)
    except importer.ImportError_ as exc:
        raise bad_request(str(exc))
    if not dry_run:
        require_admin(request)
    report = importer.import_dataframe(db, entity, df, dry_run=dry_run)
    if report.ok and not dry_run and entity in ("evidence", "evidence_kegg", "associations", "publications"):
        scores.recompute_all(db)
    return report.to_dict()
