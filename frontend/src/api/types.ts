export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Link {
  label: string;
  url: string;
}

export interface BiomarkerBrief {
  biomarker_id: number;
  biomarker_code: string;
  name: string;
  biomarker_type: string;
  prevalence_basis?: string | null;
}

export interface CancerBrief {
  cancer_id: number;
  code: string;
  name: string;
}

export interface GeneBrief {
  gene_id: number;
  official_symbol: string;
  full_name: string | null;
  ncbi_gene_id: number | null;
  hgnc_id?: string | null;
}

export interface ProteinBrief {
  protein_id: number;
  accession: string;
  name: string;
}

export interface PathwayBrief {
  pathway_id: number;
  pathway_name: string;
  pathway_database: string;
  external_identifier: string;
  source_url: string | null;
}

export interface Publication {
  publication_id: number;
  pmid: string | null;
  doi: string | null;
  title: string;
  authors: string | null;
  publication_year: number | null;
  journal: string | null;
  source_url: string | null;
}

export type ScoreStatus = "complete" | "provisional" | "insufficient";

export interface Score {
  publication_support: number | null;
  source_diversity: number | null;
  evidence_type: number | null;
  consistency: number | null;
  overall_score: number | null;
  evidence_coverage: number;
  score_status: ScoreStatus;
  missing_components: string[];
  n_publications: number;
  n_sources: number;
  scoring_version: string;
  calculated_at?: string;
}

export interface Evidence {
  evidence_id: number;
  evidence_type: string | null;
  source_name: string;
  source_record_id: string | null;
  evidence_summary: string | null;
  consistency_annotation: string | null;
  retrieved_at: string | null;
  source_url: string | null;
  publication: Publication | null;
}

/** TCGA frequency of the alteration that defines a biomarker, pooled over the cancer's cohorts. */
export interface TcgaFrequency {
  gene_symbol?: string;
  alteration_type: string;
  basis?: string;
  upper_bound?: boolean;
  altered_cases: number;
  profiled_cases: number;
  frequency: number;
  ci95_low: number;
  ci95_high: number;
  cohorts: string[];
  source?: string;
}

export interface CivicBenchmark {
  source: string;
  best_evidence_level: string | null;
  n_items: number;
  n_shared_publications: number;
  matched_on: string | null;
  retrieved_at: string | null;
}

export interface Association {
  association_id: number;
  biomarker: BiomarkerBrief;
  cancer: CancerBrief;
  biomarker_role: string;
  association_description: string | null;
  source_status: string;
  score: Score | null;
  variants: { variant_id: number; variant_identifier: string }[];
  n_evidence: number;
  n_publications: number;
  civic?: CivicBenchmark | null;
  tcga?: TcgaFrequency | null;
  evidence?: Evidence[];
}

export interface BiomarkerListItem extends BiomarkerBrief {
  gene_symbols: string[];
  cancers: string[];
  roles: string[];
  n_associations: number;
  n_publications: number;
  max_score: number | null;
  has_incomplete_score: boolean;
}

export interface Variant {
  variant_id: number;
  variant_identifier: string;
  gene: GeneBrief;
  protein_change: string | null;
  dbsnp_id: string | null;
  genome_assembly: string | null;
  chromosome: string | null;
  position: number | null;
  reference_allele: string | null;
  alternate_allele: string | null;
  clinical_or_research_annotation: string | null;
  source_identifier: string | null;
  links: Link[];
}

export interface BiomarkerDetail extends BiomarkerBrief {
  description: string | null;
  biological_function: string | null;
  external_identifier: string | null;
  genes: (GeneBrief & { description: string | null; links: Link[]; proteins: (ProteinBrief & { links: Link[] })[] })[];
  pathways: (PathwayBrief & { annotation_source: string | null })[];
  associations: Association[];
  variants: Variant[];
  publications: (Publication & { contexts: { cancer: string; role: string; evidence_type: string | null }[] })[];
  source_databases: { source_name: string; n_records: number }[];
}

