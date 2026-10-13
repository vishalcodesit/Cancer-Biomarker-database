import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { GitCompare } from "lucide-react";
import type { Cancer, CancerDetail as Detail, CompareEntry, CompareResult, NetworkData } from "../api/types";
import { ChartCard, HBar, VBar, histogramData } from "../components/charts";
import { NetworkGraph } from "../components/NetworkGraph";
import {
  AsyncBlock, Badge, Card, ExportButton, ExternalLink, KeyValue, PageHeader, RoleBadge, ScorePill,
  ScoreStatusLabel, Select, Table,
} from "../components/ui";
import { exportUrl } from "../api/client";
import { CivicBadge, FrequencyLabel } from "../components/genomic";
import { humanize } from "../lib/format";
import { useApi } from "../lib/useApi";

export function CancerList() {
  const cancers = useApi<Cancer[]>("/cancers");
  return (
    <div>
      <PageHeader title="Cancer Explorer" subtitle="Select a cancer type to explore its biomarkers, genes, pathways and evidence, or compare two cancers." />
      <CompareTool cancers={cancers.data ?? []} />
      <AsyncBlock state={cancers}>
        {(list) => (
          <div className="grid gap-4 md:grid-cols-2">
            {list.map((c) => (
              <Link key={c.cancer_id} to={`/cancers/${c.cancer_id}`}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-teal-brand">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-lg font-semibold text-navy-900">{c.name}</h2>
                  <span className="flex flex-wrap justify-end gap-1">
                    <Badge>{c.external_identifier}</Badge>
                    {c.mondo_id && <Badge>{c.mondo_id}</Badge>}
                    {c.icdo_topography && <Badge title="ICD-O-3 topography">ICD-O {c.icdo_topography}</Badge>}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{c.description}</p>
                <div className="mt-3 flex gap-6 text-sm">
                  <span><strong className="tabular">{c.n_biomarkers}</strong> biomarkers</span>
                  <span><strong className="tabular">{c.n_associations}</strong> associations</span>
                  <span className="text-slate-500">{c.tissue_origin}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </AsyncBlock>
    </div>
  );
}

function CompareTool({ cancers }: { cancers: Cancer[] }) {
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "";
  const b = params.get("b") ?? "";
  const ready = a && b && a !== b;
  const cmp = useApi<CompareResult>(ready ? "/cancers/compare" : null, { a, b });
  const opts = cancers.map((c) => ({ value: String(c.cancer_id), label: c.name }));
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };

  const roles = (e: CompareEntry, side: "a" | "b") => (
    <div className="flex flex-wrap gap-1">{e[side].map((r) => <span key={r.association_id} className="inline-flex items-center gap-1"><RoleBadge role={r.role} /><ScorePill score={r.score} status={r.score_status as never} /></span>)}</div>
  );
  return (
    <Card title={<span className="inline-flex items-center gap-2"><GitCompare className="h-4 w-4" aria-hidden /> Compare two cancer types</span>} className="mb-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Cancer A" value={a} onChange={(v) => set("a", v)} options={opts} allLabel="Select…" />
        <Select label="Cancer B" value={b} onChange={(v) => set("b", v)} options={opts} allLabel="Select…" />
      </div>
      {a && b && a === b && <p className="mt-3 text-sm text-amber-700">Choose two different cancers.</p>}
      {ready && (
        <div className="mt-4">
          <AsyncBlock state={cmp}>
            {(r) => (
              <div className="grid gap-4 lg:grid-cols-3">
                {([["Shared biomarkers", r.shared, true], [`Only in ${r.cancer_a.name}`, r.only_a, false], [`Only in ${r.cancer_b.name}`, r.only_b, false]] as const).map(([title, rows, shared], idx) => (
                  <div key={title} className="rounded-lg border border-slate-200">
                    <h3 className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-sm font-semibold text-navy-800">{title} <span className="text-slate-500">({rows.length})</span></h3>
                    {rows.length === 0 ? <p className="p-3 text-sm text-slate-500">None recorded.</p> : (
                      <ul className="divide-y divide-slate-100">
                        {rows.map((e) => (
                          <li key={e.biomarker_id} className="space-y-1 p-3 text-sm">
                            <Link to={`/biomarkers/${e.biomarker_id}`} className="font-medium text-navy-700 hover:underline">{e.name}</Link>
                            {shared ? (<>
                              <div className="text-xs text-slate-500">{r.cancer_a.name}</div>{roles(e, "a")}
                              <div className="text-xs text-slate-500">{r.cancer_b.name}</div>{roles(e, "b")}
                            </>) : roles(e, idx === 1 ? "a" : "b")}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </AsyncBlock>
        </div>
      )}
    </Card>
  );
}

export function CancerDetail() {
  const { id } = useParams();
  const state = useApi<Detail>(`/cancers/${id}`);
  const net = useApi<NetworkData>("/network", { cancer_id: id });
  const [role, setRole] = useState("");
  const navigate = useNavigate();

  return (
    <AsyncBlock state={state}>
      {(c) => {
        const assocs = role ? c.associations.filter((a) => a.biomarker_role === role) : c.associations;
        return (
          <div className="space-y-5">
            <PageHeader title={c.name} subtitle={c.description}
              actions={<ExportButton href={exportUrl("associations", { cancer_id: c.cancer_id })} label="Export associations" />} />
            <Card title="Overview">
              <KeyValue items={[
                ["Tissue origin", c.tissue_origin], ["Category", c.cancer_category],
                ["Disease Ontology", c.external_identifier], ["Mondo", c.mondo_id],
                ["ICD-O-3 topography", c.icdo_topography], ["GDC project", c.gdc_project_id],
                ["TCGA cohorts (cBioPortal)", c.cohorts.length === 0 ? "None" : (
                  <ul className="space-y-0.5">{c.cohorts.map((k) => (
                    <li key={k.study_id}>
                      {k.source_url ? <ExternalLink href={k.source_url}>{k.name}</ExternalLink> : k.name}
                      <span className="tabular text-xs text-slate-500"> · {k.n_samples_mutation} sequenced, {k.n_samples_cna} CNA-profiled</span>
                    </li>))}
                  </ul>)],
                ["Links", <span className="flex flex-wrap gap-3">{c.links.map((l) => <ExternalLink key={l.url} href={l.url}>{l.label}</ExternalLink>)}</span>],
              ]} />
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title="Biomarker roles" valueLabel="Associations"
                data={c.role_distribution.map((r) => ({ label: humanize(r.role), value: r.count }))}>
                <HBar valueLabel="Associations" data={c.role_distribution.map((r) => ({ label: humanize(r.role), value: r.count, id: r.role }))}
                  onSelect={(d) => setRole(String(d.id))} />
              </ChartCard>
              <ChartCard title="Evidence-support score distribution" valueLabel="Associations" data={histogramData(c.score_distribution)}>
                <VBar valueLabel="Associations" data={histogramData(c.score_distribution)} />
              </ChartCard>
            </div>

            {c.top_altered_genes.length > 0 && (
              <ChartCard title="Most frequently altered curated genes in TCGA (% of profiled tumours)" valueLabel="% altered"
                data={c.top_altered_genes.map((g) => ({ label: `${g.gene_symbol} · ${humanize(g.alteration_type)}`, value: Number((g.frequency * 100).toFixed(1)) }))}>
                <HBar valueLabel="% altered"
                  data={c.top_altered_genes.map((g) => ({ label: `${g.gene_symbol} · ${humanize(g.alteration_type)}`, value: Number((g.frequency * 100).toFixed(1)), id: g.gene_id }))}
                  onSelect={(d) => navigate(`/genes/${d.id}`)} />
                <p className="mt-2 text-xs text-slate-500">Counts pooled over {c.cohorts.map((k) => k.study_id).join(" + ")}; only the
                  genes curated in this database are shown, so this is not a genome-wide ranking.</p>
              </ChartCard>
            )}

            <Card title={`Associated biomarkers (${assocs.length})`} bodyClass="p-0"
              actions={<div className="w-44"><Select label="" value={role} onChange={setRole} allLabel="All roles"
                options={c.role_distribution.map((r) => ({ value: r.role, label: humanize(r.role) }))} /></div>}>
              <Table head={["Biomarker", "Role", "Publications", "Score", "Status", "TCGA frequency", "CIViC", ""]} caption="Associated biomarkers">
                {assocs.map((a) => (
                  <tr key={a.association_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2"><Link to={`/biomarkers/${a.biomarker.biomarker_id}`} className="font-medium text-navy-700 hover:underline">{a.biomarker.name}</Link></td>
                    <td className="px-3 py-2"><RoleBadge role={a.biomarker_role} /></td>
                    <td className="tabular px-3 py-2">{a.n_publications}</td>
                    <td className="px-3 py-2"><ScorePill score={a.score?.overall_score} status={a.score?.score_status} /></td>
                    <td className="px-3 py-2"><ScoreStatusLabel status={a.score?.score_status} /></td>
                    <td className="px-3 py-2">{a.tcga ? <FrequencyLabel t={a.tcga} compact /> : <span className="text-xs text-slate-400" title="Not applicable to this biomarker type">n/a</span>}</td>
                    <td className="px-3 py-2"><CivicBadge civic={a.civic} /></td>
                    <td className="px-3 py-2 text-right"><Link to={`/associations/${a.association_id}`} className="text-xs text-teal-brand hover:underline">Evidence</Link></td>
                  </tr>
                ))}
              </Table>
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <Card title={`Related genes (${c.genes.length})`}>
                <div className="flex flex-wrap gap-1.5">
                  {c.genes.map((g) => (
                    <Link key={g.gene_id} to={`/genes/${g.gene_id}`} title={g.biomarkers.join(", ")}
                      className="rounded-md border border-slate-200 px-2 py-0.5 font-mono text-xs text-navy-700 hover:border-teal-brand">{g.official_symbol}</Link>
                  ))}
                </div>
              </Card>
              <Card title={`Related pathways (${c.pathways.length})`}>
                <ul className="space-y-1 text-sm">
                  {c.pathways.map((p) => (
                    <li key={p.pathway_id} className="flex justify-between gap-2">
                      <Link to={`/pathways/${p.pathway_id}`} className="text-navy-700 hover:underline">{p.pathway_name}</Link>
                      <span className="tabular text-xs text-slate-500">{p.n_gene_links} gene link{p.n_gene_links === 1 ? "" : "s"}</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card title={`Variants (${c.variants.length})`}>
                {c.variants.length === 0 ? <p className="text-sm text-slate-500">None recorded.</p> : (
                  <ul className="space-y-1 text-sm">{c.variants.map((v) => (
                    <li key={`${v.variant_id}-${v.biomarker}`}><Link to={`/variants/${v.variant_id}`} className="font-mono text-navy-700 hover:underline">{v.variant_identifier}</Link> <span className="text-xs text-slate-500">· {v.biomarker}</span></li>
                  ))}</ul>
                )}
              </Card>
              <Card title={`Supporting publications (${c.publications.length})`} actions={<Link to={`/publications?cancer_id=${c.cancer_id}`} className="text-xs text-teal-brand hover:underline">Open in evidence explorer</Link>}>
                <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
                  {c.publications.map((p) => (
                    <li key={p.publication_id}>
                      {p.source_url ? <ExternalLink href={p.source_url}>{p.title}</ExternalLink> : p.title}
                      <div className="text-xs text-slate-500">{p.journal} {p.publication_year} · PMID {p.pmid} · {p.biomarkers.join(", ")}</div>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
            <Card title="Cancer → biomarker → gene network">
              <AsyncBlock state={net}>{(n) => <NetworkGraph data={n} height={520} />}</AsyncBlock>
            </Card>
          </div>
        );
      }}
    </AsyncBlock>
  );
}
