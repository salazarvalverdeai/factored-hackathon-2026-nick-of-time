# Spec 14 — Operational lakehouse

- **Feature:** the system learns from its own operation: the records of the cases it handles go bronze → silver → gold
  and produce the daily KPIs of `/analytics` and the analysts' decisions as labels for the next evaluation set.
- **Status:** Approved — **deferred until after the submission** (lead, 2026-10-05): nobody can build it before the
  deadline, and no P0 criterion depends on it
- **Owner:** @vldiego (follow-ups from 2026-10-05: @salazarvalverdeai) · **Priority:** P1 (Databricks: P2) ·
  **Size:** M–L
- **Challenge dimension:** Data Engineering, Data Analytics
- **Depends on:** 05 (operational tables in Postgres; `schema.sql` is in `main`), the existing pipeline
  (`data/pipeline/`), gold v1 · **Enables:** 12 (`/analytics`, AC-02) · **ADRs:** 0004, 0010, 0018, 0020, 0021
- **Issue:** #16

> Minimal profile plus sections 7 and 8. No API: a batch job reads Postgres and writes Parquet and one JSON file.

---

## 1. Introduction
ADR 0018 closes the loop *operate → record → medallion → measure → evaluate → improve*. This spec builds the
"record → medallion → measure" part with the tools the data pipeline already uses (DuckDB, Parquet, contracts, a
manifest): one idempotent job, `make ops`, that copies the append-only operational tables to bronze, cleans and joins
them in silver, and writes two gold tables. Everything it reports comes from the system's own runs, so it is
`[simulated]` until real customers use it.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 come from issue #16 with the same numbers. AC-07 onward are added by this spec; AC-10 is the lead's
definition of 2026-10-04 (issue comment). Evidence: [T] test · [C] command · [U] screenshot · [D] file.

- **AC-01 [P1]** — When the job runs (`make ops` or scheduled), the Postgres rows shall land in bronze raw, with their
  load time, and with no lost rows. · [T]
- **AC-02 [P1]** — Silver shall join each event with its gold transaction and customer and pass the contract
  checks. · [T]
- **AC-03 [P1]** — Gold `ops_kpis` shall hold per day: cases, `receipt_rate`, escalation, unsafe outcomes, cost and
  p95. · [D]
- **AC-04 [P1]** — Gold `feedback_cases` shall store the analyst's decision per case as a label for the next
  evaluation set. · [D]
- **AC-05 [P1]** — If the run is repeated on the same source rows, then the result shall be identical and recorded in
  the manifest with its version. · [T]
- **AC-06 [P2]** — Where a Databricks workspace can read S3, the same layers shall exist as Delta tables with
  notebooks versioned in the repo. · [D]
- **AC-07 [P1]** — Rows written by evaluation runs (`run_id` not null) and synthetic live-mode transactions shall be
  kept apart: they never enter `ops_kpis` or `feedback_cases` as operation, and each gold row carries its `mode`. · [T]
- **AC-08 [P1]** — No operational gold table shall hold personal data, the fraud label, the bank's score shown to a
  customer or a message transcript. · [T]
- **AC-09 [P1]** — When the job ends, it shall write `apps/web/public/data/ops_kpis.json` with the shape of §7.4. · [T]
- **AC-10 [P2]** — `ops_kpis` shall add per-engine outcomes: precision per zone against the analysts' decisions,
  override rate, deadlines met, auditor findings per 100 runs, `coherence_rate` and judge–analyst agreement. · [D]
- **AC-11 [P1]** — If a source row breaks a silver contract, then the job shall keep it in bronze, count it in the
  quality report and leave it out of silver; the job does not stop. · [T]

## 7. Data model touched
Reads the operational tables of spec 01 §6.5 (read-only, through `nick_of_time.store`) and `data/gold/` v1. Writes
under `data/ops/` (git-ignored, like `data/gold/`) and one JSON file for the web. Creates no Postgres table.

### 7.1 Bronze — `data/ops/bronze/`
One Parquet file per source table, a faithful copy plus `_loaded_at` and `_source` (`postgres` or `memory`):
`cases`, `case_events`, `product_overrides`, `notifications`, `notification_deliveries`, `policy_denials`,
`llm_calls`, `settings_events`. Not copied: `sessions` (holds the OTP hash), `customer_channels` and `link_tokens`
(addresses and tokens), `idempotency`, `demo_transactions` (synthetic, ADR 0020 rule 2).

"No lost rows" (AC-01): for each table, the row count and the maximum `created_at` in bronze equal those read from the
source in the same transaction; the run fails if they differ.

### 7.2 Silver — `data/ops/silver/`
- `case_events`: one row per event with typed columns taken from `payload` (`status_to`, `action`, `reason`), plus
  the case's `country`, `product_type`, `zone`, `mode`, `run_id`, and from gold the customer's `segment` and the
  transaction's `amount`, `currency` and `transaction_date`.
- `cases`: one row per case with its current `queue_status` (the last `status_changed`), opening and closing times,
  whether a block was verified, whether a receipt was issued and whether a handoff was emitted.
- `llm_calls` and `policy_denials`: typed, with the case reached through `trace_id` when there is one.

Contracts (pandera, as in `data/pipeline/contracts.py`): keys unique; `type` and `status_to` inside the lists of spec
01 §6.5; `seq` continuous per case; every event's case exists; `actor` in its closed list; timestamps not in the
future. A gold transaction or customer that is not found leaves the gold columns null and raises `qc_gold_missing`.

