"""Controlled vocabularies shared by the schema, validators, scoring and the UI."""

BIOMARKER_TYPES = (
    "genetic_mutation",
    "germline_variant",
    "gene_fusion",
    "copy_number_alteration",
    "protein_expression",
    "circulating_protein",
    "gene_expression_signature",
    "rna_transcript",
    "epigenetic_methylation",
    "genomic_signature",
)

BIOMARKER_ROLES = ("diagnostic", "prognostic", "predictive", "risk", "monitoring")

# Origin of an association record. Lets the UI separate literature-curated facts,
# database annotations, computational predictions and synthetic demo rows.
SOURCE_STATUSES = (
    "curated_literature",
    "database_annotation",
    "computational_prediction",
    "synthetic_demo",
    "pending_curation",
)

EVIDENCE_TYPES = (
    "meta_analysis",
    "randomized_clinical_trial",
    "clinical_trial",
    "patient_cohort",
    "clinical_guideline",
    "genomic_profiling",
    "experimental",
    "review",
    "computational_prediction",
)

# A NULL consistency_annotation means "not curated" (unknown). It is NOT agreement.
CONSISTENCY_VALUES = ("supports", "mixed", "conflicting")

PATHWAY_DATABASES = ("KEGG", "Reactome", "WikiPathways", "Other")

# Gene-level alteration classes counted in TCGA cohorts (cBioPortal Mutated Genes / CNA Genes tables).
ALTERATION_TYPES = ("somatic_mutation", "amplification", "deep_deletion")

# Which TCGA alteration frequency describes a biomarker. NULL = not meaningful (protein/RNA expression,
# germline carrier status, fusions, signatures, or acquired-resistance alterations that are rare in the
# untreated primary tumours profiled by TCGA). "_upper_bound" = the biomarker is a specific variant or hotspot,
# so the gene-level frequency is an upper bound.
PREVALENCE_BASES = ("somatic_mutation", "somatic_mutation_upper_bound", "amplification", "deep_deletion")

# CIViC evidence levels: A validated, B clinical, C case study, D preclinical, E inferential.
CIVIC_EVIDENCE_LEVELS = ("A", "B", "C", "D", "E")


def sql_in(values: tuple[str, ...]) -> str:
    """Render a tuple as a SQL IN-list for CHECK constraints."""
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"
