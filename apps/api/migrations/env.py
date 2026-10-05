"""Alembic environment (spec 05): the URL is DATABASE_URL, run with the psycopg 3 driver the store already uses."""
import os

from alembic import context
from sqlalchemy import create_engine

config = context.config


def url() -> str:
    raw = os.environ.get("DATABASE_URL", "postgresql://localhost/nickoftime")
    return raw.replace("postgresql://", "postgresql+psycopg://", 1) if raw.startswith("postgresql://") else raw


if context.is_offline_mode():
    context.configure(url=url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
