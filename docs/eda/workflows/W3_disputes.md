# Case file W3 — Transaction dispute intake

> Self-contained document for the claude.ai Project (EDA of the synthetic LATAM Bank dataset, Factored AI & Data
> Hackathon 2026). Generated with `python -m eda.report` from `outputs/tables/`. Every figure carries a label
> (`[measured]` = comes from the dataset with the indicated query; `[assumption]`; `[projected]`) and its query file in
> `docs/eda/queries/`. General context: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definition and mapping rules
Intake of complaints about unrecognized charges, wrongful charges and fraud: identify the transaction, verify, decide whether to automate (block, provisional credit, case) or escalate. It has the best case source ('Cargo no reconocido' and 'Cobro indebido' complaints, high/medium confidence) and the dataset's only near-deterministic signal (`fraud_score`). At the contact level it is approximated by the `Queja` reason (low confidence).

Rules that feed this workflow (`queries/03_workflow_mapping.csv` v1; coverage `03_coverage_by_rule.csv`)
`[measured]`:

| Rule | Source | Condition | Confidence | n | Coverage |
|---|---|---|---|---|---|
| INT-02 | interactions | `reason_category = 'Queja'` | low | 117,021 | 17.1% of interactions |
| CMP-01 | complaints | `category = 'Transactions' AND case_type = 'Claim'` | high | 3,335 | 5.0% of complaints |
| CMP-02 | complaints | `category = 'Transactions' AND case_type IN ('Complaint', 'Request')` | medium | 9,568 | 14.3% of complaints |
| CMP-03 | complaints | `category = 'Fees' AND case_type IN ('Claim', 'Complaint')` | medium | 11,528 | 17.2% of complaints |
| TRX-01 | transactions | `is_fraud` | high | 4,316 | 0.1% of transactions |
| TRX-02 | transactions | `transaction_status = 'Reversed'` | medium | 44,714 | 1.0% of transactions |

Workflow coverage and % AMBIGUOUS/OTHER by source (`03_coverage_summary.csv`) `[measured]`:

| Source | % W3_disputes | % AMBIGUOUS | % OTHER |
|---|---|---|---|
| interactions | 17.1 | 22.0 | 18.0 |
| transcripts | 0.0 | 0.0 | 0.0 |
| complaints | 36.4 | 0.0 | 61.5 |
| transactions | 1.1 | 0.0 | 2.0 |
| products | 0.0 | 0.0 | 2.0 |
| digital_events | 0.0 | 5.0 | 55.3 |

Reliability: the transcript template is independent of the reason (kappa 0.0003) and of the customer's products;
transcript coverage has no bias by workflow (p = 0.84). Details in `workflow_mapping.md` §5.

## 2. Demand
Contact population: Queja contacts (INT-02, low confidence).

- Volume: **3,241 contacts/month** (full months Jul 2023 – May 2026) `[measured]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Monthly series: mean=3241.3; sd=122.3; cv=0.0377; min=2918; max=3437 `[measured]` (`04_workflow_demand.csv`). No material trend or seasonality in the
  bank total (+0.31%/year, CI95 [−0.65, 1.27]; month-of-year index 0.975–1.028), weekends at half volume and
  a flat 24 h hourly profile (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimension | Mix (% of population) |
|---|---|
| channel | Phone 85.1%; Email 4.0%; App 3.8%; Web Chat 3.4%; WhatsApp 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.3%; Outbound Call 14.8%; Chat 10.0%; Email 4.0%; Video 1.0% |
| country | México 49.9%; Colombia 30.1%; Argentina 20.0% |
| segment | Basic 60.0%; Plus 25.1%; Premium 10.0%; Student 4.9% |

Trigger events assigned to this workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[measured]`:

| Rule | Condition | Confidence | Monthly mean | Monthly CV |
|---|---|---|---|---|
| TRX-01 | `is_fraud` | high | 119.8 | 0.1088 |
| TRX-02 | `transaction_status = 'Reversed'` | medium | 1,241.2 | 0.0478 |

