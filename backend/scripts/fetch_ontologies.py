"""Add and verify ontology identifiers (proposal item: ontology-driven standardization).

* Genes: HGNC ID for each official symbol, fetched from the HGNC REST API and checked against the
  NCBI Gene ID already in genes.csv (both must describe the same gene).
* Cancers: Mondo Disease Ontology ID, verified through EBI OLS to (a) exist, (b) not be obsolete and
  (c) cross-reference the Disease Ontology ID already stored in cancers.csv. ICD-O-3 topography codes
  are curator-assigned from the WHO ICD-O-3 topography axis (ICD-O is not available through a public API).

Usage (from backend/):
    python -m scripts.fetch_ontologies            # verify only
    python -m scripts.fetch_ontologies --write    # verify and write hgnc_id / mondo_id / icdo_topography
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._http import request  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "sample"

# Curated mappings, verified by this script before they are written.
CANCER_ONTOLOGY = {
    #  code         Mondo ID          ICD-O-3 topography (WHO ICD-O-3)
    "breast": ("MONDO:0007254", "C50"),  # C50 Breast
    "nsclc": ("MONDO:0005233", "C34"),  # C34 Bronchus and lung
    "colorectal": ("MONDO:0005575", "C18-C20"),  # C18 Colon, C19 Rectosigmoid junction, C20 Rectum
    "prostate": ("MONDO:0008315", "C61"),  # C61 Prostate gland
}


def hgnc_ids(genes: pd.DataFrame) -> tuple[dict[str, str], int]:
    out, problems = {}, 0
    for _, g in genes.iterrows():
        docs = request(f"https://rest.genenames.org/fetch/symbol/{urllib.parse.quote(g['official_symbol'])}")["response"]["docs"]
        rec = docs[0] if docs else {}
        if rec.get("status") != "Approved" or str(rec.get("entrez_id")) != str(g["ncbi_gene_id"]):
            print(f"[HGNC] {g['official_symbol']}: expected NCBI {g['ncbi_gene_id']}, HGNC says {rec.get('entrez_id')} ({rec.get('status')})")
            problems += 1
        else:
            out[g["official_symbol"]] = rec["hgnc_id"]
        time.sleep(0.12)  # HGNC asks for <= 10 requests/second
    print(f"Genes checked: {len(genes)}, HGNC IDs verified: {len(out)}, problems: {problems}")
    return out, problems


def mondo_check(cancers: pd.DataFrame) -> int:
    problems = 0
    for _, c in cancers.iterrows():
        mondo, _icdo = CANCER_ONTOLOGY[c["code"]]
        iri = urllib.parse.quote(urllib.parse.quote(f"http://purl.obolibrary.org/obo/{mondo.replace(':', '_')}", safe=""), safe="")
        rec = request(f"https://www.ebi.ac.uk/ols4/api/ontologies/mondo/terms/{iri}")
        doids = {f"DOID:{x.get('id')}" for x in rec.get("obo_xref") or [] if x.get("database") == "DOID"}
        ok = not rec.get("is_obsolete") and c["external_identifier"] in doids
        print(f"[MONDO] {c['code']:<11} {mondo} '{rec.get('label')}' xref {sorted(doids)} -> {'OK' if ok else 'MISMATCH'}")
        problems += 0 if ok else 1
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    genes = pd.read_csv(DATA / "genes.csv", dtype=str, keep_default_na=False)
    cancers = pd.read_csv(DATA / "cancers.csv", dtype=str, keep_default_na=False)
    ids, gene_problems = hgnc_ids(genes)
    cancer_problems = mondo_check(cancers)
    if args.write and not (gene_problems or cancer_problems):
        genes["hgnc_id"] = genes["official_symbol"].map(ids)
        cols = ["official_symbol", "full_name", "organism", "ncbi_gene_id", "hgnc_id", "description"]
        genes[cols].to_csv(DATA / "genes.csv", index=False)
        cancers["mondo_id"] = cancers["code"].map(lambda c: CANCER_ONTOLOGY[c][0])
        cancers["icdo_topography"] = cancers["code"].map(lambda c: CANCER_ONTOLOGY[c][1])
        cols = ["code", "name", "tissue_origin", "cancer_category", "external_identifier", "mondo_id",
                "icdo_topography", "gdc_project_id", "description"]
        cancers[cols].to_csv(DATA / "cancers.csv", index=False)
        print("Wrote genes.csv and cancers.csv")
    elif args.write:
        print("Not writing: fix the problems above first.")
    return 1 if (gene_problems or cancer_problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
