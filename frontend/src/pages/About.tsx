import { Card, Disclaimer, ExternalLink, PageHeader, SourceStatusBadge } from "../components/ui";

const SOURCES = [
  { name: "PubMed (NCBI E-utilities)", url: "https://pubmed.ncbi.nlm.nih.gov/", use: "Publication titles, authors, journals, years and DOIs for all 86 curated PMIDs were retrieved and verified with esummary." },
  { name: "NCBI Gene", url: "https://www.ncbi.nlm.nih.gov/gene/", use: "Gene IDs and official symbols verified with E-utilities esummary." },
  { name: "UniProt", url: "https://www.uniprot.org/", use: "Reviewed human protein accessions verified with the UniProt REST API." },
  { name: "KEGG", url: "https://www.kegg.jp/", use: "Pathway gene membership retrieved through KEGG REST (/link/hsa), free for academic use." },
  { name: "NCI Genomic Data Commons", url: "https://gdc.cancer.gov/", use: "TCGA project identifiers (TCGA-BRCA, -LUAD, -COAD, -PRAD) verified through the GDC API." },
  { name: "Ensembl REST / dbSNP", url: "https://rest.ensembl.org/", use: "GRCh38 coordinates and alleles of dbSNP variants verified." },
  { name: "Disease Ontology", url: "https://disease-ontology.org/", use: "Cancer identifiers (DOID)." },
  { name: "Mondo Disease Ontology (EBI OLS)", url: "https://www.ebi.ac.uk/ols4/ontologies/mondo", use: "Mondo IDs for the 4 cancers, each verified through OLS to cross-reference the stored DOID. ICD-O-3 topography codes are curator-assigned from WHO ICD-O-3." },
  { name: "HGNC", url: "https://www.genenames.org/", use: "HGNC IDs for all 43 genes, each checked against the stored NCBI Gene ID." },
  { name: "cBioPortal (TCGA PanCancer Atlas)", url: "https://www.cbioportal.org/", use: "Raw counts of tumours with a somatic mutation, amplification or deep deletion in each curated gene, for 5 TCGA cohorts (BRCA, LUAD, LUSC, COADREAD, PRAD)." },
  { name: "CIViC", url: "https://civicdb.org/", use: "Accepted expert evidence items (CC0), used only to validate the evidence-support score, never to compute it." },
];

export default function About() {
  return (
    <div className="space-y-5">
      <PageHeader title="About CancerBioMap" subtitle="An integrated cancer biomarker database with evidence-based association analysis: a university Biological Database project." />
      <Disclaimer />
      <Card title="Data sources and attribution">
        <ul className="space-y-3 text-sm">
          {SOURCES.map((s) => (
            <li key={s.name}><ExternalLink href={s.url}>{s.name}</ExternalLink><p className="text-slate-600">{s.use}</p></li>
          ))}
        </ul>
      </Card>
      <Card title="How to read record provenance">
        <ul className="space-y-2 text-sm text-slate-700">
          <li><SourceStatusBadge status="curated_literature" /> Association curated manually from the cited publications. Summaries paraphrase each paper's main reported finding.</li>
          <li><SourceStatusBadge status="database_annotation" /> Derived from a public database (e.g. KEGG gene membership). Evidence rows from KEGG support gene–cancer relevance only, not the biomarker role.</li>
          <li><SourceStatusBadge status="computational_prediction" /> Computational prediction. None are present in the sample dataset.</li>
          <li><SourceStatusBadge status="synthetic_demo" /> Synthetic demonstration record. None are present in the sample dataset; test fixtures are generated in code.</li>
          <li><SourceStatusBadge status="pending_curation" /> Association recorded but supporting evidence not yet curated (e.g. CA 15-3).</li>
        </ul>
      </Card>
      <Card title="Scope and limitations">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>The sample is a small, curated subset (47 biomarkers, 4 cancers) chosen for teaching. It is not a comprehensive knowledgebase.</li>
          <li>Consistency annotations are curator judgements recorded in the CSV; most evidence is annotated "supports" because landmark positive studies were selected.</li>
          <li>Coverage of each association reflects curation effort here, not the size of the literature.</li>
        </ul>
      </Card>
    </div>
  );
}
