"""Spec 05 / spec 06 FR-04: the api image ships the migration hook `deploy.sh` runs (`/app/migrate.sh`)."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_ac_13_the_migration_hook_is_executable_and_runs_alembic_upgrade_head():
    hook = ROOT / "apps/api/migrate.sh"
    assert os.access(hook, os.X_OK) and "alembic upgrade head" in hook.read_text()
    docker = (ROOT / "apps/api/Dockerfile").read_text()
    assert "/app/migrate.sh" in docker and "apps/api/migrations" in docker and "alembic" in docker


def test_ac_13_the_baseline_migration_adopts_the_store_schema():
    env = {**os.environ, "DATABASE_URL": "postgresql://offline/none"}
    out = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head", "--sql"], cwd=ROOT / "apps/api", env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert re.search(r"create table if not exists case_events", out.stdout, re.I)
    assert "INSERT INTO alembic_version" in out.stdout
