import { Link } from "react-router-dom";
import type { Methodology as M } from "../api/types";
import { AsyncBlock, Card, Disclaimer, PageHeader, Table } from "../components/ui";
import { COMPONENT_LABELS, humanize } from "../lib/format";
import { useApi } from "../lib/useApi";

export default function Methodology() {
  const state = useApi<M>("/scores/methodology");
  return (
    <AsyncBlock state={state}>
      {(m) => (
        <div className="space-y-5">
          <PageHeader title="Evidence-Aware Confidence & Gap Analysis"
            subtitle={`Scoring version ${m.scoring_version}. A transparent, explainable evidence-support score, not a clinical prediction model.`} />
          <Disclaimer />
          <Card title="Formula">
            {/* Rendered from the live configuration, so the page can never disagree with the weights in use. */}
            <p className="font-mono text-lg text-navy-900">
              Score = {(["publication_support", "source_diversity", "evidence_type", "consistency"] as const)
                .map((k) => `${m.weights[k]}·${COMPONENT_LABELS[k].key}`).join(" + ")}
            </p>
            <p className="mt-2 text-sm text-slate-600">
              Weights are proposed project parameters (configurable through environment variables), not validated clinical standards.
              Active configuration:{" "}
              {Object.entries(m.weights).map(([k, w]) => `${COMPONENT_LABELS[k]?.key ?? k} = ${w}`).join(", ")}; publication cap = {m.publication_cap};
              minimum coverage for a provisional score = {Math.round(m.min_coverage * 100)}%; corroboration discount
              λ = {m.breadth_discount}. How sensitive the ranking is to these choices is measured on the{" "}
              <Link to="/validation" className="text-teal-brand hover:underline">Score Validation</Link> page.
            </p>
          </Card>
          <Card title={`What changed in version ${m.scoring_version}`}>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
              {m.changes_from_previous_version.map((c) => <li key={c}>{c}</li>)}
            </ul>
            <p className="mt-2 text-sm text-slate-600">
              Both changes fix properties the original method lacked: a record that the database itself says does not support the role
              no longer raises the score, and adding a corroborating study can no longer lower it. Scores are versioned, so the original
              1.0.0 results remain available for comparison.
            </p>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Components (each 0–100)">
              <dl className="space-y-3 text-sm">
                {Object.entries(m.components).map(([k, v]) => (
                  <div key={k}><dt className="font-semibold text-navy-800">{k}</dt><dd className="text-slate-700">{v}</dd></div>
                ))}
              </dl>
            </Card>
            <Card title="Evidence-type rubric" bodyClass="p-0">
              <Table head={["Evidence type", "Rubric value"]}>
                {Object.entries(m.evidence_type_rubric).map(([k, v]) => (
                  <tr key={k}><td className="px-3 py-1.5">{humanize(k)}</td><td className="tabular px-3 py-1.5">{v}</td></tr>
                ))}
              </Table>
            </Card>
          </div>
          <Card title="Missing data and uncertainty">
            <p className="text-sm text-slate-700">{m.missing_data}</p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
              <li><strong>Complete</strong>: all four components observed; weighted sum reported.</li>
              <li><strong>Provisional</strong>: some components unknown; score = Σ(wᵢ·xᵢ) / Σwᵢ over observed components, shown with an asterisk, a dashed outline and a warning.</li>
              <li><strong>Insufficient</strong>: observed weight below the minimum; no overall score is reported.</li>
              <li>Zero recorded publications, sources, typed evidence or consistency annotations make that component <em>unknown</em>, never 0.</li>
              <li>Duplicate records are collapsed: publications by PMID/DOI, sources by name.</li>
            </ul>
          </Card>
          <Card title="Worked example (verified by automated test)">
            <p className="text-sm text-slate-700">
              Three distinct publications (an RCT and a patient cohort in PubMed, a genomic-profiling study via NCI GDC), two
              supporting sources, and two "supports" annotations (default weights):
            </p>
            <ul className="mt-2 space-y-1 font-mono text-xs text-slate-800">
              <li>P = 100·log2(1+3)/log2(1+5) = 77.37</li>
              <li>D = 100·(1 − 0.5²) = 75.00</li>
              <li>T = 100·(1 − 0.05·(1 − 0.25·0.80)·(1 − 0.25·0.65)) = 96.65</li>
              <li>C = 100·(2 supports) / 2 annotated = 100.00</li>
              <li>Score = 0.35·77.37 + 0.25·75 + 0.25·96.65 + 0.15·100 = 84.99 (complete; version 1.0.0 gave 83.45)</li>
            </ul>
          </Card>
          <p className="text-xs text-slate-500">{m.disclaimer}</p>
        </div>
      )}
    </AsyncBlock>
  );
}
