"""demo_transactions.run_id and product_type: a live demo visitor's synthetic charge belongs to that session's run
(spec 03 AC-14, spec 05 AC-19, ADR 0026)

`schema.sql` creates them on a fresh database; this revision adds them to one created before. Nullable, no default, so
no existing row changes.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table demo_transactions add column if not exists product_type text null")
    op.execute("alter table demo_transactions add column if not exists run_id text null")


def downgrade() -> None:
    raise NotImplementedError("schema changes here only add columns")
