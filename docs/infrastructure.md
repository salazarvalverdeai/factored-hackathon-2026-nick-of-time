# Infrastructure

Inventory of what runs where and **where each credential lives — never its value.** Decisions behind it: ADRs
[0008](adr/0008-agent-on-langgraph-platform-tools-over-mcp.md), [0009](adr/0009-llm-on-amazon-bedrock.md),
[0010](adr/0010-postgres-for-case-state-and-audit.md), [0011](adr/0011-single-ec2-compose-oidc-ssm-deploy.md),
[0017](adr/0017-identity-mock-otp-customers-cognito-analysts.md). Last verified: 2026-10-03.

![Architecture, option A](assets/architecture_option_a.svg)

## AWS (region `us-east-2`)
Every resource uses the prefix `nickoftime-` and the tag `Project=nickoftime`. The account is temporary and is cleaned
up after judging (2026-10-16).

| Resource | Name | Notes |
|---|---|---|
| EC2 | `nickoftime-app` | t3.medium, Ubuntu 24.04, 30 GB encrypted, IMDSv2, **no SSH** (access through SSM), Docker + Compose, Elastic IP |
| Instance role | `nickoftime-ec2-role` | Bedrock invoke, S3 and DynamoDB on `nickoftime-*`, SSM parameters under `/nickoftime/*`, SSM managed instance |
| Security group | `nickoftime-web-sg` | Inbound 80 and 443 only |
| S3 bucket | `nickoftime-gold-061039767206` | Private, versioned. Gold v1 at `gold/v1/` (verified against the manifest sha256, uploaded 2026-10-03); Postgres backups. Labels (`is_fraud`) live apart in `labels/v1/` behind a deny-by-default bucket policy: read only by `nickoftime-admin` and `nickoftime-diego` (evaluation harness), write only by `nickoftime-admin`; the EC2 role, Platform and the deploy role are denied (verified with the IAM policy simulator) |
| Bedrock | Claude Sonnet 4.6 · Sonnet 4.5 · Haiku 4.5 | Anthropic use-case form submitted 2026-10-03. Claude 5 family quota is 0 |
| Budget | `nickoftime-hackathon` | 100 USD/month filtered by the project tag; alerts at 50% and 80% actual, 100% forecast. Bedrock usage is untagged and counted in the account-wide budget |
| GitHub OIDC | provider `token.actions.githubusercontent.com` (account-wide, shared) | Deploy role `nickoftime-gha-deploy`: trusted only for this repo's `main`; may only run `AWS-RunShellScript` through SSM on `nickoftime-app` (validated with Access Analyzer) |
| Cognito | user pool `nickoftime-analysts` | Hosted domain `nickoftime-analysts.auth.us-east-2.amazoncognito.com`; app client `nickoftime-web` (public, authorization code + PKCE, callbacks `/login/callback` on the public URL and `localhost:3000`); admin-created users only (`freddy`, `gianmarco`, `diego`, `judge`); optional TOTP MFA; deletion protection on |

### IAM
| Principal | Purpose | Access |
|---|---|---|
| `nickoftime-admin` | Lead's administration profile (`nickoftime`) | Admin; MFA required |
| `nickoftime-gianmarco` | Console access | Self-service, data, infra |
| `nickoftime-diego` | Console access | Self-service, data, Bedrock |
| `nickoftime-david` | Console access | Self-service, data |
| `svc-nickoftime-langgraph` | LangGraph Platform → Bedrock | Bedrock invoke only; its key lives in the Platform deployment secrets |
| `nickoftime-gha-deploy` (role) | GitHub Actions deploy through OIDC | SSM Run Command on `nickoftime-app` only |

Policies `nickoftime-self-service`, `-data`, `-bedrock`, `-infra` were validated with IAM Access Analyzer: nobody can
touch other projects' resources, create users or attach policies to themselves.

## Domains and TLS
| Host | Serves | TLS |
|---|---|---|
| `https://nickoftime.salazarvalverdeai.com` | web app and `/api/*` (same origin, no CORS) | Let's Encrypt through Caddy, auto-renewed |
| `https://mcp.nickoftime.salazarvalverdeai.com` | MCP server (API key required) | Same |

DNS is managed at the registrar (A records to the Elastic IP). Before releasing the IP or stopping the instance, the
records are removed to avoid dangling DNS.

## Deploy (spec 06)
A merge to `main` runs `.github/workflows/deploy.yml`: build `web`, `api`, `mcp` → push to GHCR (tag = commit SHA) →
assume `nickoftime-gha-deploy` through OIDC → SSM Run Command runs `infra/deploy.sh <sha>` on `nickoftime-app`.
The script pulls the new images before touching any container, runs the migration hook, brings the stack up, reloads
Caddy and waits for `/api/health` to report the deployed SHA; if it does not, it restores the last good version and the
workflow fails. Files: `infra/compose.yml`, `infra/caddy/Caddyfile`, `infra/deploy.sh`, `infra/backup.sh`. Until specs
03 and 05 add their own `Dockerfile`, `mcp` and `api` are built from `infra/mcp-placeholder` and `infra/api-placeholder`.

