import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { buildQuery } from "../api/client";
import type { NetworkData, Score } from "../api/types";
import { layout, routeFor } from "../components/NetworkGraph";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { ScoreStatusLabel } from "../components/ui";
import { formatScore, humanize } from "../lib/format";

describe("formatting helpers", () => {
  it("humanizes vocabulary values", () => {
    expect(humanize("randomized_clinical_trial")).toBe("Randomized clinical trial");
    expect(humanize("gene_fusion")).toBe("Gene fusion");
    expect(humanize(null)).toBe("—");
  });
  it("never renders a missing score as zero", () => {
    expect(formatScore(null)).toBe("n/a");
    expect(formatScore(0)).toBe("0.0");
  });
});

describe("buildQuery", () => {
  it("drops empty filters so the backend receives only active ones", () => {
    expect(buildQuery({ q: "KRAS", cancer_id: "", role: undefined, page: 2 })).toBe("?q=KRAS&page=2");
    expect(buildQuery({})).toBe("");
  });
});

const provisional: Score = {
  publication_support: 61.31, source_diversity: 50, evidence_type: 58, consistency: null,
  overall_score: 56.2, evidence_coverage: 0.85, score_status: "provisional",
  missing_components: ["consistency"], n_publications: 2, n_sources: 1, scoring_version: "1.0.0",
};

describe("ScoreBreakdown", () => {
  it("shows unknown components as unknown and warns that the score is provisional", () => {
    render(<ScoreBreakdown score={provisional} />);
    expect(screen.getByText(/unknown$/i)).toBeInTheDocument();
    expect(screen.getByText(/Not equivalent to a fully observed score/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Evidence consistency: unknown" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Publication support: 61.3" })).toBeInTheDocument();
  });
  it("handles an insufficient score with no overall value", () => {
    render(<ScoreBreakdown score={{ ...provisional, overall_score: null, score_status: "insufficient", evidence_coverage: 0 }} />);
    expect(screen.getByText(/Insufficient evidence metadata/)).toBeInTheDocument();
    expect(screen.getByText("n/a")).toBeInTheDocument();
  });
  it("status is conveyed by text, not colour alone", () => {
    render(<ScoreStatusLabel status="complete" />);
    expect(screen.getByText("Complete")).toBeInTheDocument();
  });
});

describe("network layout", () => {
  const data: NetworkData = {
    nodes: [
      { id: "b1", label: "HER2", type: "biomarker", entity_id: 1 },
      { id: "c1", label: "Breast cancer", type: "cancer", entity_id: 1 },
      { id: "g1", label: "ERBB2", type: "gene", entity_id: 7 },
      { id: "p9", label: "PMID 3798106", type: "publication", entity_id: 9 },
    ],
    edges: [{ source: "b1", target: "c1", label: "predictive" }, { source: "b1", target: "g1", label: "gene" },
      { source: "c1", target: "p9", label: "evidence" }],
  };
  it("is deterministic and keeps the focus node centred", () => {
    const a = layout(data, 900, 460);
    const b = layout(data, 900, 460);
    expect(a).toEqual(b);
    expect(a.b1).toEqual({ x: 450, y: 230 });
  });
  it("routes nodes to their entity pages", () => {
    expect(routeFor(data.nodes[2])).toBe("/genes/7");
    expect(routeFor(data.nodes[3])).toBe("/publications?q=3798106");
  });
  it("renders inside a router", () => {
    // smoke test: ScoreBreakdown has no router dependency, network routes are pure functions
    render(<MemoryRouter><ScoreStatusLabel status="provisional" /></MemoryRouter>);
    expect(screen.getByText("Provisional")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- version 1.1 components
import type { DiscordanceItem, RobustnessItem, TcgaFrequency } from "../api/types";
import { CivicBadge, FrequencyLabel, TcgaPanel } from "../components/genomic";
import { formatFrequency } from "../lib/format";
import { quadrantPoints } from "../pages/Prevalence";
import { RankInterval } from "../pages/Validation";

const kras: TcgaFrequency = {
  gene_symbol: "KRAS", alteration_type: "somatic_mutation", basis: "somatic_mutation_upper_bound", upper_bound: true,
  altered_cases: 218, profiled_cases: 534, frequency: 0.4082, ci95_low: 0.367, ci95_high: 0.451,
  cohorts: ["coadread_tcga_pan_can_atlas_2018"], source: "cBioPortal",
};

describe("genomic context", () => {
  it("formats frequencies without ever showing a small non-zero value as 0", () => {
    expect(formatFrequency(0.4082)).toBe("40.8%");
    expect(formatFrequency(0.0004)).toBe("0.04%");
    expect(formatFrequency(0)).toBe("0.0%");
    expect(formatFrequency(null)).toBe("n/a");
  });
  it("marks gene-level frequencies of variant-specific biomarkers as upper bounds", () => {
    render(<FrequencyLabel t={kras} />);
    expect(screen.getByText("≤ 40.8%")).toBeInTheDocument();
    expect(screen.getByText(/218\/534 tumours/)).toBeInTheDocument();
  });
  it("explains when no TCGA frequency applies instead of showing zero", () => {
    render(<TcgaPanel t={null} />);
    expect(screen.getByText(/No gene-level TCGA frequency applies/)).toBeInTheDocument();
  });
  it("shows the CIViC level with its meaning, or that the association is not in CIViC", () => {
    const { rerender } = render(<CivicBadge civic={{ source: "CIViC", best_evidence_level: "A", n_items: 30, n_shared_publications: 1, matched_on: null, retrieved_at: null }} />);
    expect(screen.getByText("CIViC level A · Validated")).toBeInTheDocument();
    rerender(<CivicBadge civic={null} />);
    expect(screen.getByText("Not in CIViC")).toBeInTheDocument();
  });
});

describe("evidence vs prevalence", () => {
  it("groups points by quadrant and floors tiny frequencies for the log axis", () => {
    const base = { ...kras, association_id: 1, biomarker_id: 1, biomarker_name: "x", biomarker_code: "CBM-1", cancer_name: "c",
      biomarker_role: "predictive", overall_score: 80, score_status: "complete" as const };
    const items: DiscordanceItem[] = [
      { ...base, quadrant: "established" },
      { ...base, association_id: 2, frequency: 0.001, quadrant: "rare_thin" },
    ];
    const g = quadrantPoints(items);
    expect(g.established).toHaveLength(1);
    expect(g.under_curated).toHaveLength(0);
    expect(g.rare_thin[0].pct).toBe(0.5);  // 0.1% floored to the axis minimum, never dropped
  });
});

describe("rank interval", () => {
  it("describes the interval in text, not only graphically", () => {
    const it_: RobustnessItem = { association_id: 1, biomarker_id: 1, biomarker_name: "PSA", cancer_name: "Prostate", biomarker_role: "diagnostic",
      baseline_score: 86.5, baseline_rank: 4, median_rank: 8, rank_p05: 3, rank_p95: 51, rank_interval_width: 48, share_in_top_k: 0.69 };
    render(<RankInterval item={it_} n={55} />);
    expect(screen.getByRole("img", { name: "Baseline rank 4; 90% of weightings give rank 3 to 51" })).toBeInTheDocument();
  });
});
