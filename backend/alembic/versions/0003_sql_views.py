"""SQL views for TCGA frequency and association prevalence

Written by hand (autogenerate does not handle views). The view DDL lives in app/views.py so the migration and
the test database use exactly the same SQL.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""
from alembic import op

from app.views import VIEWS

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # op.execute works online and in offline (--sql) mode, so the PostgreSQL DDL file can be regenerated.
    for ddl in VIEWS.values():
        op.execute(ddl)


def downgrade() -> None:
    for name in reversed(list(VIEWS)):
        op.execute(f"DROP VIEW IF EXISTS {name}")
