"""Evidence-support score: manually verified cases, missing-data handling, determinism and v1.1.0 properties."""
import math
import random

import pytest

from app import scoring_legacy

from app.scoring import (
    EvidenceItem,
    ScoreWeights,
    compute_score,
    consistency_score,
    evidence_type_score,
    publication_support_score,
    source_diversity_score,
)


def test_publication_support_curve():
    assert publication_support_score(0) is None  # unknown, never 0
    assert publication_support_score(1) == pytest.approx(38.69, abs=0.01)
    assert publication_support_score(3) == pytest.approx(77.37, abs=0.01)
    assert publication_support_score(5) == 100.0
    assert publication_support_score(50) == 100.0  # capped


def test_source_diversity():
    assert source_diversity_score(0) is None
    assert [source_diversity_score(n) for n in (1, 2, 3)] == [50.0, 75.0, 87.5]


def test_evidence_type_ignores_unlabelled_and_duplicates():
    assert evidence_type_score([None, None]) is None
    # distinct values {95, 80}: 100 * (1 - 0.05 * (1 - 0.25*0.80)) = 96.0
    assert evidence_type_score(["randomized_clinical_trial", "patient_cohort", "patient_cohort", None]) == 96.0
    # a single design scores exactly its rubric value
    assert evidence_type_score(["patient_cohort"]) == 80.0


def test_consistency_only_uses_curated_annotations():
    assert consistency_score([None, None]) is None  # unknown is not agreement
    assert consistency_score(["supports", "conflicting"]) == 50.0
    assert consistency_score(["supports", "mixed", None]) == 75.0


def test_manual_complete_case():
    """Hand calculation (v1.1.0):
    P = 100*log2(4)/log2(6) = 77.37 ; D = 100*(1-0.5^2) = 75
    T = 100*(1 - 0.05*(1-0.25*0.80)*(1-0.25*0.65)) = 100*(1 - 0.05*0.80*0.8375) = 96.65 ; C = 100
    Score = 0.35*77.37 + 0.25*75 + 0.25*96.65 + 0.15*100 = 84.99
    """
    items = [
        EvidenceItem("pmid:1", "PubMed", "randomized_clinical_trial", "supports"),
        EvidenceItem("pmid:2", "PubMed", "patient_cohort", "supports"),
        EvidenceItem("pmid:3", "NCI GDC (TCGA)", "genomic_profiling", None),
    ]
    r = compute_score(items)
    assert r.score_status == "complete"
    assert (r.publication_support, r.source_diversity, r.evidence_type, r.consistency) == (77.37, 75.0, 96.65, 100.0)
    assert r.overall_score == pytest.approx(84.99, abs=0.01)
    assert r.evidence_coverage == 1.0 and r.missing_components == []


def test_duplicate_records_do_not_inflate_support():
    one = [EvidenceItem("pmid:1", "PubMed", "patient_cohort", "supports")]
    dup = one * 3 + [EvidenceItem("pmid:1", "pubmed ", "patient_cohort", "supports")]
    a, b = compute_score(one), compute_score(dup)
    assert (b.n_publications, b.n_sources) == (1, 1)
    assert a.overall_score == b.overall_score


def test_missing_consistency_gives_provisional_renormalised_score():
    items = [
        EvidenceItem("pmid:1", "PubMed", "randomized_clinical_trial", None),
        EvidenceItem("pmid:2", "PubMed", "patient_cohort", None),
        EvidenceItem("pmid:3", "NCI GDC (TCGA)", "genomic_profiling", None),
    ]
    r = compute_score(items)
    assert r.score_status == "provisional"
    assert r.consistency is None and r.missing_components == ["consistency"]
    assert r.evidence_coverage == 0.85
    expected = (0.35 * 77.37 + 0.25 * 75 + 0.25 * 96.65) / 0.85
    assert r.overall_score == pytest.approx(expected, abs=0.01)


def test_insufficient_when_coverage_below_minimum():
    r = compute_score([EvidenceItem(None, "KEGG", None, None)])
    assert r.score_status == "insufficient"
    assert r.overall_score is None
    assert r.evidence_coverage == 0.25


def test_no_evidence_is_insufficient_not_zero():
    r = compute_score([])
    assert r.overall_score is None and r.score_status == "insufficient"
    assert len(r.missing_components) == 4


def test_conflicting_evidence_lowers_consistency():
    base = [EvidenceItem("pmid:1", "PubMed", "clinical_guideline", "supports")]
    conflict = base + [EvidenceItem("pmid:2", "PubMed", "clinical_guideline", "conflicting")]
    assert compute_score(conflict).consistency == 50.0


