# CLAUDE.md — Nick of Time

Durable context for AI coding agents (Claude Code, Cursor, Copilot…). Read it at the start of every session. How we
work lives in [`CONTRIBUTING.md`](CONTRIBUTING.md); decisions in [`docs/adr/`](docs/adr/); features in
[`specs/`](specs/); current state in [`STATUS.md`](STATUS.md).

## What it is
Regulatory-clock **card dispute intake** for a synthetic LATAM bank (Factored AI & Data Hackathon 2026, workflow W3).
A customer reports an unrecognized or wrongful charge in Spanish or Portuguese; the system identifies the customer's own
transaction, decides by rules, blocks the card and opens a case with verification, computes the country's legal
deadline, gives the customer a **verified receipt** and the analyst a **handoff card** with evidence. A person always
closes the case. Main goal: raise first-contact resolution (FCR) of dispute contacts (43.6% vs 76.6% for the bank).

## Working mode
Spec-driven, **rigorous but time-boxed** (team of 3, submission Monday 2026-10-05). Every new feature has a spec in
`specs/` with EARS acceptance criteria and tests that cite them; load-bearing decisions get an ADR. Existing pipeline
code is not re-specified (brownfield adoption).

## Stack (closed — see ADRs)
- **Agent:** LangGraph graph on **LangGraph Platform** (LangSmith); customer tools as a **FastMCP** server (ADR 0008).
- **LLM:** Amazon Bedrock `us-east-2`, Claude Sonnet 4.6 and Haiku 4.5; Anthropic API as fallback (ADR 0009).
- **Backend:** FastAPI + **Postgres** for case state and audit (ADR 0010). **Frontend:** Next.js 16 + shadcn/ui.
- **Data:** bronze → silver → gold with DuckDB + Polars + pandera; gold Parquet, read-only at runtime (ADR 0004).
- **Infra:** one EC2 with Docker Compose + Caddy, two subdomains, deploy through GitHub Actions + OIDC + SSM (ADR 0011).
- **Identity:** mock session + OTP for customers, Cognito for analysts (ADR 0017).

## Constraints (constitution — never broken without a new ADR)
1. **The LLM understands, the rules decide, the tools act, verification confirms, a person closes.**
2. Decisions live in `contracts/policies.yaml` (`default: deny`); the LLM never reads or edits it.
3. `customer_id` comes **only from the session**, never from the customer's text. Tools enforce it, not prompts.
4. An action is reported to the customer only after its post-condition is verified (`accepted ≠ verified`).
5. The receipt and the handoff card contain **only facts returned by tools** (exact-match grounding).
6. No case is closed without a person. Provisional credit is always a human decision.
7. `is_fraud` lives only in `data/gold_eval/`; it is read by the evaluation harness and, by time window, by the fraud-model training pipeline (ADR 0022) — never by the runtime.
8. Every figure carries a label: `[data]` `[external]` `[assumption]` `[simulated]` `[projected]`.
9. Contracts in `contracts/` change only through a PR approved by the lead.
10. No secrets in the repo; they live in AWS SSM Parameter Store, Platform deployment secrets or GitHub secrets.

## Business rules (firm, from `contracts/policies.yaml`)
- Zones from the bank's `fraud_score` (an optional input): high ≥ 50 · medium 30–49 · human < 30 or null (own policy id).
- A ticket is always opened, in every zone. High zone blocks and verifies; medium confirms with the customer first.
- Regulatory clock: a data table in `policies.yaml`, every entry with `source_url` and `verified_on` (ADR 0019). MX
  debit: provisional credit by business day 2, Banxico 3/2012, **for claims within 90 calendar days of the charge**
  (ADR 0023; the 48 h window is for theft or loss only); MX credit the same (Circular 34/2010); ruling 45
  days (180 abroad); older MX charges: LTOSF art. 23 ruling only; AR: BCRA 10 business days to resolve (no credit date
  promised); CO: SFC 15 business days; BR: CMN 4.860; PE: SBS 04036-2022; CL: Ley 20.009; any other country →
  `POL-CLOCK-UNKNOWN` (case opened, a person decides, no invented deadline). `amount_gate` only changes the approval
  mode, never the clock. Spec 02 §4.3 is the source of truth.