| Needed once | Where | Who |
|---|---|---|
| Actions variables `AWS_DEPLOY_ROLE_ARN`, `EC2_INSTANCE_ID`, `AWS_REGION` (not secret: a role ARN and an instance id) | GitHub → Settings → Variables | lead |
| GHCR packages `web`, `api`, `mcp` set to public after the first build (or `GHCR_READ_TOKEN` in SSM) | GitHub → Packages | lead |
| SSM `/nickoftime/prod/POSTGRES_PASSWORD` (`deploy.sh` creates it if the role may `PutParameter`) | SSM | lead |
| First checkout on the instance (below) | EC2 through SSM | GianMarco |

First checkout (run once through SSM Session Manager or `aws ssm send-command`; the repository is public):
```bash
sudo git clone https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time /opt/nickoftime
```

Manual rollback (the instance has no SSH; use SSM): `cd /opt/nickoftime && git checkout --detach <good-sha> &&
bash infra/deploy.sh <good-sha>`. Backups land in `s3://nickoftime-gold-061039767206/backups/postgres/`; the restore
command is at the top of `infra/backup.sh`.

## LangGraph Platform (LangSmith)
Organization on the Plus tier, workspace `NickOfTime`, tracing project `nick-of-time`. The graph deploys from this
repository (`langgraph.json`). Deployment secrets: AWS credentials of `svc-nickoftime-langgraph`, the MCP URL and its
API key.

## Uptime monitor
`.github/workflows/uptime.yml` runs every 15 minutes (and on `workflow_dispatch`). It checks, with timeouts and 2 retries:
`https://nickoftime.salazarvalverdeai.com/api/health` (200, `status: ok`),
`https://mcp.nickoftime.salazarvalverdeai.com/health` (200, `status: ok`, `store: postgres`, loaded modules non-empty if
reported) and `https://nickoftime.salazarvalverdeai.com/chat` (200). On a healthy-to-failing transition it sends one
Telegram message (failing check, HTTP code, run URL), then one recovery message later; it stays quiet during a continued
outage. The run itself goes red on any failure.

Repository secrets the lead must create (Settings > Secrets and variables > Actions): `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALERT_CHAT_ID`. If either is missing the run fails with a clear error and leaks nothing. To test: Actions >
Uptime > Run workflow (a manual run on a failing check always alerts). Reviewer: @gianzk (owner of `.github/`).

## Where credentials live
| Secret | Location |
|---|---|
| MCP API key | SSM `/nickoftime/prod/MCP_API_KEY` (+ Platform deployment secret) |
| Telegram bot token · webhook secret | SSM `/nickoftime/prod/TELEGRAM_BOT_TOKEN` · `/nickoftime/prod/TELEGRAM_WEBHOOK_SECRET` |
| Resend API key | SSM `/nickoftime/prod/RESEND_API_KEY` |
| Cognito ids (not secret) | SSM `/nickoftime/prod/COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_DOMAIN` |
| Cognito temporary passwords (changed at first login) | SSM `/nickoftime/prod/cognito/initial-password/<user>` |
| Cognito judge password (only in the submission e-mail) | SSM `/nickoftime/prod/cognito/judge-password` |
| Uptime alerts | GitHub secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID` |
| LangSmith API key | Local `.env` (never committed) and Platform |
| AWS access for deploys | None stored: GitHub Actions assumes `nickoftime-gha-deploy` through OIDC |
| Dataset credentials | Local AWS profile `factored-dataset` (read-only, provided by the organizers) |

`.env` is never committed; `.env.example` lists the variable names. gitleaks runs as a pre-commit hook and in CI.

## Limits and capacity (checked 2026-10-05)
| Limit | Value | Where | Why |
|---|---|---|---|
| New demo sessions per IP | 100 / hour (global 1,000) | `infra/deploy.sh` → api (`RATE_SESSIONS_PER_IP_HOUR`, `RATE_SESSIONS_GLOBAL_HOUR`) | A jury behind one NAT IP must not be blocked |
| Chat turns per IP | 600 / hour (global 6,000) | `RATE_TURNS_PER_IP_HOUR`, `RATE_TURNS_GLOBAL_HOUR` | Same |
| Bedrock spend | 5 USD / day | `DAILY_LLM_CAP_USD` | The real cost guard: past it the agent understands by rules only (S0, G-OPS-01) |
| Voice clip | 30 s, size-capped | api `POST /api/voice/transcribe` | Cost and abuse |
| Customer session | 15 min | `policies.yaml` `identity.session_ttl_minutes` | Mock OTP (ADR 0017) |

Load test against production `[data]` (2026-10-05, from one client, straight to the LangGraph Platform Development
deployment so the per-IP limits did not apply; each run = one full agent turn with Haiku 4.5 (S1), the real MCP server,
Postgres and gold):

| Concurrent conversations | OK | p50 | p95 |
|---|---|---|---|
| 1 / 5 / 10 / 20 | all | 1.2–2.1 s | ≤ 2.4 s |
| 40 / 60 | all | 3.0–7.3 s | ≤ 8.2 s |
| 10 sustained for 2 min (920 turns) | 920/920 | 1.3 s | 1.5 s |

The EC2 stayed idle (load 0.06, 2.7 GB free) and Platform answered `/ok` throughout. The Development deployment is
preemptible (it can restart without notice); the uptime monitor (`.github/workflows/uptime.yml`) alerts on Telegram.
