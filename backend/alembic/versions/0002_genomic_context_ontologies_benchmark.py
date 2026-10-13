"""genomic context, ontologies and external benchmark

Adds TCGA cohort and gene-level alteration counts (cBioPortal), Mondo / ICD-O-3 / HGNC identifiers, the
biomarker prevalence basis, and the CIViC external benchmark used to validate the evidence-support score.

Generated with `alembic revision --autogenerate` and reviewed by hand: the HGNC unique constraint was given a
name (so downgrade works) and the prevalence_basis CHECK constraint was added (autogenerate cannot detect CHECK
constraints on existing tables).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 00:21:14.733440
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cohort',
    sa.Column('cohort_id', sa.Integer(), nullable=False),
    sa.Column('study_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('cancer_id', sa.Integer(), nullable=False),
    sa.Column('source_name', sa.String(length=100), nullable=False),
    sa.Column('n_samples_mutation', sa.Integer(), nullable=True),
    sa.Column('n_samples_cna', sa.Integer(), nullable=True),
    sa.Column('citation', sa.String(length=200), nullable=True),
    sa.Column('source_url', sa.String(length=300), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('n_samples_cna IS NULL OR n_samples_cna >= 0', name='ck_cohort_n_cna'),
    sa.CheckConstraint('n_samples_mutation IS NULL OR n_samples_mutation >= 0', name='ck_cohort_n_mut'),
    sa.ForeignKeyConstraint(['cancer_id'], ['cancer.cancer_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('cohort_id'),
    sa.UniqueConstraint('study_id')
    )
    with op.batch_alter_table('cohort', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cohort_cancer_id'), ['cancer_id'], unique=False)

    op.create_table('external_benchmark',
    sa.Column('benchmark_id', sa.Integer(), nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=False),
    sa.Column('benchmark_source', sa.String(length=40), nullable=False),
    sa.Column('best_evidence_level', sa.String(length=1), nullable=True),
    sa.Column('n_items', sa.Integer(), nullable=False),
    sa.Column('n_shared_publications', sa.Integer(), nullable=False),
    sa.Column('matched_on', sa.Text(), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("best_evidence_level IS NULL OR best_evidence_level IN ('A', 'B', 'C', 'D', 'E')", name='ck_benchmark_level'),
    sa.CheckConstraint('n_items >= 0 AND n_shared_publications >= 0', name='ck_benchmark_counts'),
    sa.ForeignKeyConstraint(['association_id'], ['biomarker_cancer.association_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('benchmark_id'),
    sa.UniqueConstraint('association_id', 'benchmark_source', name='uq_benchmark_assoc_source')
    )
    with op.batch_alter_table('external_benchmark', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_external_benchmark_association_id'), ['association_id'], unique=False)

    op.create_table('genomic_prevalence',
    sa.Column('prevalence_id', sa.Integer(), nullable=False),
    sa.Column('gene_id', sa.Integer(), nullable=False),
    sa.Column('cohort_id', sa.Integer(), nullable=False),
    sa.Column('alteration_type', sa.String(length=30), nullable=False),
    sa.Column('altered_cases', sa.Integer(), nullable=False),
    sa.Column('profiled_cases', sa.Integer(), nullable=False),
    sa.CheckConstraint("alteration_type IN ('somatic_mutation', 'amplification', 'deep_deletion')", name='ck_alteration_type'),
    sa.CheckConstraint('altered_cases <= profiled_cases', name='ck_altered_le_profiled'),
    sa.CheckConstraint('altered_cases >= 0', name='ck_altered_nonneg'),
    sa.CheckConstraint('profiled_cases > 0', name='ck_profiled_pos'),
    sa.ForeignKeyConstraint(['cohort_id'], ['cohort.cohort_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['gene_id'], ['gene.gene_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('prevalence_id'),
    sa.UniqueConstraint('gene_id', 'cohort_id', 'alteration_type', name='uq_prevalence_gene_cohort_type')
    )
    with op.batch_alter_table('genomic_prevalence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_genomic_prevalence_cohort_id'), ['cohort_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_genomic_prevalence_gene_id'), ['gene_id'], unique=False)

    with op.batch_alter_table('biomarker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prevalence_basis', sa.String(length=40), nullable=True))
        batch_op.create_check_constraint(
            'ck_prevalence_basis',
            "prevalence_basis IS NULL OR prevalence_basis IN "
            "('somatic_mutation', 'somatic_mutation_upper_bound', 'amplification', 'deep_deletion')",
        )

    with op.batch_alter_table('cancer', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_id', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('icdo_topography', sa.String(length=40), nullable=True))

    with op.batch_alter_table('gene', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hgnc_id', sa.String(length=20), nullable=True))
        batch_op.create_unique_constraint('uq_gene_hgnc_id', ['hgnc_id'])



def downgrade() -> None:
    with op.batch_alter_table('gene', schema=None) as batch_op:
        batch_op.drop_constraint('uq_gene_hgnc_id', type_='unique')
        batch_op.drop_column('hgnc_id')

    with op.batch_alter_table('cancer', schema=None) as batch_op:
        batch_op.drop_column('icdo_topography')
        batch_op.drop_column('mondo_id')

    with op.batch_alter_table('biomarker', schema=None) as batch_op:
        batch_op.drop_constraint('ck_prevalence_basis', type_='check')
        batch_op.drop_column('prevalence_basis')

    with op.batch_alter_table('genomic_prevalence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_genomic_prevalence_gene_id'))
        batch_op.drop_index(batch_op.f('ix_genomic_prevalence_cohort_id'))

    op.drop_table('genomic_prevalence')
    with op.batch_alter_table('external_benchmark', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_external_benchmark_association_id'))

    op.drop_table('external_benchmark')
    with op.batch_alter_table('cohort', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cohort_cancer_id'))

    op.drop_table('cohort')
