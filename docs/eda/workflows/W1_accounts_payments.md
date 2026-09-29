# Case file W1 — Account and payment inquiries

> Self-contained document for the claude.ai Project (EDA of the synthetic LATAM Bank dataset, Factored AI & Data
> Hackathon 2026). Generated with `python -m eda.report` from `outputs/tables/`. Every figure carries a label
> (`[measured]` = comes from the dataset with the indicated query; `[assumption]`; `[projected]`) and its query file in
> `docs/eda/queries/`. General context: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definition and mapping rules
Inquiries about account balances, activity, payments and transfers (savings and checking), including declined or pending payments and currency conversion. It is the workflow with the most reliable contact rule in the dataset (`Transaccional`, medium confidence).

Rules that feed this workflow (`queries/03_workflow_mapping.csv` v1; coverage `03_coverage_by_rule.csv`)
`[measured]`:

| Rule | Source | Condition | Confidence | n | Coverage |
|---|---|---|---|---|---|
| INT-01 | interactions | `reason_category = 'Transaccional'` | medium | 240,056 | 35.0% of interactions |
| TRS-01 | transcripts | `customer_text LIKE '%cuenta de ahorros%'` | high | 85,411 | 49.9% of transcripts |
| CMP-04 | complaints | `category = 'Fees' AND case_type = 'Request'` | low | 1,367 | 2.0% of complaints |
| TRX-04 | transactions | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | medium | 121,242 | 2.7% of transactions |
| TRX-05 | transactions | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | medium | 48,599 | 1.1% of transactions |
| TRX-07 | transactions | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | low | 2,240,623 | 50.6% of transactions |
| PRD-04 | products | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | high | 220,182 | 55.0% of products |
| DEV-01 | digital_events | `page_url IN ('/payments', '/transfer', '/accounts', '/transactions')` | high | 3,797,081 | 24.3% of digital_events |

Workflow coverage and % AMBIGUOUS/OTHER by source (`03_coverage_summary.csv`) `[measured]`:

| Source | % W1_accounts_payments | % AMBIGUOUS | % OTHER |
|---|---|---|---|
| interactions | 35.0 | 22.0 | 18.0 |
| transcripts | 49.9 | 0.0 | 0.0 |
| complaints | 2.0 | 0.0 | 61.5 |
| transactions | 54.5 | 0.0 | 2.0 |
| products | 55.0 | 0.0 | 2.0 |
| digital_events | 24.3 | 5.0 | 55.3 |

Reliability: the transcript template is independent of the contact reason (kappa 0.0003) and of the customer's products;
transcript coverage has no bias by workflow (p = 0.84). Details in `workflow_mapping.md` §5.

## 2. Demand
Contact population: Transaccional contacts (INT-01, medium confidence).

- Volume: **6,661 contacts/month** (full months Jul 2023 – May 2026) `[measured]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Monthly series: mean=6660.9; sd=257.0; cv=0.0386; min=6040; max=7172 `[measured]` (`04_workflow_demand.csv`). No material trend or seasonality in the
  bank total (+0.31%/year, CI95 [−0.65, 1.27]; month-of-year index 0.975–1.028), weekends at half volume and a
  flat 24 h hourly profile (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimension | Mix (% of population) |
|---|---|
| channel | Phone 85.0%; Email 4.0%; App 3.9%; Web Chat 3.3%; WhatsApp 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.0%; Outbound Call 15.0%; Chat 10.0%; Email 4.0%; Video 1.0% |
| country | México 49.9%; Colombia 30.2%; Argentina 19.9% |
| segment | Basic 59.8%; Plus 25.1%; Premium 10.1%; Student 4.9% |

Trigger events assigned to this workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[measured]`:

| Rule | Condition | Confidence | Monthly mean | Monthly CV |
|---|---|---|---|---|
| TRX-04 | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | medium | 3,364.6 | 0.0316 |
| TRX-05 | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | medium | 1,348.1 | 0.0407 |
| TRX-07 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | low | 62,166.2 | 0.0348 |

## 3. Outcomes
Each metric with its own n and denominator; Wilson CI95 (proportions) or bootstrap with 500 replicates, seed 42
(medians, p95, means). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, module `eda/outcomes.py`.
"Bank total" = same metric over all contacts or complaints. "Discriminates?" = W1–W4 CIs are separated and the
difference is ≥ 2 pp or ≥ 10% relative (`04_ci_overlap.csv`).

