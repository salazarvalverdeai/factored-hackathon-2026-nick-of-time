# 0018. Data and model lifecycle: an operational medallion that feeds evaluation

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Freddy · **Owner:** @vldiego
- **Related:** spec 14, ADRs 0004, 0007, 0015

## Context
An AI system in production must be reviewed, improved and scaled over time. Our batch medallion already covers the
bank's data; the system's own operation (cases, analyst decisions, LLM calls, denials) is not yet fed back.

## Decision
Close the loop **operate → record → medallion → measure → evaluate → improve → release**:
- case events in Postgres flow to **bronze** (raw, with load time) → **silver** (cleaned, joined with gold transactions
  and customers) → **gold** `ops_kpis` (daily cases, `receipt_rate`, escalation, unsafe outcomes, cost, p95) and
  `feedback_cases` (the analyst's decision as a label for the next evaluation set);
- fixed review triggers: any unsafe outcome stops the release; escalation-rate shifts trigger a classifier and τ review;
  intent or language drift refreshes the evaluation set; a regulatory change is a policy PR plus an ADR; cost per case
  over budget triggers a model review; a new data batch produces a new gold version in the manifest.

In the sprint it runs on the existing DuckDB pipeline. **Databricks is desirable**: where a workspace can read the S3
bucket, the same layers are built as Delta tables with notebooks versioned in the repo.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Operational medallion on the existing pipeline (chosen) | Reuses contracts and checks; works today | Batch, single node |
| Databricks with Auto Loader and Structured Streaming | Production-grade, streaming, time travel | Workspace access and time risk |
| No feedback loop | No work | The system cannot improve from its own operation |

## Consequences
The production path is documented in the README: events to a stream, Delta or S3 + Glue + Athena, RDS, ECS, a model
registry with an approval gate. Contracts, policies, the harness and the gates do not change at scale.

## Confidence
Medium-high.