## 3. Outcomes
Each metric with its own n and denominator; Wilson CI95 (proportions) or bootstrap with 500 replicates, seed 42
(medians, p95, means). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, module `eda/outcomes.py`.
"Bank total" = same metric over all contacts or complaints. "Discriminates?" = W1–W4 CIs separated and
difference ≥ 2 pp or ≥ 10% relative (`04_ci_overlap.csv`).

| Metric | Value | CI95 | n | Denominator | Bank total | Discriminates? | Label |
|---|---|---|---|---|---|---|---|
| Monthly contact volume | 3,241.3 | [3,200.70, 3,281.80] | 35 | interactions with reason_category = Queja (INT-02); full months Jul 2023 – May 2026 | 19,032.60 | yes | measured |
| FCR (%) | 43.6 | [43.32, 43.88] | 117,021 | interactions with reason_category = Queja (INT-02) with non-null was_resolved | 76.65 | yes | measured |
| % escalated | 10.0 | [9.86, 10.20] | 117,021 | interactions with reason_category = Queja (INT-02) with non-null was_escalated | 9.96 | no | measured |
| % requires follow-up | 63.0 | [62.69, 63.24] | 117,021 | interactions with reason_category = Queja (INT-02) with non-null requires_followup | 34.83 | yes | measured |
| % negative sentiment (derived) | 34.9 | [34.61, 35.16] | 117,021 | interactions with reason_category = Queja (INT-02) with non-null detected_sentiment (derived label) | 19.24 | yes | measured |
| Duration p50 (min) | 7.18 | [7.15, 7.23] | 100,727 | interactions with reason_category = Queja (INT-02) with duration | 4.85 | yes | measured |
| Duration p95 (min) | 11.05 | [11.02, 11.15] | 100,727 | interactions with reason_category = Queja (INT-02) with duration | 10.23 | yes | measured |
| Wait p50 (min) | 2.00 | [1.98, 2.02] | 82,261 | interactions with reason_category = Queja (INT-02), Inbound Call only (the only type with wait) | 1.98 | no | measured |
| Wait p95 (min) | 3.65 | [3.63, 3.68] | 82,261 | interactions with reason_category = Queja (INT-02), Inbound Call only (the only type with wait) | 3.63 | no | measured |
| CSAT top = 4 (%) | 6.4 | [6.05, 6.70] | 21,843 | CSAT surveys of interactions with reason_category = Queja (INT-02); top = 4 (observed maximum) | 11.32 | yes | measured |
| CSAT mean (1–4) | 2.43 | [2.43, 2.45] | 21,843 | CSAT surveys of interactions with reason_category = Queja (INT-02) (observed scale 1–4) | 2.77 | yes | measured |
| NPS | -85.3 | [-85.97, -84.64] | 10,821 | NPS surveys of interactions with reason_category = Queja (INT-02); no promoters observed, NPS = −% detractors | -74.51 | yes | measured |
| CES mean (1–4) | 2.44 | [2.41, 2.46] | 3,693 | CES surveys of interactions with reason_category = Queja (INT-02) (observed scale 1–4) | 2.77 | yes | measured |
| Re-contact 7 days (%) | 2.9 | [2.79, 2.98] | 116,055 | interactions with reason_category = Queja (INT-02) with 7 full days of follow-up (before 2026-06-10) | 2.88 | no | measured |
| Re-contact 30 days (%) | 11.6 | [11.45, 11.82] | 113,616 | interactions with reason_category = Queja (INT-02) with 30 full days of follow-up (before 2026-05-18) | 11.79 | no | measured |
| Monthly complaint volume | 678.9 | [669.60, 688.20] | 35 | unrecognized-charge and wrongful-charge complaints (CMP-01..03); full months Jul 2023 – May 2026 | 1,863.90 | yes | measured |
| % SLA breached | 20.0 | [19.48, 20.48] | 24,431 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with non-null sla_breached | 20.11 | no | measured |
| Resolution days p50 | 16.0 | [15.00, 16.00] | 5,622 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with resolution_days (resolved/closed) | 16.00 | no | measured |
| Resolution days p95 | 29.0 | [29.00, 29.00] | 5,622 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with resolution_days (resolved/closed) | 29.00 | no | measured |
| % resolved/closed | 24.2 | [23.63, 24.70] | 24,431 | unrecognized-charge and wrongful-charge complaints (CMP-01..03); status Resolved or Closed | 24.03 | no | measured |
| % repeat complainer | 15.0 | [14.59, 15.49] | 24,431 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with non-null is_repeat_complainer | 15.03 | no | measured |
| % with compensation | 29.5 | [28.38, 30.70] | 5,903 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) resolved/closed; with compensation_granted | 28.79 | no | measured |
| Compensation / claimed (p50) | 0.10 | [0.09, 0.11] | 610 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with compensation and claimed amount (same row, same currency) | 0.10 | not assessable (fewer than 2 workflows with data) | measured |
| Resolution satisfaction (mean) | 3.02 | [2.93, 3.12] | 880 | unrecognized-charge and wrongful-charge complaints (CMP-01..03) with resolution_satisfaction (96% null) | 3.02 | no | measured |