- Case queue: `new → verification | review → resolved → closed`; a case's status is its last event (append-only).
- Customer notifications on every status: in-app log, Telegram and email. Never send score, policy ids or transcript.
- Two time modes (ADR 0020): `replay` uses `DEMO_TODAY=2026-06-01` for evaluation and the processed sample cases;
  `live` uses the real date with recent transactions marked synthetic. Nothing reads the system clock directly.
- Conversation (spec 04): greet with capabilities, state the plan before acting, show progress, report actions only as
  in progress / requested / verified / not confirmed, re-read the system for every status question, and end every
  reply with 2–3 suggestion chips chosen by rules (a person always reachable).
- Oversight (spec 18, ADR 0021): a deterministic auditor re-derives each outcome; an LLM judge gives the analyst an
  advisory second opinion tied to evidence; every model and decision engine is in the inventory.
- Models (spec 15): one model per LLM task, chosen by a pre-registered lean rule — the cheapest arm not significantly
  worse than the best; whether a model may go to production is a result of the benchmark.

## Repository layout and owners
Target layout; spec 01 fixes the final folders. Owners are enforced by `.github/CODEOWNERS`.
```
apps/web/            Next.js app and front-end standard (apps/web/README.md)    GianMarco
apps/api/            FastAPI backend: sessions, cases, analyst actions, notify  GianMarco
apps/mcp/            FastMCP server with the 16 customer tools                   Freddy
apps/agent/          LangGraph graph deployed to Platform (langgraph.json)       Freddy
packages/nick_of_time/ shared package: contracts, policy engine, clock, store, receipt, audit  Freddy
contracts/           policies.yaml · tools.py · handoff and eval schemas         Freddy (lead)
data/pipeline/       bronze → silver → gold pipeline                             Diego
eval/                eval sets, protocol, harness, results                       Diego
queries/             pitch and analytics queries with their outputs              Diego
specs/ · docs/adr/   specs and decisions                                         Freddy (lead approves)
infra/ · .github/    compose, Caddy, CI/CD                                       GianMarco
```

## Commands
```bash
make setup            # venv + deps + pipeline from S3 + fixture + quality report (needs the dataset AWS profile)
make setup SOURCE=local
make test             # offline pytest (contracts, pipeline, fixture)
make hooks            # gitleaks pre-commit hook
cd apps/web && npm ci && npm run dev     # front end on :3000
```

## Secrets and environment
`.env` is local only (see `.env.example`). Production values live in SSM under `/nickoftime/prod/*`
(`MCP_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `RESEND_API_KEY`). Platform reaches Bedrock with the
`svc-nickoftime-langgraph` credentials stored as deployment secrets. Inventory in [`docs/infrastructure.md`](docs/infrastructure.md).

## Conventions
- English for code, docs, specs, ADRs, commits, PRs and UI; Spanish/Portuguese only for customer-facing text.
- Conventional Commits with a `why:` body; branches `spec/NN-slug`, `feat/NN-slug`, `fix/NN-slug` (CONTRIBUTING.md).
- Tests for spec NN live in `tests/test_specNN_*.py` and cite the acceptance criterion (`AC-03`) in name or docstring.
- Never call the real LLM in CI: use the `fake` provider.
- Brand: UI, avatars, favicons and customer-facing copy follow [`docs/brand/BRAND.md`](docs/brand/BRAND.md) (colors,
  Sora type, calm and precise voice). The SVGs in `docs/brand/` are the source of truth: never redraw the mark.

## Spec-driven flow (short)
Spec (what) → plan (how) → tasks → implement, with human review at each gate. One spec per person at a time; parallel
work across people is possible because spec 01 (the integration contract) is approved first. If code changes, its spec
changes in the same PR. Closing checklist: every AC has a passing test that cites it · spec marked Implemented · ADR
for any decision · lessons added here.
