"""Validation of the evidence-support score.

1. External validity: rank concordance with an independent, expert-curated knowledge base (CIViC evidence
   levels A-E). CIViC never feeds the score, so agreement is evidence that the score tracks expert judgement.
2. Internal robustness: how much the ranking depends on the chosen weights (app.robustness).
3. Coverage: which kinds of biomarkers an established genomic knowledge base does NOT cover, which tests the
   project's premise that non-DNA biomarkers are under-represented.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app import robustness
from app.config import get_settings
from app.services.scores import (_load_all, current_score, legacy_score_association, score_association,
                                 weights_from_settings)

LEVEL_ORDINAL = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
LEVEL_MEANING = {"A": "Validated association", "B": "Clinical evidence", "C": "Case study",
                 "D": "Preclinical evidence", "E": "Inferential association"}


def _spearman(x: list[float], y: list[float]) -> float | None:
    rx = robustness.average_ranks(dict(enumerate(x)))
    ry = robustness.average_ranks(dict(enumerate(y)))
    return robustness.pearson([rx[i] for i in range(len(x))], [ry[i] for i in range(len(y))])


def permutation_p_value(x: list[float], y: list[float], n: int = 10000, seed: int = 7) -> float | None:
    """Two-sided permutation test of Spearman's rho (shuffles y; add-one estimator, never exactly 0)."""
    observed = _spearman(x, y)
    if observed is None:
        return None
    rng, y2, extreme = random.Random(seed), list(y), 0
    for _ in range(n):
        rng.shuffle(y2)
        r = _spearman(x, y2)
        if r is not None and abs(r) >= abs(observed) - 1e-12:
            extreme += 1
    return (extreme + 1) / (n + 1)


def bootstrap_ci(x: list[float], y: list[float], n: int = 2000, seed: int = 7) -> tuple[float, float] | None:
    rng, rhos = random.Random(seed), []
    idx = list(range(len(x)))
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        r = _spearman([x[i] for i in s], [y[i] for i in s])
        if r is not None:
            rhos.append(r)
    if not rhos:
        return None
    return robustness.percentile(rhos, 2.5), robustness.percentile(rhos, 97.5)


def civic_concordance(db: Session, permutations: int = 10000, seed: int = 7) -> dict:
    assocs = db.scalars(select(m.BiomarkerCancer).options(
        selectinload(m.BiomarkerCancer.biomarker), selectinload(m.BiomarkerCancer.cancer),
        selectinload(m.BiomarkerCancer.scores), selectinload(m.BiomarkerCancer.benchmarks),
        selectinload(m.BiomarkerCancer.evidence))).all()
    rows, coverage = [], defaultdict(Counter)
    for a in assocs:
        bench = next((b for b in a.benchmarks if b.benchmark_source == "CIViC"), None)
        s = current_score(a)
        covered = bool(bench and bench.n_items > 0)
        coverage[a.biomarker.biomarker_type]["covered" if covered else "not_covered"] += 1
        rows.append({"association_id": a.association_id, "biomarker_name": a.biomarker.name,
                     "biomarker_code": a.biomarker.biomarker_code, "biomarker_type": a.biomarker.biomarker_type,
                     "cancer_name": a.cancer.name, "biomarker_role": a.biomarker_role,
                     "overall_score": s.overall_score if s else None, "score_status": s.score_status if s else None,
                     "civic_level": bench.best_evidence_level if covered else None,
                     "civic_items": bench.n_items if bench else 0,
                     "shared_publications": bench.n_shared_publications if bench else 0,
                     "matched_on": bench.matched_on if bench else None})

    paired = [r for r in rows if r["civic_level"] and r["overall_score"] is not None]
    x = [r["overall_score"] for r in paired]
    y = [LEVEL_ORDINAL[r["civic_level"]] for r in paired]
    rho = _spearman(x, y) if len(paired) >= 3 else None
    by_level = []
    for lv in ("A", "B", "C", "D", "E"):
        sc = [r["overall_score"] for r in paired if r["civic_level"] == lv]
        if sc:
            by_level.append({"level": lv, "meaning": LEVEL_MEANING[lv], "n": len(sc),
                             "mean_score": round(sum(sc) / len(sc), 2), "min_score": min(sc), "max_score": max(sc)})
    ci = bootstrap_ci(x, y, seed=seed) if rho is not None else None
    version_check = _version_check(db, paired, y, seed) if rho is not None else None
    return {
        "benchmark": "CIViC (civicdb.org), accepted evidence items, CC0 licence",
        "n_associations": len(rows), "n_covered": sum(1 for r in rows if r["civic_level"]), "n_paired": len(paired),
        "spearman_rho": round(rho, 3) if rho is not None else None,
        "permutation_p_value": round(permutation_p_value(x, y, permutations, seed), 4) if rho is not None else None,
        "bootstrap_ci95": [round(ci[0], 3), round(ci[1], 3)] if ci else None,
        "mean_score_by_level": by_level,
        "version_check": version_check,
        "coverage_by_biomarker_type": [
            {"biomarker_type": t, "covered": c["covered"], "not_covered": c["not_covered"]}
            for t, c in sorted(coverage.items(), key=lambda kv: -(kv[1]["covered"] + kv[1]["not_covered"]))],
        "publications_shared_with_civic": {
            "associations_sharing_at_least_one_pmid": sum(1 for r in rows if r["shared_publications"] > 0),
            "total_shared_pmids": sum(r["shared_publications"] for r in rows)},
        "items": sorted(rows, key=lambda r: (r["civic_level"] is None, r["civic_level"] or "", -(r["overall_score"] or 0))),
        "interpretation_notes": [
            "Matching is at gene (or curated variant-keyword) level with disease-name rules; see matched_on.",
            "Tumour-agnostic approvals are recorded by CIViC under 'Solid Tumor' and are not matched to a specific cancer.",
            "CIViC level reflects the single best item; the evidence-support score reflects breadth of recorded evidence.",
        ],
    }


