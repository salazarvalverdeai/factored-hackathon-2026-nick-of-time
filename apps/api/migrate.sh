#!/bin/sh
# Migration hook of infra/deploy.sh (spec 06 FR-04): `alembic upgrade head` against the stack's DATABASE_URL.
set -eu
cd /srv/apps/api
exec alembic upgrade head
