# Spec 14 — Operational lakehouse

- **Feature:** the system learns from its own operation: the records of the cases it handles go bronze → silver → gold
  and produce the daily KPIs of `/analytics` and the analysts' decisions as labels for the next evaluation set.
- **Status:** In progress — T1–T5 and T8 done (T1–T4 offline on the in-memory store, 2026-10-05; T5, the Postgres
  source and `make ops-live`, run on the restored production backup of 2026-10-06, §11.5); the Live position of
  `/analytics` (spec 12 T6) draws it as "Public demo traffic". T6 and T7 (P2) are open
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
- **AC-12 [P1]** — When `make ops-replay` runs twice on the same gold, the sample, the replay outcomes, the gold
  tables and the series of `ops_kpis.json` shall be identical (§11). · [T]
- **AC-13 [P1]** — The replay and the as-is query shall never read `is_fraud` or `data/gold_eval/`; the bank's
  `fraud_score` is read only through `get_fraud_score`, as at runtime (§11). · [T]
- **AC-14 [P1]** — The replay shall sample approved card charges per month of the window, as many as the bank's W3
  complaints that month; if the search finds several candidate charges, or none, then it shall ask, as
  `PolicyEngine.decide` does in production, and open no case (§11). · [T]
- **AC-15 [P1]** — `ops_kpis.json` shall carry the series Bank today `[data]`, With Nick of Time `[simulated]` and
  Live ("Public demo traffic", pending until T5), each with its label, source, window and method notes (§7.4, §11).
  · [T]
- **AC-16 [P1]** — A row written by an evaluation run (`run_id` set) shall never be counted in the replay series. · [T]
- **AC-17 [P1]** — Two runs of `make ops-replay` on the same commit and gold shall write byte-identical
  `ops_kpis.json` files: the export carries no manifest version or other local state, and the replay rebuilds its
  layers in a clean `data/ops/replay/`. · [T]

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
| `automated_rate` | cases with a verified block and no `handoff_emitted` ÷ `cases`: the safe automated path (§11) |

Every rate keeps its numerator and denominator in two more columns.

