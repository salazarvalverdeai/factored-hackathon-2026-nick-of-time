# Runbook · Team setup (run the project on your machine)

From a fresh machine to a working checkout with data, configuration and access checks, without anyone sending you files
or secrets in a chat. Takes about 20 minutes.

## 0. Prerequisites
Git · Python 3.13 · Node 24 · AWS CLI v2 · Docker (for the full stack, after spec 01) · `make`.
**Windows:** use **WSL2 (Ubuntu)** and run everything inside it; several Python wheels and `make` behave much better there.

## 1. Repository
1. Accept the GitHub invitation and clone the repo.
2. Once: `git config commit.template .github/commit_template.txt` and `make hooks` (gitleaks pre-commit).
3. Read [`CLAUDE.md`](../../CLAUDE.md) and [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — or point your AI assistant at them.

## 2. AWS access (your own IAM user, never shared keys)
1. Sign in at `https://061039767206.signin.aws.amazon.com/console` with the user the lead gave you (secure channel).
2. Set your password. MFA is not required during the sprint (lead decision, 2026-10-04).
3. Same page → **Create access key** (CLI). Then on your machine:
   ```bash
   aws configure --profile nickoftime     # region us-east-2, output json
   ```
4. Your Cognito password for the analyst console is in SSM Parameter Store:
   `/nickoftime/prod/cognito/initial-password/<your-user>` (you change it at first login).

| Person | IAM user | Can |
|---|---|---|
| GianMarco | `nickoftime-gianmarco` | EC2 + SSM session to the app box, S3 project data, SSM parameters |
| Diego | `nickoftime-diego` | S3 project data **including labels**, SSM parameters, Bedrock |
| Lead | `nickoftime-admin` | everything (admin) |

## 3. Configuration
```bash
cp .env.example .env
make env-pull          # fills every value that already exists in SSM; prints names only
```
Keys that do not exist yet (Telegram, Resend, Jev) stay empty until the lead creates them; re-run `make env-pull` then.

## 4. Data (no dataset credentials needed)
```bash
make gold-pull         # downloads gold v1 from the project bucket (≈ 214 MB) and verifies sha256 vs the manifest
make labels-pull       # only Diego and the lead: is_fraud labels for the harness (denied for everyone else)
```
To rebuild gold from the raw dataset instead: `make setup` with the `factored-dataset` profile (see the README).

## 5. Python and web
```bash
make deps && make test                     # venv, dependencies, offline tests
cd apps/web && npm ci && npm run dev       # http://localhost:3000 (mock API mode once spec 16 lands)
```

## 6. Access checks
```bash
make check-bedrock     # Diego and lead (GianMarco develops with LLM_PROVIDER=fake)
make check-telegram    # once the bot exists
make check-jev         # once Jev access exists
```

## 7. Full stack (after spec 01 is implemented)
`docker compose -f infra/compose.dev.yml up` (api :8000, mcp :8100, postgres) and `langgraph dev` for the agent.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `AccessDenied` on `labels/` | Expected unless you are Diego or the lead |
| `ExpiredToken` / `InvalidClientTokenId` | Re-run `aws configure --profile nickoftime` with a new access key |
| Bedrock `AccessDenied` | You are not in the Bedrock group; use `LLM_PROVIDER=fake` or ask the lead |
| `make gold-pull` reports a mismatch | Delete `data/gold/*.parquet` and pull again |
