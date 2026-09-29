# Case file W4 — Credit product information and eligibility

> Self-contained document for the claude.ai Project (EDA of the synthetic LATAM Bank dataset, Factored AI & Data
> Hackathon 2026). Generated with `python -m eda.report` from `outputs/tables/`. Every figure carries a label
> (`[measured]` = comes from the dataset with the indicated query; `[assumption]`; `[projected]`) and its query file in
> `docs/eda/queries/`. General context: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definition and mapping rules
Credit product information and pre-eligibility (credit card, personal loan, mortgage) with an explicit rules policy; the challenge forbids the LLM from inventing rules or approving credit. At the contact level it is approximated by the `Comercial` reason (low confidence); it has no complaints or text of its own.

Rules that feed this workflow (`queries/03_workflow_mapping.csv` v1; coverage `03_coverage_by_rule.csv`)
`[measured]`:

| Rule | Source | Condition | Confidence | n | Coverage |
|---|---|---|---|---|---|
| INT-03 | interactions | `reason_category = 'Comercial'` | low | 54,879 | 8.0% of interactions |
| TRX-08 | transactions | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | low | 348,631 | 7.9% of transactions |
| PRD-03 | products | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | high | 31,870 | 8.0% of products |
| DEV-03 | digital_events | `page_url = '/products/loans'` | high | 1,199,796 | 7.7% of digital_events |

Workflow coverage and % AMBIGUOUS/OTHER by source (`03_coverage_summary.csv`) `[measured]`:

| Source | % W4_credit | % AMBIGUOUS | % OTHER |
|---|---|---|---|
| interactions | 8.0 | 22.0 | 18.0 |
| transcripts | 0.0 | 0.0 | 0.0 |
| complaints | 0.0 | 0.0 | 61.5 |
| transactions | 7.9 | 0.0 | 2.0 |
| products | 8.0 | 0.0 | 2.0 |
| digital_events | 7.7 | 5.0 | 55.3 |

Reliability: the transcript template is independent of the reason (kappa 0.0003) and of the customer's products;
transcript coverage has no bias by workflow (p = 0.84). Details in `workflow_mapping.md` §5.

## 2. Demand
Contact population: Comercial contacts (INT-03, low confidence).

- Volume: **1,524 contacts/month** (full months Jul 2023 – May 2026) `[measured]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Monthly series: mean=1523.7; sd=61.1; cv=0.0401; min=1361; max=1623 `[measured]` (`04_workflow_demand.csv`). No material trend or seasonality in the
  bank total (+0.31%/year, CI95 [−0.65, 1.27]; month-of-year index 0.975–1.028), weekends at half volume and
  a flat 24 h hourly profile (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimension | Mix (% of population) |
|---|---|
| channel | Phone 84.8%; Email 4.0%; App 3.8%; Web Chat 3.5%; WhatsApp 3.4%; Web 0.5% |
| interaction_type | Inbound Call 69.9%; Outbound Call 15.0%; Chat 10.2%; Email 4.0%; Video 1.0% |
| country | México 50.4%; Colombia 30.1%; Argentina 19.6% |
| segment | Basic 60.0%; Plus 25.1%; Premium 9.9%; Student 5.0% |

Trigger events assigned to this workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[measured]`:

| Rule | Condition | Confidence | Monthly mean | Monthly CV |
|---|---|---|---|---|
| TRX-08 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | low | 9,670.5 | 0.035 |

Credit portfolio at cutoff (`04_products_by_status.csv`, single snapshot):

| Type | Status | n | with days_past_due > 0 | with known days_past_due |
|---|---|---|---|---|
| Préstamo Hipotecario | Active | 10,157 | 1,445 | 9,663 |
| Préstamo Hipotecario | Blocked | 612 | 112 | 577 |
| Préstamo Hipotecario | Closed | 912 | 130 | 868 |
| Préstamo Hipotecario | Suspended | 229 | 36 | 216 |
| Préstamo Personal | Active | 16,977 | 2,405 | 16,147 |
| Préstamo Personal | Blocked | 1,010 | 132 | 957 |
| Préstamo Personal | Closed | 1,585 | 234 | 1,517 |
| Préstamo Personal | Suspended | 388 | 69 | 372 |
| Tarjeta Crédito | Active | 85,090 | 12,039 | 80,786 |
| Tarjeta Crédito | Blocked | 4,932 | 718 | 4,689 |
| Tarjeta Crédito | Closed | 8,053 | 1,150 | 7,639 |
| Tarjeta Crédito | Suspended | 2,027 | 295 | 1,919 |

## 3. Outcomes
Each metric with its own n and denominator; Wilson CI95 (proportions) or bootstrap with 500 replicates, seed 42
(medians, p95, means). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, module `eda/outcomes.py`.
"Bank total" = same metric over all contacts or complaints. "Discriminates?" = W1–W4 CIs separated and
difference ≥ 2 pp or ≥ 10% relative (`04_ci_overlap.csv`).

