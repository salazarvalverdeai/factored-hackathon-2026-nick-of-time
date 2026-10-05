#!/usr/bin/env bash
# Deploys one git SHA on nickoftime-app. Called by .github/workflows/deploy.yml through SSM Run Command:
#   cd /opt/nickoftime && git checkout --detach <sha> && bash infra/deploy.sh <sha>
#
# Order matters (spec 06 FR-04): the new images are pulled BEFORE any container is touched, so a failed pull leaves the
# old version serving (AC-02). If the new version does not report its SHA at /api/health, the last good one is restored
# and the script exits non-zero so the workflow fails (AC-07). Secret values are never printed, only their names.
set -euo pipefail

SHA="${1:?usage: infra/deploy.sh <git-sha>}"
cd "$(dirname "$0")"
REPO_ROOT="$(cd .. && pwd)"

AWS_REGION="${AWS_REGION:-us-east-2}"
SSM_PREFIX="${SSM_PREFIX:-/nickoftime/prod}"
STATE_DIR="${STATE_DIR:-/var/lib/nickoftime}"
LAST_GOOD_FILE="$STATE_DIR/last_good_sha"
HEALTH_URL="${HEALTH_URL:-https://nickoftime.salazarvalverdeai.com/api/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_SLEEP="${HEALTH_SLEEP:-5}"
CRON_FILE="${CRON_FILE:-/etc/cron.d/nickoftime-backup}"
GOLD_S3_URI="${GOLD_S3_URI:-s3://nickoftime-gold-061039767206/gold/v1/}"   # gold only: labels live apart, never synced
GOLD_DIR="${GOLD_DIR:-$STATE_DIR/gold/v1}"                                  # mounted read-only in api and mcp
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

for tool in aws docker git python3 curl openssl; do   # fail before touching anything if the host lacks a tool
  command -v "$tool" >/dev/null 2>&1 || { log "missing $tool on the host (aws: snap install aws-cli --classic)" >&2; exit 1; }
done

ssm_get() {  # prints the parameter value, or nothing if it does not exist
  aws ssm get-parameter --name "$SSM_PREFIX/$1" --with-decryption --query Parameter.Value --output text 2>/dev/null || true
}

ensure_postgres_password() {
  local value
  value="$(ssm_get POSTGRES_PASSWORD)"
  if [ -z "$value" ]; then
    log "POSTGRES_PASSWORD not in SSM; generating it once" >&2   # stderr: stdout carries the value to the caller
    value="$(openssl rand -hex 24)"
    if ! aws ssm put-parameter --name "$SSM_PREFIX/POSTGRES_PASSWORD" --type SecureString --value "$value" >/dev/null; then
      log "cannot create $SSM_PREFIX/POSTGRES_PASSWORD (no ssm:PutParameter?). Ask the lead to create it, then rerun." >&2
      return 1
    fi
  fi
  printf '%s' "$value"
}

sync_gold() {  # copies gold v1 from S3 to the host and sets GOLD_VERSION from its manifest (spec 06 FR-09)
  case "$GOLD_S3_URI" in *gold_eval*|*labels*) log "refusing to sync labels: $GOLD_S3_URI" >&2; return 1 ;; esac
  mkdir -p "$GOLD_DIR"
  aws s3 sync "$GOLD_S3_URI" "$GOLD_DIR" --only-show-errors --delete || return 1
  GOLD_VERSION="$(python3 -c 'import json,sys; print("v%s" % json.load(open(sys.argv[1]))["version"])' "$GOLD_DIR/manifest.json" 2>/dev/null || true)"
  log "gold synced: ${GOLD_VERSION:-unknown}"
}