def test_deterministic_for_identical_inputs():
    items = [EvidenceItem(f"pmid:{i}", s, t, c) for i, (s, t, c) in enumerate(
        [("PubMed", "review", "mixed"), ("KEGG", None, None), ("PubMed", "experimental", "supports")])]
    results = [compute_score(list(items)).to_dict() for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_custom_weights_validated_and_applied():
    with pytest.raises(ValueError):
        ScoreWeights(0.5, 0.5, 0.5, 0.5).validate()
    w = ScoreWeights(1.0, 0.0, 0.0, 0.0)
    r = compute_score([EvidenceItem("pmid:1", "PubMed", "review", "supports")], weights=w)
    assert math.isclose(r.overall_score, 38.69, abs_tol=0.01)


# --------------------------------------------------------------------------- v1.1.0 properties
DESIGNS = list(scoring_legacy.EVIDENCE_TYPE_RUBRIC) + [None]


def test_context_only_records_are_not_a_supporting_source():
    """KEGG disease-map membership (no publication, no study design) must not raise source diversity."""
    pubmed = [EvidenceItem("pmid:1", "PubMed", "randomized_clinical_trial", "supports")]
    with_kegg = pubmed + [EvidenceItem(None, "KEGG", None, None, role_support=False)]
    a, b = compute_score(pubmed), compute_score(with_kegg)
    assert (a.n_sources, b.n_sources) == (1, 1)
    assert a.overall_score == b.overall_score
    assert b.n_context_only == 1 and b.n_evidence == 2


def test_legacy_module_reproduces_original_results():
    """The frozen 1.0.0 module still gives the original hand-checked 83.45 and the original KEGG inflation."""
    items = [
        scoring_legacy.EvidenceItem("pmid:1", "PubMed", "randomized_clinical_trial", "supports"),
        scoring_legacy.EvidenceItem("pmid:2", "PubMed", "patient_cohort", "supports"),
        scoring_legacy.EvidenceItem("pmid:3", "NCI GDC (TCGA)", "genomic_profiling", None),
    ]
    assert scoring_legacy.compute_score(items).overall_score == pytest.approx(83.45, abs=0.01)
    kegg = items + [scoring_legacy.EvidenceItem(None, "KEGG", None, None)]
    assert scoring_legacy.compute_score(kegg).n_sources == 3  # the 1.0.0 behaviour that 1.1.0 fixes


def test_v1_0_0_counterexample_is_fixed():
    """1.0.0 lowered the score when a 6th corroborating study (a review) was added to five RCTs."""
    base = [EvidenceItem(f"pmid:{i}", "PubMed", "randomized_clinical_trial", "supports") for i in range(5)]
    more = base + [EvidenceItem("pmid:9", "PubMed", "review", "supports")]
    old = [scoring_legacy.EvidenceItem(*astuple4(i)) for i in base], [scoring_legacy.EvidenceItem(*astuple4(i)) for i in more]
    assert scoring_legacy.compute_score(old[1]).overall_score < scoring_legacy.compute_score(old[0]).overall_score
    assert compute_score(more).overall_score >= compute_score(base).overall_score


def astuple4(i: EvidenceItem) -> tuple:
    return i.publication_key, i.source_name, i.evidence_type, i.consistency


def test_evidence_type_bounds_and_monotonicity_randomised():
    rng = random.Random(7)
    for _ in range(2000):
        types = [rng.choice(DESIGNS) for _ in range(rng.randint(1, 6))]
        t = evidence_type_score(types)
        labelled = [scoring_legacy.EVIDENCE_TYPE_RUBRIC[x] for x in types if x]
        if not labelled:
            assert t is None
            continue
        assert max(labelled) <= t <= 100.0
        t2 = evidence_type_score(types + [rng.choice(DESIGNS)])
        assert t2 >= t


def test_adding_supporting_evidence_never_lowers_score_randomised():
    """Monotonicity: appending a record that 'supports' (or carries no annotation) never lowers the overall score."""
    rng = random.Random(11)
    sources = ["PubMed", "NCI GDC (TCGA)", "ClinVar"]
    for _ in range(1500):
        items = [EvidenceItem(f"pmid:{rng.randint(1, 8)}", rng.choice(sources), rng.choice(DESIGNS),
                              rng.choice(["supports", None])) for _ in range(rng.randint(1, 6))]
        before = compute_score(items)
        extra = EvidenceItem(f"pmid:{rng.randint(1, 12)}", rng.choice(sources), rng.choice(DESIGNS), rng.choice(["supports", None]))
        after = compute_score(items + [extra])
        if before.score_status == "complete" and after.score_status == "complete":
            assert after.overall_score >= before.overall_score - 1e-9


def test_breadth_discount_zero_uses_strongest_design_only():
    assert evidence_type_score(["randomized_clinical_trial", "review"], discount=0.0) == 95.0
    with pytest.raises(ValueError):
        compute_score([], breadth_discount=1.5)
