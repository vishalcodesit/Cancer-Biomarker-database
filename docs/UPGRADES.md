# CancerBioMap 1.1: review findings and upgrades

This document records what the 1.0 codebase did well, what an independent review found, and every change made in
1.1, with the evidence behind each decision. Every number below can be reproduced with the commands in section 6.

## 1. What 1.0 got right (verified, not assumed)

| Claim in the 1.0 README | How it was checked | Result |
|---|---|---|
| 51 backend and 9 frontend tests pass; production build succeeds | Ran `pytest`, `npm test`, `npm run build` in a clean environment | Confirmed |
| Every PMID verified against PubMed | Re-ran `scripts/fetch_pubmed.py` against the live API | 84 of 84 match on title and year |
| Gene IDs, UniProt accessions, variant coordinates and KEGG membership verified | Wrote an independent checker (separate code, same public APIs) | 43/43 genes, 40/40 proteins, 8/8 variants, 14/14 KEGG pathways correct |
| Disease Ontology IDs | Looked up through EBI OLS | 4/4 correct |

The schema (3NF, per-role associations, explicit NULL-as-unknown, versioned scores), the validated idempotent
importer and the API design were sound and were kept.

## 2. Problems found in 1.0

### 2.1 Context-only KEGG rows inflated 34 of 58 scores

The 1.0 documentation states that KEGG disease-map membership "does not support a specific biomarker role", and the
KEGG evidence rows carry no evidence type for that reason. The source-diversity component (D) nevertheless counted
KEGG as an independent supporting source. Effect, measured on the sample data: 34 of 58 associations gained between
3.1 and 7.4 points (mean 5.7). Example: BRCA1 pathogenic variant / breast / predictive scored 78.96 with the KEGG row
and 72.71 without it.

### 2.2 The evidence-type component was not monotone

T = 0.7 x max + 0.3 x mean over distinct study designs. Because the mean falls when a weaker design is added, adding
a corroborating study could lower the score. Counterexample (reproduced in `tests/test_scoring.py`): five supporting
RCTs score 86.25; adding a sixth supporting publication (a review) lowers the score to 84.19.

### 2.3 The gap analysis flagged almost everything

57 of 58 associations were flagged. All 34 "untyped evidence" flags were caused by the KEGG rows that are untyped
by design, so the most frequent flag carried no information. There was no severity or prioritisation.

### 2.4 The implementation did not match the submitted proposal

| Proposal (methodology and novelty) | 1.0 | 1.1 |
|---|---|---|
| Mutation frequency statistics (TCGA / cBioPortal) | Absent; "NCI GDC (TCGA)" rows were citations of TCGA papers | Real counts for every curated gene in 5 TCGA PanCancer Atlas cohorts via the cBioPortal API |
| Ontology standardisation (ICD-O, MONDO, HGNC) | Disease Ontology only | Mondo (verified to cross-reference the DOID), ICD-O-3 topography, HGNC IDs (verified against NCBI Gene IDs) |
| SQL views | None | Two views (`v_tcga_frequency`, `v_association_prevalence`) used by new reports |
| MySQL/PostgreSQL | PostgreSQL never executed | Migrations applied to PostgreSQL 16; all 190 read endpoints return identical results on PostgreSQL and SQLite |
| Score validation | Listed as future work | External validation against CIViC plus a weight-robustness analysis |

### 2.5 PostgreSQL portability bugs (found only by actually running PostgreSQL)

Comparing every endpoint on SQLite and PostgreSQL 16 found 8 endpoints with different output:
* collation: SQLite sorts by byte value (`ALK...` before `Adenomatous...`), PostgreSQL linguistically;
* unstable ties: `ORDER BY count DESC` returned tied rows in different orders;
* a `GROUP BY` with no `ORDER BY`;
* a float on a rounding boundary (58.945) that each database summed slightly differently.

All were fixed (case-insensitive ordering, a unique tie-breaker on every ORDER BY, rounding snapped to 9 decimals
before 2). After the fixes: 190 of 190 endpoints identical.

### 2.6 Smaller issues

