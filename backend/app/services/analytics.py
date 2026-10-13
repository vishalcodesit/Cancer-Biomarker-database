"""SQL query catalogue for analytics and reports.

Every report is a documented, parameterized SQL statement (bound parameters,
never string interpolation) written in portable SQL that runs unchanged on
PostgreSQL and SQLite. The same text is shown in the UI for teaching purposes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.scoring import SCORING_VERSION


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # "int" | "cancer" | "float"
    default: int | float | None
    description: str


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    description: str
    sql: str
    params: tuple[Param, ...] = field(default_factory=tuple)
    concepts: tuple[str, ...] = field(default_factory=tuple)


REPORTS: dict[str, Report] = {
    r.key: r
    for r in [
        Report(
            "multi_cancer_biomarkers",
            "Biomarkers associated with multiple cancer types",
            "Biomarkers recorded for at least N distinct cancers.",
            """
SELECT b.biomarker_id, b.biomarker_code, b.name AS biomarker,
       COUNT(DISTINCT bc.cancer_id) AS n_cancers,
       COUNT(bc.association_id)     AS n_associations
FROM biomarker b
JOIN biomarker_cancer bc ON bc.biomarker_id = b.biomarker_id
GROUP BY b.biomarker_id, b.biomarker_code, b.name
HAVING COUNT(DISTINCT bc.cancer_id) >= :min_cancers
ORDER BY n_cancers DESC, LOWER(b.name), b.biomarker_id""",
            (Param("min_cancers", "int", 2, "Minimum number of distinct cancers"),),
            ("JOIN", "GROUP BY", "HAVING", "COUNT DISTINCT"),
        ),
        Report(
            "cancers_by_biomarker_count",
            "Cancer types with the most recorded biomarkers",
            "Number of distinct biomarkers and associations per cancer (LEFT JOIN keeps cancers with none).",
            """
SELECT c.cancer_id, c.name AS cancer,
       COUNT(DISTINCT bc.biomarker_id) AS n_biomarkers,
       COUNT(bc.association_id)        AS n_associations
FROM cancer c
LEFT JOIN biomarker_cancer bc ON bc.cancer_id = c.cancer_id
GROUP BY c.cancer_id, c.name
ORDER BY n_biomarkers DESC, LOWER(c.name), c.cancer_id""",
            (),
            ("LEFT JOIN", "GROUP BY", "COUNT DISTINCT"),
        ),
        Report(
            "top_publication_biomarkers",
            "Biomarkers with the most supporting publications",
            "Distinct publications linked through evidence records, across all associations of a biomarker.",
            """
SELECT b.biomarker_id, b.name AS biomarker,
       COUNT(DISTINCT e.publication_id) AS n_publications,
       COUNT(e.evidence_id)             AS n_evidence_records
FROM biomarker b
JOIN biomarker_cancer bc ON bc.biomarker_id = b.biomarker_id
JOIN evidence e          ON e.association_id = bc.association_id
GROUP BY b.biomarker_id, b.name
ORDER BY n_publications DESC, LOWER(b.name), b.biomarker_id
LIMIT :limit""",
            (Param("limit", "int", 10, "Number of rows"),),
            ("multi-table JOIN", "COUNT DISTINCT", "LIMIT"),
        ),
        Report(
            "associations_by_evidence_type",
            "Biomarker-cancer associations grouped by evidence type",
            "Untyped evidence is reported as 'unspecified' rather than hidden.",
            """
SELECT COALESCE(e.evidence_type, 'unspecified') AS evidence_type,
       COUNT(DISTINCT e.association_id)          AS n_associations,
       COUNT(e.evidence_id)                      AS n_evidence_records
FROM evidence e
GROUP BY COALESCE(e.evidence_type, 'unspecified')
ORDER BY n_associations DESC, evidence_type""",
            (),
            ("COALESCE", "GROUP BY expression"),
        ),
        Report(
            "shared_pathways",
            "Biomarkers linked to common biological pathways",
            "Pathways (KEGG gene membership) shared by at least N biomarkers.",
            """
SELECT p.pathway_id, p.pathway_name, p.pathway_database, p.external_identifier,
       COUNT(DISTINCT bp.biomarker_id) AS n_biomarkers
