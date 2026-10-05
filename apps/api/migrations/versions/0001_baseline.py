"""baseline: the schema of spec 01 §6.5 (D-002)

Adopts `packages/nick_of_time/store/schema.sql`, which is idempotent (`create ... if not exists`), as the first
migration, so a database that `infra/deploy.sh` already created upgrades without changes. Later schema changes are new
revisions here; the SQL file stays the source of the first one.

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import context, op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = next(p for p in (Path(__file__).resolve().parents[i] / "packages/nick_of_time/store/schema.sql"
                          for i in range(2, 6)) if p.exists())     # repo checkout and the image (/srv/packages/...)


def upgrade() -> None:
    # exec_driver_sql: the file holds `::text` casts and `%` formats that SQLAlchemy's text() would read as parameters
    sql = SCHEMA.read_text(encoding="utf-8")
    if context.is_offline_mode():                      # `--sql`: the script is printed, not run
        op.execute(sql)
    else:
        # psycopg 3 parses %-placeholders whenever params are passed (exec_driver_sql passes them); a bare
        # cursor.execute(sql) with no params sends the file as is, so the `%I` formats in the trigger block survive.
        with op.get_bind().connection.dbapi_connection.cursor() as cursor:
            cursor.execute(sql)


def downgrade() -> None:
    raise NotImplementedError("append-only audit tables are never dropped by a migration")
