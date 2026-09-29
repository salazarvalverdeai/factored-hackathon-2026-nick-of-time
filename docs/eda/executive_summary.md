# Executive summary — LATAM Bank EDA

> One page to open in the claude.ai Project alongside the dossiers (`docs/eda/workflows/W*.md`). Synthetic
> dataset from Factored (MX, CO, AR; Jun 2023 – Jun 2026; 12 of 13 tables analyzed). Figures are `[measured]` unless
> stated otherwise; each has its query in `docs/eda/queries/` and its detail in `findings.md`. Sep 26, 2026.

## What the dataset has
- **Stable volume and solid joins**: 19,033 contacts/month, 1,864 complaints/month, 122,779 transactions/month, no
  trend or seasonality. interaction → transcript → survey and transaction → product are 100% consistent.
- **Contact outcomes that depend on the reason**: FCR from 43.6% (`Queja`) to 91.5% (`Transaccional`); p50 duration from
  3.4 to 9.0 min (`04_workflow_scorecard.csv`).
- **Deterministic signals for tools**: balances and transactions per customer, payment status, ISO 8583 `response_code` on
  declines, `product_status`, daily exchange rate consistent with `amount_usd` (p95 deviation 2%).
- **An almost deterministic fraud signal**: `fraud_score` ≥ 50 → 100% precision and 48.8% recall on `is_fraud`
  (`05_fraud_score_thresholds.csv`).
- **Real quality problems** that serve as data engineering evidence: FKs to other customers' products (100% in
  complaints), future dates (~4%), transactions before the product was opened (18.7%), shifted operating day,
  `México`/`Mexico` (`data_quality.md` §C).

## What it does not have
- **Granular reason, intents or real text**: 6 reasons; `detected_intents` = 1 value; transcripts = 2 balance-inquiry
  templates independent of the reason (kappa 0.0003); complaints with 5 template descriptions.
- **Key links**: complaint → interaction (100% null), product per interaction (99.35% orphaned).
- **Informative pain metrics for cases**: `sla_breached` ≈ 20% everywhere; escalation ≈ 10% everywhere; truncated
  surveys (CSAT/CES 1–4, NPS 2–7, no promoters).
- **Dimension history** (single snapshot), **Portuguese**, **policies**, **identity**, **bank costs**, and the
  duplicates/late arrivals/schema evolution that the dictionary announces.

## Where there is learnable signal (phase 5; temporal split, majority baseline, AUC with CI95)
| Label | Workflow | Result |
|---|---|---|
| Not resolved (1 − FCR) | W1 vs W3 | AUC 0.763 [0.760, 0.766], **100% explained by the reason** (the model is a 6-row table) |
| Requires follow-up | cross-cutting | AUC 0.676 [0.674, 0.679], 100% explained by the reason |
| Fraud via `fraud_score` | W3 | AUC 0.752 [0.722, 0.782], AP 0.52 vs prevalence 0.0009; features + score 0.792 (no significant improvement) |
| Escalated, SLA, declined, reversed, blocked card, delinquency | all | **noise** (AUC 0.497–0.508, CI includes 0.5) |

## Ranking by the alternative criterion (labels, feasibility, deterministic signals)
Contact pain discriminates only by reason and two workflows have no reliable contacts, so the ranking uses the
agreed criterion (`findings.md` §C):
1. **W3 disputes**: the only signal that defines when to act (`fraud_score`), worst pain (FCR 43.6%, NPS −85.3), its
   own cases (679/month). Low-confidence contact mapping.
2. **W1 accounts/payments**: the most feasible and best mapped (35.0% of contacts, medium confidence), rich
   deterministic signals; no pain (FCR 91.5%) and no learned component of its own.
3. **W2 cards**: good deterministic signals (2,156 declines/month with `response_code`), zero attributable
   contacts, labels = noise.
4. **W4 credit**: no signal (delinquency AUC 0.497), low-confidence mapping, stricter policy requirements.

## Candidate ideas
1. **W3 — Dispute intake with verifiable 3-zone triage** (recommended): `fraud_score` ≥ 50 → verified automatic
   action; 30–50 → confirm and route; < 30 or no score → structured handoff. Numbers: 679 cases/month;
   precision 100% / recall 48.8% at ≥ 50; `Queja` FCR 43.6% vs the bank's 76.6%.
2. **W1 — Account and payment inquiries verified against the ledger**: 6,661 contacts/month; FCR 91.5%, AHT 3.7 min,
   automatable upper bound 69.3%; 4,713 rejected or pending payments per month.
3. **W2 — Deterministic diagnosis of declines and blocks**: 2,156 card declines/month with an ISO code;
   7,044 blocked cards; learned component only with team-generated data.

For all three: escalation cannot be learned from the dataset (AUC 0.501), so the handoff policy goes in
rules, outside the model. **Business case**: with LATAM costs (USD 10–20/h) the savings per contact are marginal or
negative (W1 base: −51k USD/year `[projected]`); only with Gartner's global assisted cost (USD 13.50/contact) does it turn
positive (+646k). The strong argument is risk control, 24/7 availability and consistency, not cost (`06_business_case_inputs.csv`).

## Questions for Slack
1. Are `contact_reason` = `reason_category` and `detected_intents` with a single value intentional?
2. Are the null `origin_interaction_id` and the `affected_product_id` values belonging to other customers intentional (isolation test)?
3. What is the definition of `sla_breached`? What are the actual CSAT, NPS and CES scales?
4. Is sending (synthetic) dataset data to external LLM APIs allowed? (this determines the template catalog)
5. Is `fraud_score` an input available in real time or an evaluation variable?
6. Is `reason_category` captured at the start (IVR) or at close? (if at close, the FCR signal is leakage)
7. Should the announced duplicates, late arrivals and schema evolution be simulated, or is the dataset not the final version?
