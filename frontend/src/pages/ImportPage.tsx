import { useState, type FormEvent } from "react";
import { CheckCircle2, Upload, XCircle } from "lucide-react";
import { ApiError, apiPost } from "../api/client";
import type { ImportReport, Vocabularies } from "../api/types";
import { Card, PageHeader, Select, Table } from "../components/ui";
import { useApi } from "../lib/useApi";

const COLUMNS: Record<string, string> = {
  cancers: "code, name, tissue_origin, cancer_category, external_identifier, mondo_id, icdo_topography, gdc_project_id, description",
  genes: "official_symbol, full_name, organism, ncbi_gene_id, hgnc_id, description",
  proteins: "accession, name, function, organism, gene_symbol",
  pathways: "pathway_database, external_identifier, pathway_name, description, source_url",
  publications: "pmid, doi, title, authors, publication_year, journal, source_url",
  biomarkers: "biomarker_code, name, biomarker_type, gene_symbols (; separated), prevalence_basis, description, biological_function, external_identifier",
  gene_pathways: "gene_symbol, pathway_database, external_identifier, annotation_source",
  biomarker_pathways: "biomarker_code, pathway_database, external_identifier, annotation_source",
  associations: "biomarker_code, cancer_code, biomarker_role, source_status, association_description",
  evidence: "biomarker_code, cancer_code, biomarker_role, pmid, evidence_type, source_name, source_record_id, consistency_annotation, retrieved_at, source_url, evidence_summary",
  evidence_kegg: "same columns as evidence",
  variants: "variant_identifier, gene_symbol, protein_change, dbsnp_id, genome_assembly, chromosome, position, reference_allele, alternate_allele, clinical_or_research_annotation, source_identifier, associations (CODE|cancer|role;…)",
  cohorts: "study_id, name, cancer_code, source_name, n_samples_mutation, n_samples_cna, citation, source_url, retrieved_at",
  genomic_prevalence: "gene_symbol, study_id, alteration_type, altered_cases, profiled_cases",
  external_benchmarks: "biomarker_code, cancer_code, biomarker_role, benchmark_source, best_evidence_level, n_items, n_shared_publications, matched_on, retrieved_at",
};

export default function ImportPage() {
  const vocab = useApi<Vocabularies>("/meta/vocabularies");
  const [entity, setEntity] = useState("publications");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Only needed when the backend sets ADMIN_TOKEN; kept in memory, never stored.
  const [token, setToken] = useState("");

  const submit = async (dryRun: boolean, e?: FormEvent) => {
    e?.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setReport(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      setReport(await apiPost<ImportReport>(`/import/${entity}`, fd, { dry_run: dryRun },
        token ? { "X-Admin-Token": token } : {}));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Curated Data Import"
        subtitle="Upload a CSV for one entity. Every row is validated against the schema and controlled vocabularies before anything is written; records are upserted on natural keys so duplicates are never created." />
      <Card title="Upload CSV">
        <form onSubmit={(e) => submit(true, e)} className="grid gap-4 md:grid-cols-[220px_1fr_auto] md:items-end">
          <Select label="Entity" value={entity} onChange={(v) => { setEntity(v); setReport(null); }} allLabel={null}
            options={(vocab.data?.import_entities ?? Object.keys(COLUMNS)).map((e) => ({ value: e, label: e }))} />
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            CSV file
            <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm file:mr-3 file:rounded file:border-0 file:bg-navy-50 file:px-2 file:py-1 file:text-navy-800" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={!file || busy} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-40 enabled:hover:bg-slate-50">Validate (dry run)</button>
            <button type="button" disabled={!file || busy || !report?.ok || !report.dry_run} onClick={() => submit(false)}
              className="inline-flex items-center gap-1.5 rounded-md bg-navy-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 enabled:hover:bg-navy-700">
              <Upload className="h-4 w-4" aria-hidden /> Import
            </button>
          </div>
        </form>
        <p className="mt-3 text-xs text-slate-500">Expected columns: <span className="font-mono">{COLUMNS[entity]}</span></p>
        <p className="mt-1 text-xs text-slate-500">Import order matters: referenced genes, cancers, publications and biomarkers must exist first. Import is enabled only after a successful dry run.</p>
        <label className="mt-3 flex max-w-sm flex-col gap-1 text-xs font-medium text-slate-600">
          Admin token (only if the server sets ADMIN_TOKEN)
          <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm" />
        </label>
      </Card>
      {error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {report && (
        <Card title={<span className="inline-flex items-center gap-2">
          {report.ok ? <CheckCircle2 className="h-4 w-4 text-status-good" aria-hidden /> : <XCircle className="h-4 w-4 text-status-critical" aria-hidden />}
          {report.ok ? (report.dry_run ? "Validation passed (nothing written yet)" : "Import complete") : "Validation failed: nothing was written"}
        </span>}>
          <p className="tabular text-sm text-slate-700">
            Rows: {report.rows_total} · new: {report.inserted} · updated: {report.updated} · unchanged: {report.unchanged}
          </p>
          {report.errors.length > 0 && (
            <div className="mt-3">
              <Table head={["Row", "Field", "Problem"]}>
                {report.errors.map((e, i) => (
                  <tr key={i}><td className="tabular px-3 py-1.5">{e.row || "file"}</td><td className="px-3 py-1.5 font-mono text-xs">{e.field ?? "—"}</td><td className="px-3 py-1.5">{e.message}</td></tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