| Metric | Value | CI95 | n | Denominator | Bank total | Discriminates? | Label |
|---|---|---|---|---|---|---|---|
| Monthly contact volume | 1,523.7 | [1,503.40, 1,543.90] | 35 | interactions with reason_category = Comercial (INT-03); full months Jul 2023 – May 2026 | 19,032.60 | yes | measured |
| FCR (%) | 65.2 | [64.81, 65.61] | 54,879 | interactions with reason_category = Comercial (INT-03) with non-null was_resolved | 76.65 | yes | measured |
| % escalated | 9.8 | [9.59, 10.09] | 54,879 | interactions with reason_category = Comercial (INT-03) with non-null was_escalated | 9.96 | no | measured |
| % requires follow-up | 44.5 | [44.13, 44.96] | 54,879 | interactions with reason_category = Comercial (INT-03) with non-null requires_followup | 34.83 | yes | measured |
| % negative sentiment (derived) | 34.9 | [34.47, 35.27] | 54,879 | interactions with reason_category = Comercial (INT-03) with non-null detected_sentiment (derived label) | 19.24 | yes | measured |
| Duration p50 (min) | 9.00 | [8.98, 9.08] | 47,082 | interactions with reason_category = Comercial (INT-03) with duration | 4.85 | yes | measured |
| Duration p95 (min) | 13.47 | [13.42, 13.58] | 47,082 | interactions with reason_category = Comercial (INT-03) with duration | 10.23 | yes | measured |
| Wait p50 (min) | 2.00 | [1.97, 2.00] | 38,338 | interactions with reason_category = Comercial (INT-03), Inbound Call only (the only type with wait) | 1.98 | no | measured |
| Wait p95 (min) | 3.63 | [3.62, 3.68] | 38,338 | interactions with reason_category = Comercial (INT-03), Inbound Call only (the only type with wait) | 3.63 | no | measured |
| CSAT top = 4 (%) | 9.7 | [9.17, 10.32] | 10,243 | CSAT surveys of interactions with reason_category = Comercial (INT-03); top = 4 (observed maximum) | 11.32 | yes | measured |
| CSAT mean (1–4) | 2.66 | [2.65, 2.67] | 10,243 | CSAT surveys of interactions with reason_category = Comercial (INT-03) (observed scale 1–4) | 2.77 | yes | measured |
| NPS | -78.4 | [-79.47, -77.22] | 5,144 | NPS surveys of interactions with reason_category = Comercial (INT-03); no promoters observed, NPS = −% detractors | -74.51 | yes | measured |
| CES mean (1–4) | 2.67 | [2.63, 2.70] | 1,760 | CES surveys of interactions with reason_category = Comercial (INT-03) (observed scale 1–4) | 2.77 | yes | measured |
| Re-contact 7 days (%) | 2.9 | [2.75, 3.03] | 54,464 | interactions with reason_category = Comercial (INT-03) with 7 full days of follow-up (before 2026-06-10) | 2.88 | no | measured |
| Re-contact 30 days (%) | 11.7 | [11.44, 11.99] | 53,325 | interactions with reason_category = Comercial (INT-03) with 30 full days of follow-up (before 2026-05-18) | 11.79 | no | measured |
| Monthly complaint volume | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 1,863.90 | yes | empty |
| % SLA breached | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 20.11 | no | empty |
| Resolution days p50 | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 16.00 | no | empty |
| Resolution days p95 | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 29.00 | no | empty |
| % resolved/closed | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 24.03 | no | empty |

