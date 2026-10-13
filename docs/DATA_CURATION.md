# Adding and Curating Data

All curated data lives in `backend/data/sample/*.csv`. Import order (dependencies first):

```
cancers → genes → proteins → pathways → publications → biomarkers → gene_pathways
→ biomarker_pathways → associations → evidence → evidence_kegg → variants
→ cohorts → genomic_prevalence → external_benchmarks
```

## Workflow for a new biomarker–cancer association

1. **Genes / proteins.** Add rows to `genes.csv` (official HGNC symbol and NCBI Gene ID) and
   `proteins.csv` (reviewed UniProt accession plus `gene_symbol`).
2. **Publications.** Add the PMID with an approximate title to `publications.csv`, then run:
   ```bash
   cd backend
   python -m scripts.fetch_pubmed           # reports mismatches; never trust a PMID from memory
   python -m scripts.fetch_pubmed --write   # overwrite metadata with the PubMed record
   ```
3. **Biomarker.** Add to `biomarkers.csv` with a new code (`CBM-048`, …). `gene_symbols` is a
   `;`-separated list. `biomarker_type` must be one of the vocabulary values in `app/vocab.py`.
4. **Association.** Add `biomarker_code, cancer_code, biomarker_role, source_status, description` to
   `associations.csv`. Use `pending_curation` if evidence is not yet curated, and `synthetic_demo` for
   any illustrative record. Never present synthetic rows as scientific evidence.
5. **Evidence.** One row per (association, publication, source) in `evidence.csv`:
   - `evidence_type`: the study design you verified in the paper; leave blank if unsure.
   - `consistency_annotation`: `supports`, `mixed` or `conflicting` only when the paper's finding
     clearly bears on the role; otherwise leave blank (unknown). Never invent contradictory findings.
   - `evidence_summary`: paraphrase the paper's main reported result.
   - `retrieved_at`: the date you verified the record.
6. **Pathways and verification.**
   ```bash
   python -m scripts.verify_sources --write-kegg   # gene/protein/variant checks + KEGG links
   python -m scripts.init_db                        # import (idempotent) + recompute scores
   ```

Or upload a single CSV in the UI (*Data Import* page): run a dry-run validation first, then import.

## Validation rules enforced by the importer

| Field | Rule |
|---|---|
| `official_symbol` | Uppercase HGNC-style symbol; unique |
| `ncbi_gene_id` | Positive integer; unique; cannot be reassigned to another symbol |
| `accession` | UniProt accession pattern |
| `pmid` / `doi` | At least one is required; PMID numeric; both unique |
| `publication_year` | 1900 to next year |
| `biomarker_type`, `biomarker_role`, `source_status`, `evidence_type`, `consistency_annotation` | Controlled vocabularies |
| `chromosome` | 1–22, X, Y, MT (a `chr` prefix is stripped) |
| `reference_allele`, `alternate_allele` | A, C, G, T, N or `-` |
| `dbsnp_id` | `rs` followed by digits |
| `hgnc_id` | `HGNC:` followed by digits; unique |
| `mondo_id` | `MONDO:` followed by 7 digits |
| `icdo_topography` | ICD-O-3 topography code(s) or range, e.g. `C50`, `C18-C20` |
| `prevalence_basis` | Controlled vocabulary; only for a biomarker with exactly one gene |
| `altered_cases`, `profiled_cases` | `0 <= altered <= profiled`, `profiled > 0` |
| `best_evidence_level` | A-E, present exactly when `n_items > 0` |
| Referenced codes | Must already exist (biomarker, cancer, gene, publication, association) |
| Duplicate natural key in one file | Rejected with both row numbers |

Any error rejects the whole file (atomic), and the report lists row numbers (header = row 1).

## Access and attribution

- NCBI E-utilities: at most 3 requests/second without an API key (set `NCBI_EMAIL`/`NCBI_API_KEY`
  in `.env`). The scripts batch requests and pause between calls.
- KEGG REST: free for academic use; commercial use requires a licence.
- UniProt, Ensembl and GDC: public REST APIs; cite them as described on their websites.
- Do not scrape web pages. Use the documented APIs only.

## Version 1.1 data

### Ontology identifiers

`python -m scripts.fetch_ontologies` verifies (and with `--write` writes) HGNC IDs for every gene, checked against the
stored NCBI Gene ID, and Mondo IDs for every cancer, checked through EBI OLS to exist, be current and cross-reference
the stored DOID. ICD-O-3 topography codes are curator-assigned in the script from the WHO ICD-O-3 topography axis.

### TCGA alteration counts (`cohorts.csv`, `genomic_prevalence.csv`)

`python -m scripts.fetch_prevalence --write` fetches raw counts from cBioPortal for the five TCGA PanCancer Atlas
cohorts and every gene in `genes.csv`. To add a cancer, add its cBioPortal study to `STUDIES` in the script (a cancer
may have several studies; they are pooled by summing counts).

### Choosing `prevalence_basis` for a biomarker

Set it only when a gene-level TCGA frequency honestly describes the biomarker:

| Biomarker | Basis |
|---|---|
| Defined by any activating or loss-of-function somatic mutation of one gene (TP53, PIK3CA, NRAS, STK11) | `somatic_mutation` |
| Defined by a specific variant, hotspot or class (KRAS G12C, BRAF V600E, EGFR exon 19/L858R, MET exon 14) | `somatic_mutation_upper_bound` |
| Gene amplification (HER2, AR) | `amplification` |
| Gene loss by deletion (PTEN) | `deep_deletion` |
| Protein or RNA expression, circulating protein, germline carrier status, fusion, multi-gene signature, genomic signature, acquired-resistance alteration | leave blank |

### CIViC benchmark (`external_benchmarks.csv`)

`python -m scripts.fetch_civic --write` rebuilds the benchmark. Matching rules (gene, disease-name rules, evidence
type to role, direction SUPPORTS, and `VARIANT_FILTERS` for variant-specific biomarkers) are in the script and are
recorded per row in `matched_on`. The benchmark is used only for validation: never copy CIViC items into
`evidence.csv`, or the validation becomes circular.

### Regenerating the SQL reference files

After changing a report or a migration, run `python -m scripts.export_sql` to regenerate
`sql/query_catalogue.sql` and `sql/schema_postgresql.sql`.

### Note on CSV line endings

Keep LF line endings (the repository enforces them through `.gitattributes`). Python's `csv` module writes CRLF by
default; pass `lineterminator="\n"` or use pandas `to_csv(..., lineterminator="\n")`, otherwise every line shows as
changed in a diff.