FROM pathway p
JOIN biomarker_pathway bp ON bp.pathway_id = p.pathway_id
GROUP BY p.pathway_id, p.pathway_name, p.pathway_database, p.external_identifier
HAVING COUNT(DISTINCT bp.biomarker_id) >= :min_biomarkers
ORDER BY n_biomarkers DESC, LOWER(p.pathway_name), p.pathway_id""",
            (Param("min_biomarkers", "int", 2, "Minimum biomarkers per pathway"),),
            ("JOIN", "HAVING"),
        ),
        Report(
            "biomarker_pairs_sharing_pathways",
            "Biomarker pairs that share pathways",
            "Self-join on the junction table; b1 < b2 avoids duplicate and self pairs.",
            """
SELECT b1.name AS biomarker_a, b2.name AS biomarker_b,
       COUNT(*) AS shared_pathways
FROM biomarker_pathway bp1
JOIN biomarker_pathway bp2
  ON bp1.pathway_id = bp2.pathway_id AND bp1.biomarker_id < bp2.biomarker_id
JOIN biomarker b1 ON b1.biomarker_id = bp1.biomarker_id
JOIN biomarker b2 ON b2.biomarker_id = bp2.biomarker_id
GROUP BY b1.name, b2.name
HAVING COUNT(*) >= :min_shared
ORDER BY shared_pathways DESC, LOWER(b1.name), LOWER(b2.name)
LIMIT :limit""",
            (Param("min_shared", "int", 3, "Minimum shared pathways"), Param("limit", "int", 25, "Number of rows")),
            ("self-join", "HAVING", "LIMIT"),
        ),
        Report(
            "limited_evidence_associations",
            "Associations with limited or missing supporting evidence",
            "Associations with fewer than N distinct publications (LEFT JOIN keeps those with no evidence).",
            """
SELECT bc.association_id, b.name AS biomarker, c.name AS cancer, bc.biomarker_role,
       COUNT(DISTINCT e.publication_id) AS n_publications,
       COUNT(DISTINCT e.source_name)    AS n_sources,
       COUNT(e.evidence_id)             AS n_evidence_records
FROM biomarker_cancer bc
JOIN biomarker b      ON b.biomarker_id = bc.biomarker_id
JOIN cancer c         ON c.cancer_id = bc.cancer_id
LEFT JOIN evidence e  ON e.association_id = bc.association_id
GROUP BY bc.association_id, b.name, c.name, bc.biomarker_role
HAVING COUNT(DISTINCT e.publication_id) < :max_publications
ORDER BY n_publications, n_sources, LOWER(b.name), bc.association_id""",
            (Param("max_publications", "int", 2, "Flag associations with fewer publications than this"),),
            ("LEFT JOIN", "HAVING", "COUNT DISTINCT"),
        ),
        Report(
            "shared_biomarkers",
            "Shared biomarkers between two cancers",
            "Set intersection of the biomarkers recorded for two cancers.",
            """
SELECT b.biomarker_id, b.biomarker_code, b.name AS biomarker, b.biomarker_type
FROM biomarker b
WHERE b.biomarker_id IN (
    SELECT biomarker_id FROM biomarker_cancer WHERE cancer_id = :cancer_a
    INTERSECT
    SELECT biomarker_id FROM biomarker_cancer WHERE cancer_id = :cancer_b
)
ORDER BY LOWER(b.name), b.biomarker_id""",
            (
                Param("cancer_a", "cancer", None, "First cancer"),
                Param("cancer_b", "cancer", None, "Second cancer"),
            ),
            ("INTERSECT", "subquery"),
        ),
        Report(
            "score_by_cancer_role",
            "Average evidence-support score by cancer and role",
            "Aggregates stored scores; incomplete (NULL) scores are counted separately, not averaged as zero.",
            """
SELECT c.name AS cancer, bc.biomarker_role,
       COUNT(*)                                    AS n_associations,
       AVG(s.overall_score)                        AS mean_score,
       SUM(CASE WHEN s.overall_score IS NULL THEN 1 ELSE 0 END) AS n_unscored,
       SUM(CASE WHEN s.score_status = 'provisional' THEN 1 ELSE 0 END) AS n_provisional
FROM evidence_score s
JOIN biomarker_cancer bc ON bc.association_id = s.association_id
JOIN cancer c            ON c.cancer_id = bc.cancer_id
WHERE s.scoring_version = :scoring_version
GROUP BY c.name, bc.biomarker_role
ORDER BY LOWER(c.name), bc.biomarker_role""",
            (),
            ("CASE", "AVG ignores NULL", "GROUP BY"),
        ),
        Report(
            "tcga_frequency_by_cancer",
            "Most frequently altered curated genes in a cancer (TCGA)",
            "Reads the view v_tcga_frequency, which pools raw counts over the cancer's cohorts (NSCLC = LUAD + LUSC).",
            """
