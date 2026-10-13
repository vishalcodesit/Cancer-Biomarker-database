"""Verify curated reference data against official public APIs.

Checks:
  * genes.csv     - NCBI Gene: symbol for each ncbi_gene_id (E-utilities esummary)
  * proteins.csv  - UniProt: accession is a reviewed human entry for the stated gene
  * variants.csv  - Ensembl REST: dbSNP ID maps to the stated GRCh38 chromosome/position
  * KEGG          - builds biomarker_pathways.csv from KEGG gene membership (--write-kegg)

Usage (from backend/):
    python -m scripts.verify_sources
    python -m scripts.verify_sources --write-kegg

Access notes: NCBI E-utilities, UniProt REST and Ensembl REST are public APIs.
KEGG REST is free for academic use; see https://www.kegg.jp/kegg/legal.html.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._http import request  # noqa: E402  (certifi trust store; see scripts/_http.py)

DATA = Path(__file__).resolve().parent.parent / "data" / "sample"


def _get(url: str, *, as_json: bool = True):
    return request(url, as_json=as_json, timeout=30)


def verify_genes() -> int:
    df = pd.read_csv(DATA / "genes.csv", keep_default_na=False)
    ids = ",".join(str(i) for i in df["ncbi_gene_id"])
    result = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&retmode=json&id={ids}")["result"]
    problems = 0
    for _, row in df.iterrows():
        rec = result.get(str(row["ncbi_gene_id"]), {})
        if rec.get("name") != row["official_symbol"] or rec.get("organism", {}).get("scientificname") != "Homo sapiens":
            print(f"[GENE] {row['official_symbol']} / {row['ncbi_gene_id']} -> NCBI says {rec.get('name')}")
            problems += 1
    print(f"Genes checked: {len(df)}, problems: {problems}")
    return problems


def verify_proteins() -> int:
    df = pd.read_csv(DATA / "proteins.csv", keep_default_na=False)
    problems = 0
    for _, row in df.iterrows():
        rec = _get(f"https://rest.uniprot.org/uniprotkb/{row['accession']}.json?fields=gene_names,organism_name")
        genes = [g.get("geneName", {}).get("value") for g in rec.get("genes", [])]
        reviewed = "Swiss-Prot" in rec.get("entryType", "")
        human = rec.get("organism", {}).get("scientificName") == "Homo sapiens"
        if row["gene_symbol"] not in genes or not reviewed or not human:
            print(f"[PROTEIN] {row['accession']} expected {row['gene_symbol']} -> {genes} reviewed={reviewed} human={human}")
            problems += 1
        time.sleep(0.1)
    print(f"Proteins checked: {len(df)}, problems: {problems}")
    return problems


def verify_variants() -> int:
    df = pd.read_csv(DATA / "variants.csv", keep_default_na=False, dtype=str)
    problems = checked = 0
    for _, row in df.iterrows():
        if not row["dbsnp_id"] or not row["position"]:
            continue
        checked += 1
        rec = _get(f"https://rest.ensembl.org/variation/human/{row['dbsnp_id']}?content-type=application/json")
        maps = [m for m in rec.get("mappings", []) if m.get("assembly_name") == "GRCh38"]
        ok = any(
            m["seq_region_name"] == row["chromosome"]
            and int(m["start"]) == int(row["position"])
            and row["reference_allele"] in m["allele_string"].split("/")[:1]
            and row["alternate_allele"] in m["allele_string"].split("/")[1:]
            for m in maps
        )
        if not ok:
            print(f"[VARIANT] {row['variant_identifier']} {row['dbsnp_id']} -> {[(m['seq_region_name'], m['start'], m['allele_string']) for m in maps]}")
            problems += 1
        time.sleep(0.1)
    print(f"Variants checked: {checked}, problems: {problems}")
    return problems


def build_kegg_links(write: bool) -> None:
    """Link a biomarker to a KEGG pathway when one of its genes is a KEGG member of that pathway."""
    genes = pd.read_csv(DATA / "genes.csv", keep_default_na=False)
    entrez_to_symbol = {f"hsa:{g}": s for g, s in zip(genes["ncbi_gene_id"], genes["official_symbol"])}
    pathways = pd.read_csv(DATA / "pathways.csv", keep_default_na=False)
    members: dict[str, set[str]] = {}
    for pid in pathways.loc[pathways["pathway_database"] == "KEGG", "external_identifier"]:
        text = _get(f"https://rest.kegg.jp/link/hsa/{pid}", as_json=False)
        members[pid] = {entrez_to_symbol[line.split("\t")[1]] for line in text.strip().splitlines()
                        if line.split("\t")[1] in entrez_to_symbol}
        time.sleep(0.4)
        print(f"  {pid}: {sorted(members[pid])}")

    biomarkers = pd.read_csv(DATA / "biomarkers.csv", keep_default_na=False)
    rows = []
    for _, b in biomarkers.iterrows():
        symbols = {s for s in b["gene_symbols"].split(";") if s}
        for pid, mem in members.items():
            hit = sorted(symbols & mem)
            if hit:
                rows.append({"biomarker_code": b["biomarker_code"], "pathway_database": "KEGG",
                             "external_identifier": pid,
                             "annotation_source": f"KEGG REST gene membership ({', '.join(hit)})"})
    print(f"Biomarker-pathway links derived: {len(rows)}")
    if write:
        pd.DataFrame(rows).to_csv(DATA / "biomarker_pathways.csv", index=False)
        (DATA / "kegg_membership.json").write_text(json.dumps({k: sorted(v) for k, v in members.items()}, indent=2))
        pd.DataFrame(
            [{"gene_symbol": g, "pathway_database": "KEGG", "external_identifier": pid,
              "annotation_source": "KEGG REST /link/hsa"} for pid, mem in members.items() for g in sorted(mem)]
        ).to_csv(DATA / "gene_pathways.csv", index=False)
        print("Wrote biomarker_pathways.csv, gene_pathways.csv and kegg_membership.json")


CANCER_KEGG_MAP = {"breast": "hsa05224", "nsclc": "hsa05223", "colorectal": "hsa05210", "prostate": "hsa05215"}


def build_kegg_evidence(retrieved_at: str) -> None:
    """Database-annotation evidence: a biomarker gene is a member of the KEGG disease map of the cancer.

    These rows support gene-cancer relevance only, not the specific biomarker role, so they carry
    no evidence_type and no consistency annotation (both remain unknown).
    """
    members = json.loads((DATA / "kegg_membership.json").read_text())
    biomarkers = pd.read_csv(DATA / "biomarkers.csv", keep_default_na=False).set_index("biomarker_code")
    assoc = pd.read_csv(DATA / "associations.csv", keep_default_na=False)
    rows = []
    for _, a in assoc.iterrows():
        pid = CANCER_KEGG_MAP.get(a["cancer_code"])
        symbols = {s for s in biomarkers.loc[a["biomarker_code"], "gene_symbols"].split(";") if s}
        hit = sorted(symbols & set(members.get(pid, [])))
        if not hit:
            continue
        rows.append({
            "biomarker_code": a["biomarker_code"], "cancer_code": a["cancer_code"],
            "biomarker_role": a["biomarker_role"], "pmid": "", "evidence_type": "",
            "source_name": "KEGG", "source_record_id": pid, "consistency_annotation": "",
            "retrieved_at": retrieved_at, "source_url": f"https://www.kegg.jp/pathway/{pid}",
            "evidence_summary": (f"{', '.join(hit)} is a member of the KEGG disease pathway map {pid}. "
                                 "Database annotation of gene-cancer relevance; does not by itself support the biomarker role."),
        })
    pd.DataFrame(rows).to_csv(DATA / "evidence_kegg.csv", index=False)
    print(f"Wrote evidence_kegg.csv with {len(rows)} database-annotation rows")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-kegg", action="store_true")
    args = parser.parse_args()
    problems = verify_genes() + verify_proteins() + verify_variants()
    build_kegg_links(args.write_kegg)
    if args.write_kegg:
        build_kegg_evidence(time.strftime("%Y-%m-%d"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
