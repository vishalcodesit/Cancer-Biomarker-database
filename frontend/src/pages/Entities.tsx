import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { BiomarkerBrief, GeneBrief, Link as ExtLink, PathwayBrief, ProteinBrief, TcgaFrequency, Variant } from "../api/types";
import { FrequencyLabel } from "../components/genomic";
import { humanize } from "../lib/format";
import { AsyncBlock, Badge, Card, ExternalLink, KeyValue, PageHeader, RoleBadge, Table } from "../components/ui";
import { useApi } from "../lib/useApi";

const TABS = ["genes", "proteins", "pathways", "variants"] as const;
type Tab = (typeof TABS)[number];

export function EntityBrowser() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "genes";
  const [q, setQ] = useState("");
  const list = useApi<Record<string, unknown>[]>(`/${tab}`, { q });

  return (
    <div>
      <PageHeader title="Genes, Proteins & Pathways"
        subtitle="Navigate between connected entities. Every link follows an explicit relationship stored in the database." />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div role="tablist" className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => { setQ(""); setParams({ tab: t }); }}
              className={`rounded-md px-3 py-1.5 text-sm capitalize ${tab === t ? "bg-navy-800 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{t}</button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
          Filter
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${tab}…`}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm shadow-sm" />
        </label>
      </div>
      <Card bodyClass="p-0">
        <AsyncBlock state={list} isEmpty={(d) => d.length === 0}>
          {(rows) => {
            if (tab === "genes") return (
              <Table head={["Symbol", "Name", "NCBI Gene", "Biomarkers", "Proteins"]}>
                {(rows as unknown as (GeneBrief & { n_biomarkers: number; n_proteins: number })[]).map((g) => (
                  <tr key={g.gene_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2"><Link to={`/genes/${g.gene_id}`} className="font-mono font-semibold text-navy-700 hover:underline">{g.official_symbol}</Link></td>
                    <td className="px-3 py-2">{g.full_name}</td>
                    <td className="px-3 py-2">{g.ncbi_gene_id && <ExternalLink href={`https://www.ncbi.nlm.nih.gov/gene/${g.ncbi_gene_id}`}>{g.ncbi_gene_id}</ExternalLink>}</td>
                    <td className="tabular px-3 py-2">{g.n_biomarkers}</td>
                    <td className="tabular px-3 py-2">{g.n_proteins}</td>
                  </tr>
                ))}
              </Table>
            );
            if (tab === "proteins") return (
              <Table head={["Accession", "Protein name", "Gene"]}>
                {(rows as unknown as (ProteinBrief & { genes: string[] })[]).map((p) => (
                  <tr key={p.protein_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2"><Link to={`/proteins/${p.protein_id}`} className="font-mono text-navy-700 hover:underline">{p.accession}</Link></td>
                    <td className="px-3 py-2">{p.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{p.genes.join(", ")}</td>
                  </tr>
                ))}
              </Table>
            );
            if (tab === "pathways") return (
              <Table head={["Pathway", "Source", "Genes", "Biomarkers"]}>
                {(rows as unknown as (PathwayBrief & { n_genes: number; n_biomarkers: number })[]).map((p) => (
                  <tr key={p.pathway_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2"><Link to={`/pathways/${p.pathway_id}`} className="text-navy-700 hover:underline">{p.pathway_name}</Link></td>
                    <td className="px-3 py-2 text-xs">{p.pathway_database} {p.external_identifier}</td>
                    <td className="tabular px-3 py-2">{p.n_genes}</td>
                    <td className="tabular px-3 py-2">{p.n_biomarkers}</td>
                  </tr>
                ))}
              </Table>
            );
            return (
              <Table head={["Variant", "Gene", "dbSNP", "Location (GRCh38)", "Annotation"]}>
                {(rows as unknown as Variant[]).map((v) => (
                  <tr key={v.variant_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2"><Link to={`/variants/${v.variant_id}`} className="font-mono text-navy-700 hover:underline">{v.variant_identifier}</Link></td>
                    <td className="px-3 py-2 font-mono text-xs">{v.gene.official_symbol}</td>
                    <td className="px-3 py-2 text-xs">{v.dbsnp_id ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{v.chromosome ? `chr${v.chromosome}:${v.position} ${v.reference_allele}>${v.alternate_allele}` : <span className="font-sans text-slate-400">not curated</span>}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{v.clinical_or_research_annotation}</td>
                  </tr>
                ))}
              </Table>
            );
          }}
        </AsyncBlock>
      </Card>
    </div>
  );
}

function Links({ links }: { links: ExtLink[] }) {
  return <span className="flex flex-wrap gap-3">{links.map((l) => <ExternalLink key={l.url} href={l.url}>{l.label}</ExternalLink>)}</span>;
}

function BiomarkerLinks({ items }: { items: (BiomarkerBrief & { cancers?: string[]; annotation_source?: string | null })[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">None recorded.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {items.map((b) => (
        <li key={b.biomarker_id}>
          <Link to={`/biomarkers/${b.biomarker_id}`} className="font-medium text-navy-700 hover:underline">{b.name}</Link>
          {b.cancers && <span className="text-xs text-slate-500"> · {b.cancers.join(", ")}</span>}
          {b.annotation_source && <div className="text-xs text-slate-400">{b.annotation_source}</div>}
        </li>
      ))}
    </ul>
  );
}

function PathwayLinks({ items }: { items: PathwayBrief[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">None recorded.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {items.map((p) => <li key={p.pathway_id}><Link to={`/pathways/${p.pathway_id}`} className="text-navy-700 hover:underline">{p.pathway_name}</Link> <span className="text-xs text-slate-500">{p.external_identifier}</span></li>)}
    </ul>
  );
}

interface GeneDetailData extends GeneBrief {
  tcga_prevalence: (TcgaFrequency & { cancer_id: number; cancer_name: string })[];
  organism: string; description: string | null; links: ExtLink[];
  proteins: (ProteinBrief & { links: ExtLink[] })[]; pathways: PathwayBrief[]; variants: Variant[];
  biomarkers: (BiomarkerBrief & { cancers: string[] })[];
}

export function GeneDetail() {
  const { id } = useParams();
  const state = useApi<GeneDetailData>(`/genes/${id}`);
  return (
    <AsyncBlock state={state}>
      {(g) => (
        <div className="space-y-5">
          <PageHeader title={g.official_symbol} subtitle={g.full_name} />
          <Card title="Gene record">
            <KeyValue items={[["Organism", <em>{g.organism}</em>], ["NCBI Gene ID", g.ncbi_gene_id], ["HGNC ID", g.hgnc_id],
              ["Description", g.description], ["External links", <Links links={g.links} />]]} />
          </Card>
          {g.tcga_prevalence.length > 0 && (
            <Card title="Alteration frequency in TCGA tumours (cBioPortal, PanCancer Atlas)" bodyClass="p-0">
              <Table head={["Cancer", "Alteration", "Frequency", "Cohorts"]} caption="TCGA alteration frequency">
                {g.tcga_prevalence.map((t) => (
                  <tr key={`${t.cancer_id}-${t.alteration_type}`}>
                    <td className="px-3 py-1.5"><Link to={`/cancers/${t.cancer_id}`} className="text-navy-700 hover:underline">{t.cancer_name}</Link></td>
                    <td className="px-3 py-1.5">{humanize(t.alteration_type)}</td>
                    <td className="px-3 py-1.5"><FrequencyLabel t={t} /></td>
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-500">{t.cohorts.join(" + ")}</td>
                  </tr>
                ))}
              </Table>
            </Card>
          )}
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Biomarkers"><BiomarkerLinks items={g.biomarkers} /></Card>
            <Card title="Encoded proteins">
              {g.proteins.length === 0 ? <p className="text-sm text-slate-500">No protein product recorded (e.g. non-coding RNA gene).</p> : (
                <ul className="space-y-1 text-sm">{g.proteins.map((p) => (
                  <li key={p.protein_id}><Link to={`/proteins/${p.protein_id}`} className="font-mono text-navy-700 hover:underline">{p.accession}</Link> {p.name}</li>))}</ul>
              )}
            </Card>
            <Card title={`KEGG pathway membership (${g.pathways.length})`}><PathwayLinks items={g.pathways} /></Card>
            <Card title="Variants">
              {g.variants.length === 0 ? <p className="text-sm text-slate-500">None recorded.</p> : (
                <ul className="space-y-1 text-sm">{g.variants.map((v) => <li key={v.variant_id}><Link to={`/variants/${v.variant_id}`} className="font-mono text-navy-700 hover:underline">{v.variant_identifier}</Link> <span className="text-xs text-slate-500">{v.dbsnp_id}</span></li>)}</ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </AsyncBlock>
  );
}

export function ProteinDetail() {
  const { id } = useParams();
  const state = useApi<ProteinBrief & { function: string | null; organism: string; links: ExtLink[]; genes: GeneBrief[]; biomarkers: BiomarkerBrief[]; pathways: PathwayBrief[] }>(`/proteins/${id}`);
  return (
    <AsyncBlock state={state}>
      {(p) => (
        <div className="space-y-5">
          <PageHeader title={p.name} subtitle={<span className="font-mono">UniProt {p.accession}</span>} />
          <Card title="Protein record">
            <KeyValue items={[["Function", p.function], ["Organism", <em>{p.organism}</em>],
              ["Encoding gene", <span className="flex gap-2">{p.genes.map((g) => <Link key={g.gene_id} to={`/genes/${g.gene_id}`} className="font-mono text-navy-700 hover:underline">{g.official_symbol}</Link>)}</span>],
              ["External links", <Links links={p.links} />]]} />
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Biomarkers (via gene)"><BiomarkerLinks items={p.biomarkers} /></Card>
            <Card title="Pathways (via gene)"><PathwayLinks items={p.pathways} /></Card>
          </div>
        </div>
      )}
    </AsyncBlock>
  );
}

export function PathwayDetail() {
  const { id } = useParams();
  const state = useApi<PathwayBrief & { description: string | null; genes: GeneBrief[]; biomarkers: (BiomarkerBrief & { cancers: string[]; annotation_source: string | null })[] }>(`/pathways/${id}`);
  return (
    <AsyncBlock state={state}>
      {(p) => (
        <div className="space-y-5">
          <PageHeader title={p.pathway_name} subtitle={`${p.pathway_database} ${p.external_identifier}`} />
          <Card title="Pathway record">
            <KeyValue items={[["Description", p.description], ["Source", p.source_url && <ExternalLink href={p.source_url}>{p.pathway_database} {p.external_identifier}</ExternalLink>]]} />
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title={`Member genes in this database (${p.genes.length})`}>
              <div className="flex flex-wrap gap-1.5">{p.genes.map((g) => <Link key={g.gene_id} to={`/genes/${g.gene_id}`} className="rounded-md border border-slate-200 px-2 py-0.5 font-mono text-xs text-navy-700 hover:border-teal-brand">{g.official_symbol}</Link>)}</div>
              <p className="mt-3 text-xs text-slate-500">Only genes stored in CancerBioMap are listed; see KEGG for the full membership.</p>
            </Card>
            <Card title={`Linked biomarkers (${p.biomarkers.length})`}><BiomarkerLinks items={p.biomarkers} /></Card>
          </div>
        </div>
      )}
    </AsyncBlock>
  );
}

export function VariantDetail() {
  const { id } = useParams();
  const state = useApi<Variant & { associations: { association_id: number; biomarker: BiomarkerBrief; cancer: { cancer_id: number; name: string }; biomarker_role: string }[] }>(`/variants/${id}`);
  return (
    <AsyncBlock state={state}>
      {(v) => (
        <div className="space-y-5">
          <PageHeader title={v.variant_identifier} subtitle={v.clinical_or_research_annotation} />
          <Card title="Variant record">
            <KeyValue items={[
              ["Gene", <Link to={`/genes/${v.gene.gene_id}`} className="font-mono text-navy-700 hover:underline">{v.gene.official_symbol}</Link>],
              ["Protein change", v.protein_change], ["dbSNP", v.dbsnp_id], ["Assembly", v.genome_assembly],
              ["Location", v.chromosome ? `chr${v.chromosome}:${v.position}` : "Not curated in this sample"],
              ["Alleles (genomic + strand)", v.reference_allele ? `${v.reference_allele} > ${v.alternate_allele}` : "Not curated"],
              ["Source", v.source_identifier], ["Links", <Links links={v.links} />],
            ]} />
          </Card>
          <Card title="Associations">
            <ul className="space-y-2 text-sm">{v.associations.map((a) => (
              <li key={a.association_id} className="flex flex-wrap items-center gap-2">
                <Link to={`/biomarkers/${a.biomarker.biomarker_id}`} className="text-navy-700 hover:underline">{a.biomarker.name}</Link>
                <Badge>{a.cancer.name}</Badge><RoleBadge role={a.biomarker_role} />
                <Link to={`/associations/${a.association_id}`} className="text-xs text-teal-brand hover:underline">evidence</Link>
              </li>))}</ul>
          </Card>
          <p className="text-xs text-slate-500">Coordinates were checked against Ensembl REST (GRCh38) for variants with dbSNP identifiers and positions.</p>
        </div>
      )}
    </AsyncBlock>
  );
}
