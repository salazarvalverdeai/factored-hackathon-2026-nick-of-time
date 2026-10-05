"""Spec 06 (deploy + CI): offline static checks that guard the deploy files.

These tests protect the files; the real evidence for AC-01, AC-02, AC-04, AC-05 and AC-07 is the run on the public URL
(`[C]` in the PR). Each test cites its acceptance criterion.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
WORKFLOWS = ROOT / ".github" / "workflows"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


@pytest.fixture(scope="module")
def compose() -> dict:
    return _load_yaml(INFRA / "compose.yml")


@pytest.fixture(scope="module")
def deploy_workflow() -> dict:
    return _load_yaml(WORKFLOWS / "deploy.yml")


@pytest.fixture(scope="module")
def placeholder_api():
    spec = importlib.util.spec_from_file_location("api_placeholder", INFRA / "api-placeholder" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- AC-04: compose runs the five services, Postgres has a volume, daily backup to S3 ---------------------------

def test_ac_04_compose_runs_caddy_web_api_mcp_and_postgres(compose):
    assert set(compose["services"]) == {"caddy", "web", "api", "mcp", "postgres"}


def test_ac_04_postgres_data_lives_in_a_named_volume(compose):
    mounts = compose["services"]["postgres"]["volumes"]
    assert any(m.startswith("pgdata:") for m in mounts)
    assert "pgdata" in compose["volumes"]


def test_ac_04_only_caddy_publishes_ports(compose):
    published = {name for name, svc in compose["services"].items() if "ports" in svc}
    assert published == {"caddy"}


def test_ac_04_caddy_mounts_a_directory_so_git_checkout_is_picked_up(compose):
    # A single-file bind mount keeps the old inode after `git checkout` replaces the file.
    mounts = compose["services"]["caddy"]["volumes"]
    assert any(m.startswith("./caddy:/etc/caddy") for m in mounts)
    assert (INFRA / "caddy" / "Caddyfile").is_file()


def test_ac_04_backup_dumps_postgres_to_s3_and_deploy_installs_the_daily_cron():
    backup = (INFRA / "backup.sh").read_text()
    assert "pg_dump" in backup and "aws s3 cp" in backup
    deploy = (INFRA / "deploy.sh").read_text()
    assert "/etc/cron.d/nickoftime-backup" in deploy and "infra/backup.sh" in deploy
    assert re.search(r"^\d+ \d+ \* \* \* root ", deploy, re.M), "cron entry must run every day"


# --- AC-05: both hosts, TLS by Caddy ----------------------------------------------------------------------------

def test_ac_05_caddyfile_serves_both_hosts_and_routes_api_before_web():
    caddyfile = (INFRA / "caddy" / "Caddyfile").read_text()
    assert re.search(r"^nickoftime\.salazarvalverdeai\.com \{", caddyfile, re.M)
    assert re.search(r"^mcp\.nickoftime\.salazarvalverdeai\.com \{", caddyfile, re.M)
    assert caddyfile.index("handle /api/*") < caddyfile.rindex("reverse_proxy web:3000")
    for upstream in ("api:8000", "web:3000", "mcp:8001"):
        assert f"reverse_proxy {upstream}" in caddyfile
    assert "auto_https off" not in caddyfile, "TLS must stay automatic on the public hosts"


# --- AC-03: OIDC role, GHCR, SSM; no AWS keys in GitHub ---------------------------------------------------------

def test_ac_03_deploy_assumes_the_oidc_role_and_runs_through_ssm(deploy_workflow):
    text = (WORKFLOWS / "deploy.yml").read_text()
    deploy_job = deploy_workflow["jobs"]["deploy"]
    assert deploy_job["permissions"]["id-token"] == "write"
    assert "role-to-assume" in text
    assert "AWS-RunShellScript" in text
    assert "ghcr.io" in text


@pytest.mark.parametrize("workflow", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_ac_03_no_long_lived_aws_keys_in_any_workflow(workflow):
    text = workflow.read_text().lower()
    for forbidden in ("aws-access-key-id", "aws_access_key_id", "aws-secret-access-key", "aws_secret_access_key"):
        assert forbidden not in text, f"{workflow.name} references {forbidden}"


# --- AC-02: a failed build never reaches the instance -----------------------------------------------------------

def test_ac_02_deploy_waits_for_every_build_and_builds_stop_on_first_failure(deploy_workflow):
    jobs = deploy_workflow["jobs"]
    assert jobs["deploy"]["needs"] == "build"
    assert jobs["build"]["strategy"]["fail-fast"] is True
    assert set(jobs["build"]["strategy"]["matrix"]["service"]) == {"web", "api", "mcp"}


def test_ac_02_images_are_pulled_before_any_container_is_touched():
    body = (INFRA / "deploy.sh").read_text().split("start_version() {", 1)[1].split("\n}\n", 1)[0]
    assert body.index("compose pull") < body.index("compose up -d")


# --- AC-07: failed health check restores the last good version and fails the workflow ---------------------------

def test_ac_07_deploy_script_rolls_back_and_exits_nonzero_when_health_fails():
    script = (INFRA / "deploy.sh").read_text()
    assert "last_good_sha" in script
    assert "rolling back to $PREVIOUS" in script
    assert script.rstrip().endswith("exit 1")
    assert 'grep -Eq "\\"git_sha\\": *\\"$1\\""' in script, "health must match the deployed SHA, not just any 200"


@pytest.mark.parametrize("script", ["deploy.sh", "backup.sh"])
def test_shell_scripts_have_valid_syntax(script):
    result = subprocess.run(["bash", "-n", str(INFRA / script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ac_03_deploy_script_never_prints_secret_values():
    script = (INFRA / "deploy.sh").read_text()
    # values are written to .env (mode 0600); log lines carry names only
    assert 'chmod 600 .env' in script
    assert not re.search(r'log ".*\$(pg|value)\b', script)


# --- AC-06 (and AC-01 payload): /api/health -----------------------------------------------------------------------

def test_ac_06_health_reports_version_sha_gold_policies_and_platform(placeholder_api):
    env = {
        "APP_VERSION": "v0.2.0-3-gabc1234", "GIT_SHA": "a" * 40, "GOLD_VERSION": "v1",
        "POLICIES_VERSION": "1", "PLATFORM_REVISION": "rev-7",
    }
    status, body = placeholder_api.route("GET", "/api/health", env)
    assert status == 200
    assert body["status"] == "ok"
    assert body["git_sha"] == "a" * 40
    assert {k: body[k] for k in ("version", "gold_version", "policies_version", "platform_revision")} == {
        "version": "v0.2.0-3-gabc1234", "gold_version": "v1", "policies_version": "1", "platform_revision": "rev-7",
    }


def test_ac_06_unknown_values_are_null_never_invented(placeholder_api):
    _, body = placeholder_api.route("GET", "/api/health", {"GIT_SHA": "b" * 40, "GOLD_VERSION": ""})
    assert body["gold_version"] is None
    assert body["platform_revision"] is None
    assert body["policies_version"] is None


def test_ac_06_health_ignores_the_query_string_and_other_routes_are_404(placeholder_api):
    assert placeholder_api.route("GET", "/api/health?probe=1", {})[0] == 200
    assert placeholder_api.route("GET", "/api/cases", {})[0] == 404
    assert placeholder_api.route("POST", "/api/health", {})[0] == 404