* Write endpoints (`POST /api/import` with `dry_run=false`, `POST /api/scores/recompute`) had no protection.
* CORS allowed every request header.
* The Methodology page hard-coded the formula text, so it would contradict the configuration if weights changed.
* The curation scripts failed on macOS python.org builds with `CERTIFICATE_VERIFY_FAILED` (no CA bundle).
* The README contained instructions addressed to a student ("Verify every claim you make...", "Run the steps above
  once on a PostgreSQL server to confirm before your demonstration").

## 3. Changes in 1.1

### 3.1 Scoring 1.1.0 (`app/scoring.py`; the original is frozen in `app/scoring_legacy.py`)

1. Records that cite no publication and declare no study design (context-only, such as KEGG membership) are kept for
   provenance and shown in the UI but are not counted as a supporting source.
2. T is a discounted noisy-OR over distinct designs: `T = 100 (1 - (1 - b1) prod_{i>=2} (1 - lambda b_i))`, with
   `b` = rubric / 100, `b1` the strongest design and `lambda` = 0.25 (configurable, `SCORE_BREADTH_DISCOUNT`).
   A single design scores exactly its rubric value; T is never below the strongest design or above 100; adding a
   design never lowers T. These properties are checked by 2,000 randomised cases in the test suite, and a further
   1,500 randomised cases check that adding a supporting record never lowers the overall score.

Scores are stored per version, so 1.0.0 results remain available: `GET /api/scores/comparison` scores every
association both ways and explains each difference. 42 of 58 scores changed; mean change -2.84.

### 3.2 Gap analysis v2 (`app/services/gaps.py`)

* Context-only rows no longer count as sources or raise "untyped evidence" (34 such flags removed).
* New flag `role_evidence_mismatch`: the recorded study designs are not of the kind the claimed role needs
  (for example a predictive claim supported only by laboratory or genomic-profiling studies). The rubric is in
  `ROLE_EVIDENCE_EXPECTATIONS` and is shown in the UI.
* Each flag has a severity; `curation_priority = severity x (1 + 4 x min(TCGA frequency, 0.5))`, so the same gap
  matters up to three times more for a common alteration.

### 3.3 The curation loop in practice

The new mismatch flag identified EGFR T790M and ESR1 ligand-binding-domain mutation as predictive claims supported
only by experimental studies. The two pivotal randomised trials were curated (AURA3, PMID 27959700; EMERALD,
PMID 35584336), verified through `scripts/fetch_pubmed.py`, and imported. Both flags cleared and the scores rose
(T790M 68.96 to 78.50; ESR1 71.08 to 78.68). Agreement with CIViC also rose (see 3.6). This is the workflow the
database is meant to support: find a gap, curate it, measure the effect.

### 3.4 TCGA genomic context (`scripts/fetch_prevalence.py`, `app/services/prevalence.py`)

* Raw counts (altered and profiled tumours) for somatic mutation, amplification and deep deletion of all 43 curated
  genes in 5 TCGA PanCancer Atlas cohorts (BRCA, LUAD, LUSC, COADREAD, PRAD): 645 rows. Percentages are never
  stored; NSCLC pools LUAD and LUSC by summing counts. 95% Wilson intervals are reported.
* Spot checks against the TCGA marker papers: LUAD KRAS 29.7%, LUAD EGFR 12.4%, COADREAD APC 72.5%, PRAD SPOP 11.1%,
  PRAD PTEN deep deletion 17.4%, BRCA TP53 32.6%, BRCA ERBB2 amplification 11.5%.
* `biomarker.prevalence_basis` records which frequency describes each biomarker (16 of 47). It is left empty where a
  gene-level frequency would mislead: protein or RNA expression, germline carrier status, fusions, signatures, and
  acquired-resistance alterations that are rare in untreated primary tumours. For variant-specific biomarkers (KRAS
  G12C, BRAF V600E, ...) the gene-level frequency is marked as an upper bound.
* New page "Evidence vs Prevalence" places every applicable association on frequency (x, log) against score (y).
  With the default thresholds (score 75, frequency 10%): 2 established, 7 common but thinly supported, 1 rare but
  well supported, 13 rare and thinly supported. The 7 are the curation work list: PIK3CA and TP53 in breast (both
  32.6%), PTEN loss in prostate (17.4%), KRAS G12C in NSCLC (at most 16.7%), BRAF V600E in colorectal, HER2
  prognostic in breast, SPOP in prostate.

### 3.5 Ontologies (`scripts/fetch_ontologies.py`)

HGNC IDs for 43/43 genes (each checked against the stored NCBI Gene ID), Mondo IDs for 4/4 cancers (each checked
through EBI OLS to exist, not be obsolete, and cross-reference the stored DOID), and ICD-O-3 topography codes.

### 3.6 Validation of the score (`app/services/validation.py`, `app/robustness.py`, page "Score Validation")

External: 34 of 58 associations match accepted CIViC evidence items (gene or curated variant keyword, disease rule,
matching evidence type, direction SUPPORTS). Spearman rho between the score and the best CIViC level = 0.47
(two-sided permutation p = 0.006; bootstrap 95% CI 0.17 to 0.70). Mean score falls with level: A 72.5 (n=19),
B 66.9 (n=11), C 61.7 (n=4). CIViC never feeds the score, so this is an independent check.

Coverage finding: CIViC covers 17 of 20 somatic-mutation associations but 0 of 4 serum-protein, 0 of 2 methylation
and 0 of 3 genomic-signature associations. This quantifies the project's premise that genomic knowledge bases
under-represent non-DNA biomarkers.

Version check, reported openly: version 1.0.0 had a higher rho (0.54). The decomposition script shows the drop comes
from the KEGG correction alone (the monotone-T change is neutral), because KEGG disease-map membership itself
correlates with CIViC level (rho 0.22): KEGG maps list the canonical genes that experts also rate highly. The
difference is not significant (paired bootstrap 95% CI -0.20 to 0.06). The correction is kept: an evidence score
should not be raised by something the project itself defines as non-evidence, and tuning the score to CIViC would
destroy CIViC's value as an independent check.

Robustness: over 1,000 weight vectors drawn uniformly from the simplex, the ranking of the 55 fully scored
associations keeps a mean Spearman correlation of 0.91 with the baseline (5th percentile 0.75), and 78% of the
baseline top 10 stay in the top 10. Ablation shows which components carry information: dropping publication support
(rho 0.85) or evidence type (top-10 kept 60%) changes the ranking most; dropping source diversity (0.98) or
consistency (0.97) barely changes it, because 93 of 101 supporting rows come from PubMed and almost every curated
annotation is "supports". The most weight-sensitive association is PSA (rank 4 at baseline, 3 to 51 across weightings)
because it combines four publications with documented mixed evidence.

### 3.7 Database and portability

* Migration 0002 (reviewed autogenerate: the HGNC unique constraint was named and the prevalence CHECK added by
  hand), migration 0003 (views, written by hand). Upgrade, downgrade and re-upgrade are tested; a comparison of the
  migrated schema with the ORM models finds no differences.
* Three new SQL reports: most altered genes per cancer (view), common but thinly supported associations (view join),
  score by CIViC level (LEFT JOIN, COALESCE).
* `scripts/export_sql.py` regenerates `sql/query_catalogue.sql` and `sql/schema_postgresql.sql` from the code.

### 3.8 Security and robustness

* Optional `ADMIN_TOKEN`: when set, real imports and recompute require `X-Admin-Token` (constant-time comparison).
  Dry runs stay open. Left empty, behaviour is unchanged for a local demo.
* CORS headers restricted to `Content-Type` and `X-Admin-Token`.
* Scripts use the certifi CA bundle explicitly (verification stays on).

### 3.9 Tests

Backend 80 (51 original, of which 5 were updated to the new expected values, plus 29 new); frontend 15 (9 original, 6 new). New tests cover
monotonicity and bounds (randomised), the KEGG correction, the frozen 1.0.0 results, prevalence pooling against the
SQL view, view-versus-API agreement, robustness determinism, CIViC statistics, the version comparison, the new
reports, migrations including views, and the write guard.

## 4. What was deliberately not changed

* Weights (0.35 / 0.25 / 0.25 / 0.15) and the rubric: still proposed parameters. The robustness analysis shows the
  ranking is fairly stable to them, which is a better answer than re-tuning them.
* CIViC is not used as a score input (it would make the validation circular).
* KEGG rows remain in the database and in the UI as context.

## 5. Remaining limitations

* 47 biomarkers and 4 cancers; landmark positive studies dominate, which is why D and C carry little information.
* CIViC matching is at gene or curated-keyword level with disease-name rules; tumour-agnostic approvals (NTRK) are
  filed by CIViC under "Solid Tumor" and are not matched.
* TCGA frequencies are cohort-wide (not subtype-specific) and gene-level.
* Single-curator annotations; no inter-annotator agreement.

## 6. Reproduce

```bash
cd backend
python -m pytest -q                         # 80 tests
python -m scripts.init_db --reset           # migrate (0001-0003), import 15 entities, score
python -m scripts.fetch_pubmed              # 86/86 PMIDs match PubMed
python -m scripts.fetch_ontologies          # HGNC 43/43, Mondo 4/4
python -m scripts.fetch_prevalence          # refetch TCGA counts (add --write to update the CSV)
python -m scripts.fetch_civic               # refetch the CIViC benchmark (add --write to update the CSV)
cd ../frontend && npm test && npm run build # 15 tests, production build
```
