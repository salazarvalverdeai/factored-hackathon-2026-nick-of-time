# Architecture Decision Records

One file per load-bearing decision, written from [`_template.md`](_template.md). Accepted records are never edited or
deleted: a new ADR supersedes them. How and when to write one: [`CONTRIBUTING.md`](../../CONTRIBUTING.md#4-architecture-decision-records).
*If it is not in the log, it was not decided.*

| ADR | Decision | Status | Date |
|---|---|---|---|
| [0001](0001-record-decisions-and-work-spec-driven.md) | Record decisions as ADRs and build features from specs | Accepted | 2026-10-03 |
| [0002](0002-english-as-the-repository-language.md) | English as the repository language | Accepted | 2026-09-28 |
| [0003](0003-scope-regulatory-clock-dispute-intake.md) | Scope: regulatory-clock card dispute intake (W3) | Accepted | 2026-09-28 |
| [0004](0004-medallion-pipeline-on-duckdb.md) | Medallion pipeline on DuckDB with data contracts | Accepted | 2026-09-28 |
| [0005](0005-policy-engine-outside-the-model.md) | Policy engine outside the model | Accepted | 2026-09-28 |
| [0006](0006-fraud-score-as-optional-swappable-input.md) | The bank's fraud score as an optional, swappable input | Accepted | 2026-09-28 |
| [0007](0007-evaluation-by-final-state-on-sealed-held-out.md) | Evaluation by final state on a sealed held-out | Accepted | 2026-09-28 |
| [0008](0008-agent-on-langgraph-platform-tools-over-mcp.md) | Agent on LangGraph Platform, customer tools as an MCP server | Accepted | 2026-09-28 |
| [0009](0009-llm-on-amazon-bedrock.md) | LLM on Amazon Bedrock: Claude Sonnet 4.6 and Haiku 4.5 | Accepted | 2026-09-29 |
| [0010](0010-postgres-for-case-state-and-audit.md) | Postgres for case state and audit (supersedes DynamoDB) | Accepted | 2026-10-03 |
| [0011](0011-single-ec2-compose-oidc-ssm-deploy.md) | One EC2 with Docker Compose, two subdomains, deploy through OIDC and SSM | Accepted | 2026-09-29 |
| [0012](0012-frozen-demo-date.md) | Frozen demo date | Superseded by [0020](0020-two-time-modes-historical-and-live.md) | 2026-10-03 |
| [0013](0013-customer-receives-proof-receipt-case-page-notifications.md) | The customer receives proof: verified receipt, case page and notifications | Accepted | 2026-09-29 |
| [0014](0014-main-objective-fcr.md) | Main objective: first-contact resolution of dispute contacts | Accepted | 2026-09-29 |
| [0015](0015-learned-component-vs-baseline-and-model-selection.md) | Learned components versus baselines, with a pre-registered selection rule | Accepted | 2026-09-29 |
| [0016](0016-guardrails-injection-detector-and-exact-grounding.md) | Guardrails: injection detector with rules + LR, exact-match output grounding | Accepted | 2026-09-29 |
| [0017](0017-identity-mock-otp-customers-cognito-analysts.md) | Identity: mock session + OTP for customers, Cognito for analysts | Accepted | 2026-10-03 |
| [0018](0018-data-and-model-lifecycle.md) | Data and model lifecycle: an operational medallion that feeds evaluation | Accepted | 2026-10-03 |
| [0019](0019-official-sources-for-regulatory-figures.md) | Every regulatory or external figure cites an official public source and a verification date | Accepted · amended by [0023](0023-mx-provisional-credit-90-days.md) | 2026-10-04 |
| [0020](0020-two-time-modes-historical-and-live.md) | Two time modes: historical (replay) for evaluation and processed cases, live for the demo (supersedes 0012) | Accepted · amended by [0023](0023-mx-provisional-credit-90-days.md) | 2026-10-04 |
| [0021](0021-continuous-evaluation-and-outcome-audit.md) | Continuous evaluation and outcome audit: inventory of models and decision engines, deterministic auditor, advisory judge, sealed regression sets | Accepted | 2026-10-04 |
| [0022](0022-fraud-labels-for-model-training.md) | Fraud labels may train our fraud model, by time window, and never reach the runtime | Accepted | 2026-10-04 |
| [0023](0023-mx-provisional-credit-90-days.md) | MX provisional credit by business day 2 for unrecognized-charge claims within 90 calendar days (debit and credit); the 48 h window is for theft or loss only; AR promises the 10-business-day resolution only (amends 0019, 0020) | Accepted | 2026-10-04 |
