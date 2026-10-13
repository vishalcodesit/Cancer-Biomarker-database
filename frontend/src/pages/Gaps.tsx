import { Link, useSearchParams } from "react-router-dom";
import { exportUrl } from "../api/client";
import type { Cancer, GapResponse, Vocabularies } from "../api/types";
import { AsyncBlock, Badge, Card, Disclaimer, ExportButton, PageHeader, RoleBadge, ScorePill, ScoreStatusLabel, Select } from "../components/ui";
import { formatFrequency, formatPercent, humanize } from "../lib/format";
import { useApi } from "../lib/useApi";

export default function Gaps() {
  const [params, setParams] = useSearchParams();
  const get = (k: string, d = "") => params.get(k) ?? d;
  const update = (patch: Record<string, string>) => {
    const n = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) (v ? n.set(k, v) : n.delete(k));
    setParams(n, { replace: true });
  };
  const filters = { cancer_id: get("cancer_id"), role: get("role"), flag: get("flag") };
  const cancers = useApi<Cancer[]>("/cancers");
  const vocab = useApi<Vocabularies>("/meta/vocabularies");
  const gaps = useApi<GapResponse>("/gaps", {
    ...filters, min_publications: get("min_publications", "2"), sort: get("sort", "curation_priority"), order: get("order", "desc"),
  });

  return (
    <div>
      <PageHeader title="Evidence-Gap Analysis"
        subtitle="Identifies associations whose recorded evidence is thin, narrow, inappropriate for the claimed role, or inconsistent, and ranks them into a curation work list weighted by how common the alteration is in tumours."
        actions={<ExportButton href={exportUrl("gaps", filters)} />} />

      <AsyncBlock state={gaps}>
        {(g) => (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Object.entries(g.summary).map(([flag, n]) => (
                <button key={flag} onClick={() => update({ flag: get("flag") === flag ? "" : flag })} aria-pressed={get("flag") === flag}
                  title={g.flag_descriptions[flag]}
                  className={`rounded-xl border bg-white p-3 text-left shadow-sm transition ${get("flag") === flag ? "border-teal-brand ring-2 ring-teal-brand/30" : "border-slate-200 hover:border-navy-200"}`}>
                  <div className="tabular text-xl font-semibold text-navy-900">{n}</div>
                  <div className="text-xs font-medium text-slate-600">{humanize(flag)}</div>
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-5">
              <Select label="Gap type" value={get("flag")} onChange={(v) => update({ flag: v })} allLabel="Any gap"
                options={Object.keys(vocab.data?.gap_flags ?? {}).map((f) => ({ value: f, label: humanize(f) }))} />
              <Select label="Cancer" value={get("cancer_id")} onChange={(v) => update({ cancer_id: v })}
                options={(cancers.data ?? []).map((c) => ({ value: String(c.cancer_id), label: c.name }))} />
              <Select label="Role" value={get("role")} onChange={(v) => update({ role: v })}
                options={(vocab.data?.biomarker_roles ?? []).map((r) => ({ value: r, label: humanize(r) }))} />
              <Select label="Few-publication threshold" value={get("min_publications", "2")} onChange={(v) => update({ min_publications: v })} allLabel={null}
                options={["2", "3", "4", "5"].map((v) => ({ value: v, label: `< ${v} publications` }))} />
              <Select label="Sort by" value={`${get("sort", "curation_priority")}:${get("order", "desc")}`} allLabel={null}
                onChange={(v) => { const [sort, order] = v.split(":"); update({ sort, order }); }}
                options={[
                  { value: "curation_priority:desc", label: "Curation priority" },
                  { value: "gap_severity:desc", label: "Most severe gaps" },
                  { value: "tcga_frequency:desc", label: "Most common in tumours" },
                  { value: "gap_count:desc", label: "Most gaps first" },
                  { value: "overall_score:asc", label: "Lowest score first" },
                  { value: "n_publications:asc", label: "Fewest publications" },
                  { value: "n_sources:asc", label: "Fewest sources" },
                  { value: "name:asc", label: "Biomarker name" },
                ]} />
            </div>

            {get("flag") && <p className="text-sm text-slate-600"><strong>{humanize(get("flag"))}:</strong> {g.flag_descriptions[get("flag")]}</p>}
            {get("flag") === "role_evidence_mismatch" && (
              <Card title="Study designs that can support each role (curation heuristic)">
                <ul className="grid gap-1 text-sm sm:grid-cols-2">
                  {Object.entries(g.role_evidence_expectations).map(([role, designs]) => (
                    <li key={role}><RoleBadge role={role} /> <span className="text-slate-600">{designs.map(humanize).join(", ")}</span></li>
                  ))}
                </ul>
              </Card>
            )}
            <p className="text-xs text-slate-500">
              Curation priority = gap severity × (1 + 4 × TCGA frequency, capped at 50%). Severity points:{" "}
              {Object.entries(g.severity).map(([f, n]) => `${humanize(f)} ${n}`).join(" · ")}.
            </p>

            <Card title={`${g.total} of ${g.n_associations} associations with gaps`} bodyClass="p-0">
              {g.items.length === 0 ? <p className="p-6 text-center text-sm text-slate-500">No associations match.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                      <tr><th className="px-3 py-2">Association</th><th className="px-3 py-2">Role</th><th className="px-3 py-2 text-right">Priority</th>
                        <th className="px-3 py-2 text-right">Severity</th><th className="px-3 py-2 text-right">TCGA</th><th className="px-3 py-2 text-right">Pubs</th>
                        <th className="px-3 py-2 text-right">Sources</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Coverage</th><th className="px-3 py-2">Gaps</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {g.items.map((r) => (
                        <tr key={r.association_id} className="align-top hover:bg-slate-50">
                          <td className="px-3 py-2">
                            <Link to={`/associations/${r.association_id}`} className="font-medium text-navy-700 hover:underline">{r.biomarker_name}</Link>
                            <div className="text-xs text-slate-500">{r.cancer_name}</div>
                          </td>
                          <td className="px-3 py-2"><RoleBadge role={r.biomarker_role} /></td>
                          <td className="tabular px-3 py-2 text-right font-semibold text-navy-900">{r.curation_priority.toFixed(1)}</td>
                          <td className="tabular px-3 py-2 text-right">{r.gap_severity}</td>
                          <td className="tabular px-3 py-2 text-right" title={r.prevalence_basis ? humanize(r.prevalence_basis) : "Not applicable to this biomarker type"}>
                            {r.tcga_frequency === null ? <span className="text-slate-400">n/a</span> : formatFrequency(r.tcga_frequency)}</td>
                          <td className="tabular px-3 py-2 text-right">{r.n_publications}</td>
                          <td className="tabular px-3 py-2 text-right">{r.n_sources}</td>
                          <td className="space-y-1 px-3 py-2"><ScorePill score={r.overall_score} status={r.score_status} /><div><ScoreStatusLabel status={r.score_status} /></div></td>
                          <td className="tabular px-3 py-2">{formatPercent(r.evidence_coverage)}</td>
                          <td className="px-3 py-2"><div className="flex max-w-xs flex-wrap gap-1">
                            {r.flags.map((f) => <Badge key={f} title={f === "role_evidence_mismatch" && r.details.recorded_designs
                                ? `${g.flag_descriptions[f]} Recorded: ${(r.details.recorded_designs as string[]).map(humanize).join(", ")}.` : g.flag_descriptions[f]}
                              className={(g.severity[f] ?? 0) >= 3 ? "bg-red-50 text-red-800 ring-red-200" : "bg-amber-50 text-amber-900 ring-amber-200"}>{humanize(f)}</Badge>)}
                          </div></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
            <p className="text-xs text-slate-500">
              Gaps describe this database's recorded evidence only. Absence of a record here does not mean absence of evidence in the literature.
              Conflicting flags are raised only from explicitly curated annotations.
            </p>
            <Disclaimer />
          </div>
        )}
      </AsyncBlock>
    </div>
  );
}