def _version_check(db: Session, paired: list[dict], y: list[int], seed: int) -> dict:
    """Concordance of the frozen 1.0.0 score on the same associations, with a paired bootstrap of the difference."""
    by_id = {a.association_id: a for a in _load_all(db)}
    old = [legacy_score_association(by_id[r["association_id"]]).overall_score for r in paired]
    new = [r["overall_score"] for r in paired]
    rng, idx, diffs = random.Random(seed), list(range(len(paired))), []
    for _ in range(2000):
        s = [rng.choice(idx) for _ in idx]
        a, b = _spearman([new[i] for i in s], [y[i] for i in s]), _spearman([old[i] for i in s], [y[i] for i in s])
        if a is not None and b is not None:
            diffs.append(a - b)
    rho_old = _spearman(old, y)
    return {
        "spearman_rho_v1_0_0": round(rho_old, 3) if rho_old is not None else None,
        "difference_ci95": [round(robustness.percentile(diffs, 2.5), 3), round(robustness.percentile(diffs, 97.5), 3)]
        if diffs else None,
        "explanation": (
            "Version 1.1.0 stops counting KEGG disease-map membership as a supporting source. KEGG maps list the "
            "canonical cancer genes that CIViC also rates highly, so the old boost tracked how well known a gene is, "
            "not evidence for the specific biomarker role. The score is not tuned to agree with CIViC: doing so would "
            "make CIViC useless as an independent check."
        ),
    }


def robustness_report(db: Session, draws: int = 1000, seed: int = 42, top_k: int = 10) -> dict:
    settings = get_settings()
    assocs = _load_all(db)
    comps, names = {}, {}
    for a in assocs:
        comps[a.association_id] = score_association(a, settings).components()
        names[a.association_id] = (a.biomarker.name, a.cancer.name, a.biomarker_role, a.biomarker_id)
    res = robustness.analyse(comps, weights_from_settings(settings).as_dict(), draws=draws, seed=seed, top_k=top_k)
    items = []
    for aid, d in res.pop("per_key").items():
        bname, cname, role, bid = names[aid]
        width = d["rank_p95"] - d["rank_p05"]
        items.append({"association_id": aid, "biomarker_id": bid, "biomarker_name": bname, "cancer_name": cname,
                      "biomarker_role": role, **d, "rank_interval_width": width})
    items.sort(key=lambda r: r["baseline_rank"])
    res["items"] = items
    res["baseline_weights"] = weights_from_settings(settings).as_dict()
    return res
