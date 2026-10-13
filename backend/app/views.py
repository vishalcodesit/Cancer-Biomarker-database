"""SQL views (portable SQL that runs unchanged on PostgreSQL and SQLite).

Views keep derived data out of the base tables (no stored percentages) while giving the analytics layer and the
viva a readable SQL interface. They are created by Alembic migration 0003 and, for the in-memory test database,
by create_views().
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

VIEWS: dict[str, str] = {
    # Gene-level alteration frequency per cancer, pooled over the cancer's cohorts by summing raw counts
    # (NSCLC = TCGA LUAD + TCGA LUSC). Multiplying by 1.0 forces non-integer division on both databases.
    "v_tcga_frequency": """
CREATE VIEW v_tcga_frequency AS
SELECT g.gene_id, g.official_symbol, co.cancer_id, c.name AS cancer, gp.alteration_type,
       SUM(gp.altered_cases)  AS altered_cases,
       SUM(gp.profiled_cases) AS profiled_cases,
       SUM(gp.altered_cases) * 1.0 / SUM(gp.profiled_cases) AS frequency,
       COUNT(*) AS n_cohorts
FROM genomic_prevalence gp
JOIN cohort co ON co.cohort_id = gp.cohort_id
JOIN gene g    ON g.gene_id = gp.gene_id
JOIN cancer c  ON c.cancer_id = co.cancer_id
GROUP BY g.gene_id, g.official_symbol, co.cancer_id, c.name, gp.alteration_type""",
    # Each association with the TCGA frequency of the alteration that defines its biomarker. Only single-gene
    # biomarkers with a curated prevalence_basis appear; the CASE maps the "upper bound" basis to the measured type.
    "v_association_prevalence": """
CREATE VIEW v_association_prevalence AS
SELECT bc.association_id, b.biomarker_id, b.biomarker_code, b.name AS biomarker, c.name AS cancer,
       bc.biomarker_role, b.prevalence_basis, f.official_symbol, f.alteration_type,
       f.altered_cases, f.profiled_cases, f.frequency
FROM biomarker_cancer bc
JOIN biomarker b       ON b.biomarker_id = bc.biomarker_id
JOIN cancer c          ON c.cancer_id = bc.cancer_id
JOIN biomarker_gene bg ON bg.biomarker_id = b.biomarker_id
JOIN v_tcga_frequency f
  ON f.gene_id = bg.gene_id
 AND f.cancer_id = bc.cancer_id
 AND f.alteration_type = CASE WHEN b.prevalence_basis = 'somatic_mutation_upper_bound'
                              THEN 'somatic_mutation' ELSE b.prevalence_basis END
WHERE b.prevalence_basis IS NOT NULL
  AND (SELECT COUNT(*) FROM biomarker_gene x WHERE x.biomarker_id = b.biomarker_id) = 1""",
}


def create_views(conn: Connection) -> None:
    for ddl in VIEWS.values():
        conn.execute(text(ddl))


def drop_views(conn: Connection) -> None:
    for name in reversed(list(VIEWS)):
        conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
