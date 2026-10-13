# Project guide: how the code fits together

A tour for reviewers and presenters. Each section answers "where does this happen?" with the file and function to
open. Line numbers refer to version 1.1.

## 1. The five-minute picture

```
public APIs --(scripts/*.py)--> curated CSVs --(importer)--> database --(services)--> REST API --> React UI
```

* Curation is offline and reproducible: scripts verify or fetch data from public APIs and write CSVs.
* The application never calls external APIs at run time. It reads only its own database, so a demo works offline.
* All business logic lives in the backend services; the frontend only displays what the API returns.

## 2. Follow one request end to end

Example: opening a biomarker page in the browser.

1. `frontend/src/pages/BiomarkerDetail.tsx` calls `useApi("/biomarkers/{id}")` (`frontend/src/lib/useApi.ts`), which
   fetches `/api/biomarkers/{id}`. Vite proxies `/api` to the FastAPI server (`frontend/vite.config.ts`).
2. `backend/app/routers/catalog.py`, `get_biomarker`, validates the path parameter and calls the service.
3. `backend/app/services/queries.py`, `biomarker_detail`, loads the biomarker with its genes, proteins, pathways and
   associations in a few `selectinload` queries (no N+1), then serialises them. For each association it attaches the
   stored score (`services/scores.py`, `current_score`), the CIViC benchmark (`benchmark_dict`) and the TCGA
   frequency (`services/prevalence.py`, `association_prevalence`).
4. Errors become `{"error": {...}}` through the handlers in `backend/app/main.py`.
5. The page renders the evidence cards (`components/EvidenceList.tsx`), the score breakdown
   (`components/ScoreBreakdown.tsx`) and the external context panel (`components/genomic.tsx`).

## 3. Where each feature lives

| Feature | Backend | Frontend |
|---|---|---|
| Schema (18 tables) | `app/models.py`; migrations in `alembic/versions/` | |
| SQL views | `app/views.py`, migration `0003_sql_views.py` | |
| Controlled vocabularies | `app/vocab.py` (used by CHECK constraints, validators and the UI) | `/api/meta/vocabularies` |
| CSV import and validation | `app/services/importer.py`: row models, `import_dataframe` (atomic per file), upsert handlers `_h_*` | `pages/ImportPage.tsx` |
| Evidence-support score | `app/scoring.py` (pure): components, `combine` (missing-data rule), `compute_score` | `components/ScoreBreakdown.tsx`, `pages/Methodology.tsx` |
| Original score 1.0.0 | `app/scoring_legacy.py` (frozen, used only for comparison) | Score Validation, section 3 |
| Scoring against the DB | `app/services/scores.py`: `supports_role`, `evidence_items`, `recompute_all`, `version_comparison` | |
| Gap analysis | `app/services/gaps.py`: `GAP_SEVERITY`, `ROLE_EVIDENCE_EXPECTATIONS`, `analyse_association` | `pages/Gaps.tsx` |
| TCGA frequencies and priority | `app/services/prevalence.py`: `load_counts` (pooling), `wilson_interval`, `curation_priority`, `discordance` | `pages/Prevalence.tsx`, `components/genomic.tsx` |
| Weight robustness | `app/robustness.py` (pure): `dirichlet`, `average_ranks`, `spearman`, `analyse` | `pages/Validation.tsx`, section 2 |
| CIViC validation | `app/services/validation.py`: `civic_concordance`, `permutation_p_value`, `bootstrap_ci` | `pages/Validation.tsx`, section 1 |
| SQL report catalogue | `app/services/analytics.py`: `REPORTS`, `run_report` | `pages/Analytics.tsx` |
| Write protection | `app/security.py`, `require_admin` | admin token field on the import page |
| Configuration | `app/config.py` (validates that weights sum to 1) and `backend/.env` | |

## 4. The scoring pipeline in detail

1. `services/scores.py`, `evidence_items`, turns each evidence row into an `EvidenceItem`: a publication key (PMID or
   DOI, so duplicates collapse), the source name, the study design, the consistency annotation, and `role_support`.
   `supports_role` is true when the row cites a publication or declares a design; KEGG membership rows have neither.
2. `scoring.py`, `compute_score`, computes the four components on distinct values: P from distinct publications,
   D from distinct supporting sources, T from distinct designs (noisy-OR), C from curated annotations only. A
   component with no input is `None`, never 0.
3. `scoring.py`, `combine`, applies the missing-data rule: complete, provisional (renormalised over observed weights
   when at least 50% of the weight is observed) or insufficient (no score).
4. `services/scores.py`, `recompute_all`, upserts one `evidence_score` row per association for the current version
   (`UNIQUE(association_id, scoring_version)` in `models.py`).

## 5. How TCGA frequencies are computed

1. `scripts/fetch_prevalence.py` calls cBioPortal for 5 TCGA PanCancer Atlas studies and writes raw counts per gene,
   cohort and alteration type. A gene absent from the Mutated Genes table is a measured 0 (the cohorts are
   whole-exome), not a missing value.
2. The importer loads `cohorts.csv` and `genomic_prevalence.csv`, enforcing `0 <= altered <= profiled > 0`.
3. `services/prevalence.py`, `load_counts`, sums altered and profiled counts over a cancer's cohorts (NSCLC = LUAD +
   LUSC). The SQL view `v_tcga_frequency` does the same in SQL; a test checks that both agree.
4. `association_prevalence` returns a frequency only when the biomarker has a curated `prevalence_basis` and exactly
   one gene, so expression, germline, fusion and signature biomarkers never get a misleading number.

## 6. How the validation works

* CIViC (`scripts/fetch_civic.py`): for each association, accepted CIViC evidence items are matched on gene (fusion
  features such as `EML4::ALK` are split into partners), disease-name rules, evidence type mapped to role, direction
  SUPPORTS, and for variant-specific biomarkers a curated keyword (for example `t790m`). The best level and counts
  are stored in `external_benchmark`. `services/validation.py` computes Spearman rho with tie-aware ranks, a seeded
  two-sided permutation p-value and a bootstrap confidence interval.
* Robustness (`app/robustness.py`): 1,000 weight vectors drawn from Dirichlet(1,1,1,1) (uniform on the simplex);
  for each, all complete associations are re-scored with the same `combine` rule and re-ranked. Reported: Spearman
  correlation with the baseline ranking, top-10 retention, per-association 5th to 95th percentile rank, and a
  one-component-at-a-time ablation. Seeded, so results are reproducible.

## 7. Database guarantees worth pointing at

* Foreign keys are enforced on SQLite too: `app/database.py` turns on `PRAGMA foreign_keys=ON` for every connection.
* Duplicate prevention: natural-key UNIQUE constraints plus importer upserts; re-importing inserts nothing (tested).
* Imports are atomic per file: any invalid row rolls back the whole file and the report lists row numbers.
* Every ORDER BY ends with a unique, collation-independent key, so SQLite and PostgreSQL return identical results
  (verified on all 190 read requests).

## 8. Running the checks yourself

```bash
cd backend
python -m pytest -q                    # 80 tests in about 2 seconds
python -m scripts.init_db --reset      # rebuild the database from the CSVs
uvicorn app.main:app --port 8000       # then open http://127.0.0.1:8000/docs
cd ../frontend && npm test && npm run dev
```

Suggested demo route: Dashboard, a biomarker page (KRAS codon 12/13: evidence, score breakdown, TCGA frequency, CIViC
level), Evidence Gaps sorted by curation priority, Evidence vs Prevalence, Score Validation, Scoring Method, and one
SQL Analytics report with its SQL visible.