SELECT f.official_symbol, f.alteration_type, f.altered_cases, f.profiled_cases,
       100 * f.frequency AS percent_altered, f.n_cohorts
FROM v_tcga_frequency f
WHERE f.cancer_id = :cancer_a AND f.altered_cases > 0
ORDER BY f.frequency DESC, f.official_symbol, f.alteration_type
LIMIT :limit""",
            (Param("cancer_a", "cancer", None, "Cancer"), Param("limit", "int", 15, "Number of rows")),
            ("VIEW", "aggregate pooling", "ORDER BY expression"),
        ),
        Report(
            "common_but_thinly_supported",
            "Common alterations with thin recorded evidence (curation priority)",
            "Joins the view v_association_prevalence with stored scores: frequent in tumours, low evidence-support score.",
            """
SELECT ap.biomarker, ap.cancer, ap.biomarker_role, ap.official_symbol,
       100 * ap.frequency AS percent_altered, s.overall_score, s.score_status
FROM v_association_prevalence ap
JOIN evidence_score s ON s.association_id = ap.association_id AND s.scoring_version = :scoring_version
WHERE ap.frequency >= :min_frequency AND (s.overall_score IS NULL OR s.overall_score < :max_score)
ORDER BY ap.frequency DESC, ap.association_id""",
            (Param("min_frequency", "float", 0.1, "Minimum TCGA frequency (0-1)"),
             Param("max_score", "float", 75, "Score below which evidence counts as thin")),
            ("VIEW", "JOIN on composite condition", "NULL handling"),
        ),
        Report(
            "score_by_civic_level",
            "Evidence-support score by CIViC evidence level (external validation)",
            "Does the score rise with the expert-assigned CIViC level? LEFT JOIN keeps associations CIViC does not cover.",
            """
SELECT COALESCE(eb.best_evidence_level, 'not in CIViC') AS civic_level,
       COUNT(*)                AS n_associations,
       AVG(s.overall_score)    AS mean_score,
       MIN(s.overall_score)    AS min_score,
       MAX(s.overall_score)    AS max_score
FROM biomarker_cancer bc
JOIN evidence_score s ON s.association_id = bc.association_id AND s.scoring_version = :scoring_version
LEFT JOIN external_benchmark eb ON eb.association_id = bc.association_id AND eb.benchmark_source = 'CIViC'
                               AND eb.n_items > 0
GROUP BY COALESCE(eb.best_evidence_level, 'not in CIViC')
ORDER BY civic_level""",
            (),
            ("LEFT JOIN", "COALESCE", "GROUP BY expression", "AVG ignores NULL"),
        ),
    ]
}


class ReportError(ValueError):
    pass


def run_report(db: Session, key: str, raw_params: dict[str, str | None]) -> dict:
    report = REPORTS.get(key)
    if report is None:
        raise KeyError(key)
    params: dict[str, object] = {}
    for p in report.params:
        raw = raw_params.get(p.name)
        if raw in (None, ""):
            if p.default is None:
                raise ReportError(f"Parameter '{p.name}' is required")
            params[p.name] = p.default
            continue
        try:
            params[p.name] = float(raw) if p.type == "float" else int(raw)
        except ValueError as exc:
            raise ReportError(f"Parameter '{p.name}' must be a number") from exc
        if p.type == "int" and params[p.name] < 0:
            raise ReportError(f"Parameter '{p.name}' must be non-negative")
    if ":scoring_version" in report.sql:
        params["scoring_version"] = SCORING_VERSION
    result = db.execute(text(report.sql), params)
    columns = list(result.keys())
    rows = []
    for r in result.mappings():
        row = dict(r)
        for k, v in row.items():
            # Rounding happens here, not in SQL: PostgreSQL has no ROUND(double precision, int). Values are first
            # snapped to 9 decimals so that SQLite and PostgreSQL, which sum floats in different orders, round alike.
            if isinstance(v, (float, Decimal)):
                row[k] = round(round(float(v), 9), 2)
        rows.append(row)
    return {"key": key, "title": report.title, "columns": columns, "rows": rows, "params": params}


def catalogue() -> list[dict]:
    return [
        {
            "key": r.key,
            "title": r.title,
            "description": r.description,
            "sql": r.sql.strip(),
            "params": [p.__dict__ for p in r.params],
            "concepts": list(r.concepts),
        }
        for r in REPORTS.values()
    ]
