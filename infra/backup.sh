#!/usr/bin/env bash
# Daily Postgres backup to S3 (spec 06 FR-07, AC-04). Installed in /etc/cron.d by infra/deploy.sh.
# Restore: gunzip -c nickoftime-<stamp>.sql.gz | docker compose exec -T postgres psql -U nickoftime -d nickoftime
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_S3_URI="${BACKUP_S3_URI:-s3://nickoftime-gold-061039767206/backups/postgres}"
AWS_REGION="${AWS_REGION:-us-east-2}"
STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
TMP="$(umask 077 && mktemp /tmp/nickoftime-pg.XXXXXX)"
trap 'rm -f "$TMP"' EXIT

docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip -9 >"$TMP"
[ -s "$TMP" ] || { echo "backup is empty, not uploading" >&2; exit 1; }

aws s3 cp "$TMP" "$BACKUP_S3_URI/nickoftime-$STAMP.sql.gz" --region "$AWS_REGION" --only-show-errors
echo "backup ok: $BACKUP_S3_URI/nickoftime-$STAMP.sql.gz ($(stat -c %s "$TMP") bytes gzipped)"
