# Case file W2 — Card support

> Self-contained document for the claude.ai Project (EDA of the synthetic LATAM Bank dataset, Factored AI & Data
> Hackathon 2026). Generated with `python -m eda.report` from `outputs/tables/`. Every figure carries a label
> (`[measured]` = comes from the dataset with the indicated query; `[assumption]`; `[projected]`) and its query file in
> `docs/eda/queries/`. General context: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definition and mapping rules
Inquiries and problems with credit and debit cards: declines, blocks, balance and available limit. **It has no contact-level rule**: its contact population comes from the transcript template 'saldo de mi tarjeta de crédito' (medium confidence, text independent of everything). Its real signals are events: declines with `response_code` and blocked cards.

Rules that feed this workflow (`queries/03_workflow_mapping.csv` v1; coverage `03_coverage_by_rule.csv`)
`[measured]`:

| Rule | Source | Condition | Confidence | n | Coverage |
|---|---|---|---|---|---|
| TRS-02 | transcripts | `customer_text LIKE '%tarjeta de crédito%'` | medium | 85,910 | 50.1% of transcripts |
| TRX-03 | transactions | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | high | 77,641 | 1.8% of transactions |
| TRX-06 | transactions | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | low | 1,452,465 | 32.8% of transactions |
| PRD-01 | products | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND product_status = 'Blocked'` | high | 7,044 | 1.8% of products |
| PRD-02 | products | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | high | 132,996 | 33.2% of products |
| DEV-02 | digital_events | `page_url = '/products/credit-card'` | medium | 1,198,674 | 7.7% of digital_events |

Workflow coverage and % AMBIGUOUS/OTHER by source (`03_coverage_summary.csv`) `[measured]`:

| Source | % W2_cards | % AMBIGUOUS | % OTHER |
|---|---|---|---|
| interactions | 0.0 | 22.0 | 18.0 |
| transcripts | 50.1 | 0.0 | 0.0 |
| complaints | 0.0 | 0.0 | 61.5 |
| transactions | 34.6 | 0.0 | 2.0 |
| products | 35.0 | 0.0 | 2.0 |
| digital_events | 7.7 | 5.0 | 55.3 |

Reliability: the transcript template is independent of the contact reason (kappa 0.0003) and of the customer's products;
transcript coverage has no bias by workflow (p = 0.84). Details in `workflow_mapping.md` §5.

## 2. Demand
Contact population: contacts with a card-balance transcript (TRS-02; unreliable text, only 25% have a transcript).

- Volume: **2,383 contacts/month** (full months Jul 2023 – May 2026) `[measured]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Monthly series: mean=2382.7; sd=96.4; cv=0.0405; min=2094; max=2631 `[measured]` (`04_workflow_demand.csv`). No material trend or seasonality in the
  bank total (+0.31%/year, CI95 [−0.65, 1.27]; month-of-year index 0.975–1.028), weekends at half volume and a
  flat 24 h hourly profile (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimension | Mix (% of population) |
|---|---|
| channel | Phone 84.9%; Email 4.2%; App 3.8%; WhatsApp 3.4%; Web Chat 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.1%; Outbound Call 14.8%; Chat 9.9%; Email 4.2%; Video 1.0% |
| country | México 50.0%; Colombia 30.0%; Argentina 20.0% |
| segment | Basic 59.8%; Plus 24.9%; Premium 10.1%; Student 5.1% |

Trigger events assigned to this workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[measured]`:

| Rule | Condition | Confidence | Monthly mean | Monthly CV |
|---|---|---|---|---|
| TRX-03 | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | high | 2,156.3 | 0.0397 |
| TRX-06 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | low | 40,304.3 | 0.0333 |

Card portfolio at cutoff (`04_products_by_status.csv`, single snapshot):

| Type | Status | n |
|---|---|---|
| Tarjeta Crédito | Active | 85,090 |
| Tarjeta Crédito | Blocked | 4,932 |
| Tarjeta Crédito | Closed | 8,053 |
| Tarjeta Crédito | Suspended | 2,027 |
| Tarjeta Débito | Active | 33,749 |
| Tarjeta Débito | Blocked | 2,112 |
| Tarjeta Débito | Closed | 3,244 |
| Tarjeta Débito | Suspended | 833 |

## 3. Outcomes
Each metric with its own n and denominator; Wilson CI95 (proportions) or bootstrap with 500 replicates, seed 42
(medians, p95, means). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, module `eda/outcomes.py`.
"Bank total" = same metric over all contacts or complaints. "Discriminates?" = W1–W4 CIs are separated and the
difference is ≥ 2 pp or ≥ 10% relative (`04_ci_overlap.csv`).

| Metric | Value | CI95 | n | Denominator | Bank total | Discriminates? | Label |
|---|---|---|---|---|---|---|---|
| Monthly contact volume | 2,382.7 | [2,350.80, 2,414.70] | 35 | interactions with a card-balance transcript (TRS-02); full months Jul 2023 – May 2026 | 19,032.60 | yes | measured |
| FCR (%) | 76.6 | [76.28, 76.85] | 85,910 | interactions with a card-balance transcript (TRS-02) with non-null was_resolved | 76.65 | yes | measured |
| % escalated | 9.9 | [9.75, 10.15] | 85,910 | interactions with a card-balance transcript (TRS-02) with non-null was_escalated | 9.96 | no | measured |
| % requires follow-up | 34.9 | [34.58, 35.22] | 85,910 | interactions with a card-balance transcript (TRS-02) with non-null requires_followup | 34.83 | yes | measured |
| % negative sentiment (derived) | 19.5 | [19.27, 19.80] | 85,910 | interactions with a card-balance transcript (TRS-02) with non-null detected_sentiment (derived label) | 19.24 | yes | measured |
| Duration p50 (min) | 4.85 | [4.80, 4.88] | 73,812 | interactions with a card-balance transcript (TRS-02) with duration | 4.85 | yes | measured |
| Duration p95 (min) | 10.27 | [10.20, 10.45] | 73,812 | interactions with a card-balance transcript (TRS-02) with duration | 10.23 | yes | measured |
| Wait p50 (min) | 1.98 | [1.97, 2.00] | 60,211 | interactions with a card-balance transcript (TRS-02), Inbound Call only (the only type with wait) | 1.98 | no | measured |
| Wait p95 (min) | 3.63 | [3.60, 3.66] | 60,211 | interactions with a card-balance transcript (TRS-02), Inbound Call only (the only type with wait) | 3.63 | no | measured |
| CSAT top = 4 (%) | 11.3 | [10.85, 11.83] | 16,173 | CSAT surveys of interactions with a card-balance transcript (TRS-02); top = 4 (observed maximum) | 11.32 | yes | measured |
| CSAT mean (1–4) | 2.77 | [2.76, 2.78] | 16,173 | CSAT surveys of interactions with a card-balance transcript (TRS-02) (observed scale 1–4) | 2.77 | yes | measured |
| NPS | -73.9 | [-74.81, -72.87] | 7,860 | NPS surveys of interactions with a card-balance transcript (TRS-02); no promoters observed, NPS = −% detractors | -74.51 | yes | measured |
| CES mean (1–4) | 2.75 | [2.72, 2.78] | 2,729 | CES surveys of interactions with a card-balance transcript (TRS-02) (observed scale 1–4) | 2.77 | yes | measured |
| 7-day re-contact (%) | 2.8 | [2.70, 2.92] | 85,222 | interactions with a card-balance transcript (TRS-02) with 7 full days of follow-up (before 2026-06-10) | 2.88 | no | measured |
| 30-day re-contact (%) | 11.7 | [11.49, 11.92] | 83,441 | interactions with a card-balance transcript (TRS-02) with 30 full days of follow-up (before 2026-05-18) | 11.79 | no | measured |
| Monthly complaint volume | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 1,863.90 | yes | empty |
| % SLA breached | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 20.11 | no | empty |
| Resolution days p50 | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 16.00 | no | empty |
| Resolution days p95 | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 29.00 | no | empty |
| % resolved/closed | n/a | — | 0 | no complaints assignable to this workflow (workflow_mapping.md §3) | 24.03 | no | empty |

Cross-cutting reading (`04_discrimination_tests.csv`) `[measured]`: contact outcomes depend **only on the contact reason**
(FCR Cramér's V 0.43, duration ε² 0.48); channel, country, segment, accent and agent do not move them (V ≤ 0.008).
Escalation, wait, re-contact and all complaint metrics are flat across all cuts.

## 4. Labels, quality, leakage, baseline and split
Learnable-signal check (`05_learnable_signal.csv`, module `eda/labels.py`, datasets `05_ds_*.sql`) `[measured]`.
Baseline = majority class (AUC 0.5). AUC with Hanley-McNeil CI95; AP vs prevalence; F1 vs "all positive".

| Label | Model | AUC [CI95] | AP (prevalence) | F1 (all positive) | Test prevalence % | Verdict |
|---|---|---|---|---|---|---|
| transactions.declined | majority_baseline | 0.5 [0.5, 0.5] | 0.0504 (0.0504) | 0.0 (all+ 0.0961) | 5.045 | reference |
| transactions.declined | logistic_regression | 0.5028 [0.4986, 0.5069] | 0.0512 (0.0504) | 0.0959 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | tree_depth4 | 0.5029 [0.4987, 0.507] | 0.0508 (0.0504) | 0.0959 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | existing_score_fraud_score | 0.5011 [0.497, 0.5053] | 0.0506 (0.0504) | 0.096 (all+ 0.0961) | 5.045 | noise |
| transactions.declined | logistic_regression_features_plus_fraud_score | 0.5033 [0.4991, 0.5074] | 0.0512 (0.0504) | 0.0952 (all+ 0.0961) | 5.045 | noise |
| products.blocked_card | majority_baseline | 0.5 [0.5, 0.5] | 0.05 (0.05) | 0.0 (all+ 0.0952) | 4.997 | reference |
| products.blocked_card | logistic_regression | 0.505 [0.4924, 0.5176] | 0.0505 (0.05) | 0.0921 (all+ 0.0952) | 4.997 | noise |
| products.blocked_card | tree_depth4 | 0.5052 [0.4926, 0.5178] | 0.051 (0.05) | 0.0843 (all+ 0.0952) | 4.997 | noise |
| interactions.not_resolved | majority_baseline | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (all+ 0.3786) | 23.353 | reference |
| interactions.not_resolved | logistic_regression | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | tree_depth4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.not_resolved | logistic_regression_reason_only | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (all+ 0.3786) | 23.353 | signal |
| interactions.was_escalated | majority_baseline | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (all+ 0.1819) | 10.002 | reference |
| interactions.was_escalated | logistic_regression | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | tree_depth4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |
| interactions.was_escalated | logistic_regression_reason_only | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (all+ 0.1819) | 10.002 | noise |

- **Suggested baseline**: Deterministic rules: `response_code` explains the decline (05 do not honor, 14 invalid card, 51 insufficient funds, 54 expired card) and `product_status` explains the block. There is no learnable label in the dataset; a learned component would have to be, for example, an intent classifier trained on a team-generated ES/PT set.
- **Split**: Temporal (transactions from 2025-07-01; cards by opening date from 2024-01-01) + grouping by `customer_id`.

Fields with leakage risk in this workflow's tables (`05_leakage_fields.csv`):

| Table | Field | Why | Risk |
|---|---|---|---|
| transactions | response_code | Authorization outcome (explains the decline) | high |
| transactions | transaction_status | Outcome; Declined/Reversed are labels | high |
| transactions | fraud_score | Score from another model; valid at authorization time but not a feature of our own | medium |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Single snapshot at cutoff: final state, not the state at the time of the event | high (W4) / medium |
| products | product_status / days_past_due / current_balance / credit_limit | Single snapshot at cutoff; product_status and days_past_due are labels | high (W2, W4) |

## 5. Cost proxies and business case inputs
Formula shared by the 4 workflows: savings = contacts/month × % automatable (bound) × (human cost − AI cost).
What is measured is volume and handling time; the % automatable is a definition (assumption) and the unit
costs are assumptions with an external source (`06_business_case_inputs.csv`, module `eda/cost.py`).

- Mean AHT: **5.37 min** (duration known for 85.9% of contacts);
  12,789 handling minutes/month; mean wait (Inbound Call only)
  2.00 min; 84.9% by phone `[measured]`.
- Safe-automatable bound: **57.8%** (resolved, not escalated, no follow-up and no
  complaint from the customer within 30 days) `[assumption over measured rates]`.

| Input | Scenario | Value | Label | Source |
|---|---|---|---|---|
| contacts per month | — | 2,383 | measured | 06_cost_base.sql (eda/cost.py); population: contacts with a card-balance transcript (TRS-02; unreliable text, only 25% have a transcript) |
| mean AHT (min) | — | 5.4 | measured | 06_cost_base.sql (eda/cost.py); non-null duration_seconds (85.933%) |
| handling minutes per month | — | 12,789 | measured | 06_cost_base.sql (eda/cost.py); mean duration × contacts (imputes the 14.1% without duration) |
| % safe automatable (upper bound) | — | 57.8 | assumption | 06_cost_base.sql (eda/cost.py); definition: resolved + not escalated + no follow-up + no complaint within 30 days (the rate is measured; that this is automatable is an assumption) |
| agent cost per minute (USD) | conservative | 0.167 | assumption | [1] |
| cost per human contact (USD) | conservative | 0.90 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | conservative | 1.84 | assumption | [2] |
| monthly savings (USD) | conservative | -1,303 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | conservative | -15,637 | projected | 12 × monthly savings |
| agent cost per minute (USD) | base | 0.250 | assumption | [1] |
| cost per human contact (USD) | base | 1.34 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | base | 1.84 | assumption | [2] |
| monthly savings (USD) | base | -687 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | base | -8,239 | projected | 12 × monthly savings |
| agent cost per minute (USD) | optimistic | 0.333 | assumption | [1] |
| cost per human contact (USD) | optimistic | 1.79 | projected | mean AHT [measured] × cost per minute [assumption] |
| cost per AI contact (USD) | optimistic | 0.50 | assumption | [2] |
| monthly savings (USD) | optimistic | 1,777 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | optimistic | 21,322 | projected | 12 × monthly savings |
| cost per human contact (USD) | global_reference | 13.50 | assumption | [2] global assisted cost |
| cost per AI contact (USD) | global_reference | 1.84 | assumption | [2] |
| monthly savings (USD) | global_reference | 16,071 | projected | contacts/month × % automatable (bound) × (human cost − AI cost); negative = AI costs more |
| annual savings (USD) | global_reference | 192,851 | projected | 12 × monthly savings |

Sources for the assumptions:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (Jul 29, 2026): LATAM contact center USD 10–20 per agent hour (base = midpoint); cost per minute = rate/60, no occupancy adjustment. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, 'Cost per contact' glossary (2026): self-service USD 1.84 median (Gartner), assisted USD 13.50 (Gartner, global), chatbot/AI ~USD 0.50. Secondary source: verify in Phase B3 of the strategic analysis. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Workflow-specific gaps
- No contact can be attributed to cards with confidence: `mentioned_products` is 99.35% orphan and the contact reason does not distinguish the product.
- `product_status = Blocked` is a single snapshot: we do not know when the card was blocked or whether the block came before or after a call.
- Transaction declines and card blocks are noise for the models (AUC ≈ 0.50): it is not possible to predict which card will have problems.
- No policies for card replacement, unblocking or limit increases.
- The 'app error → call' funnel does not exist in the data (errors in the prior 24 h: 0.154% vs 0.149% for the control group).

## 7. Possible explorations
| Exploration | Estimated effort |
|---|---|
| Map of `response_code` × card type × channel (POS/ATM/Web) as a catalog of explanations for the agent. | 2 hours |
| Sequences of repeated declines per card within 24 h (candidates for preventive blocking or escalation). | half a day |
| Team-generated ES/PT set of card intents (block, decline, limit, balance) for a classifier with a rules baseline. | 1 day |

## 8. Text template catalog
Distinct templates assigned to this workflow, deduplicated, without identifiers (no `customer_id`,
`interaction_id`, names, ID documents, emails or phone numbers), with their frequency (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[measured]`. The dataset is 100% synthetic and the text is template-based; its use outside
the repo is subject to Slack question 4 (`04_brechas_y_preguntas.md`).

| Field | Template | n | % of field | Distribution by workflow |
|---|---|---|---|---|
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. | 51,555 | 30.1 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. | 4,365 | 2.5 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 4,329 | 2.5 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. | 4,264 | 2.5 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? | 4,239 | 2.5 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. No hay problema, que tenga buen día. | 1,132 | 0.7 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,113 | 0.7 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. No hay problema, que tenga buen día. | 1,109 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Claro, estoy para servirle. | 1,105 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? No hay problema, que tenga buen día. | 1,088 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Perfecto, ¿necesita algo más? | 1,086 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Claro, estoy para servirle. | 1,075 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,075 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Claro, estoy para servirle. | 1,071 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? No hay problema, que tenga buen día. | 1,065 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,058 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,050 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Perfecto, ¿necesita algo más? | 1,049 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Perfecto, ¿necesita algo más? | 1,046 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Perfecto, ¿necesita algo más? | 1,039 | 0.6 | W2_cards=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Claro, estoy para servirle. | 997 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. | 51,555 | 30.1 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. | 4,393 | 2.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. | 4,328 | 2.5 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? | 4,269 | 2.5 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? | 4,207 | 2.5 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Entiendo, muchas gracias. | 1,130 | 0.7 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? ¿Y eso cuánto tiempo tarda? | 1,130 | 0.7 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Entiendo, muchas gracias. | 1,124 | 0.7 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. ¿Y eso cuánto tiempo tarda? | 1,120 | 0.7 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Perfecto, eso es lo que necesitaba. | 1,114 | 0.7 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? ¿Y eso cuánto tiempo tarda? | 1,089 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Muy bien, ¿hay algo más que deba saber? | 1,085 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Entiendo, muchas gracias. | 1,079 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. ¿Y eso cuánto tiempo tarda? | 1,075 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Perfecto, eso es lo que necesitaba. | 1,061 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Muy bien, ¿hay algo más que deba saber? | 1,058 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Perfecto, eso es lo que necesitaba. | 1,053 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Muy bien, ¿hay algo más que deba saber? | 1,037 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Perfecto, eso es lo que necesitaba. | 1,020 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Entiendo, muchas gracias. | 1,008 | 0.6 | W2_cards=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Muy bien, ¿hay algo más que deba saber? | 975 | 0.6 | W2_cards=100.0% |

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
