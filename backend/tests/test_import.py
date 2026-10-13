"""CSV import validation, duplicate prevention and idempotency."""
import pandas as pd
from sqlalchemy import func, select

from app import models as m
from app.services.importer import import_dataframe, import_directory
from tests.conftest import SAMPLE_DIR


def df(rows):
    return pd.DataFrame(rows).astype(str).replace("None", "")


def test_sample_dataset_counts(db):
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    assert count(m.Biomarker) == 47
    assert count(m.Cancer) == 4
    assert count(m.Publication) == 86  # 84 original + AURA3 and EMERALD added through the gap workflow (v1.1)
    assert count(m.BiomarkerCancer) == 58
    assert count(m.Gene) == 43


def test_reimport_creates_no_duplicates(empty_db):
    first = import_directory(empty_db, SAMPLE_DIR)
    second = import_directory(empty_db, SAMPLE_DIR)
    assert all(r.ok for r in first + second)
    assert sum(r.inserted for r in second) == 0
    assert empty_db.scalar(select(func.count()).select_from(m.Evidence)) == 135


def test_invalid_vocabulary_and_types_reported_with_row_numbers(empty_db):
    rep = import_dataframe(empty_db, "genes", df([
        {"official_symbol": "TP53", "ncbi_gene_id": "7157"},
        {"official_symbol": "bad symbol", "ncbi_gene_id": "x"},
    ]))
    assert not rep.ok
    rows = {e["row"] for e in rep.errors}
    assert rows == {3}  # header is row 1
    assert empty_db.scalar(select(func.count()).select_from(m.Gene)) == 0  # atomic per file


def test_duplicate_rows_within_file_rejected(empty_db):
    rep = import_dataframe(empty_db, "publications", df([
        {"pmid": "123", "title": "A"}, {"pmid": "123", "title": "A again"}]))
    assert not rep.ok and "Duplicate" in rep.errors[0]["message"]


def test_missing_required_column(empty_db):
    rep = import_dataframe(empty_db, "biomarkers", df([{"biomarker_code": "X-1", "name": "x"}]))
    assert not rep.ok and "biomarker_type" in rep.errors[0]["message"]


def test_unknown_foreign_reference_rejected(empty_db):
    rep = import_dataframe(empty_db, "associations", df([
        {"biomarker_code": "NOPE", "cancer_code": "breast", "biomarker_role": "diagnostic"}]))
    assert not rep.ok and "Unknown biomarker_code" in rep.errors[0]["message"]


def test_publication_needs_identifier_and_valid_year(empty_db):
    rep = import_dataframe(empty_db, "publications", df([
        {"pmid": "", "doi": "", "title": "no id"},
        {"pmid": "55", "title": "future", "publication_year": "3020"}]))
    msgs = " ".join(e["message"] for e in rep.errors)
    assert "pmid or doi" in msgs and "out of range" in msgs


def test_dry_run_validates_without_writing(empty_db):
    rep = import_dataframe(empty_db, "cancers", df([{"code": "liver", "name": "Liver cancer"}]), dry_run=True)
    assert rep.ok and rep.inserted == 1 and rep.dry_run
    assert empty_db.scalar(select(func.count()).select_from(m.Cancer)) == 0


def test_update_existing_record(empty_db):
    import_dataframe(empty_db, "cancers", df([{"code": "liver", "name": "Liver cancer"}]))
    rep = import_dataframe(empty_db, "cancers", df([{"code": "liver", "name": "Liver cancer", "tissue_origin": "Liver"}]))
    assert rep.updated == 1
    assert empty_db.scalars(select(m.Cancer)).one().tissue_origin == "Liver"


def test_variant_allele_and_chromosome_validation(empty_db):
    import_dataframe(empty_db, "genes", df([{"official_symbol": "KRAS"}]))
    rep = import_dataframe(empty_db, "variants", df([
        {"variant_identifier": "x", "gene_symbol": "KRAS", "chromosome": "chr99", "reference_allele": "Z"}]))
    fields = {e["field"] for e in rep.errors}
    assert {"chromosome", "reference_allele"} <= fields


# --------------------------------------------------------------------------- v1.1 entities and columns
def test_upgrade_entities_imported(db):
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    assert count(m.Cohort) == 5
    assert count(m.GenomicPrevalence) == 43 * 5 * 3  # every gene x cohort x alteration type, measured zeros included
    assert count(m.ExternalBenchmark) == 58
    assert db.scalars(select(m.Gene).filter_by(official_symbol="BRCA1")).one().hgnc_id == "HGNC:1100"
    assert db.scalars(select(m.Cancer).filter_by(code="nsclc")).one().mondo_id == "MONDO:0005233"


def test_prevalence_counts_validated(empty_db):
    import_dataframe(empty_db, "cancers", df([{"code": "breast", "name": "Breast cancer"}]))
    import_dataframe(empty_db, "genes", df([{"official_symbol": "TP53"}]))
    import_dataframe(empty_db, "cohorts", df([{"study_id": "s1", "name": "cohort", "cancer_code": "breast"}]))
    rep = import_dataframe(empty_db, "genomic_prevalence", df([
        {"gene_symbol": "TP53", "study_id": "s1", "alteration_type": "somatic_mutation", "altered_cases": "11", "profiled_cases": "10"},
        {"gene_symbol": "TP53", "study_id": "s1", "alteration_type": "fusion", "altered_cases": "1", "profiled_cases": "10"},
    ]))
    msgs = " ".join(e["message"] for e in rep.errors)
    assert "cannot exceed" in msgs and "alteration_type must be one of" in msgs


def test_prevalence_basis_requires_single_gene(empty_db):
    rep = import_dataframe(empty_db, "biomarkers", df([{
        "biomarker_code": "X-1", "name": "x", "biomarker_type": "genetic_mutation",
        "gene_symbols": "KRAS;NRAS", "prevalence_basis": "somatic_mutation"}]))
    assert not rep.ok and "exactly one gene" in rep.errors[0]["message"]


def test_ontology_identifier_formats(empty_db):
    rep = import_dataframe(empty_db, "cancers", df([{"code": "x", "name": "x", "mondo_id": "DOID:1", "icdo_topography": "50"}]))
    fields = {e["field"] for e in rep.errors}
    assert {"mondo_id", "icdo_topography"} <= fields
    rep = import_dataframe(empty_db, "genes", df([{"official_symbol": "TP53", "hgnc_id": "11998"}]))
    assert not rep.ok and rep.errors[0]["field"] == "hgnc_id"
