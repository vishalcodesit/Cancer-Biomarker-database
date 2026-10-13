import type { CivicBenchmark, TcgaFrequency } from "../api/types";
import { CIVIC_LEVELS, formatFrequency, humanize } from "../lib/format";
import { Badge } from "./ui";

/** TCGA alteration frequency with its 95% Wilson interval and raw counts; marks gene-level upper bounds. */
export function FrequencyLabel({ t, compact = false }: { t: TcgaFrequency; compact?: boolean }) {
  const bound = t.upper_bound ? "≤ " : "";
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5 text-sm" title={t.upper_bound
      ? "Gene-level frequency: an upper bound for this specific variant" : undefined}>
      <strong className="tabular text-navy-900">{bound}{formatFrequency(t.frequency)}</strong>
      {!compact && (
        <span className="tabular text-xs text-slate-500">
          95% CI {formatFrequency(t.ci95_low)}–{formatFrequency(t.ci95_high)} · {t.altered_cases}/{t.profiled_cases} tumours
        </span>
      )}
    </span>
  );
}

export function TcgaPanel({ t }: { t: TcgaFrequency | null | undefined }) {
  if (!t) {
    return <p className="text-xs text-slate-500">No gene-level TCGA frequency applies to this biomarker type.</p>;
  }
  return (
    <div className="space-y-1">
      <FrequencyLabel t={t} />
      <p className="text-xs text-slate-600">
        {humanize(t.alteration_type)} of {t.gene_symbol} in {t.cohorts.length > 1 ? `${t.cohorts.length} pooled ` : ""}TCGA
        PanCancer Atlas cohort{t.cohorts.length > 1 ? "s" : ""} (cBioPortal).
        {t.upper_bound && " Gene-level count, so an upper bound for this specific variant."}
      </p>
    </div>
  );
}

export function CivicBadge({ civic }: { civic: CivicBenchmark | null | undefined }) {
  if (!civic || !civic.best_evidence_level) {
    return <Badge title="No matching accepted CIViC evidence item">Not in CIViC</Badge>;
  }
  const lv = civic.best_evidence_level;
  return (
    <Badge className="bg-indigo-50 text-indigo-800 ring-indigo-200"
      title={`${civic.n_items} matching CIViC evidence item(s); ${civic.n_shared_publications} PMID(s) shared with this database. ${civic.matched_on ?? ""}`}>
      CIViC level {lv} · {CIVIC_LEVELS[lv]}
    </Badge>
  );
}
