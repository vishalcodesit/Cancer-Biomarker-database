"""Version 1.1 features: gap analysis v2, TCGA prevalence, SQL views, robustness, CIViC validation, security."""
import pytest
from sqlalchemy import text

from app import robustness
from app.services.prevalence import curation_priority, wilson_interval
from app.services.validation import _spearman


def _code_items(rows, code, role=None):
    return [r for r in rows if r["biomarker_code"] == code and (role is None or r["biomarker_role"] == role)]


# --------------------------------------------------------------------------- gap analysis v2
def test_context_only_kegg_rows_no_longer_raise_untyped_flags(client):
    g = client.get("/api/gaps").json()
    assert g["summary"]["untyped_evidence"] == 0  # was 34 in version 1, all caused by KEGG rows
    assert g["n_associations"] == 58


def test_role_evidence_mismatch_and_the_curation_loop(client):
    items = client.get("/api/gaps", params={"flag": "role_evidence_mismatch"}).json()["items"]
    codes = {r["biomarker_code"] for r in items}
    # CDK12 predictive is supported only by genomic profiling: flagged.
    assert "CBM-046" in codes
    # T790M and ESR1 were flagged before the AURA3 and EMERALD trials were curated; the flag is now resolved.
    assert "CBM-018" not in codes and "CBM-008" not in codes
    cdk12 = _code_items(items, "CBM-046")[0]
    assert cdk12["details"]["recorded_designs"] == ["genomic_profiling"]
    assert cdk12["gap_severity"] >= 4


def test_gaps_ranked_by_prevalence_weighted_priority(client):
    items = client.get("/api/gaps", params={"sort": "curation_priority"}).json()["items"]
    prios = [r["curation_priority"] for r in items]
    assert prios == sorted(prios, reverse=True)
    for r in items:
        assert r["curation_priority"] == curation_priority(r["gap_severity"], r["tcga_frequency"])


# --------------------------------------------------------------------------- TCGA prevalence
def test_wilson_interval_properties():
    lo, hi = wilson_interval(0, 500)
    assert lo == 0.0 and 0 < hi < 0.01  # a measured zero still has an upper bound
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi and hi - lo < 0.21


def test_nsclc_frequency_pools_luad_and_lusc(db):
    rows = db.execute(text("""
        SELECT co.study_id, gp.altered_cases, gp.profiled_cases
        FROM genomic_prevalence gp JOIN cohort co ON co.cohort_id = gp.cohort_id
        JOIN gene g ON g.gene_id = gp.gene_id
        WHERE g.official_symbol = 'KRAS' AND gp.alteration_type = 'somatic_mutation'
          AND co.study_id IN ('luad_tcga_pan_can_atlas_2018', 'lusc_tcga_pan_can_atlas_2018')""")).all()
    assert len(rows) == 2
    expected = sum(r[1] for r in rows) / sum(r[2] for r in rows)
    view = db.execute(text("""SELECT frequency, n_cohorts FROM v_tcga_frequency
                              WHERE official_symbol = 'KRAS' AND cancer = 'Non-small cell lung cancer'
                                AND alteration_type = 'somatic_mutation'""")).one()
    assert view[1] == 2 and view[0] == pytest.approx(expected)


def test_association_prevalence_in_api(client):
    bid = client.get("/api/biomarkers", params={"q": "CBM-022"}).json()["items"][0]["biomarker_id"]
    a = client.get(f"/api/biomarkers/{bid}").json()["associations"][0]
    t = a["tcga"]
    assert t["gene_symbol"] == "KRAS" and t["upper_bound"] is True
    assert 0.3 < t["frequency"] < 0.5 and t["ci95_low"] < t["frequency"] < t["ci95_high"]
    # protein-expression biomarkers have no gene-level frequency
    er = client.get("/api/biomarkers", params={"q": "CBM-004"}).json()["items"][0]["biomarker_id"]
    assert client.get(f"/api/biomarkers/{er}").json()["associations"][0]["tcga"] is None


def test_view_and_api_agree_on_discordance_points(client, db):
    d = client.get("/api/prevalence/discordance").json()
    n_view = db.execute(text("""SELECT COUNT(*) FROM v_association_prevalence ap
                                JOIN evidence_score s ON s.association_id = ap.association_id
                                WHERE s.overall_score IS NOT NULL""")).scalar()
    assert d["n_plotted"] == n_view
    assert d["n_plotted"] + d["n_not_applicable"] == 58
    assert sum(d["quadrant_counts"].values()) == d["n_plotted"]


