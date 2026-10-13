"""Validated CSV import pipeline.

Each entity has a Pydantic row model. A file is validated completely before any
row is written; if any row fails, nothing from that file is written (the import
is atomic per file). Records are upserted on their natural keys (gene symbol,
UniProt accession, PMID, biomarker code, ...) so re-importing never creates
duplicates.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models as m
from app.vocab import (
    ALTERATION_TYPES,
    BIOMARKER_ROLES,
    BIOMARKER_TYPES,
    CIVIC_EVIDENCE_LEVELS,
    CONSISTENCY_VALUES,
    EVIDENCE_TYPES,
    PATHWAY_DATABASES,
    PREVALENCE_BASES,
    SOURCE_STATUSES,
)

ENTITY_ORDER = (
    "cancers",
    "genes",
    "proteins",
    "pathways",
    "publications",
    "biomarkers",
    "gene_pathways",
    "biomarker_pathways",
    "associations",
    "evidence",
    "evidence_kegg",
    "variants",
    "cohorts",
    "genomic_prevalence",
    "external_benchmarks",
)


# --------------------------------------------------------------------------- helpers
def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class Row(BaseModel):
    model_config = {"str_strip_whitespace": True}

    @field_validator("*", mode="before")
    @classmethod
    def _blanks(cls, v: Any) -> Any:
        return _blank_to_none(v)


def _choice(value: str | None, allowed: tuple[str, ...], name: str, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value


# --------------------------------------------------------------------------- row models
class CancerRow(Row):
    code: str
    name: str
    tissue_origin: str | None = None
    cancer_category: str | None = None
    external_identifier: str | None = None
    mondo_id: str | None = None
    icdo_topography: str | None = None
    gdc_project_id: str | None = None
    description: str | None = None

    @field_validator("mondo_id")
    @classmethod
    def _mondo(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"MONDO:\d{7}", v):
            raise ValueError("mondo_id must look like MONDO:0007254")
        return v

    @field_validator("icdo_topography")
    @classmethod
    def _icdo(cls, v: str | None) -> str | None:
        # One or more ICD-O-3 topography codes or ranges, e.g. C50, C34.1, C18-C20
        if v is not None and not re.fullmatch(r"C\d{2}(\.\d)?(-C\d{2}(\.\d)?)?(;C\d{2}(\.\d)?(-C\d{2}(\.\d)?)?)*", v):
            raise ValueError("icdo_topography must be ICD-O-3 topography code(s) such as C50 or C18-C20")
        return v

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", v):
            raise ValueError("code must be lowercase letters, digits or underscore")
        return v


class GeneRow(Row):
    official_symbol: str
    full_name: str | None = None
    organism: str = "Homo sapiens"
    ncbi_gene_id: int | None = None
    hgnc_id: str | None = None
    description: str | None = None

    @field_validator("hgnc_id")
    @classmethod
    def _hgnc(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"HGNC:\d+", v):
            raise ValueError("hgnc_id must look like HGNC:1100")
        return v

    @field_validator("official_symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-\.]*", v):
            raise ValueError("official_symbol must be an uppercase HGNC-style symbol")
        return v

    @field_validator("ncbi_gene_id")
    @classmethod
    def _gid(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("ncbi_gene_id must be positive")
        return v


class ProteinRow(Row):
    accession: str
    name: str
    function: str | None = None
    organism: str = "Homo sapiens"
    gene_symbol: str | None = None

    @field_validator("accession")
    @classmethod
    def _acc(cls, v: str) -> str:
        # UniProt accession format (https://www.uniprot.org/help/accession_numbers)
        if not re.fullmatch(r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}", v):
            raise ValueError("accession is not a valid UniProt accession")
        return v


class PathwayRow(Row):
    pathway_database: str
    external_identifier: str
    pathway_name: str
    description: str | None = None
    source_url: str | None = None

    @field_validator("pathway_database")
    @classmethod
    def _db(cls, v: str) -> str:
        return _choice(v, PATHWAY_DATABASES, "pathway_database")


class PublicationRow(Row):
    pmid: str | None = None
    doi: str | None = None
    title: str
    authors: str | None = None
    publication_year: int | None = None
    journal: str | None = None
    source_url: str | None = None

    @field_validator("pmid", mode="before")
    @classmethod
    def _pmid(cls, v: Any) -> Any:
        v = _blank_to_none(v)
        if v is None:
            return None
        v = str(v).split(".")[0]
        if not v.isdigit():
            raise ValueError("pmid must be numeric")
        return v

    @field_validator("publication_year")
    @classmethod
    def _year(cls, v: int | None) -> int | None:
        if v is not None and not (1900 <= v <= date.today().year + 1):
            raise ValueError("publication_year out of range")
        return v

    @model_validator(mode="after")
    def _identifier(self) -> "PublicationRow":
        if not self.pmid and not self.doi:
            raise ValueError("either pmid or doi is required")
        if not self.source_url and self.pmid:
            self.source_url = f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        return self


class BiomarkerRow(Row):
    biomarker_code: str
    name: str
    biomarker_type: str
    gene_symbols: str | None = None
    prevalence_basis: str | None = None
    description: str | None = None
    biological_function: str | None = None
    external_identifier: str | None = None

    @field_validator("biomarker_type")
    @classmethod
    def _type(cls, v: str) -> str:
        return _choice(v, BIOMARKER_TYPES, "biomarker_type")

    @field_validator("prevalence_basis")
    @classmethod
    def _basis(cls, v: str | None) -> str | None:
        return _choice(v, PREVALENCE_BASES, "prevalence_basis", required=False)

    @model_validator(mode="after")
    def _basis_needs_one_gene(self) -> "BiomarkerRow":
        # A gene-level frequency only describes a biomarker that is defined by exactly one gene.
        if self.prevalence_basis and len(self.symbols) != 1:
            raise ValueError("prevalence_basis can only be set for a biomarker with exactly one gene symbol")
        return self

    @property
    def symbols(self) -> list[str]:
        return [s.strip() for s in (self.gene_symbols or "").split(";") if s.strip()]


class BiomarkerPathwayRow(Row):
    biomarker_code: str
    pathway_database: str
    external_identifier: str
    annotation_source: str | None = None


class GenePathwayRow(Row):
    gene_symbol: str
    pathway_database: str
    external_identifier: str
    annotation_source: str | None = None


class AssociationRow(Row):
    biomarker_code: str
    cancer_code: str
    biomarker_role: str
    source_status: str = "curated_literature"
    association_description: str | None = None

    @field_validator("biomarker_role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _choice(v, BIOMARKER_ROLES, "biomarker_role")

    @field_validator("source_status")
    @classmethod
    def _status(cls, v: str) -> str:
        return _choice(v, SOURCE_STATUSES, "source_status")


class EvidenceRow(Row):
    biomarker_code: str
    cancer_code: str
    biomarker_role: str
    pmid: str | None = None
    evidence_type: str | None = None
    source_name: str
    source_record_id: str | None = None
    consistency_annotation: str | None = None
    retrieved_at: datetime | None = None
    source_url: str | None = None
    evidence_summary: str | None = None

    @field_validator("pmid", mode="before")
    @classmethod
    def _pmid(cls, v: Any) -> Any:
        v = _blank_to_none(v)
        return None if v is None else str(v).split(".")[0]

    @field_validator("evidence_type")
    @classmethod
    def _etype(cls, v: str | None) -> str | None:
        return _choice(v, EVIDENCE_TYPES, "evidence_type", required=False)

    @field_validator("consistency_annotation")
    @classmethod
    def _cons(cls, v: str | None) -> str | None:
        return _choice(v, CONSISTENCY_VALUES, "consistency_annotation", required=False)

    @field_validator("retrieved_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def _pubmed_defaults(self) -> "EvidenceRow":
        # For PubMed-derived evidence the PMID is the source record identifier.
        if self.pmid and self.source_name == "PubMed":
            self.source_record_id = self.source_record_id or self.pmid
            self.source_url = self.source_url or f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        return self


class VariantRow(Row):
    variant_identifier: str
    gene_symbol: str
    protein_change: str | None = None
    dbsnp_id: str | None = None
    genome_assembly: str | None = None
    chromosome: str | None = None
    position: int | None = None
    reference_allele: str | None = None
    alternate_allele: str | None = None
    clinical_or_research_annotation: str | None = None
    source_identifier: str | None = None
    associations: str | None = None

    @field_validator("chromosome", mode="before")
    @classmethod
    def _chrom(cls, v: Any) -> Any:
        v = _blank_to_none(v)
        if v is None:
            return None
        v = str(v).split(".")[0].removeprefix("chr")
        if v not in {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}:
            raise ValueError("chromosome must be 1-22, X, Y or MT")
        return v

    @field_validator("dbsnp_id")
    @classmethod
    def _rs(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"rs\d+", v):
            raise ValueError("dbsnp_id must look like rs12345")
        return v

    @field_validator("reference_allele", "alternate_allele")
    @classmethod
    def _allele(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[ACGTN\-]+", v):
            raise ValueError("alleles must contain only A, C, G, T, N or -")
        return v

    @field_validator("position")
    @classmethod
    def _pos(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("position must be positive")
        return v

    @property
    def association_keys(self) -> list[tuple[str, str, str]]:
        keys = []
        for part in (self.associations or "").split(";"):
            bits = [b.strip() for b in part.split("|")]
            if len(bits) == 3 and all(bits):
                keys.append((bits[0], bits[1], bits[2]))
        return keys


class CohortRow(Row):
    study_id: str
    name: str
    cancer_code: str
    source_name: str = "cBioPortal"
    n_samples_mutation: int | None = None
    n_samples_cna: int | None = None
    citation: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None

    @field_validator("n_samples_mutation", "n_samples_cna")
    @classmethod
    def _nonneg(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("sample counts must be non-negative")
        return v

    @field_validator("retrieved_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v


class PrevalenceRow(Row):
    gene_symbol: str
    study_id: str
    alteration_type: str
    altered_cases: int
    profiled_cases: int

    @field_validator("alteration_type")
    @classmethod
    def _atype(cls, v: str) -> str:
        return _choice(v, ALTERATION_TYPES, "alteration_type")

    @model_validator(mode="after")
    def _counts(self) -> "PrevalenceRow":
        if self.altered_cases < 0 or self.profiled_cases <= 0:
            raise ValueError("altered_cases must be >= 0 and profiled_cases > 0")
        if self.altered_cases > self.profiled_cases:
            raise ValueError("altered_cases cannot exceed profiled_cases")
        return self


class BenchmarkRow(Row):
    biomarker_code: str
    cancer_code: str
    biomarker_role: str
    benchmark_source: str
    best_evidence_level: str | None = None
    n_items: int = 0
    n_shared_publications: int = 0
    matched_on: str | None = None
    retrieved_at: datetime | None = None

    @field_validator("best_evidence_level")
    @classmethod
    def _level(cls, v: str | None) -> str | None:
        return _choice(v, CIVIC_EVIDENCE_LEVELS, "best_evidence_level", required=False)

    @field_validator("retrieved_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v

    @model_validator(mode="after")
    def _consistent(self) -> "BenchmarkRow":
        if self.n_items < 0 or self.n_shared_publications < 0:
            raise ValueError("counts must be non-negative")
        if (self.n_items == 0) != (self.best_evidence_level is None):
            raise ValueError("best_evidence_level must be present exactly when n_items > 0")
        return self


ROW_MODELS: dict[str, type[Row]] = {
    "cancers": CancerRow,
    "genes": GeneRow,
    "proteins": ProteinRow,
    "pathways": PathwayRow,
    "publications": PublicationRow,
    "biomarkers": BiomarkerRow,
    "gene_pathways": GenePathwayRow,
    "biomarker_pathways": BiomarkerPathwayRow,
    "associations": AssociationRow,
    "evidence": EvidenceRow,
    "evidence_kegg": EvidenceRow,
    "variants": VariantRow,
    "cohorts": CohortRow,
    "genomic_prevalence": PrevalenceRow,
    "external_benchmarks": BenchmarkRow,
}

NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "cancers": ("code",),
    "genes": ("official_symbol",),
    "proteins": ("accession",),
    "pathways": ("pathway_database", "external_identifier"),
    "publications": ("pmid", "doi"),
    "biomarkers": ("biomarker_code",),
    "gene_pathways": ("gene_symbol", "pathway_database", "external_identifier"),
    "biomarker_pathways": ("biomarker_code", "pathway_database", "external_identifier"),
    "associations": ("biomarker_code", "cancer_code", "biomarker_role"),
    "evidence": ("biomarker_code", "cancer_code", "biomarker_role", "pmid", "source_name", "source_record_id"),
    "evidence_kegg": ("biomarker_code", "cancer_code", "biomarker_role", "pmid", "source_name", "source_record_id"),
    "variants": ("variant_identifier",),
    "cohorts": ("study_id",),
    "genomic_prevalence": ("gene_symbol", "study_id", "alteration_type"),
    "external_benchmarks": ("biomarker_code", "cancer_code", "biomarker_role", "benchmark_source"),
}


# --------------------------------------------------------------------------- report
@dataclass
class ImportReport:
    entity: str
    rows_total: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, row: int, message: str, field_name: str | None = None) -> None:
        self.errors.append({"row": row, "field": field_name, "message": message})

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "rows_total": self.rows_total,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "ok": self.ok,
        }


class ImportError_(Exception):
    pass


# --------------------------------------------------------------------------- main entry points
def read_csv_bytes(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:  # malformed CSV
        raise ImportError_(f"Could not parse CSV: {exc}") from exc


def import_dataframe(db: Session, entity: str, df: pd.DataFrame, dry_run: bool = False) -> ImportReport:
    if entity not in ROW_MODELS:
        raise ImportError_(f"Unknown entity '{entity}'. Expected one of: {', '.join(ROW_MODELS)}")
    report = ImportReport(entity=entity, rows_total=len(df), dry_run=dry_run)
    model = ROW_MODELS[entity]

    required = [n for n, f in model.model_fields.items() if f.is_required()]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        report.error(0, f"Missing required column(s): {', '.join(missing_cols)}")
        return report

    rows: list[tuple[int, Row]] = []
    seen: dict[tuple, int] = {}
    for idx, record in enumerate(df.to_dict(orient="records"), start=2):  # row 1 = header
        try:
            row = model.model_validate(record)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or None
                report.error(idx, err["msg"].removeprefix("Value error, "), loc)
            continue
        key = tuple(getattr(row, k, None) for k in NATURAL_KEYS[entity])
        if entity == "publications":
            key = (row.pmid,) if row.pmid else ("doi", row.doi)
        if key in seen:
            report.error(idx, f"Duplicate record in file (same natural key as row {seen[key]})")
            continue
        seen[key] = idx
        rows.append((idx, row))

    if report.errors:
        return report

    handler = _HANDLERS[entity]
    try:
        for idx, row in rows:
            try:
                handler(db, row, report)
                db.flush()
            except ImportError_ as exc:
                report.error(idx, str(exc))
            except IntegrityError as exc:
                report.error(idx, f"Integrity constraint violated: {exc.orig}")
                break
        if report.errors or dry_run:
            db.rollback()
            if report.errors:
                report.inserted = report.updated = report.unchanged = 0
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return report


def import_directory(db: Session, directory: Path) -> list[ImportReport]:
    reports = []
    for entity in ENTITY_ORDER:
        path = directory / f"{entity}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        report = import_dataframe(db, entity, df)
        reports.append(report)
        if not report.ok:
            break
    return reports


# --------------------------------------------------------------------------- upsert handlers
def _apply(obj: Any, values: dict, report: ImportReport, is_new: bool) -> None:
    changed = False
    for k, v in values.items():
        if getattr(obj, k) != v:
            setattr(obj, k, v)
            changed = True
    if is_new:
        report.inserted += 1
    elif changed:
        report.updated += 1
    else:
        report.unchanged += 1


def _get_or_new(db: Session, model: type, **filters: Any) -> tuple[Any, bool]:
    obj = db.scalars(select(model).filter_by(**filters)).first()
    if obj is None:
        obj = model(**filters)
        db.add(obj)
        return obj, True
    return obj, False


def _gene(db: Session, symbol: str) -> m.Gene:
    gene = db.scalars(select(m.Gene).filter_by(official_symbol=symbol)).first()
    if gene is None:
        raise ImportError_(f"Unknown gene symbol '{symbol}' (import genes first)")
    return gene


def _association(db: Session, code: str, cancer_code: str, role: str) -> m.BiomarkerCancer:
    assoc = db.scalars(
        select(m.BiomarkerCancer)
        .join(m.Biomarker)
        .join(m.Cancer)
        .where(m.Biomarker.biomarker_code == code, m.Cancer.code == cancer_code, m.BiomarkerCancer.biomarker_role == role)
    ).first()
    if assoc is None:
        raise ImportError_(f"Unknown association {code} / {cancer_code} / {role} (import associations first)")
    return assoc


def _h_cancer(db: Session, r: CancerRow, rep: ImportReport) -> None:
    obj, new = _get_or_new(db, m.Cancer, code=r.code)
    _apply(obj, r.model_dump(exclude={"code"}), rep, new)


def _h_gene(db: Session, r: GeneRow, rep: ImportReport) -> None:
    if r.ncbi_gene_id is not None:
        clash = db.scalars(select(m.Gene).filter_by(ncbi_gene_id=r.ncbi_gene_id)).first()
        if clash and clash.official_symbol != r.official_symbol:
            raise ImportError_(f"ncbi_gene_id {r.ncbi_gene_id} already belongs to {clash.official_symbol}")
    obj, new = _get_or_new(db, m.Gene, official_symbol=r.official_symbol)
    _apply(obj, r.model_dump(exclude={"official_symbol"}), rep, new)


def _h_protein(db: Session, r: ProteinRow, rep: ImportReport) -> None:
    obj, new = _get_or_new(db, m.Protein, accession=r.accession)
    _apply(obj, r.model_dump(exclude={"accession", "gene_symbol"}), rep, new)
    if r.gene_symbol:
        gene = _gene(db, r.gene_symbol)
        if gene not in obj.genes:
            obj.genes.append(gene)


def _h_pathway(db: Session, r: PathwayRow, rep: ImportReport) -> None:
    obj, new = _get_or_new(db, m.Pathway, pathway_database=r.pathway_database, external_identifier=r.external_identifier)
    _apply(obj, r.model_dump(exclude={"pathway_database", "external_identifier"}), rep, new)


def _h_publication(db: Session, r: PublicationRow, rep: ImportReport) -> None:
    obj = None
    if r.pmid:
        obj = db.scalars(select(m.Publication).filter_by(pmid=r.pmid)).first()
    if obj is None and r.doi:
        obj = db.scalars(select(m.Publication).filter_by(doi=r.doi)).first()
    new = obj is None
    if new:
        obj = m.Publication(title=r.title)
        db.add(obj)
    _apply(obj, r.model_dump(), rep, new)


def _h_biomarker(db: Session, r: BiomarkerRow, rep: ImportReport) -> None:
    obj, new = _get_or_new(db, m.Biomarker, biomarker_code=r.biomarker_code)
    _apply(obj, r.model_dump(exclude={"biomarker_code", "gene_symbols"}), rep, new)
    genes = [_gene(db, s) for s in r.symbols]
    if set(obj.genes) != set(genes):
        obj.genes = genes


def _h_biomarker_pathway(db: Session, r: BiomarkerPathwayRow, rep: ImportReport) -> None:
    bm = db.scalars(select(m.Biomarker).filter_by(biomarker_code=r.biomarker_code)).first()
    pw = db.scalars(
        select(m.Pathway).filter_by(pathway_database=r.pathway_database, external_identifier=r.external_identifier)
    ).first()
    if bm is None or pw is None:
        raise ImportError_(f"Unknown biomarker or pathway: {r.biomarker_code} / {r.external_identifier}")
    db.flush()
    link = db.get(m.BiomarkerPathway, (bm.biomarker_id, pw.pathway_id))
    new = link is None
    if new:
        link = m.BiomarkerPathway(biomarker_id=bm.biomarker_id, pathway_id=pw.pathway_id)
        db.add(link)
    _apply(link, {"annotation_source": r.annotation_source}, rep, new)


def _h_gene_pathway(db: Session, r: GenePathwayRow, rep: ImportReport) -> None:
    gene = _gene(db, r.gene_symbol)
    pw = db.scalars(
        select(m.Pathway).filter_by(pathway_database=r.pathway_database, external_identifier=r.external_identifier)
    ).first()
    if pw is None:
        raise ImportError_(f"Unknown pathway {r.pathway_database}:{r.external_identifier}")
    db.flush()
    link = db.get(m.GenePathway, (gene.gene_id, pw.pathway_id))
    new = link is None
    if new:
        link = m.GenePathway(gene_id=gene.gene_id, pathway_id=pw.pathway_id)
        db.add(link)
    _apply(link, {"annotation_source": r.annotation_source}, rep, new)


def _h_association(db: Session, r: AssociationRow, rep: ImportReport) -> None:
    bm = db.scalars(select(m.Biomarker).filter_by(biomarker_code=r.biomarker_code)).first()
    ca = db.scalars(select(m.Cancer).filter_by(code=r.cancer_code)).first()
    if bm is None:
        raise ImportError_(f"Unknown biomarker_code '{r.biomarker_code}'")
    if ca is None:
        raise ImportError_(f"Unknown cancer_code '{r.cancer_code}'")
    db.flush()
    obj, new = _get_or_new(
        db, m.BiomarkerCancer, biomarker_id=bm.biomarker_id, cancer_id=ca.cancer_id, biomarker_role=r.biomarker_role
    )
    _apply(obj, {"source_status": r.source_status, "association_description": r.association_description}, rep, new)


def _h_evidence(db: Session, r: EvidenceRow, rep: ImportReport) -> None:
    assoc = _association(db, r.biomarker_code, r.cancer_code, r.biomarker_role)
    pub = None
    if r.pmid:
        pub = db.scalars(select(m.Publication).filter_by(pmid=r.pmid)).first()
        if pub is None:
            raise ImportError_(f"Unknown PMID {r.pmid} (import publications first)")
    db.flush()
    q = select(m.Evidence).filter_by(association_id=assoc.association_id, source_name=r.source_name)
    q = q.filter_by(publication_id=pub.publication_id) if pub else q.filter(
        m.Evidence.publication_id.is_(None), m.Evidence.source_record_id == r.source_record_id
    )
    obj = db.scalars(q).first()
    new = obj is None
    if new:
        obj = m.Evidence(association_id=assoc.association_id, source_name=r.source_name)
        db.add(obj)
    values = r.model_dump(include={
        "evidence_type", "source_record_id", "consistency_annotation", "retrieved_at", "source_url", "evidence_summary"
    })
    values["publication_id"] = pub.publication_id if pub else None
    # Compare datetimes timezone-insensitively (SQLite drops tzinfo).
    if not new and obj.retrieved_at and values["retrieved_at"] and \
            obj.retrieved_at.replace(tzinfo=None) == values["retrieved_at"].replace(tzinfo=None):
        values["retrieved_at"] = obj.retrieved_at
    _apply(obj, values, rep, new)


def _h_variant(db: Session, r: VariantRow, rep: ImportReport) -> None:
    gene = _gene(db, r.gene_symbol)
    db.flush()
    obj, new = _get_or_new(db, m.Variant, variant_identifier=r.variant_identifier)
    values = r.model_dump(exclude={"variant_identifier", "gene_symbol", "associations"})
    values["gene_id"] = gene.gene_id
    _apply(obj, values, rep, new)
    assocs = [_association(db, *k) for k in r.association_keys]
    if set(obj.associations) != set(assocs):
        obj.associations = assocs


def _h_cohort(db: Session, r: CohortRow, rep: ImportReport) -> None:
    ca = db.scalars(select(m.Cancer).filter_by(code=r.cancer_code)).first()
    if ca is None:
        raise ImportError_(f"Unknown cancer_code '{r.cancer_code}'")
    db.flush()
    obj, new = _get_or_new(db, m.Cohort, study_id=r.study_id)
    values = r.model_dump(exclude={"study_id", "cancer_code"})
    values["cancer_id"] = ca.cancer_id
    if not new and obj.retrieved_at and values["retrieved_at"] and \
            obj.retrieved_at.replace(tzinfo=None) == values["retrieved_at"].replace(tzinfo=None):
        values["retrieved_at"] = obj.retrieved_at
    _apply(obj, values, rep, new)


def _h_prevalence(db: Session, r: PrevalenceRow, rep: ImportReport) -> None:
    gene = _gene(db, r.gene_symbol)
    cohort = db.scalars(select(m.Cohort).filter_by(study_id=r.study_id)).first()
    if cohort is None:
        raise ImportError_(f"Unknown study_id '{r.study_id}' (import cohorts first)")
    db.flush()
    obj, new = _get_or_new(db, m.GenomicPrevalence, gene_id=gene.gene_id, cohort_id=cohort.cohort_id,
                           alteration_type=r.alteration_type)
    _apply(obj, {"altered_cases": r.altered_cases, "profiled_cases": r.profiled_cases}, rep, new)


def _h_benchmark(db: Session, r: BenchmarkRow, rep: ImportReport) -> None:
    assoc = _association(db, r.biomarker_code, r.cancer_code, r.biomarker_role)
    db.flush()
    obj, new = _get_or_new(db, m.ExternalBenchmark, association_id=assoc.association_id,
                           benchmark_source=r.benchmark_source)
    values = r.model_dump(include={"best_evidence_level", "n_items", "n_shared_publications", "matched_on",
                                   "retrieved_at"})
    if not new and obj.retrieved_at and values["retrieved_at"] and \
            obj.retrieved_at.replace(tzinfo=None) == values["retrieved_at"].replace(tzinfo=None):
        values["retrieved_at"] = obj.retrieved_at
    _apply(obj, values, rep, new)


_HANDLERS = {
    "cancers": _h_cancer,
    "genes": _h_gene,
    "proteins": _h_protein,
    "pathways": _h_pathway,
    "publications": _h_publication,
    "biomarkers": _h_biomarker,
    "gene_pathways": _h_gene_pathway,
    "biomarker_pathways": _h_biomarker_pathway,
    "associations": _h_association,
    "evidence": _h_evidence,
    "evidence_kegg": _h_evidence,
    "variants": _h_variant,
    "cohorts": _h_cohort,
    "genomic_prevalence": _h_prevalence,
    "external_benchmarks": _h_benchmark,
}
