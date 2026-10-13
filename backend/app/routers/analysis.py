"""Upgrade endpoints: genomic context (TCGA), evidence-vs-prevalence map, score robustness and external validation."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common import ERROR_RESPONSES
from app.database import get_db
from app.services import prevalence, validation

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)


@router.get("/cohorts", tags=["Genomic context"], summary="TCGA cohorts used for alteration frequencies")
def list_cohorts(db: Session = Depends(get_db)):
    return prevalence.cohorts(db)


@router.get("/prevalence/discordance", tags=["Genomic context"],
            summary="Evidence-support score versus TCGA alteration frequency, per association")
def evidence_vs_prevalence(score_threshold: float = Query(75, ge=0, le=100),
                           common_threshold: float = Query(0.10, gt=0, lt=1), db: Session = Depends(get_db)):
    return prevalence.discordance(db, score_threshold, common_threshold)


@router.get("/scores/robustness", tags=["Evidence & scores"],
            summary="How much the ranking of associations depends on the score weights (Monte Carlo + ablation)")
def score_robustness(draws: int = Query(1000, ge=100, le=5000), seed: int = Query(42, ge=0),
                     top_k: int = Query(10, ge=3, le=30), db: Session = Depends(get_db)):
    return validation.robustness_report(db, draws, seed, top_k)


@router.get("/validation/civic", tags=["Evidence & scores"],
            summary="Rank concordance of the evidence-support score with CIViC expert evidence levels")
def civic_validation(permutations: int = Query(10000, ge=1000, le=50000), db: Session = Depends(get_db)):
    return validation.civic_concordance(db, permutations)