| Metric | Value | CI95 | n | Denominator | Bank total | Discriminates? | Label |
|---|---|---|---|---|---|---|---|
| Monthly contact volume | 6,660.9 | [6,575.70, 6,746.00] | 35 | interactions with reason_category = Transaccional (INT-01); full months Jul 2023 – May 2026 | 19,032.60 | yes | measured |
| FCR (%) | 91.5 | [91.40, 91.62] | 240,056 | interactions with reason_category = Transaccional (INT-01) with non-null was_resolved | 76.65 | yes | measured |
| % escalated | 9.9 | [9.81, 10.05] | 240,056 | interactions with reason_category = Transaccional (INT-01) with non-null was_escalated | 9.96 | no | measured |
| % requires follow-up | 22.1 | [21.97, 22.30] | 240,056 | interactions with reason_category = Transaccional (INT-01) with non-null requires_followup | 34.83 | yes | measured |
| % negative sentiment (derived) | 0.0 | [-0.00, 0.00] | 240,056 | interactions with reason_category = Transaccional (INT-01) with non-null detected_sentiment (derived label) | 19.24 | yes | measured |
| Duration p50 (min) | 3.42 | [3.38, 3.42] | 206,465 | interactions with reason_category = Transaccional (INT-01) with duration | 4.85 | yes | measured |
| Duration p95 (min) | 6.80 | [6.65, 6.92] | 206,465 | interactions with reason_category = Transaccional (INT-01) with duration | 10.23 | yes | measured |
| Wait p50 (min) | 1.98 | [1.97, 2.00] | 168,074 | interactions with reason_category = Transaccional (INT-01), Inbound Call only (the only type with wait) | 1.98 | no | measured |
| Wait p95 (min) | 3.62 | [3.58, 3.63] | 168,074 | interactions with reason_category = Transaccional (INT-01), Inbound Call only (the only type with wait) | 3.63 | no | measured |
| CSAT top = 4 (%) | 13.5 | [13.16, 13.79] | 44,837 | CSAT surveys of interactions with reason_category = Transaccional (INT-01); top = 4 (observed maximum) | 11.32 | yes | measured |
| CSAT mean (1–4) | 2.91 | [2.90, 2.92] | 44,837 | CSAT surveys of interactions with reason_category = Transaccional (INT-01) (observed scale 1–4) | 2.77 | yes | measured |
| NPS | -69.9 | [-70.47, -69.26] | 22,341 | NPS surveys of interactions with reason_category = Transaccional (INT-01); no promoters observed, NPS = −% detractors | -74.51 | yes | measured |
| CES mean (1–4) | 2.91 | [2.90, 2.93] | 7,354 | CES surveys of interactions with reason_category = Transaccional (INT-01) (observed scale 1–4) | 2.77 | yes | measured |
| 7-day re-contact (%) | 2.9 | [2.81, 2.95] | 238,253 | interactions with reason_category = Transaccional (INT-01) with 7 full days of follow-up (before 2026-06-10) | 2.88 | no | measured |
| 30-day re-contact (%) | 11.9 | [11.73, 11.99] | 233,193 | interactions with reason_category = Transaccional (INT-01) with 30 full days of follow-up (before 2026-05-18) | 11.79 | no | measured |
| Monthly complaint volume | 37.7 | [35.40, 39.90] | 35 | complaints Fees + Request (CMP-04); full months Jul 2023 – May 2026 | 1,863.90 | yes | measured |
| % SLA breached | 20.4 | [18.36, 22.63] | 1,367 | complaints Fees + Request (CMP-04) with non-null sla_breached | 20.11 | no | measured |
| Resolution days p50 | 15.0 | [13.00, 15.00] | 342 | complaints Fees + Request (CMP-04) with resolution_days (resolved/closed) | 16.00 | no | measured |
| Resolution days p95 | 28.0 | [27.95, 29.00] | 342 | complaints Fees + Request (CMP-04) with resolution_days (resolved/closed) | 29.00 | no | measured |
| % resolved/closed | 25.7 | [23.43, 28.06] | 1,367 | complaints Fees + Request (CMP-04); status Resolved or Closed | 24.03 | no | measured |
| % repeat complainer | 13.9 | [12.17, 15.83] | 1,367 | complaints Fees + Request (CMP-04) with non-null is_repeat_complainer | 15.03 | no | measured |
| % with compensation | 29.6 | [25.09, 34.61] | 351 | complaints Fees + Request (CMP-04) resolved/closed; with compensation_granted | 28.79 | no | measured |
| Compensation / claimed (p50) | n/a | — | 0 | complaints Fees + Request (CMP-04) with compensation and claimed amount (same row, same currency) | 0.10 | not assessable (fewer than 2 workflows with data) | measured |
| Resolution satisfaction (mean) | 3.22 | [2.88, 3.60] | 63 | complaints Fees + Request (CMP-04) with resolution_satisfaction (96% null) | 3.02 | no | measured |

