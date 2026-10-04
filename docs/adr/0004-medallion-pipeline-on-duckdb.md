# 0004. Medallion pipeline on DuckDB with data contracts

- **Status:** Accepted
- **Date:** 2026-09-28 (amended 2026-09-29 with the organizers' answers on mock data)
- **Deciders:** David, Freddy · **Owner:** @vldiego
- **Related:** [`contracts/gold_contract.md`](../../contracts/gold_contract.md), [`data/pipeline/`](../../data/pipeline/), ADR 0018

## Context
The dataset arrives as partitioned CSVs on S3 with duplicates, late arrivals, mixed labels (`México`/`Mexico`), broken
foreign keys and a fraud label that must never reach the agent. We need a reproducible snapshot in about a minute, on a
laptop and on the server.

## Decision
Bronze → silver → gold in Python with DuckDB and Polars. Silver contracts in pandera; gold rules G1–G5 are checked on
every run (if one fails, gold is not published). `is_fraud` lives only in `data/gold_eval/`. A manifest records rows and
sha256 per table and version. `make setup` reproduces everything; a late-arrival and schema-change fixture proves the
incremental path.

Organizers' answers (Slack, 2026-09-29): mock data is acceptable when the problem needs data the dataset lacks, and not
all tables must be used if the choice is justified. So: transactions, customers, products and `is_fraud` come from the
dataset; only the customer's message is synthetic — **"synthetic message over real state"**. The README documents the
tables used and not used, with the reason.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| DuckDB + Polars + pandera (chosen) | 60 s reproducible setup, in-process, no cluster | Single node |
| Databricks / Delta | Production-grade lakehouse | Workspace access to the bucket not guaranteed; slower feedback |
| Postgres as analytical store | Familiar SQL | A load step and a server for read-only analytics |

## Consequences
The solution reads Parquet in-process; the label leak is impossible by construction; the manifest gives a light
"time travel" to earlier gold versions. A production version moves the same SQL to a lakehouse (ADR 0018).

## Confidence
High.
