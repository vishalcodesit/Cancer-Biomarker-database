import { Link } from "react-router-dom";
import type { CivicValidation, Robustness, RobustnessItem, VersionComparison } from "../api/types";
import { ChartCard, VBar } from "../components/charts";
import { AsyncBlock, Card, Disclaimer, PageHeader, RoleBadge, StatTile, Table } from "../components/ui";
import { CIVIC_LEVELS, humanize } from "../lib/format";
import { useApi } from "../lib/useApi";

/** One row of the rank-interval plot: a track from rank 1 to n, the 5th-95th percentile band and the baseline rank. */
export function RankInterval({ item, n }: { item: RobustnessItem; n: number }) {
  const pos = (r: number) => `${((r - 1) / Math.max(1, n - 1)) * 100}%`;
  const label = `Baseline rank ${item.baseline_rank}; 90% of weightings give rank ${item.rank_p05} to ${item.rank_p95}`;
  return (
    <div className="relative h-3 w-full rounded-full bg-slate-100" role="img" aria-label={label} title={label}>
      <div className="absolute top-0 h-3 rounded-full bg-chart-1-soft"
        style={{ left: pos(item.rank_p05), width: `calc(${pos(item.rank_p95)} - ${pos(item.rank_p05)})`, minWidth: "4px" }} />
      <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-chart-1"
        style={{ left: pos(item.baseline_rank) }} />
    </div>
  );
}

