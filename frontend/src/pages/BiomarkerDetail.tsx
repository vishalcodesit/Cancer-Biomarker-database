import { Link, useParams } from "react-router-dom";
import type { Association, BiomarkerDetail as Detail, NetworkData } from "../api/types";
import { EvidenceList } from "../components/EvidenceList";
import { CivicBadge, TcgaPanel } from "../components/genomic";
import { NetworkGraph } from "../components/NetworkGraph";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import {
  AsyncBlock,
  Badge,
  Card,
  Disclaimer,
  ExternalLink,
  KeyValue,
  PageHeader,
  RoleBadge,
  SourceStatusBadge,
} from "../components/ui";
import { humanize } from "../lib/format";
import { useApi } from "../lib/useApi";

function AssociationCard({ a }: { a: Association }) {
  return (
    <Card
      title={<span className="flex flex-wrap items-center gap-2">
        <Link to={`/cancers/${a.cancer.cancer_id}`} className="hover:underline">{a.cancer.name}</Link>
        <RoleBadge role={a.biomarker_role} />
        <SourceStatusBadge status={a.source_status} />
      </span>}
      actions={<Link to={`/associations/${a.association_id}`} className="text-xs text-teal-brand hover:underline">Full evidence view</Link>}
    >
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-3">
          {a.association_description && <p className="text-sm text-slate-700">{a.association_description}</p>}
          {a.variants.length > 0 && (
            <p className="text-xs text-slate-600">Variants: {a.variants.map((v, i) => (
              <span key={v.variant_id}>{i > 0 && ", "}<Link className="font-mono text-teal-brand hover:underline" to={`/variants/${v.variant_id}`}>{v.variant_identifier}</Link></span>
            ))}</p>
          )}
          <EvidenceList evidence={a.evidence ?? []} />
        </div>
        <div className="space-y-3">
          <div className="rounded-lg bg-slate-50 p-3"><ScoreBreakdown score={a.score} /></div>
          <div className="space-y-2 rounded-lg border border-slate-200 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">External context</h3>
            <div><div className="mb-1 text-xs font-medium text-slate-600">Frequency in tumours (TCGA)</div><TcgaPanel t={a.tcga} /></div>
            <div><div className="mb-1 text-xs font-medium text-slate-600">Expert benchmark</div><CivicBadge civic={a.civic} /></div>
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function BiomarkerDetail() {
  const { id } = useParams();
  const state = useApi<Detail>(`/biomarkers/${id}`);
  const net = useApi<NetworkData>("/network", { biomarker_id: id });

  return (
    <AsyncBlock state={state}>
      {(b) => (
        <div className="space-y-5">
          <PageHeader title={b.name}
            subtitle={<span className="flex flex-wrap items-center gap-2"><span className="font-mono">{b.biomarker_code}</span>
              <Badge>{humanize(b.biomarker_type)}</Badge>
              {b.external_identifier && <Badge>{b.external_identifier}</Badge>}</span>} />

          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Overview" className="lg:col-span-2">
              <KeyValue items={[
                ["Description", b.description],
                ["Biological function", b.biological_function],
                ["Associated cancers", Array.from(new Set(b.associations.map((a) => a.cancer.name))).join(", ") || "None recorded"],
                ["Evidence sources", b.source_databases.map((s) => `${s.source_name} (${s.n_records})`).join(", ") || "None"],
              ]} />
            </Card>
            <Card title="Genes & proteins">
              {b.genes.length === 0 ? <p className="text-sm text-slate-500">Multi-gene or genome-wide signature; no single gene linked.</p> : (
                <ul className="space-y-3 text-sm">
                  {b.genes.map((g) => (
                    <li key={g.gene_id}>
                      <Link to={`/genes/${g.gene_id}`} className="font-mono font-semibold text-navy-700 hover:underline">{g.official_symbol}</Link>
                      <span className="text-slate-500"> · {g.full_name}</span>
                      <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs">
                        {g.links.map((l) => <ExternalLink key={l.url} href={l.url}>{l.label}</ExternalLink>)}
                        {g.proteins.map((p) => <Link key={p.protein_id} to={`/proteins/${p.protein_id}`} className="text-teal-brand hover:underline">UniProt {p.accession}</Link>)}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <h2 className="pt-2 text-lg font-semibold text-navy-900">Cancer associations & evidence</h2>
          {b.associations.map((a) => <AssociationCard key={a.association_id} a={a} />)}

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title={`Pathways (${b.pathways.length})`}>
              {b.pathways.length === 0 ? <p className="text-sm text-slate-500">No pathway links recorded.</p> : (
                <ul className="space-y-1.5 text-sm">
                  {b.pathways.map((p) => (
                    <li key={p.pathway_id} className="flex flex-wrap items-baseline justify-between gap-2">
                      <Link to={`/pathways/${p.pathway_id}`} className="text-navy-700 hover:underline">{p.pathway_name}</Link>
                      <span className="text-xs text-slate-500">{p.pathway_database} {p.external_identifier} · {p.annotation_source}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-slate-500">Database annotation: derived from KEGG gene membership of the linked gene(s).</p>
            </Card>
            <Card title={`Variants (${b.variants.length})`}>
              {b.variants.length === 0 ? <p className="text-sm text-slate-500">No variants recorded for this biomarker.</p> : (
                <ul className="space-y-1.5 text-sm">
                  {b.variants.map((v) => (
                    <li key={v.variant_id}>
                      <Link to={`/variants/${v.variant_id}`} className="font-mono text-navy-700 hover:underline">{v.variant_identifier}</Link>
                      <span className="text-xs text-slate-500"> {v.dbsnp_id ?? ""} {v.chromosome ? `chr${v.chromosome}:${v.position} ${v.reference_allele}>${v.alternate_allele} (${v.genome_assembly})` : "· coordinates not curated"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card title="Relationship network">
            <AsyncBlock state={net}>{(n) => <NetworkGraph data={n} />}</AsyncBlock>
          </Card>
          <Disclaimer />
        </div>
      )}
    </AsyncBlock>
  );
}