Cross-cutting reading (`04_discrimination_tests.csv`) `[measured]`: contact outcomes depend **only on the reason**
(FCR Cramér's V 0.43, duration ε² 0.48); channel, country, segment, accent and agent do not move them (V ≤ 0.008).
Escalation, wait, re-contact and all complaint metrics are flat across all cuts.

## 4. Labels, quality, leakage, baseline and split
Learnable-signal check (`05_learnable_signal.csv`, module `eda/labels.py`, datasets `05_ds_*.sql`) `[measured]`.
Baseline = majority class (AUC 0.5). AUC with Hanley-McNeil CI95; AP vs prevalence; F1 vs "all positive".

| Label | Model | AUC [CI95] | AP (prevalence) | F1 (all positive) | Test prevalence % | Verdict |
|---|---|---|---|---|---|---|
| transactions.is_fraud | majority_baseline | 0.5 [0.5, 0.5] | 0.0009 (0.0009) | 0.0 (all+ 0.0018) | 0.088 | reference |
| transactions.is_fraud | logistic_regression | 0.507 [0.4762, 0.5377] | 0.0009 (0.0009) | 0.0018 (all+ 0.0018) | 0.088 | noise |
| transactions.is_fraud | tree_depth4 | 0.5078 [0.477, 0.5385] | 0.0009 (0.0009) | 0.0016 (all+ 0.0018) | 0.088 | noise |
| transactions.is_fraud | existing_score_fraud_score | 0.7521 [0.7221, 0.7821] | 0.5217 (0.0009) | 0.0837 (all+ 0.0018) | 0.088 | signal |
| transactions.is_fraud | logistic_regression_features_plus_fraud_score | 0.7918 [0.7632, 0.8204] | 0.5007 (0.0009) | 0.0802 (all+ 0.0018) | 0.088 | signal |
| transactions.reversed | majority_baseline | 0.5 [0.5, 0.5] | 0.0099 (0.0099) | 0.0 (all+ 0.0196) | 0.988 | reference |
| transactions.reversed | logistic_regression | 0.4977 [0.4885, 0.5068] | 0.0099 (0.0099) | 0.0193 (all+ 0.0196) | 0.988 | noise |
| transactions.reversed | tree_depth4 | 0.4975 [0.4883, 0.5066] | 0.0099 (0.0099) | 0.0093 (all+ 0.0196) | 0.988 | noise |
| transactions.reversed | existing_score_fraud_score | 0.5033 [0.4941, 0.5125] | 0.0099 (0.0099) | 0.0196 (all+ 0.0196) | 0.988 | noise |
| transactions.reversed | logistic_regression_features_plus_fraud_score | 0.4945 [0.4854, 0.5037] | 0.0097 (0.0099) | 0.0194 (all+ 0.0196) | 0.988 | noise |
| complaints.sla_breached | majority_baseline | 0.5 [0.5, 0.5] | 0.1992 (0.1992) | 0.0 (all+ 0.3322) | 19.918 | reference |
| complaints.sla_breached | logistic_regression | 0.5004 [0.4908, 0.5101] | 0.2006 (0.1992) | 0.3321 (all+ 0.3322) | 19.918 | noise |
| complaints.sla_breached | tree_depth4 | 0.4924 [0.4828, 0.5019] | 0.1966 (0.1992) | 0.3306 (all+ 0.3322) | 19.918 | noise |
| interactions.not_resolved | majority_baseline | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (all+ 0.3786) | 23.353 | reference |
| interactions.not_resolved | logistic_regression | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | tree_depth4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | logistic_regression_reason_only | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.requires_followup | majority_baseline | 0.5 [0.5, 0.5] | 0.348 (0.348) | 0.0 (all+ 0.5163) | 34.801 | reference |
| interactions.requires_followup | logistic_regression | 0.6763 [0.6739, 0.6787] | 0.524 (0.348) | 0.5617 (all+ 0.5163) | 34.801 | signal |
| interactions.requires_followup | tree_depth4 | 0.6759 [0.6734, 0.6783] | 0.5089 (0.348) | 0.5618 (all+ 0.5163) | 34.801 | signal |
| interactions.requires_followup | logistic_regression_reason_only | 0.6763 [0.6739, 0.6788] | 0.5059 (0.348) | 0.5618 (all+ 0.5163) | 34.801 | signal |

- **Suggested baseline**: `fraud_score` threshold: ≥ 50 flags fraud with 100% precision (48.8% recall); 30–50 is a gray zone (79.6% precision at ≥ 30). Possible learned component: calibrating the triage (automate / confirm / escalate) against held-out `is_fraud`; the features + score model (AUC 0.79) does not significantly improve on the score alone (0.75).
- **Split**: Temporal (transactions and complaints from 2025-07-01) + grouping by `customer_id`.

Fields at risk of leakage in this workflow's tables (`05_leakage_fields.csv`):

| Table | Field | Why | Risk |
|---|---|---|---|
| complaints | status / resolution / resolution_date / resolution_days / closing_date | Set after the case is closed | high |
| complaints | compensation_granted / resolution_satisfaction | Set after closure | high |
| complaints | assignment_date / first_response_date / assigned_agent_id | Set after creation | medium |
| transactions | response_code | Authorization outcome (explains the decline) | high |
| transactions | transaction_status | Outcome; Declined/Reversed are labels | high |
| transactions | fraud_score | Another model's score; valid at authorization time but not a feature of our own | medium |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Single snapshot at cutoff: final state, not the state at the time of the event | high (W4) / medium |

## 5. Cost proxies and business case inputs
Formula shared by the 4 workflows: savings = contacts/month × % automatable (bound) × (human cost − AI cost).
What is measured is volume and handling time; the % automatable is a definition (assumption) and the unit
costs are assumptions with an external source (`06_business_case_inputs.csv`, module `eda/cost.py`).

- Mean AHT: **7.24 min** (duration known for 86.1% of contacts);
  23,477 handling minutes/month; mean wait (Inbound Call only)
  2.00 min; 85.1% by phone `[measured]`.
- Safe-automatable bound: **32.8%** (resolved, not escalated, no follow-up and no
  complaint from the customer within 30 days) `[assumption based on measured rates]`.

| Input | Scenario | Value | Label | Source |
|---|---|---|---|---|
| contacts per month | — | 3,241 | measured | 06_cost_base.sql (eda/cost.py); population: Queja contacts (INT-02, low confidence) |
| mean AHT (min) | — | 7.2 | measured | 06_cost_base.sql (eda/cost.py); non-null duration_seconds (86.086%) |
| handling minutes per month | — | 23,477 | measured | 06_cost_base.sql (eda/cost.py); mean duration × contacts (imputes the 13.9% without duration) |
| % safely automatable (upper bound) | — | 32.8 | assumption | 06_cost_base.sql (eda/cost.py); definition: resolved + not escalated + no follow-up + no complaint within 30 days (the rate is measured; that this is automatable is an assumption) |
| agent cost per minute (USD) | conservative | 0.167 | assumption | [1] |
| cost per human contact (USD) | conservative | 1.21 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | conservative | 1.84 | assumption | [2] |
| monthly savings (USD) | conservative | -673 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | conservative | -8,079 | projected | 12 × monthly savings |
| agent cost per minute (USD) | base | 0.250 | assumption | [1] |
| cost per human contact (USD) | base | 1.81 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | base | 1.84 | assumption | [2] |
| monthly savings (USD) | base | -31 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | base | -373 | projected | 12 × monthly savings |
| agent cost per minute (USD) | optimistic | 0.333 | assumption | [1] |
| cost per human contact (USD) | optimistic | 2.41 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | optimistic | 0.50 | assumption | [2] |
| monthly savings (USD) | optimistic | 2,037 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | optimistic | 24,440 | projected | 12 × monthly savings |
| cost per human contact (USD) | global_reference | 13.50 | assumption | [2] global assisted cost |
| cost per AI contact (USD) | global_reference | 1.84 | assumption | [2] |
| monthly savings (USD) | global_reference | 12,405 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | global_reference | 148,855 | projected | 12 × monthly savings |

Sources for the assumptions:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (Jul 29, 2026): LATAM contact center USD 10–20 per agent hour (base = midpoint); cost per minute = rate/60, no occupancy adjustment. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, 'Cost per contact' glossary (2026): self-service USD 1.84 median (Gartner), assisted USD 13.50 (Gartner, global), chatbot/AI ~USD 0.50. Secondary source: verify in Phase B3 of the strategic analysis. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Workflow-specific gaps
- Complaints do not link to the interaction (`origin_interaction_id` 100% null) or to a product of the customer (`affected_product_id` belongs to another customer in 100% of rows): the disputed transaction has to be found in the customer's own `transactions`.
- `description` is 5 templates ('Queja relacionada con transactions/fees/...'): there is no customer narrative.
- `sla_breached` is ~20% across all cuts and does not depend on resolution time: it is useless as a metric or as a label.
- Complaints `currency` is independent of the customer's country and `claimed_amount` is not comparable across cases; compensation is ~10% of the claimed amount in every case (generator rule).
- 20.6% of frauds have no `fraud_score`: those cases cannot be triaged with the rule.
- No regulatory framework for dispute deadlines by country (it defines the real SLA): it comes from the external analysis.

## 7. Possible explorations
| Exploration | Estimated effort |
|---|---|
| Link each W3 complaint to reversed or fraudulent transactions of the same customer within ±30 days (how many cases would have an identifiable transaction). | half a day |
| `fraud_score` precision/recall curve by country, channel and product type (triage fairness). | 2–3 hours |
| Design and evaluation of the 3-zone triage policy with error costs (false positive = unnecessary block; false negative = unhandled fraud). | 1 day |

## 8. Text template catalog
Distinct templates assigned to this workflow, deduplicated, without identifiers (no `customer_id`,
`interaction_id`, names, ID documents, emails or phone numbers), with their frequency (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[measured]`. The dataset is 100% synthetic and the text is templated; its use outside
the repo is subject to Slack question 4 (`04_brechas_y_preguntas.md`).

| Field | Template | n | % of field | Distribution by workflow |
|---|---|---|---|---|
| complaints.description | Queja relacionada con transactions | 13,580 | 20.2 | W3_disputes=95.0%; OTHER=5.0% |
| complaints.description | Queja relacionada con fees | 13,553 | 20.2 | W3_disputes=85.1%; W1_accounts_payments=10.1%; OTHER=4.9% |

Survey comments (shared across all workflows; `satisfaction_surveys.open_comments`):

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