Cross-cutting reading (`04_discrimination_tests.csv`) `[measured]`: contact outcomes depend **only on the contact reason**
(FCR Cramér's V 0.43, duration ε² 0.48); channel, country, segment, accent and agent do not move them (V ≤ 0.008).
Escalation, wait, re-contact and all complaint metrics are flat across all cuts.

## 4. Labels, quality, leakage, baseline and split
Learnable-signal check (`05_learnable_signal.csv`, module `eda/labels.py`, datasets `05_ds_*.sql`) `[measured]`.
Baseline = majority class (AUC 0.5). AUC with Hanley-McNeil CI95; AP vs prevalence; F1 vs "all positive".

| Label | Model | AUC [CI95] | AP (prevalence) | F1 (all positive) | Test prevalence % | Verdict |
|---|---|---|---|---|---|---|
| interactions.not_resolved | majority_baseline | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (all+ 0.3786) | 23.353 | reference |
| interactions.not_resolved | logistic_regression | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | tree_depth4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | logistic_regression_reason_only | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.requires_followup | majority_baseline | 0.5 [0.5, 0.5] | 0.348 (0.348) | 0.0 (all+ 0.5163) | 34.801 | reference |
| interactions.requires_followup | logistic_regression | 0.6763 [0.6739, 0.6787] | 0.524 (0.348) | 0.5617 (all+ 0.5163) | 34.801 | signal |
| interactions.requires_followup | tree_depth4 | 0.6759 [0.6734, 0.6783] | 0.5089 (0.348) | 0.5618 (all+ 0.5163) | 34.801 | signal |
| interactions.requires_followup | logistic_regression_reason_only | 0.6763 [0.6739, 0.6788] | 0.5059 (0.348) | 0.5618 (all+ 0.5163) | 34.801 | signal |
| interactions.was_escalated | majority_baseline | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (all+ 0.1819) | 10.002 | reference |
| interactions.was_escalated | logistic_regression | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | tree_depth4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | logistic_regression_reason_only | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |
| transactions.declined | majority_baseline | 0.5 [0.5, 0.5] | 0.0504 (0.0504) | 0.0 (all+ 0.0961) | 5.045 | reference |
| transactions.declined | logistic_regression | 0.5028 [0.4986, 0.5069] | 0.0512 (0.0504) | 0.0959 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | tree_depth4 | 0.5029 [0.4987, 0.507] | 0.0508 (0.0504) | 0.0959 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | existing_score_fraud_score | 0.5011 [0.497, 0.5053] | 0.0506 (0.0504) | 0.096 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | logistic_regression_features_plus_fraud_score | 0.5033 [0.4991, 0.5074] | 0.0512 (0.0504) | 0.0952 (all+ 0.0961) | 5.045 | noise |

- **Suggested baseline**: Rule by `reason_category` for FCR/follow-up (the model does not beat it). For the agent: evaluation against deterministic ground truth (balance, account activity and payment status come from `transactions`/`products`, 100% consistent with the product owner).
- **Split**: Temporal (test from 2025-07-01) + grouping by `customer_id` (95.5% of test contacts come from customers seen in train).

Fields with leakage risk in this workflow's tables (`05_leakage_fields.csv`):

| Table | Field | Why | Risk |
|---|---|---|---|
| call_center_interactions | duration_seconds | Known only when the contact ends | high |
| call_center_interactions | detected_sentiment / sentiment_score | Derived from the full call | high |
| call_center_interactions | customer_detected_accent / agent_used_accent | Derived from the call audio | medium |
| call_center_interactions | has_transcript / has_recording | Decided after the contact | medium |
| call_center_interactions | reason_category | Assumed known at the start (IVR). If the agent records it at close, it is leakage | medium (assumption) |
| transactions | response_code | Authorization outcome (explains the decline) | high |
| transactions | transaction_status | Outcome; Declined/Reversed are labels | high |
| transactions | fraud_score | Score from another model; valid at authorization time but not a feature of our own | medium |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Single snapshot at cutoff: final state, not the state at the time of the event | high (W4) / medium |
| products | product_status / days_past_due / current_balance / credit_limit | Single snapshot at cutoff; product_status and days_past_due are labels | high (W2, W4) |
| service_agents | avg_csat / total_monthly_interactions | Aggregate outcomes, including future ones | high |

## 5. Cost proxies and business case inputs
Formula shared by the 4 workflows: savings = contacts/month × % automatable (bound) × (human cost − AI cost).
What is measured is volume and handling time; the % automatable is a definition (assumption) and the unit
costs are assumptions with an external source (`06_business_case_inputs.csv`, module `eda/cost.py`).

- Mean AHT: **3.68 min** (duration known for 86.0% of contacts);
  24,515 handling minutes/month; mean wait (Inbound Call only)
  1.99 min; 85.0% by phone `[measured]`.
- Safe-automatable bound: **69.3%** (resolved, not escalated, no follow-up and no
  complaint from the customer within 30 days) `[assumption over measured rates]`.

| Input | Scenario | Value | Label | Source |
|---|---|---|---|---|
| contacts per month | — | 6,661 | measured | 06_cost_base.sql (eda/cost.py); population: Transaccional contacts (INT-01, medium confidence) |
| mean AHT (min) | — | 3.7 | measured | 06_cost_base.sql (eda/cost.py); non-null duration_seconds (85.992%) |
| handling minutes per month | — | 24,515 | measured | 06_cost_base.sql (eda/cost.py); mean duration × contacts (imputes the 14.0% without duration) |
| % safe automatable (upper bound) | — | 69.3 | assumption | 06_cost_base.sql (eda/cost.py); definition: resolved + not escalated + no follow-up + no complaint within 30 days (the rate is measured; that this is automatable is an assumption) |
| agent cost per minute (USD) | conservative | 0.167 | assumption | [1] |
| cost per human contact (USD) | conservative | 0.61 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | conservative | 1.84 | assumption | [2] |
| monthly savings (USD) | conservative | -5,662 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | conservative | -67,941 | projected | 12 × monthly savings |
| agent cost per minute (USD) | base | 0.250 | assumption | [1] |
| cost per human contact (USD) | base | 0.92 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | base | 1.84 | assumption | [2] |
| monthly savings (USD) | base | -4,246 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | base | -50,952 | projected | 12 × monthly savings |
| agent cost per minute (USD) | optimistic | 0.333 | assumption | [1] |
| cost per human contact (USD) | optimistic | 1.23 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | optimistic | 0.50 | assumption | [2] |
| monthly savings (USD) | optimistic | 3,355 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | optimistic | 40,260 | projected | 12 × monthly savings |
| cost per human contact (USD) | global_reference | 13.50 | assumption | [2] global assisted cost |
| cost per AI contact (USD) | global_reference | 1.84 | assumption | [2] |
| monthly savings (USD) | global_reference | 53,821 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | global_reference | 645,853 | projected | 12 × monthly savings |

Sources for the assumptions:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (Jul 29, 2026): LATAM contact center USD 10–20 per agent hour (base = midpoint); cost per minute = rate/60, no occupancy adjustment. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, 'Cost per contact' glossary (2026): self-service USD 1.84 median (Gartner), assisted USD 13.50 (Gartner, global), chatbot/AI ~USD 0.50. Secondary source: verify in Phase B3 of the strategic analysis. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Workflow-specific gaps
- There is no real customer text: W1 transcripts are 21 variants of a single sentence ('saldo actual en mi cuenta de ahorros'), independent of the contact reason and of the customer's products.
- `products.current_balance` is a single snapshot at cutoff: it cannot answer the balance at a past date; the historical balance would have to be rebuilt from `transactions` (18.7% predate the product's opening: an inconsistency to handle).
- `amount_usd` is null in 100% of USD transactions, and México operates 100% in USD (no MXN): currency conversion in W1 only applies to COP and ARS.
- No fee or transfer-limit policies: a synthetic policy base has to be created.
- The `Transaccional` reason may include card activity or charges to dispute; no field tells them apart (medium confidence).

## 7. Possible explorations
| Exploration | Estimated effort |
|---|---|
| Rebuild the historical balance per product from `transactions` and measure the inconsistency with `current_balance` ('balance as of a date' tool). | half a day |
| Table of declined/pending payments by customer and month as a source of test cases (normal, ambiguous, requires a human). | 2–3 hours |
| Team-generated ES/PT evaluation set of balance/activity inquiries, with the expected answer computed from the dataset. | 1 day |

## 8. Text template catalog
Distinct templates assigned to this workflow, deduplicated, without identifiers (no `customer_id`,
`interaction_id`, names, ID documents, emails or phone numbers), with their frequency (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[measured]`. The dataset is 100% synthetic and the text is template-based; its use outside
the repo is subject to Slack question 4 (`04_brechas_y_preguntas.md`).

| Field | Template | n | % of field | Distribution by workflow |
|---|---|---|---|---|
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. | 51,189 | 29.9 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. | 4,282 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? | 4,278 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 4,276 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. | 4,274 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Claro, estoy para servirle. | 1,120 | 0.7 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? No hay problema, que tenga buen día. | 1,106 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Perfecto, ¿necesita algo más? | 1,103 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? No hay problema, que tenga buen día. | 1,103 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Claro, estoy para servirle. | 1,094 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,089 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. No hay problema, que tenga buen día. | 1,085 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Perfecto, ¿necesita algo más? | 1,084 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,079 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Claro, estoy para servirle. | 1,063 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Claro, estoy para servirle. | 1,053 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,047 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Perfecto, ¿necesita algo más? | 1,036 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,030 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. No hay problema, que tenga buen día. | 1,016 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Perfecto, ¿necesita algo más? | 1,004 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. | 51,189 | 29.9 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? | 4,365 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? | 4,315 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. | 4,258 | 2.5 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. | 4,172 | 2.4 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? ¿Y eso cuánto tiempo tarda? | 1,112 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Entiendo, muchas gracias. | 1,106 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Muy bien, ¿hay algo más que deba saber? | 1,105 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Entiendo, muchas gracias. | 1,084 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? ¿Y eso cuánto tiempo tarda? | 1,081 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Perfecto, eso es lo que necesitaba. | 1,080 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Entiendo, muchas gracias. | 1,074 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Muy bien, ¿hay algo más que deba saber? | 1,071 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Muy bien, ¿hay algo más que deba saber? | 1,067 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Perfecto, eso es lo que necesitaba. | 1,062 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Muy bien, ¿hay algo más que deba saber? | 1,059 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. ¿Y eso cuánto tiempo tarda? | 1,059 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Perfecto, eso es lo que necesitaba. | 1,051 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Entiendo, muchas gracias. | 1,042 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. ¿Y eso cuánto tiempo tarda? | 1,031 | 0.6 | W1_accounts_payments=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Perfecto, eso es lo que necesitaba. | 1,028 | 0.6 | W1_accounts_payments=100.0% |

Survey comments (common to all workflows; `satisfaction_surveys.open_comments`):

| Comment | n | % of comments |
|---|---|---|
| Tardaron mucho en atenderme. | 13,620 | 13.5 |
| No resolvieron mi problema completamente. | 13,546 | 13.4 |
| Tuve que esperar demasiado tiempo. | 13,501 | 13.3 |
| No estoy satisfecho con la solución. | 13,472 | 13.3 |
| El agente no fue muy claro en sus explicaciones. | 13,338 | 13.2 |
| Normal, sin problemas mayores. | 8,975 | 8.9 |
| El servicio estuvo bien. | 8,964 | 8.9 |
| Aceptable. | 8,799 | 8.7 |
| Resolvieron mi problema rápidamente. | 1,442 | 1.4 |
| Muy satisfecho con el servicio. | 1,406 | 1.4 |
| Excelente atención, muy amable el agente. | 1,395 | 1.4 |
| El agente fue muy profesional y eficiente. | 1,394 | 1.4 |
| Buena experiencia, gracias. | 1,344 | 1.3 |
