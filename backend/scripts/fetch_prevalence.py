"""Fetch gene-level alteration counts for every curated gene from TCGA PanCancer Atlas cohorts (cBioPortal).

Proposal item: "mutation frequency statistics" integrated with literature evidence.

For each cohort the script calls the public cBioPortal REST API:
  * GET  /api/studies/{studyId}         -> cohort name, citation, number of sequenced and CNA-profiled samples
  * POST /api/mutated-genes/fetch       -> samples with >= 1 somatic mutation in each gene
  * POST /api/cna-genes/fetch           -> samples with a high-level amplification (+2) or deep deletion (-2)
and writes RAW COUNTS (altered, profiled) to data/sample/genomic_prevalence.csv plus data/sample/cohorts.csv.
Percentages are derived by the application, and a cancer with two cohorts (NSCLC = LUAD + LUSC) is pooled
by summing counts, never by averaging percentages.

A gene missing from the Mutated Genes table had no mutated sample in that whole-exome cohort, so it is
stored as 0 altered of N profiled (a measured zero, unlike a missing value).

Usage (from backend/):
    python -m scripts.fetch_prevalence            # fetch and print a summary
    python -m scripts.fetch_prevalence --write    # fetch and write the two CSV files
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._http import request  # noqa: E402

API = "https://www.cbioportal.org/api"
DATA = Path(__file__).resolve().parent.parent / "data" / "sample"

# cBioPortal study -> cancer code in cancers.csv. NSCLC needs both TCGA lung cohorts; TCGA colon and
# rectum are combined by cBioPortal into a single colorectal study.
STUDIES = {
    "brca_tcga_pan_can_atlas_2018": "breast",
    "luad_tcga_pan_can_atlas_2018": "nsclc",
    "lusc_tcga_pan_can_atlas_2018": "nsclc",
    "coadread_tcga_pan_can_atlas_2018": "colorectal",
    "prad_tcga_pan_can_atlas_2018": "prostate",
}


def fetch_study(study_id: str, symbols: set[str]) -> tuple[dict, list[dict]]:
    meta = request(f"{API}/studies/{study_id}")
    mutated = request(f"{API}/mutated-genes/fetch", data={"studyIds": [study_id]})
    time.sleep(0.5)
    cna = request(f"{API}/cna-genes/fetch", data={"studyIds": [study_id]})
    time.sleep(0.5)

    n_mut, n_cna = meta["sequencedSampleCount"], meta["cnaSampleCount"]
    mut = {r["hugoGeneSymbol"]: (r["numberOfAlteredCases"], r["numberOfProfiledCases"]) for r in mutated
           if r.get("hugoGeneSymbol") in symbols}
    amp = {r["hugoGeneSymbol"]: (r["numberOfAlteredCases"], r["numberOfProfiledCases"]) for r in cna
           if r.get("hugoGeneSymbol") in symbols and r.get("alteration") == 2}
    dele = {r["hugoGeneSymbol"]: (r["numberOfAlteredCases"], r["numberOfProfiledCases"]) for r in cna
            if r.get("hugoGeneSymbol") in symbols and r.get("alteration") == -2}

    rows = []
    for sym in sorted(symbols):
        for atype, table, default_n in (("somatic_mutation", mut, n_mut), ("amplification", amp, n_cna),
                                        ("deep_deletion", dele, n_cna)):
            altered, profiled = table.get(sym, (0, default_n))
            rows.append({"gene_symbol": sym, "study_id": study_id, "alteration_type": atype,
                         "altered_cases": altered, "profiled_cases": profiled})
    cohort = {
        "study_id": study_id, "name": meta["name"], "cancer_code": STUDIES[study_id], "source_name": "cBioPortal",
        "n_samples_mutation": n_mut, "n_samples_cna": n_cna, "citation": meta.get("citation", ""),
        "source_url": f"https://www.cbioportal.org/study/summary?id={study_id}",
        "retrieved_at": date.today().isoformat(),
    }
    return cohort, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    symbols = set(pd.read_csv(DATA / "genes.csv", dtype=str, keep_default_na=False)["official_symbol"])
    cohorts, rows = [], []
    for study in STUDIES:
        cohort, r = fetch_study(study, symbols)
        cohorts.append(cohort)
        rows.extend(r)
        print(f"{study}: {cohort['n_samples_mutation']} sequenced, {cohort['n_samples_cna']} CNA-profiled samples")

    prev = pd.DataFrame(rows)
    # Sanity print: a few well-known frequencies that can be compared with the TCGA marker papers.
    for sym, study, atype in [("TP53", "brca_tcga_pan_can_atlas_2018", "somatic_mutation"),
                              ("ERBB2", "brca_tcga_pan_can_atlas_2018", "amplification"),
                              ("KRAS", "luad_tcga_pan_can_atlas_2018", "somatic_mutation"),
                              ("EGFR", "luad_tcga_pan_can_atlas_2018", "somatic_mutation"),
                              ("APC", "coadread_tcga_pan_can_atlas_2018", "somatic_mutation"),
                              ("SPOP", "prad_tcga_pan_can_atlas_2018", "somatic_mutation"),
                              ("PTEN", "prad_tcga_pan_can_atlas_2018", "deep_deletion")]:
        r = prev[(prev.gene_symbol == sym) & (prev.study_id == study) & (prev.alteration_type == atype)].iloc[0]
        print(f"  check {sym:<6} {atype:<17} {study.split('_')[0]:<9} {r.altered_cases}/{r.profiled_cases} "
              f"= {100 * r.altered_cases / r.profiled_cases:.1f}%")
    if args.write:
        pd.DataFrame(cohorts).to_csv(DATA / "cohorts.csv", index=False)
        prev.to_csv(DATA / "genomic_prevalence.csv", index=False)
        print(f"Wrote cohorts.csv ({len(cohorts)} rows) and genomic_prevalence.csv ({len(prev)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