Cross-cutting reading (`04_discrimination_tests.csv`) `[measured]`: contact outcomes depend **only on the reason**
(FCR Cramér's V 0.43, duration ε² 0.48); channel, country, segment, accent and agent do not move them (V ≤ 0.008).
Escalation, wait, re-contact and all complaint metrics are flat across all cuts.

## 4. Labels, quality, leakage, baseline and split
Learnable-signal check (`05_learnable_signal.csv`, module `eda/labels.py`, datasets `05_ds_*.sql`) `[measured]`.
Baseline = majority class (AUC 0.5). AUC with Hanley-McNeil CI95; AP vs prevalence; F1 vs "all positive".

| Label | Model | AUC [CI95] | AP (prevalence) | F1 (all positive) | Test prevalence % | Verdict |
|---|---|---|---|---|---|---|
| products.past_due_credit | majority_baseline | 0.5 [0.5, 0.5] | 0.1502 (0.1502) | 0.0 (all+ 0.2612) | 15.022 | reference |
| products.past_due_credit | logistic_regression | 0.4961 [0.4881, 0.5042] | 0.1491 (0.1502) | 0.2606 (all+ 0.2612) | 15.022 | noise |
| products.past_due_credit | tree_depth4 | 0.4966 [0.4885, 0.5047] | 0.1494 (0.1502) | 0.2583 (all+ 0.2612) | 15.022 | noise |
| interactions.not_resolved | majority_baseline | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (all+ 0.3786) | 23.353 | reference |
| interactions.not_resolved | logistic_regression | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | tree_depth4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | logistic_regression_reason_only | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.was_escalated | majority_baseline | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (all+ 0.1819) | 10.002 | reference |
| interactions.was_escalated | logistic_regression | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | tree_depth4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | logistic_regression_reason_only | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |

- **Suggested baseline**: Synthetic, versioned rules policy (the challenge requires it). There is no risk estimate to demonstrate: delinquency (`days_past_due` > 0) cannot be predicted with the available features (AUC 0.497). The learned component, if any, is not in risk.
- **Split**: By product opening date (test from 2024-01-01); single snapshot of customers and products.

Fields at risk of leakage in this workflow's tables (`05_leakage_fields.csv`):

| Table | Field | Why | Risk |
|---|---|---|---|
| customers | segment / credit_score / customer_status / estimated_monthly_income | Single snapshot at cutoff: final state, not the state at the time of the event | high (W4) / medium |
| products | product_status / days_past_due / current_balance / credit_limit | Single snapshot at cutoff; product_status and days_past_due are labels | high (W2, W4) |

## 5. Cost proxies and business case inputs
Formula shared by the 4 workflows: savings = contacts/month × % automatable (bound) × (human cost − AI cost).
What is measured is volume and handling time; the % automatable is a definition (assumption) and the unit
costs are assumptions with an external source (`06_business_case_inputs.csv`, module `eda/cost.py`).

- Mean AHT: **9.00 min** (duration known for 85.8% of contacts);
  13,711 handling minutes/month; mean wait (Inbound Call only)
  2.00 min; 84.8% by phone `[measured]`.
- Safe-automatable bound: **49.4%** (resolved, not escalated, no follow-up and no
  complaint from the customer within 30 days) `[assumption based on measured rates]`.

| Input | Scenario | Value | Label | Source |
|---|---|---|---|---|
| contacts per month | — | 1,524 | measured | 06_cost_base.sql (eda/cost.py); population: Comercial contacts (INT-03, low confidence) |
| mean AHT (min) | — | 9.0 | measured | 06_cost_base.sql (eda/cost.py); non-null duration_seconds (85.784%) |
| handling minutes per month | — | 13,711 | measured | 06_cost_base.sql (eda/cost.py); mean duration × contacts (imputes the 14.2% without duration) |
| % safely automatable (upper bound) | — | 49.4 | assumption | 06_cost_base.sql (eda/cost.py); definition: resolved + not escalated + no follow-up + no complaint within 30 days (the rate is measured; that this is automatable is an assumption) |
| agent cost per minute (USD) | conservative | 0.167 | assumption | [1] |
| cost per human contact (USD) | conservative | 1.50 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | conservative | 1.84 | assumption | [2] |
| monthly savings (USD) | conservative | -256 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | conservative | -3,070 | projected | 12 × monthly savings |
| agent cost per minute (USD) | base | 0.250 | assumption | [1] |
| cost per human contact (USD) | base | 2.25 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | base | 1.84 | assumption | [2] |
| monthly savings (USD) | base | 308 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | base | 3,697 | projected | 12 × monthly savings |
| agent cost per minute (USD) | optimistic | 0.333 | assumption | [1] |
| cost per human contact (USD) | optimistic | 3.00 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | optimistic | 0.50 | assumption | [2] |
| monthly savings (USD) | optimistic | 1,880 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | optimistic | 22,556 | projected | 12 × monthly savings |
| cost per human contact (USD) | global_reference | 13.50 | assumption | [2] global assisted cost |
| cost per AI contact (USD) | global_reference | 1.84 | assumption | [2] |
| monthly savings (USD) | global_reference | 8,768 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | global_reference | 105,217 | projected | 12 × monthly savings |

Sources for the assumptions:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (Jul 29, 2026): LATAM contact center USD 10–20 per agent hour (base = midpoint); cost per minute = rate/60, no occupancy adjustment. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, 'Cost per contact' glossary (2026): self-service USD 1.84 median (Gartner), assisted USD 13.50 (Gartner, global), chatbot/AI ~USD 0.50. Secondary source: verify in Phase B3 of the strategic analysis. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Workflow-specific gaps
- No history of `credit_score`, income or delinquency: the single snapshot at cutoff makes it impossible to know the state at the time of an application (direct leakage if used as a feature or label).
- `credit_score` 15.0% null and `estimated_monthly_income` 20.0% null (random): the flow must handle missing data and route to human review.
- No credit applications, approvals or rejections: there is no eligibility outcome.
- No credit policy: every rule will be synthetic and must be labeled as such.
- `Comercial` contacts include savings and investment; there is no product per interaction.

## 7. Possible explorations
| Exploration | Estimated effort |
|---|---|
| Design the synthetic pre-eligibility policy and measure how many customers fall into 'approvable', 'rejectable' and 'review due to missing data'. | half a day |
| Distribution of `credit_limit` and `interest_rate` by segment and country as input for informational answers. | 2 hours |
| Edge test cases (null score, null income, delinquency) to demonstrate abstention and handoff. | half a day |

## 8. Text template catalog
Distinct templates assigned to this workflow, deduplicated, without identifiers (no `customer_id`,
`interaction_id`, names, ID documents, emails or phone numbers), with their frequency (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[measured]`. The dataset is 100% synthetic and the text is templated; its use outside
the repo is subject to Slack question 4 (`04_brechas_y_preguntas.md`).

No text templates are assigned to this workflow: neither transcripts nor complaints fall into it.

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
