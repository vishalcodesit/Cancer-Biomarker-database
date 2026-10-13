"""Weight-robustness analysis of the evidence-support score (pure functions, deterministic for a given seed).

The four weights (0.35 / 0.25 / 0.25 / 0.15) are proposed parameters, not validated ones. Instead of
defending the exact numbers, this module measures how much the RANKING of associations depends on them:

1. Monte Carlo: draw many weight vectors uniformly from the simplex (Dirichlet(1,1,1,1)), re-rank the
   associations each time, and report per association the 5th-95th percentile rank interval and how often it
   stays in the baseline top-k; globally, the Spearman correlation with the baseline ranking.
2. Ablation: drop one component at a time (its weight set to 0, the others renormalised) and measure how
   much the ranking changes, which shows which component drives the ranking.

Only associations whose four components are all observed ("complete") are ranked, so missing-data
renormalisation cannot confound the comparison.
"""
from __future__ import annotations

import random
from collections.abc import Hashable, Mapping

from app.scoring import COMPONENTS, combine

Components = Mapping[str, float | None]


def dirichlet(rng: random.Random, k: int = 4, alpha: float = 1.0) -> list[float]:
    draws = [rng.gammavariate(alpha, 1.0) for _ in range(k)]
    total = sum(draws)
    return [d / total for d in draws]


def average_ranks(scores: Mapping[Hashable, float]) -> dict[Hashable, float]:
    """Rank 1 = highest score; tied scores share the average of their positions."""
    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    ranks: dict[Hashable, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        avg = (i + j) / 2 + 1
        for t in range(i, j + 1):
            ranks[ordered[t][0]] = avg
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def spearman(a: Mapping[Hashable, float], b: Mapping[Hashable, float]) -> float | None:
    """Spearman rank correlation with average ranks for ties (Pearson correlation of the ranks)."""
    keys = [k for k in a if k in b]
    ra, rb = average_ranks({k: a[k] for k in keys}), average_ranks({k: b[k] for k in keys})
    return pearson([ra[k] for k in keys], [rb[k] for k in keys])


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0-100)."""
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(q / 100 * len(s) + 0.5)) - 1))
    return s[idx]


def _scores(components: Mapping[Hashable, Components], weights: Mapping[str, float]) -> dict[Hashable, float]:
    out = {}
    for key, comps in components.items():
        overall, _status, _cov, _missing = combine(comps, weights)
        out[key] = overall
    return out


def _top(scores: Mapping[Hashable, float], k: int) -> set:
    return set(sorted(scores, key=lambda key: (-scores[key], str(key)))[:k])


def analyse(components: Mapping[Hashable, Components], baseline_weights: Mapping[str, float],
            draws: int = 1000, seed: int = 42, top_k: int = 10) -> dict:
    complete = {k: c for k, c in components.items() if all(c.get(x) is not None for x in COMPONENTS)}
    base = _scores(complete, baseline_weights)
    base_ranks = average_ranks(base)
    base_top = _top(base, top_k)

    rng = random.Random(seed)
    per_key_ranks: dict[Hashable, list[float]] = {k: [] for k in complete}
    in_top = {k: 0 for k in complete}
    rhos, retention = [], []
    for _ in range(draws):
        w = dict(zip(COMPONENTS, dirichlet(rng)))
        s = _scores(complete, w)
        r = average_ranks(s)
        for k, v in r.items():
            per_key_ranks[k].append(v)
        top = _top(s, top_k)
        for k in top:
            in_top[k] += 1
        rho = spearman(base, s)
        if rho is not None:
            rhos.append(rho)
        retention.append(len(top & base_top) / max(1, len(base_top)))

    per_key = {
        k: {"baseline_score": round(base[k], 2), "baseline_rank": base_ranks[k],
            "median_rank": percentile(v, 50), "rank_p05": percentile(v, 5), "rank_p95": percentile(v, 95),
            "share_in_top_k": round(in_top[k] / draws, 3)}
        for k, v in per_key_ranks.items()
    }

    ablation = []
    for comp in COMPONENTS:
        rest = {c: baseline_weights[c] for c in COMPONENTS if c != comp}
        total = sum(rest.values())
        w = {c: (rest[c] / total if c != comp else 0.0) for c in COMPONENTS}
        s = _scores(complete, w)
        ablation.append({"dropped_component": comp, "spearman_vs_baseline": round(spearman(base, s) or 0.0, 3),
                         "top_k_retained": round(len(_top(s, top_k) & base_top) / max(1, len(base_top)), 3)})

    return {
        "n_ranked": len(complete), "n_excluded_incomplete": len(components) - len(complete),
        "draws": draws, "seed": seed, "top_k": top_k, "weight_distribution": "Dirichlet(1,1,1,1), uniform on the simplex",
        "spearman_mean": round(sum(rhos) / len(rhos), 3) if rhos else None,
        "spearman_p05": round(percentile(rhos, 5), 3) if rhos else None,
        "top_k_retention_mean": round(sum(retention) / len(retention), 3) if retention else None,
        "per_key": per_key, "ablation": ablation,
    }
