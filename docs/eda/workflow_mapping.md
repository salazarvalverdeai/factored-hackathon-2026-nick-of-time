# Workflow mapping — rules, coverage and reliability

> Self-contained document for the claude.ai Project. Generated with `python -m eda.report mapping` from
> `outputs/tables/03_*.csv` (module `python -m eda.workflows`). Rules versioned in
> `docs/eda/queries/03_workflow_mapping.csv` (version **v1**). All figures are `[measured]` unless
> stated otherwise. Mapping done by Claude using its own judgment (plan decision 11); pending Freddy's review.

## 1. Why a mapping is needed and what limits it
No field in the dataset says "workflow". The challenge proposes 4 example workflows (W1 accounts/payments, W2 cards,
W3 disputes, W4 credit/eligibility) and the EDA must compare them with the same yardstick. What limits the mapping
(see `data_quality.md`):
- `contact_reason` is identical to `reason_category`: **only 6 reasons** for all contacts.
- `detected_intents` has **a single value** (`consulta_general`); `main_topics` copies `reason_category`.
- The product of an interaction cannot be known: `mentioned_products` is 99.35% orphaned.
- Complaints do not link to the interaction (`origin_interaction_id` 100% null) and their `affected_product_id` belongs to
  another customer in 100% of cases.
- The transcript text is **2 balance-inquiry templates** (credit card / savings account) with
  filler phrases, **independent of the reason and of the customer's products** (§5).

That is why the mapping is done **per source**, each with its own rule and its own denominator, and each rule carries a
confidence: **high** (the field's semantics match unambiguously), **medium** (matches in most
cases, with a plausible alternative workflow), **low** (assignment by convenience, with several alternatives).

## 2. Coverage by source
**Strict** coverage = % assigned to W1–W4 by high- or medium-confidence rules. **Broad** = also includes the
low-confidence ones. Source: `03_coverage_summary.csv` (`queries/03_apply_mapping.sql` over `03_mapping_sources.sql`).

| Source | n | % W1 | % W2 | % W3 | % W4 | % OTHER | % AMBIGUOUS | % 4W strict | % 4W broad |
|---|---|---|---|---|---|---|---|---|---|
| call_center_interactions (contacts) | 686,296 | 35.0 | 0.0 | 17.1 | 8.0 | 18.0 | 22.0 | 35.0 | 60.0 |
| call_transcripts (call text) | 171,321 | 49.9 | 50.1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| complaints (cases) | 67,095 | 2.0 | 0.0 | 36.4 | 0.0 | 61.5 | 0.0 | 36.4 | 38.5 |
| transactions (trigger events) | 4,425,008 | 54.5 | 34.6 | 1.1 | 7.9 | 2.0 | 0.0 | 6.7 | 98.0 |
| products (portfolio, single snapshot) | 400,000 | 55.0 | 35.0 | 0.0 | 8.0 | 2.0 | 0.0 | 98.0 | 98.0 |
| digital_events (browsing) | 15,620,994 | 24.3 | 7.7 | 0.0 | 7.7 | 55.3 | 5.0 | 39.7 | 39.7 |

Reading:
- **Contacts (interactions)**: only W1 has a medium-confidence rule (`Transaccional`, 35.0%).
  W3 (`Queja`) and W4 (`Comercial`) come in with low confidence; **W2 has no rule at the contact level**.
  22.0% remains AMBIGUOUS (`Producto`) and 18.0% OTHER (`Técnico`, `Retención`). Strict coverage
  of the 4 workflows: **35.0%**; broad: 60.0%.
- **Transcripts**: 100% assigned (W1 / W2 ≈ 50/50), but the assignment comes from a template that is unrelated to
  anything else (§5). Not usable for sizing.
- **Complaints**: W3 36.4% (unrecognized charges and wrongful charges), W1 2.0% (low),
  OTHER 61.5% (app, branch, service). **W2 and W4 have no assignable complaints.**
- **Transactions**: the strict coverage (6.7%) is the contact **trigger events**:
  fraud and reversals (W3), card declines (W2), rejected or pending payments (W1). The rest is
  normal activity (low confidence). Transactions are consistent with their product (phase 1, C12).
