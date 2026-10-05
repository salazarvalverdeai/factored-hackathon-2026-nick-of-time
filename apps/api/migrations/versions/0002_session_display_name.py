"""sessions.display_name: the name a public demo visitor typed (ADR 0026, D-068)

`schema.sql` creates it on a fresh database; this revision adds it to one created before. Nullable, no default, so no
existing row changes.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table sessions add column if not exists display_name text null")


def downgrade() -> None:
    raise NotImplementedError("schema changes here only add columns")