function CivicSection() {
  const state = useApi<CivicValidation>("/validation/civic");
  return (
    <AsyncBlock state={state}>
      {(v) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Spearman rho vs CIViC" value={v.spearman_rho?.toFixed(2) ?? "n/a"} />
            <StatTile label="Permutation p-value" value={v.permutation_p_value?.toFixed(3) ?? "n/a"} />
            <StatTile label="Bootstrap 95% CI" value={v.bootstrap_ci95 ? `${v.bootstrap_ci95[0].toFixed(2)} to ${v.bootstrap_ci95[1].toFixed(2)}` : "n/a"} />
            <StatTile label={`Benchmarked of ${v.n_associations}`} value={v.n_paired} />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard title="Mean evidence-support score by CIViC evidence level" valueLabel="Mean score"
              data={v.mean_score_by_level.map((l) => ({ label: `${l.level} · ${l.meaning} (n=${l.n})`, value: l.mean_score }))}>
              <VBar valueLabel="Mean score" height={240}
                data={v.mean_score_by_level.map((l) => ({ label: `${l.level} ${CIVIC_LEVELS[l.level]} (n=${l.n})`, value: l.mean_score }))} />
              <p className="mt-2 text-xs text-slate-500">
                CIViC levels are assigned by expert curators and are never used to compute the score, so agreement is an independent check.
              </p>
            </ChartCard>
            <Card title="Which biomarker types does CIViC cover?" bodyClass="p-0">
              <Table head={["Biomarker type", "In CIViC", "Not in CIViC", ""]} caption="CIViC coverage by biomarker type">
                {v.coverage_by_biomarker_type.map((c) => {
                  const total = c.covered + c.not_covered;
                  return (
                    <tr key={c.biomarker_type}>
                      <td className="px-3 py-1.5">{humanize(c.biomarker_type)}</td>
                      <td className="tabular px-3 py-1.5">{c.covered}</td>
                      <td className="tabular px-3 py-1.5">{c.not_covered}</td>
                      <td className="w-32 px-3 py-1.5">
                        <div className="flex h-2 overflow-hidden rounded-full bg-slate-200" role="img" aria-label={`${c.covered} of ${total} covered`}>
                          <div className="h-full bg-chart-1" style={{ width: `${(100 * c.covered) / total}%` }} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </Table>
              <p className="px-4 py-3 text-xs text-slate-600">
                Serum protein, methylation and genomic-signature markers have no CIViC coverage at all: quantitative support for the
                project's premise that genomic knowledge bases under-represent non-DNA biomarkers.
              </p>
            </Card>
          </div>
          {v.version_check && (
            <Card title="Did the 1.1.0 corrections change agreement with experts?">
              <p className="text-sm text-slate-700">
                Version 1.0.0 gave rho = {v.version_check.spearman_rho_v1_0_0?.toFixed(2)}; version 1.1.0 gives rho = {v.spearman_rho?.toFixed(2)}.
                {v.version_check.difference_ci95 && ` The 95% bootstrap interval for the difference (${v.version_check.difference_ci95[0].toFixed(2)} to ${v.version_check.difference_ci95[1].toFixed(2)}) includes zero, so the change is not statistically significant.`}
              </p>
              <p className="mt-2 text-sm text-slate-600">{v.version_check.explanation}</p>
            </Card>
          )}
          <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
            {v.interpretation_notes.map((n) => <li key={n}>{n}</li>)}
            <li>{v.publications_shared_with_civic.associations_sharing_at_least_one_pmid} associations share at least one PMID with
              CIViC ({v.publications_shared_with_civic.total_shared_pmids} shared PMIDs in total).</li>
          </ul>
        </div>
      )}
    </AsyncBlock>
  );
}

function RobustnessSection() {
  const state = useApi<Robustness>("/scores/robustness", { draws: 1000 });
  return (
    <AsyncBlock state={state}>
      {(r) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Mean rank correlation" value={r.spearman_mean?.toFixed(2) ?? "n/a"} />
            <StatTile label="5th percentile" value={r.spearman_p05?.toFixed(2) ?? "n/a"} />
            <StatTile label={`Top-${r.top_k} retained`} value={r.top_k_retention_mean !== null ? `${Math.round(r.top_k_retention_mean * 100)}%` : "n/a"} />
            <StatTile label="Weightings tested" value={r.draws.toLocaleString()} />
          </div>
          <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
            <Card title="Ablation: drop one component" bodyClass="p-0">
              <Table head={["Component removed", "Spearman", `Top-${r.top_k} kept`]} caption="Component ablation">
                {r.ablation.map((a) => (
                  <tr key={a.dropped_component}>
                    <td className="px-3 py-1.5">{humanize(a.dropped_component)}</td>
                    <td className="tabular px-3 py-1.5">{a.spearman_vs_baseline.toFixed(2)}</td>
                    <td className="tabular px-3 py-1.5">{Math.round(a.top_k_retained * 100)}%</td>
                  </tr>
                ))}
              </Table>
              <p className="px-4 py-3 text-xs text-slate-600">
                A component whose removal barely changes the ranking (Spearman close to 1) carries little information in the current data.
                Source diversity and consistency are in that position: almost all supporting evidence is from PubMed and almost all
                curated annotations are "supports". More independent sources and curated negative evidence would make them informative.
              </p>
            </Card>
            <Card title={`Rank stability of the ${r.n_ranked} fully scored associations`} bodyClass="p-0">
              <div className="max-h-[440px] overflow-y-auto">
                <Table head={["#", "Association", `Rank range across weightings (1 to ${r.n_ranked})`]} caption="Rank intervals">
                  {r.items.map((it) => (
                    <tr key={it.association_id}>
                      <td className="tabular px-3 py-1.5 text-xs text-slate-500">{it.baseline_rank}</td>
                      <td className="px-3 py-1.5">
                        <Link to={`/associations/${it.association_id}`} className="text-sm text-navy-700 hover:underline">{it.biomarker_name}</Link>
                        <div className="text-xs text-slate-500">{it.cancer_name} · {humanize(it.biomarker_role)} · score {it.baseline_score.toFixed(1)}</div>
                      </td>
                      <td className="w-1/2 px-3 py-1.5"><RankInterval item={it} n={r.n_ranked} />
                        <div className="tabular mt-0.5 text-[11px] text-slate-500">5th to 95th percentile: {it.rank_p05} to {it.rank_p95}</div></td>
                    </tr>
                  ))}
                </Table>
              </div>
            </Card>
          </div>
          <p className="text-xs text-slate-500">
            Weights drawn from {r.weight_distribution}; {r.n_excluded_incomplete} provisional or insufficient associations are excluded so
            missing-data renormalisation cannot affect the comparison. Seed {r.seed} (deterministic).
          </p>
        </div>
      )}
    </AsyncBlock>
  );
}

function VersionSection() {
  const state = useApi<VersionComparison>("/scores/comparison");
  return (
    <AsyncBlock state={state}>
      {(c) => (
        <Card title={`${c.n_changed} of ${c.n_associations} scores changed from ${c.from_version} to ${c.to_version} (mean change ${c.mean_delta})`} bodyClass="p-0">
          <div className="max-h-96 overflow-y-auto">
            <Table head={["Association", "Role", c.from_version, c.to_version, "Change", "Why"]} caption="Score version comparison">
              {c.items.filter((r) => r.delta !== null && Math.abs(r.delta) >= 0.005).map((r) => (
                <tr key={r.association_id}>
                  <td className="px-3 py-1.5"><Link to={`/associations/${r.association_id}`} className="text-navy-700 hover:underline">{r.biomarker_name}</Link>
                    <div className="text-xs text-slate-500">{r.cancer_name}</div></td>
                  <td className="px-3 py-1.5"><RoleBadge role={r.biomarker_role} /></td>
                  <td className="tabular px-3 py-1.5">{r.score_v1_0_0?.toFixed(1)}</td>
                  <td className="tabular px-3 py-1.5">{r.score_v1_1_0?.toFixed(1)}</td>
                  <td className="tabular px-3 py-1.5">{r.delta! > 0 ? "+" : ""}{r.delta?.toFixed(1)}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-600">{r.reasons.join("; ")}</td>
                </tr>
              ))}
            </Table>
          </div>
        </Card>
      )}
    </AsyncBlock>
  );
}

export default function Validation() {
  return (
    <div className="space-y-6">
      <PageHeader title="Score Validation"
        subtitle="Is the evidence-support score meaningful? Three checks: agreement with independent expert curation, sensitivity to the chosen weights, and an audit of what changed between scoring versions." />
      <Disclaimer />
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-navy-900">1. Agreement with expert curation (CIViC)</h2>
        <CivicSection />
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-navy-900">2. Robustness to the chosen weights</h2>
        <RobustnessSection />
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-navy-900">3. Version audit: original 1.0.0 vs corrected 1.1.0</h2>
        <VersionSection />
      </section>
    </div>
  );
}
