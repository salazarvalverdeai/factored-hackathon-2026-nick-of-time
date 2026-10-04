# 0010. Postgres for case state and audit

- **Status:** Accepted (supersedes the DynamoDB choice of 2026-09-28)
- **Date:** 2026-10-03
- **Deciders:** Freddy · **Owner:** @gianzk
- **Related:** specs 01, 05, 14

## Context
State is small but must be auditable: cases, case events, sessions, notifications, policy denials, LLM calls and the
product-status overlay. The analyst console and the operational KPIs need joins and aggregates. A case's status is its
last event; nothing is updated or deleted.

## Decision
**Postgres**, as a container in the EC2 Docker Compose with a persistent volume and a daily `pg_dump` to the project's
S3 bucket. Tables are append-only where they record events (`case_events`, `llm_calls`, `policy_denials`,
`notifications`). Gold Parquet stays read-only; a card block is an overlay row, never a write to gold.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Postgres in Compose (chosen) | SQL for the console and KPIs; zero extra services; same in local and prod | Single instance, backups are ours |
| DynamoDB | Serverless, AWS-native | Key design for joins and aggregates; awkward local setup |
| Amazon RDS / Aurora | Managed, HA | Cost and setup time for a demo; it is the production path |
| SQLite | Simplest | Weak concurrency between api and mcp containers |

## Consequences
The console, the harness and the operational lakehouse read the same rows an auditor would. Production moves to
RDS/Aurora without code changes.

## Confidence
High.