### 7.3 Gold — `data/ops/gold/`
**`ops_kpis`** — one row per `day` (the case's `opened_on`) × `mode`:

| Column | Definition |
|---|---|
| `cases` | cases opened that day |
| `receipt_rate` | cases with a receipt issued that carries a deadline ÷ `cases` (ADR 0013) |
| `escalation_rate` | cases with a `handoff_emitted` event ÷ `cases` |
| `unsafe_outcomes` | cases with a critical finding of `nick_of_time.audit` (same checks as spec 10 §4.1) |
| `cost_usd` | sum of `llm_calls.cost_usd` for the day; `cost_per_case` = that ÷ `cases` |
| `latency_p95_ms` | p95 of `llm_calls.latency_ms` for the day `[assumption]` (Q2) |
| `denials` | `policy_denials` rows that day |

Every rate keeps its numerator and denominator in two more columns.

**`feedback_cases`** — one row per case that a person decided: `case_id`, `transaction_id`, `country`, `segment`,
`zone`, `agent_decision` (what the system did at intake), `analyst_decision` (the last deciding `analyst_action`:
`approve_credit`, `approve_block`, `unblock_card`, `resolve`, `close_case`), `analyst_reason`, `agreed` (the analyst
kept the system's proposal) and `decided_at`. It holds no customer text, so it is a label set, not a case set: turning
it into evaluation cases is a new sealed set under ADR 0021, outside this spec.

**Manifest** — `data/ops/manifest.json` with the same fields as the gold manifest: version, run time, rows and sha256
per table, source row counts, checks with counts. The version goes up only when a table's hash changes (AC-05).

### 7.4 `apps/web/public/data/ops_kpis.json`
`{generated_at, git_sha, source, data}` (spec 01 §6.2), with `data`:
`{"label": "[simulated]", "mode": "replay", "days": [{"day": "2026-06-01", "cases": 0, "receipt_rate": {"value": 0.0,
"numerator": 0, "denominator": 0}, "escalation_rate": {…}, "unsafe_outcomes": 0, "cost_per_case": 0.0,
"latency_p95_ms": 0, "denials": 0}], "feedback": {"decided": 0, "agreed": 0}}`.

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (@gianzk) — source.** Is reading through `nick_of_time.store` right, or do you prefer a read-only Postgres role
  and plain SQL? The job needs every row of the eight tables of §7.1, not per-customer accessors.
- **Q2 (@salazarvalverdeai) — p95.** `llm_calls` has the latency of each model call, not of a whole turn. Default: p95
  of model calls, named as such on the page. Or is there a turn-level latency I should read instead?
- **Q3 (@salazarvalverdeai) — what counts as operation.** Default (AC-07): rows with a `run_id` are evaluation and are
  left out; `replay` sample cases and `live` demo cases are reported in separate rows by `mode`. Agreed?
- **Q4 (@salazarvalverdeai) — AC-10.** The per-engine outcomes need the auditor findings and the judge's opinions to be
  stored (spec 18, P1). Default: P2, built only if those tables exist by then.
- **Q5 (@gianzk) — schedule.** "Scheduled" in AC-01: a cron entry on the EC2 that runs `make ops` after the demo
  seeder, or manual only for the submission? Default: manual, with the cron line documented.
- **Q6 (@salazarvalverdeai) — Databricks.** Is there a workspace that can read the bucket? Without one AC-06 stays a
  documented path.
- Assumption: until the backend of spec 05 is deployed, the job is developed and tested against the in-memory store
  with recorded fixtures; the Postgres path is the same code with a different source. `[assumption]`
- Assumption: with a handful of demo cases the daily rates are illustrations, not measurements; the page shows the
  counts next to every rate. `[assumption]`

## 9. Out of scope
Real streaming · automatic retraining · turning `feedback_cases` into evaluation cases (a new sealed set, ADR 0021) ·
the online auditor (spec 18) · any write to Postgres · the `/analytics` section that displays the KPIs (spec 12 T6).

## 10. Plan, tasks and verification
Implementation goes in `feat/14-…` branches once this spec is approved, after specs 09, 10 and 12 (P0).
- [x] T1 — bronze extractor with row-count and high-water checks, on the in-memory store · covers AC-01, AC-07 ·
      `data/ops/bronze.py`, [T] `tests/test_spec14_bronze_silver.py`
- [x] T2 — silver tables, contracts and the quality counts · covers AC-02, AC-11 · `data/ops/silver.py`
- [ ] T3 — gold `ops_kpis` and `feedback_cases`, manifest, `make ops` · covers AC-03, AC-04, AC-05, AC-08
- [ ] T4 — `ops_kpis.json` export · covers AC-09
- [ ] T5 — run against Postgres (after spec 05 is deployed); schedule documented · covers AC-01
- [ ] T6 [P2] — per-engine outcomes · covers AC-10
- [ ] T7 [P2] — Delta tables and notebooks on Databricks · covers AC-06

Tests live in `tests/test_spec14_*.py`, cite their criterion and run offline on fixtures.

**Closing checklist:** every P1 criterion has a passing test or check that cites it · status → Implemented · the
labels `[simulated]` and `mode` reach the page · lessons added to `CLAUDE.md`.
