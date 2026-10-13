/** Formatting helpers shared across pages. */

const LABEL_OVERRIDES: Record<string, string> = {
  nsclc: "NSCLC",
  msi: "MSI",
  randomized_clinical_trial: "Randomized clinical trial",
  genomic_profiling: "Genomic profiling",
  copy_number_alteration: "Copy-number alteration",
  pending_curation: "Pending curation",
  curated_literature: "Curated literature",
  rna_transcript: "RNA transcript",
  epigenetic_methylation: "Epigenetic methylation",
  role_evidence_mismatch: "Role-evidence mismatch",
  somatic_mutation: "Somatic mutation",
  somatic_mutation_upper_bound: "Somatic mutation (gene-level upper bound)",
  deep_deletion: "Deep deletion",
  under_curated: "Common but thinly supported",
  niche_supported: "Rare but well supported",
  rare_thin: "Rare and thinly supported",
  established: "Common and well supported",
};

/** snake_case vocabulary value -> readable label. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  if (LABEL_OVERRIDES[value]) return LABEL_OVERRIDES[value];
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "n/a" : score.toFixed(1);
}

export function formatPercent(fraction: number | null | undefined): string {
  return fraction === null || fraction === undefined ? "n/a" : `${Math.round(fraction * 100)}%`;
}

export function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export const COMPONENT_LABELS: Record<string, { label: string; key: "P" | "D" | "T" | "C" }> = {
  publication_support: { label: "Publication support", key: "P" },
  source_diversity: { label: "Source diversity", key: "D" },
  evidence_type: { label: "Evidence type", key: "T" },
  consistency: { label: "Evidence consistency", key: "C" },
};

export const WEIGHT_KEYS: Record<string, string> = {
  publication_support: "publication_support",
  source_diversity: "source_diversity",
  evidence_type: "evidence_type",
  consistency: "consistency",
};

/** Fraction (0-1) -> percent with one decimal; frequencies below 0.1% keep two decimals so they never read as 0. */
export function formatFrequency(f: number | null | undefined): string {
  if (f === null || f === undefined) return "n/a";
  const pct = f * 100;
  if (pct > 0 && pct < 0.1) return `${pct.toFixed(2)}%`;
  return `${pct.toFixed(1)}%`;
}

/** CIViC evidence level -> short meaning shown next to the letter. */
export const CIVIC_LEVELS: Record<string, string> = {
  A: "Validated", B: "Clinical", C: "Case study", D: "Preclinical", E: "Inferential",
};

export const QUADRANT_ORDER = ["established", "under_curated", "niche_supported", "rare_thin"] as const;