- **Products** and **digital_events** describe the portfolio and browsing: useful for context and for an
  agent's tools, not for counting contacts.

## 3. Per-workflow populations used by phases 4–6
Decision made: each scorecard metric is computed over its source's population, with its own n. The
populations can overlap (a `Transaccional` interaction with a card transcript counts in W1 and in W2).

| Workflow | Contacts (interactions) | Text (transcripts) | Cases (complaints) | Trigger events (transactions / products) |
|---|---|---|---|---|
| W1_accounts_payments | INT-01 `Transaccional` (medium) | TRS-01 (high) | CMP-04 (low) | TRX-04, TRX-05 (medium) |
| W2_cards | — (no rule) | TRS-02 (medium) | — | TRX-03 card decline (high); PRD-01 blocked card (high) |
| W3_disputes | INT-02 `Queja` (low) | — | CMP-01 (high), CMP-02, CMP-03 (medium) | TRX-01 fraud (high); TRX-02 reversal (medium) |
| W4_credit | INT-03 `Comercial` (low) | — | — | PRD-03 loan portfolio (high); TRX-08 (low) |

## 4. Rule table (v1)
Order: within each source, the first rule (by priority) that matches wins. n and % over the source total
(`03_coverage_by_rule.csv`).

| Rule | Source | Prio. | Condition | Workflow | Confidence | n | % | Rationale |
|---|---|---|---|---|---|---|---|---|
| INT-01 | interactions | 1 | `reason_category = 'Transaccional'` | W1_accounts_payments | medium | 240,056 | 35.0 | Inquiries about account activity, payments and transfers: core of W1. Medium because it can include card activity (W2) or charges to dispute (W3) and no field tells them apart |
| INT-02 | interactions | 2 | `reason_category = 'Queja'` | W3_disputes | low | 117,021 | 17.1 | A banking complaint usually leads to a claim or dispute. Low: it can be a service or branch complaint and complaints is not linked to the interaction (origin_interaction_id 100% null) |
| INT-03 | interactions | 3 | `reason_category = 'Comercial'` | W4_credit | low | 54,879 | 8.0 | Commercial contacts = product offers and eligibility; in retail banking cards and loans dominate. Low: it also includes savings and investment and there is no reliable product per interaction |
| INT-04 | interactions | 4 | `reason_category = 'Técnico'` | OTHER | medium | 102,899 | 15.0 | Technical support (app/digital channels) is not one of the 4 workflows. Medium: a technical failure can be card-related (W2) |
| INT-05 | interactions | 5 | `reason_category = 'Retención'` | OTHER | high | 20,578 | 3.0 | Retention/cancellation is not one of the 4 workflows |
| INT-06 | interactions | 6 | `reason_category = 'Producto'` | AMBIGUOUS | low | 150,863 | 22.0 | Product inquiry: can be account (W1), card (W2) or credit (W4). mentioned_products is 99.35% orphans and cannot settle it |
| TRS-01 | transcripts | 1 | `customer_text LIKE '%cuenta de ahorros%'` | W1_accounts_payments | high | 85,411 | 49.9 | Template 'saldo actual en mi cuenta de ahorros' (current balance in my savings account): account balance inquiry. Caution: the template is independent of reason_category and of the customer's products |
| TRS-02 | transcripts | 2 | `customer_text LIKE '%tarjeta de crédito%'` | W2_cards | medium | 85,910 | 50.1 | Template 'saldo de mi tarjeta de crédito' (my credit card balance) + reply with the available limit: card servicing. Medium: a balance inquiry also fits W1. Same independence caveat |
| TRS-03 | transcripts | 3 | `TRUE` | AMBIGUOUS | low | 0 | 0.0 | Text with no recognized template (does not occur in v1) |
| CMP-01 | complaints | 1 | `category = 'Transactions' AND case_type = 'Claim'` | W3_disputes | high | 3,335 | 5.0 | Formal claim about 'Cargo no reconocido' (unrecognized charge): dispute intake. Note: case_type is independent of category in the data (the confidence reflects semantics not evidence) |
| CMP-02 | complaints | 2 | `category = 'Transactions' AND case_type IN ('Complaint', 'Request')` | W3_disputes | medium | 9,568 | 14.3 | Complaint or request about 'Cargo no reconocido': a dispute even if it is not typed as Claim |
| CMP-03 | complaints | 3 | `category = 'Fees' AND case_type IN ('Claim', 'Complaint')` | W3_disputes | medium | 11,528 | 17.2 | Claim or complaint about 'Cobro indebido' (wrongful charge): fee/charge dispute |
| CMP-04 | complaints | 4 | `category = 'Fees' AND case_type = 'Request'` | W1_accounts_payments | low | 1,367 | 2.0 | Request about fees: an account inquiry more than a dispute |
| CMP-05 | complaints | 5 | `category IN ('Technical', 'Branch', 'Service')` | OTHER | high | 39,962 | 59.6 | 'Problema con app', 'Atención en sucursal' and 'Calidad de servicio' (app problem, branch service, service quality) are not among the 4 workflows |
| CMP-06 | complaints | 6 | `case_type = 'Suggestion'` | OTHER | medium | 1,335 | 2.0 | Suggestions about transactions or fees: not dispute intake |
| CMP-07 | complaints | 7 | `TRUE` | AMBIGUOUS | low | 0 | 0.0 | Everything else (does not occur in v1) |
| TRX-01 | transactions | 1 | `is_fraud` | W3_disputes | high | 4,316 | 0.1 | Transaction flagged as fraud: triggers a customer claim/dispute |
| TRX-02 | transactions | 2 | `transaction_status = 'Reversed'` | W3_disputes | medium | 44,714 | 1.0 | Reversal: typical outcome of a dispute or chargeback. Medium: there are also operational reversals |
| TRX-03 | transactions | 3 | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_cards | high | 77,641 | 1.8 | Card decline with an ISO 8583 response_code: classic card support trigger |
| TRX-04 | transactions | 4 | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_accounts_payments | medium | 121,242 | 2.7 | Payment or transfer rejected from an account: payments inquiry |
| TRX-05 | transactions | 5 | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_accounts_payments | medium | 48,599 | 1.1 | Pending payment or transfer: payments inquiry |
| TRX-06 | transactions | 6 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_cards | low | 1,452,465 | 32.8 | Normal card activity: W2 context not a contact event |
| TRX-07 | transactions | 7 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_accounts_payments | low | 2,240,623 | 50.6 | Normal account activity: W1 context not a contact event |
| TRX-08 | transactions | 8 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | W4_credit | low | 348,631 | 7.9 | Loan payments and adjustments: credit servicing (not eligibility) |
| TRX-09 | transactions | 9 | `TRUE` | OTHER | medium | 86,777 | 2.0 | Inversión and Seguro (investment and insurance): outside the 4 workflows |
| PRD-01 | products | 1 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND product_status = 'Blocked'` | W2_cards | high | 7,044 | 1.8 | Blocked card: card support trigger (status at the cutoff: single snapshot) |
| PRD-02 | products | 2 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_cards | high | 132,996 | 33.2 | Card portfolio |
| PRD-03 | products | 3 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | W4_credit | high | 31,870 | 8.0 | Loan portfolio |
| PRD-04 | products | 4 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_accounts_payments | high | 220,182 | 55.0 | Account portfolio |
| PRD-05 | products | 5 | `TRUE` | OTHER | high | 7,908 | 2.0 | Inversión and Seguro (investment and insurance) |
| DEV-01 | digital_events | 1 | `page_url IN ('/payments', '/transfer', '/accounts', '/transactions')` | W1_accounts_payments | high | 3,797,081 | 24.3 | Payments, transfers, accounts and transactions pages |
| DEV-02 | digital_events | 2 | `page_url = '/products/credit-card'` | W2_cards | medium | 1,198,674 | 7.7 | Credit card page. Medium: it can be a card application (W4) |
| DEV-03 | digital_events | 3 | `page_url = '/products/loans'` | W4_credit | high | 1,199,796 | 7.7 | Loans page |
| DEV-04 | digital_events | 4 | `page_url IN ('/login', '/logout', '/home', '/help', '/products', '/products/savings')` | OTHER | medium | 8,645,049 | 55.3 | General navigation, authentication, help and savings |
| DEV-05 | digital_events | 5 | `TRUE` | AMBIGUOUS | low | 780,394 | 5.0 | Event without page_url |

## 5. Reliability: reason vs text and coverage bias
**Reason vs transcript template** (replaces the reason vs `detected_intents` agreement, since that field has a single value).
Source: `03_reason_vs_text_agreement.csv` (`queries/03_reason_vs_text.sql`).

| Workflow by reason | Workflow by text | n | % of transcripts |
|---|---|---|---|
| AMBIGUOUS | W1_accounts_payments | 18,973 | 11.1 |
| AMBIGUOUS | W2_cards | 18,685 | 10.9 |
| OTHER | W1_accounts_payments | 15,347 | 9.0 |
| OTHER | W2_cards | 15,524 | 9.1 |
| W1_accounts_payments | W1_accounts_payments | 29,850 | 17.4 |
| W1_accounts_payments | W2_cards | 29,936 | 17.5 |
| W3_disputes | W1_accounts_payments | 14,476 | 8.4 |
| W3_disputes | W2_cards | 14,722 | 8.6 |
| W4_credit | W1_accounts_payments | 6,765 | 3.9 |
| W4_credit | W2_cards | 7,043 | 4.1 |

- Raw agreement: 17.4%; **Cohen's kappa = 0.0003** (≈ 0: agreement is at chance level).
- Reason × template: χ² = 10.19, p = 0.07,
  **Cramér's V = 0.00771**. The template (card balance vs account balance) is
  split ~50/50 within each reason, including `Queja` and `Técnico`.
- The template is not related to the customer's products either: 48.8–48.9% of customers with either of the two
  templates have a credit card, the same as all customers (48.8%) `[measured]`
  (validation query in `queries/03_template_vs_ownership.sql`).
- Conclusion: **neither the reason nor the text is a reliable intent label**, and there is no second source to
  validate them. An intent classifier trained on this text would learn a template, not an intent.

**`has_transcript` and survey bias by workflow** (plan decision 3). Source:
`03_transcript_bias_by_workflow.csv` (`queries/03_transcript_bias.sql`).

| Rule | Workflow | n | % with transcript | % with survey |
|---|---|---|---|---|
| INT-01 | W1_accounts_payments | 240,056 | 24.9 | 31.0 |
| INT-02 | W3_disputes | 117,021 | 25.0 | 31.1 |
| INT-03 | W4_credit | 54,879 | 25.2 | 31.2 |
| INT-04 | OTHER | 102,899 | 25.0 | 30.9 |
| INT-05 | OTHER | 20,578 | 25.2 | 30.9 |
| INT-06 | AMBIGUOUS | 150,863 | 25.0 | 30.9 |

- χ² (transcript × rule) p = 0.839, Cramér's V = 0.00174: **no bias**. Whatever comes out of
  transcripts or surveys is representative of the workflow in terms of coverage (not in terms of content).

## 6. What ended up in OTHER and AMBIGUOUS
- **AMBIGUOUS in contacts** (22.0%): `Producto`. It could be split among W1, W2 and W4 if the
  interaction's product existed; it does not.
- **OTHER in contacts** (18.0%): `Técnico` (app and channel support, 15.0%) and `Retención` (3.0%).
  `Técnico` is the strongest candidate for a "fifth workflow" (digital support), outside the challenge's 4.
- **OTHER in complaints** (61.5%): `Problema con app`, `Atención en sucursal`, `Calidad de servicio` and
  suggestions.
- **AMBIGUOUS in digital_events** (5.0%): events without `page_url`.

## 7. Text template catalog
The full catalog (deduplicated, with frequency and workflow, no identifiers) is in
`outputs/tables/03_template_catalog.csv` and is split across section 8 of each dossier. Distinct templates:
`call_transcripts.agent_text` = 42, `call_transcripts.customer_text` = 42, `complaints.description` = 5, `complaints.resolution` = 5, `satisfaction_surveys.open_comments` = 13. Subject to Slack question 4.

## 8. How to change the mapping
Edit `docs/eda/queries/03_workflow_mapping.csv` (bump `version`), run `python -m eda.workflows` and
`python -m eda.report`. Phases 4–6 use the same rules via `eda.workflows.case_expr()`.
