# Board (move to GitHub issues on Monday)

> **Historical (2026-09-28).** Kept for context. Current decisions live in [`docs/adr/`](adr/README.md), the work
> plan in [`specs/`](../specs/README.md) and GitHub issues, and how we work in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Mon 28 · contracts and repo (everyone, 2 h)
- [ ] Public repo `factored-hackathon-2026-nick-of-time` with `.gitignore` (`.env`, `data/`) from commit 1
- [ ] Review `problem.md`, `contracts/policies.yaml`, `contracts/tools.py`, `contracts/handoff.schema.json`, `eval/eval_case.schema.json` (30 min, everyone)
- [ ] Ask on Slack #technical-help: synthetic data to external APIs? fraud_score available in real time? cutoff time on Oct 5?
- [ ] Data 1: download the dataset with credentials in `.env`; snapshot of customers/products/transactions/complaints/surveys
- [ ] Data 2: freeze the pitch queries in `queries/` (36.4%, FCR, AHT, NPS, 16 days, 120 frauds, score zones)

## Tue 29 · skeleton
- [ ] Data 1: DuckDB + checks (dedupe, schema, cross FK, future dates, México/Mexico) + `make setup`
- [ ] Full stack: FastAPI + tools per `contracts/tools.py` with session filter + mock identity (OTP, TTL 15 min)
- [ ] Freddy: `policies.yaml` evaluator (zones, amount gate, per-country clock with business days) + trace logger (OTel or JSONL with spans)
- [ ] Data 2: first 60 ES cases of the set (normal/ambiguous/human) with expected response
- [ ] Data 2 (Diego): **Q-AMT**, amounts and current resolution by country to calibrate `amount_gate` in `contracts/policies.yaml`. Four queries, each with its output: `queries/q_amt_fraud_by_country.csv`, `queries/q_amt_claimed_by_country.csv`, `queries/q_amt_resolution_by_country.csv`, `queries/q_amt_channel.csv`. Threshold proposal = p90 per country in local currency. Also confirm the provisional MXN (18.0) and BRL (5.5) rates: MX transactions are 100% USD and the dataset has no BR; `complaints.currency` does not follow the country (`docs/eda/data_quality.md`)

## Wed 30 · normal case end-to-end + Jev
- [ ] Full stack + Freddy: EV-0001 runs end to end with verification (Blocked + case + MX deadline)
- [ ] Freddy: Jev test on 40 ES/PT sentences vs rules; if it does not beat rules on PT or access fails → dropped today
- [ ] Data 2: 60 PT cases + 40 attack cases (injection, session, tool down, missing data)
- [ ] Data 1: labeled late-arrivals fixture; snapshot lineage

## Thu 1 · classifier + customer UI
- [ ] Freddy: rules → embeddings + LR (calibrated) → [Jev]; split by template; τ on validation
- [ ] Full stack: ES/PT chat UI with trace panel
- [ ] Data 2: a second person labels a sample of 40 cases (agreement)
- [ ] Everyone: the 3 mandatory cases run

## Fri 2 · agent view + explainability
- [ ] Full stack: handoff card per schema + buttons (approve credit / request info) + evidence graph from the log
- [ ] Freddy: full harness (final state, pass^4, latency, token cost) + "no" cases
- [ ] Data 1: missing_data and late_arrival cases in the harness

## Sat 3 · eval and deploy
- [ ] Freddy: run the full eval, error analysis, table by scenario × language × segment with n
- [ ] Full stack: public deploy, retries and fallback, record the demo
- [ ] Data 2: results table + measured/simulated/projected separation in the slides

## Sun 4 · submission
- [ ] 3 min video (script in `guion_slides_w3.md`), 4–6 slides, README with one-command setup
- [ ] Data 1: check the git history for secrets (`git log -p | grep -i AKIA`)
- [ ] Mon 5 first thing in the morning: send repo + deploy + slides + video to hackathon.admin@factored.ai