write_env() {  # $1 = image tag to run. Writes infra/.env with mode 0600, no values on stdout.
  local tag="$1" tmp pg
  pg="$(ensure_postgres_password)" || return 1
  tmp="$(umask 077 && mktemp .env.XXXXXX)"
  {
    echo "IMAGE_TAG=$tag"
    echo "APP_VERSION=$(git -C "$REPO_ROOT" describe --tags --always 2>/dev/null || true)"
    echo "GIT_SHA=$tag"
    echo "GOLD_VERSION=${GOLD_VERSION:-}"
    echo "POLICIES_VERSION=$(awk '/^version:/ {print $2; exit}' "$REPO_ROOT/contracts/policies.yaml" 2>/dev/null || true)"
    echo "PLATFORM_REVISION=${PLATFORM_REVISION:-}"
    echo "POSTGRES_PASSWORD=$pg"
    local name value
    echo "GOLD_HOST_DIR=$GOLD_DIR"
    echo "AWS_REGION=$AWS_REGION"
    echo "DEFAULT_SESSION_MODE=live"
    echo "DEMO_TODAY=2026-06-01"
    echo "LANGGRAPH_ASSISTANT=${LANGGRAPH_ASSISTANT:-dispute_intake}"
    for name in MCP_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET RESEND_API_KEY RESEND_WEBHOOK_SECRET \
                LANGGRAPH_API_URL LANGSMITH_API_KEY LINK_SIGNING_KEY \
                COGNITO_USER_POOL_ID COGNITO_CLIENT_ID COGNITO_DOMAIN; do
      value="$(ssm_get "$name")"
      if [ -z "$value" ]; then log "warning: $name is not in SSM yet (left empty)" >&2; fi
      echo "$name=$value"
    done
  } >"$tmp"
  mv "$tmp" .env
  chmod 600 .env
}

compose() { docker compose "$@"; }

health_ok() {  # $1 = SHA that /api/health must report
  local i body
  for ((i = 1; i <= HEALTH_RETRIES; i++)); do
    body="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -Eq "\"git_sha\": *\"$1\""; then
      log "health ok on attempt $i: $1"
      return 0
    fi
    sleep "$HEALTH_SLEEP"
  done
  return 1
}

start_version() {  # $1 = SHA. Explicit || return 1: set -e is ignored inside functions used in an `if`.
  sync_gold || return 1
  write_env "$1" || return 1
  compose pull web api mcp || return 1                  # new images first; nothing running has been touched yet
  compose up -d --wait postgres || return 1
  # Migration hook for spec 05: runs only if the api image ships /app/migrate.sh.
  compose run --rm --no-deps api sh -c '[ ! -x /app/migrate.sh ] || /app/migrate.sh' || return 1
  compose up -d --remove-orphans || return 1
  compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true   # first start already loaded it
  health_ok "$1"
}

install_backup_cron() {
  cat >"$CRON_FILE" <<EOF
# Daily Postgres dump to S3 (spec 06 AC-04). 07:17 UTC = 02:17 America/Lima.
17 7 * * * root $REPO_ROOT/infra/backup.sh >>/var/log/nickoftime-backup.log 2>&1
EOF
  chmod 644 "$CRON_FILE"
}

mkdir -p "$STATE_DIR"
PREVIOUS="$(cat "$LAST_GOOD_FILE" 2>/dev/null || true)"
log "deploying $SHA (last good: ${PREVIOUS:-none})"

if start_version "$SHA"; then
  echo "$SHA" >"$LAST_GOOD_FILE"
  install_backup_cron
  docker image prune -f --filter "until=72h" >/dev/null || true
  log "done: $SHA is serving"
  exit 0
fi

log "ERROR: $SHA did not become healthy"
compose logs --tail 40 api web mcp 2>&1 | sed 's/^/  | /' || true
if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$SHA" ]; then
  log "rolling back to $PREVIOUS"
  if start_version "$PREVIOUS"; then
    log "rolled back: $PREVIOUS is serving"
  else
    log "CRITICAL: rollback to $PREVIOUS also failed; inspect with 'docker compose ps' through SSM"
  fi
else
  log "no previous version recorded; nothing to roll back to"
fi
exit 1
