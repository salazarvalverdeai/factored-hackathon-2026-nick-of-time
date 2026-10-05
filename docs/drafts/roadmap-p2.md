# P2 roadmap (DOCUMENTED ONLY, nothing built or applied)

**This file is a proposal. No code, infrastructure, workflow or model was created or changed for any item below.** It is
a draft for the lead's review, written 2026-10-05 against `origin/main` at `5636caa`. Sizes are S, M or L (no hours).
Every item keeps the constitution in `CLAUDE.md`: the LLM understands and never decides, decisions live in
`contracts/policies.yaml`, `customer_id` comes only from the session, `is_fraud` lives only in `data/gold_eval/` and is
read only by the evaluation harness and, by time window, by the fraud-model pipeline (ADR 0022), a person closes every
case, and every figure carries a label. Voice is tracked in `architecture.md` section 3d, not here.

## Overview
| # | Item | Size | Builds on |
|---|---|---|---|
| 1 | Monitoring and alerting | M | `.github/workflows/uptime.yml`, `llm_calls`, `/api/health` |
| 2 | MLflow registry and experiments | M | `eval/bench/`, `eval/PROTOCOL.md`, ADR 0015 |
| 3 | Continuous model evaluation | M | spec 18 auditor and judge, spec 14 `ops_kpis` |
| 4 | Model tests in the CI pipeline | S | `.github/workflows/ci.yml`, `eval/bench/gate.py` |
| 5 | Data upload, retrain, re-evaluate loop | L | spec 17 pipeline, ADR 0018, ADR 0022 |
| 6 | Maintenance and versioning of models, prompts and policies | M | `contracts/policies.yaml`, `/api/health` fields |
| 7 | Databricks ops lakehouse | L | spec 14 local lakehouse (#145, #146) |

## 1. Monitoring and alerting
- **Goal:** know within minutes when the public demo is down, slow, over budget or answering badly.
- **Exists today:** `uptime.yml` checks the public endpoints every 15 minutes and sends a Telegram alert only on a
  healthy-to-failing change plus one recovery (PR #147). The api records every LLM call in `llm_calls`
  (`packages/nick_of_time/store`, PR #117) and the daily cap reads the day's spend (`llm/steps.py`, spec 05 AC-18).
  `/api/health` reports `git_sha`, contract, models and `platform_revision`.
- **Proposed design:** keep uptime as is; add (a) a daily spend and p95 latency report computed from `llm_calls` and case
  events into the Telegram alert chat, (b) alerts on the abuse guard's 429 rate and on the share of turns that fall back
  to S0 or the calm Platform-down turn, (c) LangSmith traces on the Platform graph as the trace source for debugging.
- **Effort:** M.
- **Risks:** alert fatigue; Telegram token is a secret (GitHub secret/SSM only); in-process guard counters reset on
  restart (`apps/api/app/guard.py`).
- **Guardrails:** alerts and dashboards never contain score, policy ids or transcripts (CLAUDE.md notification rule);
  monitoring reads, it does not change a decision; thresholds are `[assumption]` until measured.

## 2. MLflow registry and experiments
- **Goal:** one place that records which model, prompt and threshold produced which result, and which is approved.
- **Exists today:** benchmark arms and prices in `eval/bench/arms.yaml` and `prices.yaml`, gate evidence in
  `gate_evidence.yaml`, the lean-rule protocol in `eval/PROTOCOL.md` (spec 15, ADR 0015); the fraud screen and its
  split hash (spec 17). Results are committed files under `eval/results/`; there is no MLflow today.
- **Proposed design:** a self-hosted MLflow tracking server (a new compose service, or a local file store for the first
  step) logging each benchmark and fraud run with its split hash, arm, parameters, metrics and the git SHA; a registry
  entry per production model with stages that mirror the lean rule's decision. The committed files stay the source of
  truth for the pitch; MLflow is an index.
- **Effort:** M.
- **Risks:** a new stateful service on one EC2 (ADR 0011); duplicate sources of truth; artifacts must not hold labels.
- **Guardrails:** model files and logged artifacts contain no `is_fraud` label and no transaction id (ADR 0022 rule 4);
  the registry cannot promote a model: promotion remains a pre-registered rule plus a lead decision; the LLM never
  edits `policies.yaml` or the registry.

## 3. Continuous model evaluation
- **Goal:** keep measuring the live system against the evaluation protocol, not only once at release.
- **Exists today:** deterministic auditor checks A1-A7 as pure functions and the advisory judge (spec 18, ADR 0021,
  PRs #54, #79, #85, #73); harness and sealed held-out guard (spec 10); ops KPIs in `data/ops` and `ops_kpis.json`
  (spec 14 T3-T4, #146); the robustness suite with a constitution checker (`eval/robustness`, PR #157).
- **Proposed design:** a scheduled job (GitHub Actions cron or the host) that (a) re-runs the auditor over new case
  events, (b) runs the dev set and the robustness characters on the latest deploy with the `fake` provider for gates and
  a small real-model sample under the daily LLM cap, (c) writes results to `ops_kpis` and flags drift per the fixed
  triggers of ADR 0018 (unsafe outcome stops the release; escalation shift reviews the classifier; intent or language
  drift refreshes the set).
- **Effort:** M.
- **Risks:** cost of real-model runs; the sealed held-out must never be used for tuning (spec 10 T4 guard); judge
  opinions are advisory and can be wrong.
- **Guardrails:** the held-out set is run only through its guard and hash; labels are read only by the harness; the
  judge never closes or approves anything; findings reach a person.

## 4. Model tests in the CI pipeline
- **Goal:** a change to a prompt, threshold, policy or model cannot merge if it breaks behavior.
- **Exists today:** CI runs pytest (with the Postgres suite), ruff, an AC-coverage gate, web lint and build, gitleaks
  (`ci.yml`); offline tests with the `fake` LLM including the robustness smoke (`tests/test_robustness_suite.py`) and the
  local real-stack test (`tests/test_spec04_int_local.py`); the structured-output smoke and gate in `eval/bench`.
- **Proposed design:** add a CI job "model tests" that runs, on every PR touching `packages/nick_of_time/nlu`, `llm`,
  `contracts/policies.yaml` or `apps/agent`: the decision-table tests, the dev-set slice on the fake provider, the
  constitution checker, and a snapshot of prompt hashes. Never call the real LLM in CI (CLAUDE.md).
- **Effort:** S.
- **Risks:** CI time (target under 5 minutes, `ci.yml` header); flaky tests if a real model slips in.
- **Guardrails:** `fake` provider only; no labels or dataset files in the repo or the runner; contracts still change
  only by PR approved by the lead (rule 9).

## 5. Data upload, retrain, re-evaluate loop
- **Goal:** when the bank uploads a new data batch, produce a new gold version, retrain the fraud screen and re-evaluate
  before anything is promoted.
- **Exists today:** the bronze to gold pipeline with manifest and versioned gold (`data/pipeline`, ADR 0004, `make setup`),
  the time split, leakage-safe features and sklearn screen (spec 17 T1-T3), the benchmark harness, and ADR 0018's rule
  that a new batch yields a new gold version in the manifest.
- **Proposed design:** upload to a staging prefix in the gold bucket, run the pipeline checks (pandera, G1-G5), cut
  `gold/v2` with a manifest, retrain on the training and validation windows only, evaluate once on the test window, log
  to MLflow (item 2), and open a PR that updates the model hash and `fraud_benchmark.json`. A person approves.
- **Effort:** L.
- **Risks:** label leakage across windows; schema drift in late-arriving data; the pipeline needs label access that the
  deployed roles do not have by design.
- **Guardrails:** runs where label access already is (the lead or Diego), never in the deployed stack (ADR 0022 rule 5);
  training reads labels only for the training and validation windows, the test window once after the model file is
  frozen and hashed; the agent, MCP, api, web and LLMs never read labels; the score stays an optional input to the rules
  (ADR 0006), so a model never decides.

## 6. Maintenance and versioning of models, prompts and policies
- **Goal:** every answer can be traced to the exact model, prompt and policy versions that produced it.
- **Exists today:** `policies.yaml` is versioned (version 2, loader and rule ids, PR #63) and changes only by lead-approved
  PR; the contract is versioned (`1.7.0`, `packages/nick_of_time/__init__.py`); `/api/health` exposes `git_sha`,
  `policies_version`, `models`, and `prompt_hash` and `classifier_version`, both `null` today
  (`apps/api/app/live.py`); `llm_calls` stores each call; the inventory of models and decision engines is required by
  ADR 0021.
- **Proposed design:** fill `prompt_hash` and `classifier_version`; stamp them on each `llm_calls` row and on the
  case's audit events; keep prompts as files in the repo with a hash test; add a short change log per model, prompt and
  policy with its evaluation evidence; regulatory changes remain a policy PR plus an ADR (ADR 0018, ADR 0019, each row
  with `source_url` and `verified_on`).
- **Effort:** M.
- **Risks:** hash churn on harmless edits; the stamp must not leak prompts to customers.
- **Guardrails:** the LLM never reads or edits `policies.yaml`; the stamps are internal and never in a customer message
  or notification; a rollback is a git revert plus the deploy gate (`deploy.yml`), not a hot edit.

## 7. Databricks ops lakehouse
- **Goal:** the operational medallion of ADR 0018 on Databricks as Delta tables with notebooks, as the production path.
- **Exists today (relation to spec 14):** the local lakehouse is merged: bronze extractor and silver on the in-memory
  store (#145, `data/ops/bronze.py`, `silver.py`), gold `ops_kpis` and `feedback_cases`, manifest and `ops_kpis.json`
  (#146, `data/ops/gold.py`, `make ops` with `--source sample`). Spec 14 T5 (run against Postgres) and T7 (Delta and
  notebooks) are open; T6 per-engine outcomes is P2 (`specs/14-ops-lakehouse.md` section 10).
- **Proposed design:** keep the same layers and contracts. Replace the extractor's source with a read replica or export
  of the Postgres case events landed in S3, read by a Databricks workspace as Delta tables (bronze, silver, gold),
  notebooks versioned in the repo, and the `ops_kpis` table feeding `/analytics` through the existing JSON export. The
  local DuckDB path stays as the fallback and as the test oracle.
- **Effort:** L.
- **Risks:** workspace and S3 access are an unresolved dependency; cost; a second implementation can drift from the
  local one, so a parity test on the sample is needed.
- **Guardrails:** the lakehouse holds case operations data, not labels; `is_fraud` stays in `data/gold_eval/` (ADR 0022);
  the runtime still reads only read-only gold (ADR 0004); customer notifications and exports exclude score, policy ids
  and transcripts; every KPI carries a label (`[simulated]` for demo data).
