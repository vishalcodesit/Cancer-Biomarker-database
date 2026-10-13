"""Build an external benchmark from CIViC (civicdb.org, CC0) to validate the evidence-support score.

For every biomarker-cancer-role association the script finds ACCEPTED CIViC evidence items that
  * concern one of the biomarker's genes (and, for variant-specific biomarkers, a matching variant; see
    VARIANT_FILTERS below),
  * concern the same cancer (disease-name rules in DISEASE_RULES, which also accept CIViC sub-types such as
    "Lung Adenocarcinoma" for NSCLC),
  * have the matching CIViC evidence type (PREDICTIVE, PROGNOSTIC, DIAGNOSTIC, PREDISPOSING -> risk),
  * have evidence direction SUPPORTS,
and records the best CIViC evidence level (A validated > B clinical > C case study > D preclinical >
E inferential), the number of matching items and how many PMIDs they share with this database.

CIViC is used ONLY to validate the score (rank concordance on /validation), never as an input to it.

Usage (from backend/):
    python -m scripts.fetch_civic            # fetch and print a summary
    python -m scripts.fetch_civic --write    # fetch and write data/sample/external_benchmarks.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._http import request  # noqa: E402

GRAPHQL = "https://civicdb.org/api/graphql"
DATA = Path(__file__).resolve().parent.parent / "data" / "sample"

QUERY = """query($name: String!, $after: String) {
  evidenceItems(first: 100, after: $after, molecularProfileName: $name, status: ACCEPTED) {
    pageInfo { hasNextPage endCursor }
    nodes { id evidenceLevel evidenceType evidenceDirection
            disease { name doid }
            molecularProfile { name variants { name feature { name } } }
            source { citationId sourceType } }
  }
}"""

ROLE_FOR_TYPE = {"PREDICTIVE": "predictive", "PROGNOSTIC": "prognostic", "DIAGNOSTIC": "diagnostic",
                 "PREDISPOSING": "risk"}


def _lung(n: str) -> bool:
    return "lung" in n and ("non-small" in n or "adenocarcinoma" in n or "squamous" in n)


DISEASE_RULES = {
    "breast": lambda n: "breast" in n,
    "nsclc": _lung,
    "colorectal": lambda n: any(t in n for t in ("colorectal", "colon", "rectal", "rectum")),
    "prostate": lambda n: "prostate" in n,
}

# Variant-specific biomarkers: a CIViC molecular profile must contain one of these substrings (case-insensitive).
# Biomarkers not listed are matched at gene level.
VARIANT_FILTERS = {
    "CBM-003": ("amplification", "overexpression", "expression"),
    "CBM-004": ("expression", "positive"),
    "CBM-005": ("expression", "positive"),
    "CBM-006": ("expression",),
    "CBM-008": ("y537", "d538", "e380", "l536", "mutation"),
    "CBM-016": ("loss", "mutation", "expression"),
    "CBM-017": ("l858r", "exon 19", "e746", "sensitizing"),
    "CBM-018": ("t790m",),
    "CBM-019": ("fusion", "rearrangement", "eml4"),
    "CBM-020": ("fusion", "rearrangement"),
    "CBM-021": ("g12c",),
    "CBM-022": ("g12", "g13", "exon 2", "mutation"),
    "CBM-024": ("v600e",),
    "CBM-025": ("exon 14",),
    "CBM-026": ("fusion", "rearrangement"),
    "CBM-027": ("expression",),
    "CBM-030": ("fusion",),
    "CBM-039": ("fusion", "tmprss2"),
    "CBM-041": ("v7", "splice"),
    "CBM-042": ("amplification",),
    "CBM-043": ("loss", "deletion", "mutation"),
}

LEVEL_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}


def fetch_gene(symbol: str) -> list[dict]:
    nodes, after = [], None
    while True:
        res = request(GRAPHQL, data={"query": QUERY, "variables": {"name": symbol, "after": after}})
        if "errors" in res:
            raise RuntimeError(f"CIViC error for {symbol}: {res['errors']}")
        page = res["data"]["evidenceItems"]
        nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return nodes
        after = page["pageInfo"]["endCursor"]
        time.sleep(0.3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    biomarkers = pd.read_csv(DATA / "biomarkers.csv", dtype=str, keep_default_na=False).set_index("biomarker_code")
    assocs = pd.read_csv(DATA / "associations.csv", dtype=str, keep_default_na=False)
    evidence = pd.read_csv(DATA / "evidence.csv", dtype=str, keep_default_na=False)
    our_pmids = defaultdict(set)
    for _, e in evidence.iterrows():
        if e["pmid"]:
            our_pmids[(e["biomarker_code"], e["cancer_code"], e["biomarker_role"])].add(e["pmid"])

    genes = sorted({g for s in biomarkers["gene_symbols"] for g in s.split(";") if g})
    items_by_gene: dict[str, list[dict]] = {}
    for g in genes:
        items_by_gene[g] = fetch_gene(g)
        print(f"  {g:<8} {len(items_by_gene[g])} accepted CIViC evidence items")
        time.sleep(0.3)

    rows, today = [], date.today().isoformat()
    for _, a in assocs.iterrows():
        code, cancer, role = a["biomarker_code"], a["cancer_code"], a["biomarker_role"]
        symbols = [g for g in biomarkers.loc[code, "gene_symbols"].split(";") if g]
        filt = VARIANT_FILTERS.get(code)
        matched, diseases = [], set()
        for g in symbols:
            for it in items_by_gene.get(g, []):
                # Fusion features are named "5'partner::3'partner" (e.g. "EML4::ALK", or "v::ALK" for an unknown
                # partner), so a gene matches if it is the feature or one of the fusion partners.
                features = {part for v in it["molecularProfile"]["variants"] if v.get("feature")
                            for part in v["feature"]["name"].split("::")}
                profile = it["molecularProfile"]["name"].lower()
                disease = (it["disease"] or {}).get("name") or ""
                if (g in features and DISEASE_RULES[cancer](disease.lower())
                        and ROLE_FOR_TYPE.get(it["evidenceType"]) == role and it["evidenceDirection"] == "SUPPORTS"
                        and (filt is None or any(f in profile for f in filt))):
                    matched.append(it)
                    diseases.add(disease)
        unique = {it["id"]: it for it in matched}.values()
        best = max((it["evidenceLevel"] for it in unique), key=lambda lv: LEVEL_RANK[lv], default=None)
        civic_pmids = {it["source"]["citationId"] for it in unique if it["source"]["sourceType"] == "PUBMED"}
        rows.append({
            "biomarker_code": code, "cancer_code": cancer, "biomarker_role": role, "benchmark_source": "CIViC",
            "best_evidence_level": best or "", "n_items": len(unique),
            "n_shared_publications": len(civic_pmids & our_pmids[(code, cancer, role)]),
            "matched_on": (f"genes {'/'.join(symbols)}; " + (f"profile contains {'|'.join(filt)}; " if filt else "gene level; ")
                           + f"diseases {', '.join(sorted(diseases)) or 'none'}"),
            "retrieved_at": today,
        })

    out = pd.DataFrame(rows)
    covered = out[out.n_items > 0]
    print(f"\nAssociations covered by CIViC: {len(covered)} of {len(out)}")
    print(covered["best_evidence_level"].value_counts().sort_index().to_string())
    if args.write:
        out.to_csv(DATA / "external_benchmarks.csv", index=False)
        print("Wrote external_benchmarks.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
