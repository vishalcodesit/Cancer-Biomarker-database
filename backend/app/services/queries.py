"""Read-side query services used by the API routers.

All filtering, searching, sorting and pagination is done in the database with
SQLAlchemy expressions (bound parameters), not on the client.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import Select, and_, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.scoring import SCORING_VERSION
from app.services import prevalence
from app.services.scores import current_score, score_to_dict

BC = m.BiomarkerCancer
EV = m.Evidence
ES = m.EvidenceScore


# --------------------------------------------------------------------------- external links
def gene_links(g: m.Gene) -> list[dict]:
    links = []
    if g.ncbi_gene_id:
        links.append({"label": "NCBI Gene", "url": f"https://www.ncbi.nlm.nih.gov/gene/{g.ncbi_gene_id}"})
    if g.hgnc_id:
        links.append({"label": g.hgnc_id, "url": f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{g.hgnc_id}"})
    else:
        links.append({"label": "HGNC search", "url": f"https://www.genenames.org/tools/search/#!/?query={g.official_symbol}"})
    return links


def protein_links(p: m.Protein) -> list[dict]:
    return [{"label": "UniProt", "url": f"https://www.uniprot.org/uniprotkb/{p.accession}/entry"}]


def cancer_links(c: m.Cancer) -> list[dict]:
    links = []
    if c.external_identifier and c.external_identifier.startswith("DOID:"):
        links.append({"label": "Disease Ontology", "url": f"https://disease-ontology.org/?id={c.external_identifier}"})
    if c.mondo_id:
        links.append({"label": c.mondo_id, "url": f"https://monarchinitiative.org/{c.mondo_id}"})
    if c.gdc_project_id:
        links.append({"label": "NCI GDC project", "url": f"https://portal.gdc.cancer.gov/projects/{c.gdc_project_id}"})
    return links


def variant_links(v: m.Variant) -> list[dict]:
    return [{"label": "dbSNP", "url": f"https://www.ncbi.nlm.nih.gov/snp/{v.dbsnp_id}"}] if v.dbsnp_id else []


# --------------------------------------------------------------------------- serializers
def gene_brief(g: m.Gene) -> dict:
    return {"gene_id": g.gene_id, "official_symbol": g.official_symbol, "full_name": g.full_name,
            "ncbi_gene_id": g.ncbi_gene_id, "hgnc_id": g.hgnc_id}


def protein_brief(p: m.Protein) -> dict:
    return {"protein_id": p.protein_id, "accession": p.accession, "name": p.name}


def pathway_brief(p: m.Pathway) -> dict:
    return {"pathway_id": p.pathway_id, "pathway_name": p.pathway_name, "pathway_database": p.pathway_database,
            "external_identifier": p.external_identifier, "source_url": p.source_url}


def cancer_brief(c: m.Cancer) -> dict:
    return {"cancer_id": c.cancer_id, "code": c.code, "name": c.name}


def biomarker_brief(b: m.Biomarker) -> dict:
    return {"biomarker_id": b.biomarker_id, "biomarker_code": b.biomarker_code, "name": b.name,
            "biomarker_type": b.biomarker_type, "prevalence_basis": b.prevalence_basis}


def benchmark_dict(a: m.BiomarkerCancer) -> dict | None:
    b = next((x for x in a.benchmarks if x.benchmark_source == "CIViC"), None)
    if b is None:
        return None
    return {"source": b.benchmark_source, "best_evidence_level": b.best_evidence_level, "n_items": b.n_items,
            "n_shared_publications": b.n_shared_publications, "matched_on": b.matched_on, "retrieved_at": b.retrieved_at}


def publication_dict(p: m.Publication) -> dict:
    return {"publication_id": p.publication_id, "pmid": p.pmid, "doi": p.doi, "title": p.title,
            "authors": p.authors, "publication_year": p.publication_year, "journal": p.journal,
            "source_url": p.source_url}


def variant_dict(v: m.Variant) -> dict:
    return {"variant_id": v.variant_id, "variant_identifier": v.variant_identifier, "gene": gene_brief(v.gene),
            "protein_change": v.protein_change, "dbsnp_id": v.dbsnp_id, "genome_assembly": v.genome_assembly,
            "chromosome": v.chromosome, "position": v.position, "reference_allele": v.reference_allele,
            "alternate_allele": v.alternate_allele,
            "clinical_or_research_annotation": v.clinical_or_research_annotation,
            "source_identifier": v.source_identifier, "links": variant_links(v)}


def evidence_dict(e: m.Evidence) -> dict:
    return {"evidence_id": e.evidence_id, "evidence_type": e.evidence_type, "source_name": e.source_name,
            "source_record_id": e.source_record_id, "evidence_summary": e.evidence_summary,
            "consistency_annotation": e.consistency_annotation, "retrieved_at": e.retrieved_at,
            "source_url": e.source_url,
            "publication": publication_dict(e.publication) if e.publication else None}


def association_dict(a: m.BiomarkerCancer, with_evidence: bool = True, counts: dict | None = None) -> dict:
    d = {"association_id": a.association_id, "biomarker": biomarker_brief(a.biomarker),
         "cancer": cancer_brief(a.cancer), "biomarker_role": a.biomarker_role,
         "association_description": a.association_description, "source_status": a.source_status,
         "score": score_to_dict(current_score(a)),
         "variants": [{"variant_id": v.variant_id, "variant_identifier": v.variant_identifier} for v in a.variants],
         "n_evidence": len(a.evidence),
         "n_publications": len({e.publication_id for e in a.evidence if e.publication_id}),
         "civic": benchmark_dict(a),
         "tcga": prevalence.association_prevalence(a, counts) if counts is not None else None}
    if with_evidence:
        d["evidence"] = [evidence_dict(e) for e in a.evidence]
    return d


ASSOC_LOAD = (
    selectinload(BC.biomarker).selectinload(m.Biomarker.genes),
    selectinload(BC.benchmarks),
    selectinload(BC.cancer),
    selectinload(BC.scores),
    selectinload(BC.variants),
    selectinload(BC.evidence).selectinload(EV.publication),
)


# --------------------------------------------------------------------------- biomarkers
def _filtered_biomarker_ids(cancer_id: int | None, role: str | None) -> Select | None:
    if cancer_id is None and role is None:
        return None
    q = select(BC.biomarker_id)
    if cancer_id is not None:
        q = q.where(BC.cancer_id == cancer_id)
    if role is not None:
        q = q.where(BC.biomarker_role == role)
    return q


def list_biomarkers(db: Session, *, q: str | None, cancer_id: int | None, biomarker_type: str | None,
                    role: str | None, sort: str, order: str, offset: int | None, limit: int | None
                    ) -> tuple[list[dict], int]:
    pubs = (select(BC.biomarker_id.label("bid"), func.count(distinct(EV.publication_id)).label("n_pubs"))
            .join(EV, EV.association_id == BC.association_id).group_by(BC.biomarker_id).subquery())
    best = (select(BC.biomarker_id.label("bid"), func.max(ES.overall_score).label("max_score"))
            .join(ES, and_(ES.association_id == BC.association_id, ES.scoring_version == SCORING_VERSION))
            .group_by(BC.biomarker_id).subquery())
    n_pubs = func.coalesce(pubs.c.n_pubs, 0)
    stmt = (select(m.Biomarker, n_pubs.label("n_pubs"), best.c.max_score)
            .outerjoin(pubs, pubs.c.bid == m.Biomarker.biomarker_id)
            .outerjoin(best, best.c.bid == m.Biomarker.biomarker_id))
    if q:
        like = f"%{q.strip()}%"
        gene_hits = (select(m.BiomarkerGene.biomarker_id).join(m.Gene, m.Gene.gene_id == m.BiomarkerGene.gene_id)
                     .where(or_(m.Gene.official_symbol.ilike(like), m.Gene.full_name.ilike(like))))
        stmt = stmt.where(or_(m.Biomarker.name.ilike(like), m.Biomarker.biomarker_code.ilike(like),
                              m.Biomarker.external_identifier.ilike(like), m.Biomarker.biomarker_id.in_(gene_hits)))
    if biomarker_type:
        stmt = stmt.where(m.Biomarker.biomarker_type == biomarker_type)
    sub = _filtered_biomarker_ids(cancer_id, role)
    if sub is not None:
        stmt = stmt.where(m.Biomarker.biomarker_id.in_(sub))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    key = {"name": func.lower(m.Biomarker.name), "publications": n_pubs, "score": best.c.max_score,
           "code": m.Biomarker.biomarker_code}.get(sort, m.Biomarker.name)
    key = key.desc() if order == "desc" else key.asc()
    stmt = stmt.order_by(key.nulls_last(), func.lower(m.Biomarker.name))
    if limit is not None:
        stmt = stmt.offset(offset or 0).limit(limit)
    rows = db.execute(stmt).all()

    ids = [r[0].biomarker_id for r in rows]
    assocs = db.scalars(select(BC).where(BC.biomarker_id.in_(ids)).options(
        selectinload(BC.cancer), selectinload(BC.scores))).all()
    by_bm: dict[int, list[m.BiomarkerCancer]] = defaultdict(list)
    for a in assocs:
        by_bm[a.biomarker_id].append(a)
    genes = db.execute(select(m.BiomarkerGene.biomarker_id, m.Gene.official_symbol)
                       .join(m.Gene).where(m.BiomarkerGene.biomarker_id.in_(ids))).all()
    gene_map: dict[int, list[str]] = defaultdict(list)
    for bid, sym in genes:
        gene_map[bid].append(sym)

    items = []
    for b, npubs, max_score in rows:
        al = by_bm[b.biomarker_id]
        statuses = {s.score_status for a in al for s in a.scores if s.scoring_version == SCORING_VERSION}
        items.append({
            **biomarker_brief(b),
            "gene_symbols": sorted(gene_map[b.biomarker_id]),
            "cancers": sorted({a.cancer.name for a in al}),
            "roles": sorted({a.biomarker_role for a in al}),
            "n_associations": len(al),
            "n_publications": npubs,
            "max_score": round(max_score, 2) if max_score is not None else None,
            "has_incomplete_score": bool(statuses - {"complete"}),
        })
    return items, total


def biomarker_detail(db: Session, biomarker_id: int) -> dict | None:
    b = db.scalars(select(m.Biomarker).where(m.Biomarker.biomarker_id == biomarker_id).options(
        selectinload(m.Biomarker.genes).selectinload(m.Gene.proteins),
        selectinload(m.Biomarker.genes).selectinload(m.Gene.variants),
        selectinload(m.Biomarker.pathways),
        selectinload(m.Biomarker.associations).options(*ASSOC_LOAD),
    )).first()
    if b is None:
        return None
    path_src = dict(db.execute(select(m.BiomarkerPathway.pathway_id, m.BiomarkerPathway.annotation_source)
                               .where(m.BiomarkerPathway.biomarker_id == biomarker_id)).all())
    pubs: dict[int, dict] = {}
    for a in b.associations:
        for e in a.evidence:
            if e.publication:
                p = pubs.setdefault(e.publication_id, {**publication_dict(e.publication), "contexts": []})
                p["contexts"].append({"cancer": a.cancer.name, "role": a.biomarker_role,
                                      "evidence_type": e.evidence_type})
    variant_ids = {v.variant_id for a in b.associations for v in a.variants}
    variants = [variant_dict(v) for g in b.genes for v in g.variants if v.variant_id in variant_ids]
    sources = Counter(e.source_name for a in b.associations for e in a.evidence)
    counts = prevalence.load_counts(db)
    return {
        **biomarker_brief(b),
        "description": b.description,
        "biological_function": b.biological_function,
        "external_identifier": b.external_identifier,
        "created_at": b.created_at,
        "genes": [{**gene_brief(g), "description": g.description, "links": gene_links(g),
                   "proteins": [{**protein_brief(p), "links": protein_links(p)} for p in g.proteins]}
                  for g in b.genes],
        "pathways": [{**pathway_brief(p), "annotation_source": path_src.get(p.pathway_id)} for p in b.pathways],
        "associations": sorted((association_dict(a, counts=counts) for a in b.associations),
                               key=lambda d: (d["cancer"]["name"], d["biomarker_role"])),
        "variants": variants,
        "publications": sorted(pubs.values(), key=lambda p: -(p["publication_year"] or 0)),
        "source_databases": [{"source_name": k, "n_records": v} for k, v in sources.most_common()],
    }


# --------------------------------------------------------------------------- cancers
def list_cancers(db: Session) -> list[dict]:
    rows = db.execute(
        select(m.Cancer, func.count(distinct(BC.biomarker_id)), func.count(BC.association_id))
        .outerjoin(BC, BC.cancer_id == m.Cancer.cancer_id).group_by(m.Cancer.cancer_id).order_by(m.Cancer.name)
    ).all()
    return [{**cancer_brief(c), "tissue_origin": c.tissue_origin, "cancer_category": c.cancer_category,
             "external_identifier": c.external_identifier, "mondo_id": c.mondo_id, "icdo_topography": c.icdo_topography,
             "gdc_project_id": c.gdc_project_id, "description": c.description, "n_biomarkers": nb,
             "n_associations": na, "links": cancer_links(c)}
            for c, nb, na in rows]


def score_histogram(scores: list[m.EvidenceScore | None]) -> list[dict]:
    bins = [{"bin": f"{lo}-{lo + 10}", "lower": lo, "count": 0} for lo in range(0, 100, 10)]
    unscored = 0
    for s in scores:
        if s is None or s.overall_score is None:
            unscored += 1
        else:
            bins[min(int(s.overall_score // 10), 9)]["count"] += 1
    return bins + [{"bin": "not scored", "lower": None, "count": unscored}]


def cancer_detail(db: Session, cancer_id: int) -> dict | None:
    c = db.get(m.Cancer, cancer_id)
    if c is None:
        return None
    assocs = db.scalars(select(BC).where(BC.cancer_id == cancer_id).options(
        *ASSOC_LOAD,
        selectinload(BC.biomarker).selectinload(m.Biomarker.genes).selectinload(m.Gene.pathways),
    )).all()
    genes: dict[int, dict] = {}
    pathways: Counter = Counter()
    path_obj: dict[int, m.Pathway] = {}
    pubs: dict[int, dict] = {}
    variants: dict[int, dict] = {}
    for a in assocs:
        for g in a.biomarker.genes:
            genes.setdefault(g.gene_id, {**gene_brief(g), "biomarkers": set()})["biomarkers"].add(a.biomarker.name)
            for p in g.pathways:
                pathways[p.pathway_id] += 1
                path_obj[p.pathway_id] = p
        for e in a.evidence:
            if e.publication:
                pubs.setdefault(e.publication_id, {**publication_dict(e.publication), "biomarkers": set()})[
                    "biomarkers"].add(a.biomarker.name)
        for v in a.variants:
            variants.setdefault(v.variant_id, {"variant_id": v.variant_id, "variant_identifier": v.variant_identifier,
                                               "biomarker": a.biomarker.name})
    role_counts = Counter(a.biomarker_role for a in assocs)
    counts = prevalence.load_counts(db)
    return {
        **cancer_brief(c),
        "tissue_origin": c.tissue_origin, "cancer_category": c.cancer_category,
        "external_identifier": c.external_identifier, "mondo_id": c.mondo_id, "icdo_topography": c.icdo_topography,
        "gdc_project_id": c.gdc_project_id, "description": c.description, "links": cancer_links(c),
        "cohorts": [x for x in prevalence.cohorts(db) if x["cancer_id"] == cancer_id],
        "top_altered_genes": prevalence.cancer_top_altered(db, cancer_id),
        "associations": sorted((association_dict(a, with_evidence=False, counts=counts) for a in assocs),
                               key=lambda d: (-(d["score"]["overall_score"] or -1) if d["score"] else 1,
                                              d["biomarker"]["name"])),
        "role_distribution": [{"role": k, "count": v} for k, v in sorted(role_counts.items())],
        "genes": sorted(({**g, "biomarkers": sorted(g["biomarkers"])} for g in genes.values()),
                        key=lambda g: g["official_symbol"]),
        "pathways": [{**pathway_brief(path_obj[pid]), "n_gene_links": n} for pid, n in pathways.most_common()],
        "variants": list(variants.values()),
        "publications": sorted(({**p, "biomarkers": sorted(p["biomarkers"])} for p in pubs.values()),
                               key=lambda p: -(p["publication_year"] or 0)),
        "score_distribution": score_histogram([current_score(a) for a in assocs]),
    }


def compare_cancers(db: Session, a_id: int, b_id: int) -> dict | None:
    ca, cb = db.get(m.Cancer, a_id), db.get(m.Cancer, b_id)
    if ca is None or cb is None:
        return None
    assocs = db.scalars(select(BC).where(BC.cancer_id.in_([a_id, b_id])).options(
        selectinload(BC.biomarker), selectinload(BC.scores))).all()
    per: dict[int, dict] = {}
    for a in assocs:
        entry = per.setdefault(a.biomarker_id, {**biomarker_brief(a.biomarker), "a": [], "b": []})
        s = current_score(a)
        entry["a" if a.cancer_id == a_id else "b"].append(
            {"role": a.biomarker_role, "score": s.overall_score if s else None,
             "score_status": s.score_status if s else None, "association_id": a.association_id})
    shared = [e for e in per.values() if e["a"] and e["b"]]
    only_a = [e for e in per.values() if e["a"] and not e["b"]]
    only_b = [e for e in per.values() if e["b"] and not e["a"]]
    key = lambda e: e["name"]  # noqa: E731
    return {"cancer_a": cancer_brief(ca), "cancer_b": cancer_brief(cb),
            "shared": sorted(shared, key=key), "only_a": sorted(only_a, key=key), "only_b": sorted(only_b, key=key)}


# --------------------------------------------------------------------------- genes / proteins / pathways / variants
def list_genes(db: Session, q: str | None) -> list[dict]:
    stmt = select(m.Gene).options(selectinload(m.Gene.biomarkers), selectinload(m.Gene.proteins)).order_by(
        m.Gene.official_symbol)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Gene.official_symbol.ilike(like), m.Gene.full_name.ilike(like)))
    genes = sorted(db.scalars(stmt).all(), key=lambda g: g.official_symbol)
    return [{**gene_brief(g), "n_biomarkers": len(g.biomarkers), "n_proteins": len(g.proteins)} for g in genes]


def gene_detail(db: Session, gene_id: int) -> dict | None:
    g = db.scalars(select(m.Gene).where(m.Gene.gene_id == gene_id).options(
        selectinload(m.Gene.proteins), selectinload(m.Gene.pathways), selectinload(m.Gene.variants),
        selectinload(m.Gene.biomarkers).selectinload(m.Biomarker.associations).selectinload(BC.cancer))).first()
    if g is None:
        return None
    return {**gene_brief(g), "organism": g.organism, "description": g.description, "links": gene_links(g),
            "tcga_prevalence": prevalence.gene_prevalence(db, gene_id),
            "proteins": [{**protein_brief(p), "links": protein_links(p)} for p in g.proteins],
            "pathways": [pathway_brief(p) for p in sorted(g.pathways, key=lambda p: p.pathway_name)],
            "variants": [variant_dict(v) for v in g.variants],
            "biomarkers": [{**biomarker_brief(b), "cancers": sorted({a.cancer.name for a in b.associations})}
                           for b in g.biomarkers]}


def list_proteins(db: Session, q: str | None) -> list[dict]:
    stmt = select(m.Protein).options(selectinload(m.Protein.genes)).order_by(m.Protein.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Protein.name.ilike(like), m.Protein.accession.ilike(like)))
    proteins = sorted(db.scalars(stmt).all(), key=lambda p: (p.name.casefold(), p.accession))
    return [{**protein_brief(p), "genes": [g.official_symbol for g in p.genes]} for p in proteins]


def protein_detail(db: Session, protein_id: int) -> dict | None:
    p = db.scalars(select(m.Protein).where(m.Protein.protein_id == protein_id).options(
        selectinload(m.Protein.genes).selectinload(m.Gene.biomarkers),
        selectinload(m.Protein.genes).selectinload(m.Gene.pathways))).first()
    if p is None:
        return None
    return {**protein_brief(p), "function": p.function, "organism": p.organism, "links": protein_links(p),
            "genes": [gene_brief(g) for g in p.genes],
            "biomarkers": [biomarker_brief(b) for g in p.genes for b in g.biomarkers],
            "pathways": [pathway_brief(pw) for g in p.genes for pw in g.pathways]}


def list_pathways(db: Session, q: str | None) -> list[dict]:
    stmt = select(m.Pathway).options(selectinload(m.Pathway.biomarkers), selectinload(m.Pathway.genes)).order_by(
        m.Pathway.pathway_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Pathway.pathway_name.ilike(like), m.Pathway.external_identifier.ilike(like)))
    pathways = sorted(db.scalars(stmt).all(), key=lambda p: (p.pathway_name.casefold(), p.pathway_id))
    return [{**pathway_brief(p), "description": p.description, "n_biomarkers": len(p.biomarkers),
             "n_genes": len(p.genes)} for p in pathways]


def pathway_detail(db: Session, pathway_id: int) -> dict | None:
    p = db.scalars(select(m.Pathway).where(m.Pathway.pathway_id == pathway_id).options(
        selectinload(m.Pathway.genes),
        selectinload(m.Pathway.biomarkers).selectinload(m.Biomarker.associations).selectinload(BC.cancer))).first()
    if p is None:
        return None
    src = dict(db.execute(select(m.BiomarkerPathway.biomarker_id, m.BiomarkerPathway.annotation_source)
                          .where(m.BiomarkerPathway.pathway_id == pathway_id)).all())
    return {**pathway_brief(p), "description": p.description,
            "genes": [gene_brief(g) for g in sorted(p.genes, key=lambda g: g.official_symbol)],
            "biomarkers": [{**biomarker_brief(b), "annotation_source": src.get(b.biomarker_id),
                            "cancers": sorted({a.cancer.name for a in b.associations})}
                           for b in sorted(p.biomarkers, key=lambda b: b.name)]}


def list_variants(db: Session, q: str | None, gene_id: int | None) -> list[dict]:
    stmt = select(m.Variant).options(selectinload(m.Variant.gene)).order_by(m.Variant.variant_identifier)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Variant.variant_identifier.ilike(like), m.Variant.dbsnp_id.ilike(like)))
    if gene_id:
        stmt = stmt.where(m.Variant.gene_id == gene_id)
    return [variant_dict(v) for v in db.scalars(stmt).all()]


def variant_detail(db: Session, variant_id: int) -> dict | None:
    v = db.scalars(select(m.Variant).where(m.Variant.variant_id == variant_id).options(
        selectinload(m.Variant.gene),
        selectinload(m.Variant.associations).options(selectinload(BC.biomarker), selectinload(BC.cancer),
                                                     selectinload(BC.scores)))).first()
    if v is None:
        return None
    return {**variant_dict(v), "associations": [
        {"association_id": a.association_id, "biomarker": biomarker_brief(a.biomarker),
         "cancer": cancer_brief(a.cancer), "biomarker_role": a.biomarker_role} for a in v.associations]}


# --------------------------------------------------------------------------- publications
def list_publications(db: Session, *, q: str | None, biomarker_id: int | None, cancer_id: int | None,
                      year_from: int | None, year_to: int | None, evidence_type: str | None,
                      offset: int | None, limit: int | None) -> tuple[list[dict], int]:
    ev_filter = select(EV.publication_id).join(BC, BC.association_id == EV.association_id).where(
        EV.publication_id.is_not(None))
    filtered = False
    if biomarker_id is not None:
        ev_filter, filtered = ev_filter.where(BC.biomarker_id == biomarker_id), True
    if cancer_id is not None:
        ev_filter, filtered = ev_filter.where(BC.cancer_id == cancer_id), True
    if evidence_type:
        ev_filter, filtered = ev_filter.where(EV.evidence_type == evidence_type), True
    stmt = select(m.Publication)
    if filtered:
        stmt = stmt.where(m.Publication.publication_id.in_(ev_filter))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Publication.title.ilike(like), m.Publication.pmid.ilike(like),
                              m.Publication.authors.ilike(like), m.Publication.journal.ilike(like),
                              m.Publication.doi.ilike(like)))
    if year_from is not None:
        stmt = stmt.where(m.Publication.publication_year >= year_from)
    if year_to is not None:
        stmt = stmt.where(m.Publication.publication_year <= year_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(m.Publication.publication_year.desc().nulls_last(), func.lower(m.Publication.title),
                         m.Publication.publication_id)
    if limit is not None:
        stmt = stmt.offset(offset or 0).limit(limit)
    pubs = db.scalars(stmt).all()
    ids = [p.publication_id for p in pubs]
    evs = db.scalars(select(EV).where(EV.publication_id.in_(ids)).order_by(EV.evidence_id).options(
        selectinload(EV.association).selectinload(BC.biomarker),
        selectinload(EV.association).selectinload(BC.cancer))).all()
    ctx: dict[int, list[m.Evidence]] = defaultdict(list)
    for e in evs:
        ctx[e.publication_id].append(e)
    items = []
    for p in pubs:
        es = ctx[p.publication_id]
        items.append({**publication_dict(p),
                      "biomarkers": sorted({e.association.biomarker.name for e in es}),
                      "biomarker_links": sorted({(e.association.biomarker_id, e.association.biomarker.name) for e in es},
                                                key=lambda t: t[1]),
                      "cancers": sorted({e.association.cancer.name for e in es}),
                      "evidence_types": sorted({e.evidence_type for e in es if e.evidence_type}),
                      "source_names": sorted({e.source_name for e in es}),
                      "summaries": [{"biomarker": e.association.biomarker.name, "cancer": e.association.cancer.name,
                                     "role": e.association.biomarker_role, "summary": e.evidence_summary,
                                     "consistency": e.consistency_annotation} for e in es]})
    return items, total


# --------------------------------------------------------------------------- associations
def list_associations(db: Session, *, cancer_id: int | None, biomarker_id: int | None, role: str | None,
                      score_status: str | None) -> list[dict]:
    stmt = select(BC).options(*ASSOC_LOAD)
    if cancer_id is not None:
        stmt = stmt.where(BC.cancer_id == cancer_id)
    if biomarker_id is not None:
        stmt = stmt.where(BC.biomarker_id == biomarker_id)
    if role:
        stmt = stmt.where(BC.biomarker_role == role)
    if score_status:
        stmt = stmt.where(BC.association_id.in_(select(ES.association_id).where(
            ES.score_status == score_status, ES.scoring_version == SCORING_VERSION)))
    counts = prevalence.load_counts(db)
    return [association_dict(a, with_evidence=False, counts=counts) for a in db.scalars(stmt).all()]


def count_associations(db: Session, cancer_id: int | None, role: str | None) -> int:
    stmt = select(func.count()).select_from(BC)
    if cancer_id is not None:
        stmt = stmt.where(BC.cancer_id == cancer_id)
    if role:
        stmt = stmt.where(BC.biomarker_role == role)
    return db.scalar(stmt) or 0


def association_detail(db: Session, association_id: int) -> m.BiomarkerCancer | None:
    return db.scalars(select(BC).where(BC.association_id == association_id).options(*ASSOC_LOAD)).first()


# --------------------------------------------------------------------------- dashboard
def dashboard_stats(db: Session, cancer_id: int | None, role: str | None, evidence_type: str | None) -> dict:
    assoc_q = select(BC.association_id)
    if cancer_id is not None:
        assoc_q = assoc_q.where(BC.cancer_id == cancer_id)
    if role:
        assoc_q = assoc_q.where(BC.biomarker_role == role)
    if evidence_type:
        assoc_q = assoc_q.where(BC.association_id.in_(select(EV.association_id).where(EV.evidence_type == evidence_type)))
    assoc_ids = assoc_q.subquery()
    in_scope = BC.association_id.in_(select(assoc_ids.c.association_id))
    ev_scope = EV.association_id.in_(select(assoc_ids.c.association_id))
    if evidence_type:
        ev_scope = and_(ev_scope, EV.evidence_type == evidence_type)
    filtered = any(v is not None for v in (cancer_id, role, evidence_type))

    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    totals = {
        "biomarkers": count(select(func.count(distinct(BC.biomarker_id))).where(in_scope)) if filtered
        else count(select(func.count()).select_from(m.Biomarker)),
        "cancers": count(select(func.count()).select_from(m.Cancer)),
        "genes": count(select(func.count()).select_from(m.Gene)),
        "proteins": count(select(func.count()).select_from(m.Protein)),
        "pathways": count(select(func.count()).select_from(m.Pathway)),
        "variants": count(select(func.count()).select_from(m.Variant)),
        "publications": count(select(func.count(distinct(EV.publication_id))).where(ev_scope)) if filtered
        else count(select(func.count()).select_from(m.Publication)),
        "associations": count(select(func.count()).where(in_scope)),
        "evidence_records": count(select(func.count()).select_from(EV).where(ev_scope)),
    }
    # Every ORDER BY ends with a unique, collation-independent key so SQLite and PostgreSQL return ties in the
    # same order (verified by comparing all endpoints on both databases).
    by_role = db.execute(select(BC.biomarker_role, func.count()).where(in_scope).group_by(BC.biomarker_role)
                         .order_by(func.count().desc(), BC.biomarker_role)).all()
    by_cancer = db.execute(select(m.Cancer.cancer_id, m.Cancer.name, func.count(BC.association_id))
                           .join(BC, BC.cancer_id == m.Cancer.cancer_id).where(in_scope)
                           .group_by(m.Cancer.cancer_id, m.Cancer.name).order_by(m.Cancer.name)).all()
    etype = func.coalesce(EV.evidence_type, "unspecified")
    by_etype = db.execute(select(etype, func.count()).where(ev_scope).group_by(etype)
                          .order_by(func.count().desc(), etype)).all()
    by_type = db.execute(select(m.Biomarker.biomarker_type, func.count(distinct(m.Biomarker.biomarker_id)))
                         .join(BC, BC.biomarker_id == m.Biomarker.biomarker_id).where(in_scope)
                         .group_by(m.Biomarker.biomarker_type)
                         .order_by(func.count(distinct(m.Biomarker.biomarker_id)).desc(), m.Biomarker.biomarker_type)).all()
    top = db.execute(select(m.Biomarker.biomarker_id, m.Biomarker.name, func.count(distinct(BC.cancer_id)),
                            func.count(distinct(EV.publication_id)))
                     .join(BC, BC.biomarker_id == m.Biomarker.biomarker_id)
                     .outerjoin(EV, EV.association_id == BC.association_id).where(in_scope)
                     .group_by(m.Biomarker.biomarker_id, m.Biomarker.name)
                     .order_by(func.count(distinct(EV.publication_id)).desc(), m.Biomarker.biomarker_code).limit(10)).all()
    status = db.execute(select(ES.score_status, func.count()).where(
        ES.scoring_version == SCORING_VERSION, ES.association_id.in_(select(assoc_ids.c.association_id)))
                        .group_by(ES.score_status).order_by(ES.score_status)).all()
    scores = db.scalars(select(ES).where(ES.scoring_version == SCORING_VERSION,
                                         ES.association_id.in_(select(assoc_ids.c.association_id)))).all()
    return {
        "filters": {"cancer_id": cancer_id, "role": role, "evidence_type": evidence_type},
        "totals": totals,
        "by_role": [{"role": r, "count": c} for r, c in by_role],
        "by_cancer": [{"cancer_id": i, "cancer": n, "count": c} for i, n, c in by_cancer],
        "by_evidence_type": [{"evidence_type": t, "count": c} for t, c in by_etype],
        "by_biomarker_type": [{"biomarker_type": t, "count": c} for t, c in by_type],
        "top_biomarkers": [{"biomarker_id": i, "name": n, "n_cancers": nc, "n_publications": np_}
                           for i, n, nc, np_ in top],
        "score_status": [{"status": s, "count": c} for s, c in status],
        "score_distribution": score_histogram(list(scores)),
    }


# --------------------------------------------------------------------------- relationship network
def network(db: Session, biomarker_id: int | None = None, cancer_id: int | None = None,
            include_publications: bool = True) -> dict | None:
    """Nodes and edges generated from explicit database relationships only."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(key: str, label: str, ntype: str, ident: int) -> str:
        nodes.setdefault(key, {"id": key, "label": label, "type": ntype, "entity_id": ident})
        return key

    def edge(src: str, dst: str, label: str) -> None:
        edges.append({"source": src, "target": dst, "label": label})

    if biomarker_id is not None:
        b = db.scalars(select(m.Biomarker).where(m.Biomarker.biomarker_id == biomarker_id).options(
            selectinload(m.Biomarker.genes).selectinload(m.Gene.proteins),
            selectinload(m.Biomarker.pathways),
            selectinload(m.Biomarker.associations).options(*ASSOC_LOAD))).first()
        if b is None:
            return None
        root = node(f"b{b.biomarker_id}", b.name, "biomarker", b.biomarker_id)
        for a in b.associations:
            c = node(f"c{a.cancer_id}", a.cancer.name, "cancer", a.cancer_id)
            edge(root, c, a.biomarker_role)
            if include_publications:
                for e in a.evidence:
                    if e.publication:
                        p = node(f"p{e.publication_id}", f"PMID {e.publication.pmid}", "publication", e.publication_id)
                        edge(c, p, "evidence")
            for v in a.variants:
                edge(root, node(f"v{v.variant_id}", v.variant_identifier, "variant", v.variant_id), "variant")
        for g in b.genes:
            gk = node(f"g{g.gene_id}", g.official_symbol, "gene", g.gene_id)
            edge(root, gk, "involves gene")
            for pr in g.proteins:
                edge(gk, node(f"r{pr.protein_id}", pr.accession, "protein", pr.protein_id), "encodes")
        for pw in b.pathways:
            edge(root, node(f"w{pw.pathway_id}", f"{pw.pathway_name} ({pw.external_identifier})", "pathway",
                            pw.pathway_id), "pathway")
    elif cancer_id is not None:
        c = db.get(m.Cancer, cancer_id)
        if c is None:
            return None
        root = node(f"c{c.cancer_id}", c.name, "cancer", c.cancer_id)
        assocs = db.scalars(select(BC).where(BC.cancer_id == cancer_id).options(
            selectinload(BC.biomarker).selectinload(m.Biomarker.genes))).all()
        for a in assocs:
            bk = node(f"b{a.biomarker_id}", a.biomarker.name, "biomarker", a.biomarker_id)
            edge(root, bk, a.biomarker_role)
            for g in a.biomarker.genes:
                edge(bk, node(f"g{g.gene_id}", g.official_symbol, "gene", g.gene_id), "involves gene")
    else:
        return None
    # Collapse duplicate edges (e.g. same publication supporting two roles).
    seen, unique = set(), []
    for e in edges:
        k = (e["source"], e["target"], e["label"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return {"nodes": list(nodes.values()), "edges": unique}