def test_gene_and_cancer_pages_show_genomic_context(client):
    cid = next(c["cancer_id"] for c in client.get("/api/cancers").json() if c["code"] == "nsclc")
    c = client.get(f"/api/cancers/{cid}").json()
    assert {x["study_id"] for x in c["cohorts"]} == {"luad_tcga_pan_can_atlas_2018", "lusc_tcga_pan_can_atlas_2018"}
    assert c["top_altered_genes"][0]["frequency"] >= c["top_altered_genes"][-1]["frequency"]
    assert c["mondo_id"] == "MONDO:0005233" and c["icdo_topography"] == "C34"


# --------------------------------------------------------------------------- robustness
def test_robustness_is_deterministic_and_bounded(client):
    a = client.get("/api/scores/robustness", params={"draws": 200, "seed": 1}).json()
    b = client.get("/api/scores/robustness", params={"draws": 200, "seed": 1}).json()
    assert a == b
    assert a["n_ranked"] + a["n_excluded_incomplete"] == 58
    assert -1 <= a["spearman_p05"] <= a["spearman_mean"] <= 1
    assert {x["dropped_component"] for x in a["ablation"]} == {"publication_support", "source_diversity",
                                                                "evidence_type", "consistency"}
    for r in a["items"]:
        assert r["rank_p05"] <= r["median_rank"] <= r["rank_p95"]


def test_robustness_with_baseline_weights_only_reproduces_baseline():
    comps = {i: {"publication_support": 10.0 * i, "source_diversity": 50.0, "evidence_type": 80.0, "consistency": 100.0}
             for i in range(1, 8)}
    w = {"publication_support": 0.35, "source_diversity": 0.25, "evidence_type": 0.25, "consistency": 0.15}
    res = robustness.analyse(comps, w, draws=50, seed=3)
    # only P varies between items, so every positive weighting gives the same order
    assert res["spearman_mean"] == pytest.approx(1.0)
    assert res["per_key"][7]["baseline_rank"] == 1


def test_average_ranks_handles_ties():
    assert robustness.average_ranks({"a": 3.0, "b": 3.0, "c": 1.0}) == {"a": 1.5, "b": 1.5, "c": 3.0}


# --------------------------------------------------------------------------- CIViC validation
def test_civic_validation_report(client):
    v = client.get("/api/validation/civic", params={"permutations": 2000}).json()
    assert v["n_paired"] == v["n_covered"] > 0
    assert -1 <= v["spearman_rho"] <= 1 and 0 < v["permutation_p_value"] <= 1
    assert v["bootstrap_ci95"][0] <= v["spearman_rho"] <= v["bootstrap_ci95"][1]
    cov = {c["biomarker_type"]: c for c in v["coverage_by_biomarker_type"]}
    assert cov["circulating_protein"]["covered"] == 0  # serum markers are absent from CIViC
    assert v["version_check"]["spearman_rho_v1_0_0"] is not None


def test_spearman_known_values():
    assert _spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert _spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_version_comparison_endpoint(client):
    c = client.get("/api/scores/comparison").json()
    assert (c["from_version"], c["to_version"]) == ("1.0.0", "1.1.0")
    assert c["n_associations"] == 58
    assert any("context-only" in reason for r in c["items"] for reason in r["reasons"])


# --------------------------------------------------------------------------- analytics, migration, security
@pytest.mark.parametrize("report,params", [
    ("tcga_frequency_by_cancer", {"cancer_a": 1}),
    ("common_but_thinly_supported", {}),
    ("score_by_civic_level", {}),
])
def test_new_sql_reports_run(client, report, params):
    r = client.get(f"/api/analytics/{report}", params=params)
    assert r.status_code == 200 and r.json()["rows"]


def test_migrations_create_views(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.config import BACKEND_DIR

    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    assert {"v_tcga_frequency", "v_association_prevalence"} <= set(inspect(create_engine(url)).get_view_names())
    command.downgrade(cfg, "0001")
    assert not inspect(create_engine(url)).get_view_names()


def test_write_endpoints_require_token_when_configured(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_token", "s3cret")
    good = "code,name\nliver,Liver cancer\n"
    assert client.post("/api/scores/recompute").status_code == 401
    assert client.post("/api/import/cancers", params={"dry_run": "false"}, files={"file": ("c.csv", good)}).status_code == 401
    # dry runs stay open; a correct token is accepted
    assert client.post("/api/import/cancers", files={"file": ("c.csv", good)}).status_code == 200
    assert client.post("/api/scores/recompute", headers={"X-Admin-Token": "s3cret"}).status_code == 200