export interface Cancer extends CancerBrief {
  tissue_origin: string | null;
  cancer_category: string | null;
  external_identifier: string | null;
  mondo_id?: string | null;
  icdo_topography?: string | null;
  gdc_project_id: string | null;
  description: string | null;
  n_biomarkers: number;
  n_associations: number;
  links: Link[];
}

export interface HistogramBin {
  bin: string;
  lower: number | null;
  count: number;
}

export interface Cohort {
  cohort_id: number;
  study_id: string;
  name: string;
  cancer_id: number;
  cancer_name: string;
  source_name: string;
  n_samples_mutation: number | null;
  n_samples_cna: number | null;
  citation: string | null;
  source_url: string | null;
  retrieved_at: string | null;
}

export interface CancerDetail extends Omit<Cancer, "n_biomarkers" | "n_associations"> {
  cohorts: Cohort[];
  top_altered_genes: (TcgaFrequency & { gene_id: number; gene_symbol: string })[];
  associations: Association[];
  role_distribution: { role: string; count: number }[];
  genes: (GeneBrief & { biomarkers: string[] })[];
  pathways: (PathwayBrief & { n_gene_links: number })[];
  variants: { variant_id: number; variant_identifier: string; biomarker: string }[];
  publications: (Publication & { biomarkers: string[] })[];
  score_distribution: HistogramBin[];
}

export interface CompareEntry extends BiomarkerBrief {
  a: { role: string; score: number | null; score_status: string | null; association_id: number }[];
  b: { role: string; score: number | null; score_status: string | null; association_id: number }[];
}

export interface CompareResult {
  cancer_a: CancerBrief;
  cancer_b: CancerBrief;
  shared: CompareEntry[];
  only_a: CompareEntry[];
  only_b: CompareEntry[];
}

export interface PublicationListItem extends Publication {
  biomarkers: string[];
  biomarker_links: [number, string][];
  cancers: string[];
  evidence_types: string[];
  source_names: string[];
  summaries: { biomarker: string; cancer: string; role: string; summary: string | null; consistency: string | null }[];
}

export interface DashboardStats {
  totals: Record<string, number>;
  by_role: { role: string; count: number }[];
  by_cancer: { cancer_id: number; cancer: string; count: number }[];
  by_evidence_type: { evidence_type: string; count: number }[];
  by_biomarker_type: { biomarker_type: string; count: number }[];
  top_biomarkers: { biomarker_id: number; name: string; n_cancers: number; n_publications: number }[];
  score_status: { status: ScoreStatus; count: number }[];
  score_distribution: HistogramBin[];
}

export interface GapItem {
  association_id: number;
  biomarker_id: number;
  biomarker_name: string;
  biomarker_code: string;
  cancer_id: number;
  cancer_name: string;
  biomarker_role: string;
  source_status: string;
  n_evidence: number;
  n_publications: number;
  n_sources: number;
  overall_score: number | null;
  score_status: ScoreStatus | null;
  evidence_coverage: number | null;
  flags: string[];
  gap_count: number;
  gap_severity: number;
  n_context_records: number;
  tcga_frequency: number | null;
  prevalence_basis: string | null;
  curation_priority: number;
  details: Record<string, unknown>;
}

export interface GapResponse {
  summary: Record<string, number>;
  flag_descriptions: Record<string, string>;
  severity: Record<string, number>;
  role_evidence_expectations: Record<string, string[]>;
  n_associations: number;
  total: number;
  items: GapItem[];
}

export interface ReportParam {
  name: string;
  type: "int" | "float" | "cancer";
  default: number | null;
  description: string;
}

export interface CatalogueEntry {
  key: string;
  title: string;
  description: string;
  sql: string;
  params: ReportParam[];
  concepts: string[];
}

export interface ReportResult {
  key: string;
  title: string;
  columns: string[];
  rows: Record<string, string | number | null>[];
  params: Record<string, unknown>;
}

export interface NetworkNode {
  id: string;
  label: string;
  type: "biomarker" | "cancer" | "gene" | "protein" | "pathway" | "publication" | "variant";
  entity_id: number;
}

