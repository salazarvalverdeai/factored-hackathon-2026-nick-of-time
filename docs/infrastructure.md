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
| S3 bucket | `nickoftime-gold-061039767206` | Private, versioned. Gold snapshot and Postgres backups. `gold_eval` (labels) is **not** uploaded |
| Bedrock | Claude Sonnet 4.6 · Sonnet 4.5 · Haiku 4.5 | Anthropic use-case form submitted 2026-10-03. Claude 5 family quota is 0 |
| Budget | `nickoftime-hackathon` | 100 USD/month filtered by the project tag; alerts at 50% and 80% actual, 100% forecast. Bedrock usage is untagged and counted in the account-wide budget |
| GitHub OIDC | provider `token.actions.githubusercontent.com` | Deploy role `nickoftime-gha-deploy` (repo `main` only) |
| Cognito | user pool for analysts | Created in spec 05 |

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

## LangGraph Platform (LangSmith)
Organization on the Plus tier, workspace `NickOfTime`, tracing project `nick-of-time`. The graph deploys from this
repository (`langgraph.json`). Deployment secrets: AWS credentials of `svc-nickoftime-langgraph`, the MCP URL and its
API key.

## Where credentials live
| Secret | Location |
|---|---|
| MCP API key | SSM `/nickoftime/prod/MCP_API_KEY` (+ Platform deployment secret) |
| Telegram bot token · webhook secret | SSM `/nickoftime/prod/TELEGRAM_BOT_TOKEN` · `/nickoftime/prod/TELEGRAM_WEBHOOK_SECRET` |
| Resend API key | SSM `/nickoftime/prod/RESEND_API_KEY` |
| LangSmith API key | Local `.env` (never committed) and Platform |
| AWS access for deploys | None stored: GitHub Actions assumes `nickoftime-gha-deploy` through OIDC |
| Dataset credentials | Local AWS profile `factored-dataset` (read-only, provided by the organizers) |

`.env` is never committed; `.env.example` lists the variable names. gitleaks runs as a pre-commit hook and in CI.