**`feedback_cases`** — one row per case that a person decided: `case_id`, `transaction_id`, `country`, `segment`,
`zone`, `agent_decision` (what the system did at intake), `analyst_decision` (the last deciding `analyst_action`:
`approve_credit`, `approve_block`, `unblock_card`, `resolve`, `close_case`), `analyst_reason`, `agreed` (the analyst
kept the system's proposal) and `decided_at`. It holds no customer text, so it is a label set, not a case set: turning
it into evaluation cases is a new sealed set under ADR 0021, outside this spec.

**`replay_contacts`** (§11, `make ops-replay` only) — one row per month × country × outcome × candidates bucket ×
zone × confirmed × expected block × complete intake, with `contacts`: every replayed contact, also those that end in
a question and open no case. No id, name or text.

**Manifest** — `data/ops/manifest.json` with the same fields as the gold manifest: version, run time, rows and sha256
per table, source row counts, checks with counts. The version goes up only when a table's hash changes (AC-05).

### 7.4 `apps/web/public/data/ops_kpis.json`
`{generated_at, git_sha, source, data}` (spec 01 §6.2), with `data`:
`{"label": "[simulated]", "mode": "replay", "days": [{"day": "2026-06-01", "cases": 0, "receipt_rate": {"value": 0.0,
"numerator": 0, "denominator": 0}, "escalation_rate": {…}, "unsafe_outcomes": 0, "cost_per_case": 0.0,
"latency_p95_ms": 0, "denials": 0}], "feedback": {"decided": 0, "agreed": 0}}`.

Amended (§11): `make ops-replay` adds `data.series = {window, compare, bank_today, replay, live}`. `compare` lists
the only pairs shown side by side: `{bank_today: first_contact_resolution, replay: complete_intake}` and
`{bank_today: days_to_receipt, replay: days_to_receipt}`. `bank_today` and `replay` each hold `key`, `name`, `label`,
`source`, `window` (`["2026-01", "2026-05"]`), `notes` (one sentence per metric), `months` and `total` (same fields,
`month: "total"`). A month carries `contacts`, `days_to_receipt` `{p50, mean, n, missing}` and rates
`{value, numerator, denominator}`. Bank: `first_contact_resolution` (with `constant: true`), and as context
`escalated`, `outside_sla_at_intake` and `resolution_days` `{p50, n}`. Replay: `complete_intake`, and as context
`handed_to_analyst`, `opened_without_deadline`, `safe_automated_resolution`, `asked_several`, `asked_none`,
`cases_opened` and `confirmations_assumed`; plus `sensitivity` `{variant, named, amount_and_date}`, each with
`complete_intake` and `asked`. `live` (named "Public demo traffic", §8) is `{key, name, status: "pending", message,
reason}` while the source has no case of a public demo session or of operation; `make ops-live` (T5, §11.5) replaces
it with `{key, name, status: "ready", label: "[simulated]", message, reason, source, window: [first day, last day],
as_of, days, total, feedback, notes}`, where `days` has the shape of `data.days` plus `automated_rate` and
`cases_by_mode` `{live, replay}`, and `total` the same fields over the window plus `cost_usd`, `demo_sessions`,
`cases_without_demo_session`, `synthetic_charges` and `by_mode` `{live, replay}`, each with `cases`, `receipt_rate`,
`escalation_rate`, `automated_rate`, `unsafe_outcomes`, `demo_sessions` and `synthetic_charges`. `days` and
`feedback` keep their meaning: here they are the replay's, `[simulated]`. `generated_at` is the HEAD commit time
(AC-17).

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
  seeder, or manual only for the submission? Default: manual, with the cron line documented. Answered in T5: see the
  Schedule line of §11.5.
- **Q6 (@salazarvalverdeai) — Databricks.** Is there a workspace that can read the bucket? Without one AC-06 stays a
  documented path.
- Assumption: until the backend of spec 05 is deployed, the job is developed and tested against the in-memory store
  with recorded fixtures; the Postgres path is the same code with a different source. `[assumption]`
- Readings of T1–T4 where this spec is silent `[assumption]`: unsafe outcomes use A7 (lifecycle) only, the one
  critical audit check that runs on store rows alone; LLM calls and denials reach a day and a mode only through a case
  (by `trace_id`), others are counted as `without_case`; a live-mode transaction missing from gold is synthetic;
  `agent_decision` is `block_and_open_case` or `open_case`, and `agreed` is false only when the analyst reverses it
  (`unblock_card` after a block, `approve_block` without one); gold hashes are of the rows, not the Parquet bytes.
- The readings of §11 (replay and Bank today) are listed in §11.3.
- Assumption: with a handful of demo cases the daily rates are illustrations, not measurements; the page shows the
  counts next to every rate. `[assumption]`
- Readings of T5 `[assumption]`: every public session runs under its own `demo-` run (ADR 0026); any `run_id` that
  is not null and does not start with `demo-` is an evaluation run and never counts (AC-07). The gold tables stay
  operation only (`run_id` null). The lifecycle check (A7) runs per mode and run, so two demo sessions on one charge
  are not a duplicate. A `reason` reaches silver only from `analyst_action` and `status_changed`: a customer's
  `reevaluation_requested` reason is free text and stays in bronze (AC-08).
- **Live is the public demo traffic (lead's decision, 2026-10-06, option B).** Live mode alone had one case in the
  first production backup, so the Live series, named "Public demo traffic" (key `live`), counts the cases of the
  public demo sessions (`demo-` runs) and of operation (`run_id` null) in **both** modes, with a `by_mode` breakdown
  (live, replay) in `total` and `cases_by_mode` per day. Message: "Public demo traffic on the deployed app since
  <first day>". Label `[simulated]`: replay-mode demos run over the historical gold state with the fixed demo date
  2026-06-01, and live-mode charges are synthetic (ADR 0020). A case's day is the UTC date its row was written
  (`created_at`), because a replay-mode case's `opened_on` is always the demo date. Evaluation runs never count.

## 9. Out of scope
Real streaming · automatic retraining · turning `feedback_cases` into evaluation cases (a new sealed set, ADR 0021) ·
the online auditor (spec 18) · any write to Postgres · the `/analytics` section that displays the KPIs (spec 12 T6).

## 10. Plan, tasks and verification
Implementation goes in `feat/14-…` branches once this spec is approved, after specs 09, 10 and 12 (P0).
- [x] T1 — bronze extractor with row-count and high-water checks, on the in-memory store · covers AC-01, AC-07 ·
      `data/ops/bronze.py`, [T] `tests/test_spec14_bronze_silver.py`
- [x] T2 — silver tables, contracts and the quality counts · covers AC-02, AC-11 · `data/ops/silver.py`
- [x] T3 — gold `ops_kpis` and `feedback_cases`, manifest, `make ops` · covers AC-03, AC-04, AC-05, AC-08 ·
      `data/ops/gold.py`, `data/ops/run.py`, [T] `tests/test_spec14_gold.py`
- [x] T4 — `ops_kpis.json` export · covers AC-09 · the sample source writes it to `data/ops/` only; shape fixture in
      `apps/web/app/analytics/__fixtures__/ops_kpis.json`
- [x] T8 — Bank today and the replay over the dataset, `make ops-replay`, the committed export · covers AC-12 to
      AC-17 · `queries/ops/asis_monthly.sql`, `queries/ops/replay_sample.sql`, `data/ops/replay.py`,
      `data/ops/series.py`, [T]
      `tests/test_spec14_replay.py`
- [x] T5 — run against Postgres (after spec 05 is deployed); schedule documented · covers AC-01, AC-07, AC-08,
      AC-09 · `bronze.from_postgres`, `series.live`, `run.update_live`, `make ops-live`, [T]
      `tests/test_spec14_postgres.py` (the Postgres tests run in CI's postgres:16 service); run on the restored
      production backup `nickoftime-2026-10-06T035613Z` (§11.5): only `data.series.live` changed, a rerun wrote the
      same bytes, and no display name, id, address or free text of the backup is in the export
- [ ] T6 [P2] — per-engine outcomes · covers AC-10
- [ ] T7 [P2] — Delta tables and notebooks on Databricks · covers AC-06

Tests live in `tests/test_spec14_*.py`, cite their criterion and run offline on fixtures.

**Closing checklist:** every P1 criterion has a passing test or check that cites it · status → Implemented · the
labels `[simulated]` and `mode` reach the page · lessons added to `CLAUDE.md`.

## 11. Amendment: Bank today and replay over the dataset (lead, 2026-10-05)
Decisions E1 and E2 of the lead, revised the same day: `/analytics` shows an "Operation" switch with three positions,
Bank today `[data]`, With Nick of Time `[simulated]` and Live, over the same five months, 2026-01..2026-05. The repo
has verified holiday calendars for 2026 only (ADR 0019), so in this window no case loses its legal deadline for want
of a calendar. The headline pair is the lead's goal metric: the bank's FCR against the system's complete intake at
first contact.

### 11.1 Bank today `[data]`
`queries/ops/asis_monthly.sql` over gold `complaints`, W3 by the rules of `queries/pitch/p01`, per creation month,
plus a 5-month total row; its output is committed as `queries/ops/asis_monthly.csv`. First contact resolution is the
FCR of `queries/pitch/p02` (43.6%, Queja contacts, the whole dataset window): the interactions table is not in this
repo's gold, so the value repeats every month with `constant: true`. The bank's FCR means a complaint contact resolved
at first contact; the system's complete intake means a case, its legal deadline and the evidence handed to a person.

### 11.2 With Nick of Time `[simulated]`: the replay (`data/ops/replay.py`)
Spec 09's method, "synthetic message over real state". `queries/ops/replay_sample.sql` draws real approved card
charges of MX, CO and AR customers, a fixed seeded sample per month (md5 of the id and a fixed seed), as many as the
bank's W3 complaints that month (3,404 over the window), so both series count the same volume. The customer reports
each charge the next day in a templated Spanish message that names it as the statement shows it: amount, currency,
date and merchant when there is one; half the messages read as an unrecognized charge, half as a wrongful one. Then
the same S0 path as production, deterministic and offline, no LLM: the B0 rules; `search_transaction`,
`get_fraud_score`, `get_customer_profile` and `compute_deadline` as the MCP read handlers run them over the customer's
own card transactions; `PolicyEngine.decide`. Several candidates or none → the engine asks and the contact ends. An
opened case is written to an in-memory store as the write tools leave it (case opened and verified; block verified
and status `verification` in zone high; `review` and `handoff_emitted` otherwise; `receipt_issued` with its
deadline), with mode `replay`. Each contact is then read back from the store for complete intake. The spec 14 job
runs unchanged on that store and `series.py` aggregates `ops_kpis` and `replay_contacts` per month. The final
resolution time is not simulated: a person decides it, so it is shown for the bank only.

| Metric | Bank today | With Nick of Time |
|---|---|---|
| Headline | FCR 43.6%, resolved at first contact (period value) | complete intake (spec 10 §4.1 `complete_intake_rate`): a case on the reported charge, the expected queue status and a receipt with its legal deadline, all at first contact ÷ contacts |
| Time to a receipt with a legal deadline | first response − creation, days (closest proxy) | 0 days when a case opens with a deadline at first contact |

Only those two rows are compared. Every other figure is context of its own series, with its own definition, and is
never drawn next to the other series' figure:
- Bank: escalated (status `Escalated` ÷ complaints: moved up a level inside the bank); outside SLA (the dataset's
  `sla_breached` ÷ complaints, an SLA the dataset does not name); days to the final resolution.
- System: handed to an analyst with evidence and a legal deadline (a handoff with complete intake ÷ contacts; charges
  with a medium or low bank score always go to a person, who decides the block or the credit); opened without a legal
  deadline (÷ cases opened); safe automated resolution (high-zone charges blocked and verified with no person, on the
  reported charge ÷ contacts whose charge is in the high zone).

The expected queue status comes from the policy file, as spec 09 derives expected states: `verification` when the
charge's bank score is in the high zone and the amount tier does not need a person, `review` otherwise.

### 11.3 Readings where the decision was silent `[assumption]`
- "Today" is the contact date, the day after the charge, at noon in the customer's country. Replay pins
  `clock.today` to DEMO_TODAY, so the read handlers run with their `utc_now` hook at that instant; cases are stored
  with mode `replay`.
- The message names the charge exactly as the customer's statement shows it. Complete intake is therefore an upper
  bound on how often a customer's own words identify the charge; real customers misremember amounts and dates. A
  sensitivity run on the same contacts names only the amount and the date, with no merchant (`sensitivity`).
- A zone medium confirmation is answered yes. Option cards for several charges are not answered: the replay does not
  pick a charge for the customer.
- Escalated and `sla_breached` are the dataset's own fields at its snapshot; neither says which SLA it measures.

### 11.4 Dataset limitation: complaints cannot be replayed as they are
The first version of this replay ran the 8,129 W3 complaints of 2025-06..2026-05 themselves. The dataset does not
link a complaint to a transaction: only 1,597 of those complainants (19.6%) have any approved or pending card charge
in the 30 days before the complaint, and almost no claimed amount matches one within the ±2% the search allows. The
engine asked in 90% of the contacts, which says nothing about the system and everything about the data. So the replay
uses real card charges with a written message (§11.2), and the bank series keeps the complaints only for its own
figures. The versioned measure of this limitation, shown on `/data`, is `queries/data/d01_complaint_transaction_link.sql`
`[data]`: over 2025-07..2026-05 (so the 30-day look-back stays inside gold), 22.1% of W3 complainants have a card
transaction in the 30 days before the complaint (21.5% for other complaints), and 2 of 579 claimed amounts (0.3%)
match one within ±2% in the same currency. The counts above are this replay's own first run, over its 12-month window.

### 11.5 Live: the Postgres source (T5, `make ops-live`)
`python -m data.ops run --source postgres` (`make ops-live`) reads the eight §7.1 tables in one read-only REPEATABLE
READ transaction (`set transaction ... read only`, checked with `show transaction_read_only`, ended by a rollback), with
the row count and maximum `created_at` of each table taken in the same transaction (AC-01). It selects only the
schema.sql columns, never `sessions` (display name, OTP hash), `customer_channels` (addresses) or `link_tokens`, and
writes nothing to the source. The layers go to `data/ops/live/` (git-ignored, rebuilt each run); in the committed
`apps/web/public/data/ops_kpis.json` only `data.series.live` changes, so Bank today, the replay, `days`, `feedback` and
the envelope keep their bytes, and the same snapshot writes the same file (AC-05). Live is "Public demo traffic" (§8,
lead's decision 2026-10-06): the demo sessions and operation in both modes, labeled "Public demo traffic on the
deployed app since <first day>" and `[simulated]`, because replay-mode demos run over the historical gold state with
the fixed demo date and live-mode charges are synthetic (ADR 0020). With no such case it stays pending. The DSN comes
from `--dsn` or `DATABASE_URL`, never from the repo; the target does not echo it.

**First run (2026-10-06, backup `nickoftime-2026-10-06T035613Z`)** `[simulated]`: 18 cases from 2026-10-05 to
2026-10-06 (17 demo sessions, 1 run-null case), 1 in live mode and 17 in replay mode; a receipt with its legal deadline
in 14 of 18 (77.8%), handed to an analyst 14 of 18 (77.8%), 0 unsafe outcomes. Only `data.series.live` changed, a
rerun wrote the same bytes, and none of the backup's display names, case, customer, transaction or run ids, addresses
or free-text reasons is in the export (checked against the restored tables). The dump and the container were deleted
after the run.

Run on a restored production backup (the daily `infra/backup.sh` dump; the lead's `nickoftime` AWS profile; the real
gold at `data/gold` or `GOLD_PATH`; run after any `make ops-replay`, which resets Live to pending):

```bash
aws s3 ls s3://nickoftime-gold-061039767206/backups/postgres/ --profile nickoftime
LATEST=$(aws s3 ls s3://nickoftime-gold-061039767206/backups/postgres/ --profile nickoftime | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://nickoftime-gold-061039767206/backups/postgres/$LATEST" /tmp/nickoftime-ops.sql.gz --profile nickoftime
docker run -d --rm --name nickoftime-ops-pg -e POSTGRES_USER=nickoftime -e POSTGRES_PASSWORD=local_only -e POSTGRES_DB=nickoftime -p 55432:5432 postgres:16
sleep 5
gunzip -c /tmp/nickoftime-ops.sql.gz | docker exec -i nickoftime-ops-pg psql -q -U nickoftime -d nickoftime
make ops-live DSN=postgresql://nickoftime:local_only@localhost:55432/nickoftime
git diff --stat apps/web/public/data/ops_kpis.json
docker stop nickoftime-ops-pg
rm /tmp/nickoftime-ops.sql.gz
```

The local container and its password exist only for the run. The command prints the source rows, the eval rows left
out, the silver checks and the Live status; the export is then committed through a PR like any other.

**Schedule:** manual after demos for the submission (the steps above). After the submission, a daily cron on the EC2
after the 07:17 backup, with a read-only role's DSN from SSM: `47 7 * * * root cd /opt/nickoftime && make ops-live`
`[assumption]`; not installed yet.