export interface NetworkData {
  nodes: NetworkNode[];
  edges: { source: string; target: string; label: string }[];
}

export interface Vocabularies {
  biomarker_types: string[];
  biomarker_roles: string[];
  evidence_types: string[];
  consistency_values: string[];
  source_statuses: string[];
  gap_flags: Record<string, string>;
  import_entities: string[];
}

export interface Methodology {
  scoring_version: string;
  formula: string;
  components: Record<string, string>;
  evidence_type_rubric: Record<string, number>;
  missing_data: string;
  disclaimer: string;
  weights: Record<string, number>;
  publication_cap: number;
  min_coverage: number;
  breadth_discount: number;
  changes_from_previous_version: string[];
}

export interface ImportReport {
  entity: string;
  rows_total: number;
  inserted: number;
  updated: number;
  unchanged: number;
  errors: { row: number; field: string | null; message: string }[];
  dry_run: boolean;
  ok: boolean;
}

export interface DiscordanceItem extends TcgaFrequency {
  association_id: number;
  biomarker_id: number;
  biomarker_name: string;
  biomarker_code: string;
  cancer_name: string;
  biomarker_role: string;
  overall_score: number;
  score_status: ScoreStatus;
  quadrant: "established" | "under_curated" | "niche_supported" | "rare_thin";
}

export interface Discordance {
  score_threshold: number;
  common_threshold: number;
  quadrant_descriptions: Record<string, string>;
  quadrant_counts: Record<string, number>;
  n_plotted: number;
  n_not_applicable: number;
  items: DiscordanceItem[];
  caveats: string[];
}

export interface RobustnessItem {
  association_id: number;
  biomarker_id: number;
  biomarker_name: string;
  cancer_name: string;
  biomarker_role: string;
  baseline_score: number;
  baseline_rank: number;
  median_rank: number;
  rank_p05: number;
  rank_p95: number;
  rank_interval_width: number;
  share_in_top_k: number;
}

export interface Robustness {
  n_ranked: number;
  n_excluded_incomplete: number;
  draws: number;
  seed: number;
  top_k: number;
  weight_distribution: string;
  spearman_mean: number | null;
  spearman_p05: number | null;
  top_k_retention_mean: number | null;
  ablation: { dropped_component: string; spearman_vs_baseline: number; top_k_retained: number }[];
  items: RobustnessItem[];
  baseline_weights: Record<string, number>;
}

export interface CivicValidation {
  benchmark: string;
  n_associations: number;
  n_covered: number;
  n_paired: number;
  spearman_rho: number | null;
  permutation_p_value: number | null;
  bootstrap_ci95: [number, number] | null;
  mean_score_by_level: { level: string; meaning: string; n: number; mean_score: number; min_score: number; max_score: number }[];
  version_check: { spearman_rho_v1_0_0: number | null; difference_ci95: [number, number] | null; explanation: string } | null;
  coverage_by_biomarker_type: { biomarker_type: string; covered: number; not_covered: number }[];
  publications_shared_with_civic: { associations_sharing_at_least_one_pmid: number; total_shared_pmids: number };
  items: {
    association_id: number; biomarker_name: string; biomarker_code: string; biomarker_type: string; cancer_name: string;
    biomarker_role: string; overall_score: number | null; score_status: ScoreStatus | null; civic_level: string | null;
    civic_items: number; shared_publications: number; matched_on: string | null;
  }[];
  interpretation_notes: string[];
}

export interface VersionComparison {
  from_version: string;
  to_version: string;
  n_associations: number;
  n_changed: number;
  mean_delta: number | null;
  items: {
    association_id: number; biomarker_name: string; biomarker_code: string; cancer_name: string; biomarker_role: string;
    score_v1_0_0: number | null; score_v1_1_0: number | null; status_v1_0_0: string; status_v1_1_0: string;
    rank_v1_0_0: number | null; rank_v1_1_0: number | null; delta: number | null; reasons: string[];
  }[];
}
