# Spec 06 — Deploy + CI

- **Feature:** a merge to `main` reaches the public URL by itself, with no AWS keys in GitHub.
- **Status:** Draft
- **Owner:** @gianzk · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment
- **Depends on:** framework PR (#2), OIDC role `nickoftime-gha-deploy`, Actions secrets (loaded by the lead)
- **Enables:** every spec that must run on the public URL (05, 07, 08, 13, 16)
- **ADRs:** [0010](../docs/adr/0010-postgres-for-case-state-and-audit.md), [0011](../docs/adr/0011-single-ec2-compose-oidc-ssm-deploy.md)
- **Issue:** #8

> **Profile.** Full minus sections 2 and 7: the deploy path is delicate (production, rollback, secrets) but has no
> user-facing stories and no business data model.
> **Anti spec-drift.** If the deploy code changes later, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
One EC2 (`nickoftime-app`) runs Docker Compose with Caddy, web, api, mcp and Postgres (ADR 0011). A merge to `main`
builds the images in GitHub Actions, pushes them to GHCR, assumes the AWS role `nickoftime-gha-deploy` through OIDC and
deploys with SSM Run Command. The instance has no SSH and GitHub holds no AWS keys. Judges open the public URL after the
deadline, so a bad merge must never take the previous version down.

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 are copied from issue #8 with the same numbers. AC-06 and AC-07 are added by the owner; none of the
original criteria is dropped or weakened.

- AC-01 — When a PR is merged to `main`, within 10 minutes the EC2 shall run the new version and `/api/health` shall
  return its git SHA. · [C]
- AC-02 — If the build fails, then the previous version shall keep serving. · [C]
- AC-03 — The deploy shall use the OIDC role (no AWS keys in GitHub), pull images from GHCR and run through SSM. · [D]
- AC-04 — Compose shall run caddy, web, api, mcp and postgres (with a volume), with a daily Postgres backup to S3. · [C]
- AC-05 — `nickoftime.salazarvalverdeai.com` and `mcp.nickoftime.salazarvalverdeai.com` shall answer with valid TLS. · [C]
- AC-06 — `/api/health` shall report the app version, git SHA, gold version, `policies.yaml` version and Platform
  revision (CONTRIBUTING §7); a value not yet known shall be `null`, never invented. · [T]
- AC-07 — If the post-deploy health check does not return the deployed SHA after its retries, then the deploy shall
  restore the last good version and the workflow shall fail. · [C]

Each criterion also has an offline static check in `tests/test_spec06_deploy.py` (compose services and volume, Caddy
hosts, no AWS keys in workflows, rollback and backup present, health payload shape). Those checks guard the files; the
`[C]` evidence is the real run on the public URL.

## 4. Functional requirements
- FR-01 — `build` job: build `web`, `api` and `mcp` images, tag them with the commit SHA, push to GHCR with
  `GITHUB_TOKEN`. The deploy job `needs` the build job, so a failed build never reaches the instance (AC-02).
- FR-02 — `deploy` job: `aws-actions/configure-aws-credentials` with `role-to-assume` and `id-token: write`; no
  long-lived keys (AC-03).
- FR-03 — The deploy runs `AWS-RunShellScript` through SSM on `nickoftime-app` and waits for the command result.
  The script updates the checkout in `/opt/nickoftime` to the deployed SHA and runs `infra/deploy.sh <sha>`.
- FR-04 — `infra/deploy.sh`: load secrets from SSM `/nickoftime/prod/*` into a `0600` env file → pull the new images
  **before touching any container** → run the migration hook → `docker compose up -d` → reload Caddy → health check
  with retries → record the SHA as last good, or roll back (AC-02, AC-07).
- FR-05 — `infra/compose.yml`: caddy (80/443, certificate volume), web, api, mcp, postgres (named volume, healthcheck).
  Only caddy publishes ports.
- FR-06 — `infra/Caddyfile`: `nickoftime.salazarvalverdeai.com` serves `/api/*` → api and everything else → web (same
  origin, no CORS); `mcp.nickoftime.salazarvalverdeai.com` → mcp (AC-05).
- FR-07 — `infra/backup.sh` runs `pg_dump`, compresses it and copies it to `s3://nickoftime-gold-061039767206/backups/postgres/`;
  `deploy.sh` installs a daily cron entry for it (AC-04).
- FR-08 — Until specs 03 and 05 land their own `Dockerfile`s, the workflow builds `mcp` and `api` from the placeholders in
  `infra/`; a service switches to its real image the moment `apps/<service>/Dockerfile` exists, with no change here.

## 5. Non-functional requirements
- Performance: merge to serving in under 10 minutes (AC-01); downtime during `up -d` of a few seconds.
- Security: no AWS keys in GitHub; the deploy role is trusted only for this repo's `main` and may only run
  `AWS-RunShellScript` on `nickoftime-app`; only 80 and 443 are open; secrets live in SSM and are never printed (the
  health check and logs show names only).
- Observability: the SSM command output is attached to the workflow log; `/api/health` is the liveness and version
  probe; `docker compose logs` on the instance through SSM.

## 6. API contract (I/O)
Only the health route; the rest of `/api` belongs to spec 05.

| Method | Path | Request | Response | Status codes |
|---|---|---|---|---|
| GET | /api/health | — | `{status, service, version, git_sha, gold_version, policies_version, platform_revision}` | 200 |

## 8. Assumptions and open questions
- Assumption `[assumption]`: the repository and its GHCR packages are public, so the instance pulls images without a
  token. If the packages stay private, `deploy.sh` reads an optional `GHCR_READ_TOKEN` from SSM.
- Assumption `[assumption]`: the instance keeps a git checkout in `/opt/nickoftime` (public repo, `git fetch` works); the
  first checkout is done once by the owner through SSM.
- Assumption `[assumption]`: internal ports are web 3000, api 8000, mcp 8001.
- Assumption `[assumption]`: Actions secrets `AWS_DEPLOY_ROLE_ARN` and `EC2_INSTANCE_ID` are loaded by the lead; the
  region is `us-east-2`.
- Open question (lead): the instance role needs `ssm:GetParameter*` on `/nickoftime/prod/*` (already in the inventory).
  Does it also have `ssm:PutParameter` so `deploy.sh` can create `POSTGRES_PASSWORD` on first run? If not, the lead
  creates that SecureString parameter. The agent must not invent the value.
- Open question (lead): do specs 03 and 05 keep `apps/mcp/Dockerfile` and `apps/api/Dockerfile` as the build contexts?
  Spec 01 must fix the folders; this spec follows whatever it decides.

## 9. Out of scope
- Multi-instance or managed container services (ECS, RDS).
- Infrastructure as code for the AWS resources (already created and documented in `docs/infrastructure.md`).
- Blue-green or zero-downtime deploys.
- The real API and MCP servers (specs 05 and 03).

## 10. Plan, tasks and verification
- [ ] T1 — `infra/compose.yml` and `infra/Caddyfile` · covers FR-05, FR-06, AC-04, AC-05 · done when: `docker compose config`
  passes and the static test finds the five services, the volume and both hosts
- [ ] T2 — web and api placeholder images, health payload · covers FR-08, AC-06 · done when: the health test passes
- [ ] T3 — `infra/deploy.sh` with pull-first, migration hook, health check and rollback · covers FR-04, AC-02, AC-07 ·
  done when: the static test finds the rollback path and `bash -n` passes
- [ ] T4 — `infra/backup.sh` and its cron entry · covers FR-07, AC-04 · done when: `bash -n` passes; first dump seen in S3 `[C]`
- [ ] T5 — `.github/workflows/deploy.yml` (build → OIDC → SSM) · covers FR-01..FR-03, AC-01, AC-03 · done when: no AWS key
  names in workflows (test) and the first merge shows the new SHA at `/api/health` `[C]`
- [ ] T6 — first real run on the public URL, TLS check, rollback drill · covers AC-01, AC-02, AC-05, AC-07 · done when: the
  outputs are pasted in the PR

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for any
decision taken · lessons added to `CLAUDE.md`.
