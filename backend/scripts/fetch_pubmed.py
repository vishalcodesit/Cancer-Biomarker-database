"""Verify and enrich publications.csv from NCBI PubMed (E-utilities esummary).

For every PMID the script retrieves the official title, authors, journal, year
and DOI, reports any disagreement with the curated CSV, and (with --write)
rewrites the CSV using the PubMed record as the source of truth.

Usage (from backend/):
    python -m scripts.fetch_pubmed                 # verify only
    python -m scripts.fetch_pubmed --write         # verify and enrich in place

Respects NCBI usage policy: batches of up to 200 IDs, <= 3 requests/second
(10/s with NCBI_API_KEY), tool + email parameters set from .env.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.parse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from scripts._http import request  # noqa: E402  (certifi trust store; see scripts/_http.py)

ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "sample" / "publications.csv"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def fetch_summaries(pmids: list[str]) -> dict[str, dict]:
    settings = get_settings()
    out: dict[str, dict] = {}
    for start in range(0, len(pmids), 200):
        batch = pmids[start : start + 200]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "json", "tool": "cancerbiomap"}
        if settings.ncbi_email:
            params["email"] = settings.ncbi_email
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
        url = f"{ESUMMARY}?{urllib.parse.urlencode(params)}"
        result = request(url)["result"]
        for pmid in batch:
            if pmid in result and "error" not in result[pmid]:
                out[pmid] = result[pmid]
        time.sleep(0.4)
    return out


def summary_to_row(pmid: str, rec: dict) -> dict:
    authors = [a["name"] for a in rec.get("authors", []) if a.get("authtype") == "Author"]
    if not authors:  # consortium-only author lists
        authors = [a["name"] for a in rec.get("authors", [])]
    author_text = ", ".join(authors[:6]) + (", et al." if len(authors) > 6 else "")
    doi = next((a["value"] for a in rec.get("articleids", []) if a.get("idtype") == "doi"), None)
    year_match = re.match(r"(\d{4})", rec.get("pubdate", "") or rec.get("epubdate", ""))
    return {
        "pmid": pmid,
        "doi": doi or "",
        "title": rec.get("title", "").strip(),
        "authors": author_text,
        "publication_year": int(year_match.group(1)) if year_match else None,
        "journal": rec.get("source", ""),
        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--write", action="store_true", help="rewrite the CSV with PubMed metadata")
    args = parser.parse_args()

    df = pd.read_csv(args.csv, dtype={"pmid": str}, keep_default_na=False)
    pmids = [p for p in df["pmid"].tolist() if p]
    records = fetch_summaries(pmids)

    problems = 0
    rows = []
    for _, row in df.iterrows():
        pmid = row["pmid"]
        rec = records.get(pmid)
        if rec is None:
            print(f"[MISSING] PMID {pmid} not found in PubMed")
            problems += 1
            rows.append(row.to_dict())
            continue
        new = summary_to_row(pmid, rec)
        if _norm(new["title"]) != _norm(row["title"]):
            print(f"[TITLE]   PMID {pmid}\n   curated: {row['title']}\n   pubmed:  {new['title']}")
            problems += 1
        if str(new["publication_year"]) != str(row["publication_year"]):
            print(f"[YEAR]    PMID {pmid}: curated {row['publication_year']} vs pubmed {new['publication_year']}")
            problems += 1
        rows.append(new)

    print(f"\nChecked {len(df)} publications; {len(records)} found in PubMed; {problems} discrepancies.")
    if args.write:
        pd.DataFrame(rows).to_csv(args.csv, index=False, lineterminator="\n")
        print(f"Wrote enriched metadata to {args.csv}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
