# Data quality — LATAM Bank dataset

> Self-contained document for the claude.ai Project. Every figure carries a label (`[measured]` / `[assumption]` /
> `[projected]`) and the file that produces it. `[measured]` = comes from the dataset with the query shown.
> Sources: `python scripts/s3_inventory.py`, `python -m eda.inventory` (phase 0), `python -m eda.quality` (phase 1).
> Output tables in `outputs/tables/`, queries in `docs/eda/queries/`.
> Last updated: Sep 26, 2026 (phases 0, 1 and wrap-up in phase 7).

## Context
Synthetic dataset from a fictional bank (LATAM Bank) with customers from Mexico, Colombia and Argentina, 13 tables,
range 2023-06-17 → 2026-06-17. The official dictionary announces intentional quality problems: ~2% duplicates,
~5% nulls in optional fields, late arrivals, schema evolution and FK orphans. This document measures
which of them are really there and where.

## A. Inventory (phase 0)

### A1. Format, partitions and load
- **100% CSV**, UTF-8 with BOM, no Parquet or compressed files. 7,671 objects, 5.35 GB `[measured]`
  (`00_inventory_files.csv`, `queries/00_s3_partition_coverage.sql` block 1).
- **Facts** (transactions, interactions, transcripts, surveys, digital_events, complaints, campaign_sends):
  `data/<table>/year=YYYY/month=MM/day=DD/<table>_YYYYMMDD.csv`, one file per day, 1,097 days with no gaps
  `[measured]`. Exception: `campaign_sends` starts on 2023-07-01 (14 days without a partition; probably by design)
  (`00_s3_partition_coverage.sql` block 2).
- **Dimensions** (customers, products, branches, service_agents, marketing_campaigns, daily_exchange_rates): **a
  single flat CSV**. The dictionary talks about `monthly_snapshot` / `full_snapshot`, but there is no history: it is **a
  single snapshot at the cutoff** `[measured]`. Consequence: `segment`, `credit_score`, `customer_status`, `product_status`,
  `days_past_due`, `current_balance`, `credit_limit` reflect the final state, not the state at the time of each contact.
  **Leakage risk for W2 (cards) and W4 (credit)**, and a gap for any point-in-time analysis.
- **No `process_date` in the path**: the partition is `year/month/day`. `process_date` exists as a **column** inside
  the fact files `[measured]` (`00_column_types.csv`).
- **Single load**: all objects were uploaded on 2026-08-31 between 21:36 and 21:51 (Lima time) `[measured]`
  (`00_s3_partition_coverage.sql` block 1). There is no real incremental delivery: the "late arrivals" the
  dictionary announces are **simulated inside the files** (difference between `process_date`, event date and partition
  date), not in arrival times. Demonstrating update handling will require a labeled test fixture.
- **Weekly pattern** (proxy based on file size, before downloading): in interactions, Saturday and Sunday weigh
  ~75 KB vs ~148–150 KB Monday to Friday; month over month the size is stable (120–135 KB/day) `[measured]`
  (`00_s3_partition_coverage.sql` blocks 3 and 4). Confirmed with row counts in phase 1.

### A2. Counts vs dictionary
Source: `00_row_counts.csv` (`eda/inventory.py` + `queries/00_row_counts.sql`) `[measured]`.

| Table | Rows | Dictionary | Ratio | PK duplicates |
|---|---:|---:|---:|---:|
| customers | 150,000 | 150,000 | 1.000 | 0 |
| products | 400,000 | 400,000 | 1.000 | 0 |
| branches | 350 | 350 | 1.000 | 0 |
| service_agents | 1,200 | 1,200 | 1.000 | 0 |
| marketing_campaigns | 200 | 200 | 1.000 | 0 |
| transactions | 4,425,008 | 5,000,000 | 0.885 | 0 |
| call_center_interactions | 686,296 | 800,000 | 0.858 | 0 |
| call_transcripts | 171,321 | 200,000 | 0.857 | 0 |
| satisfaction_surveys | 212,759 | 250,000 | 0.851 | 0 |
| digital_events | 15,620,994 | 10,000,000 | 1.562 | 0 |
| complaints | 67,095 | 80,000 | 0.839 | 0 |
| daily_exchange_rates | 13,164 | 3,000 | 4.388 | 0 |
| campaign_sends | not synced | 2,000,000 | — | — |

- The dimensions match exactly. The customer-service fact tables have ~14–16% fewer rows than announced.
  Hypothesis `[assumption]`: the generator set the nominal total and then halved weekends
  (5 days × 1 + 2 days × 0.5 = 6/7 = 0.857). It matches interactions and transcripts very well; complaints
  (0.839) and transactions (0.885) less so. Verified in phase 1.
- `digital_events` has 56% more rows and `daily_exchange_rates` 4.4 times the announced count. It blocks nothing.
- **Zero PK duplicates in all tables.** The announced ~2% of duplicates is not in the primary key; it is
  searched for as content duplicates (same row with a different ID) in phase 1.

### A3. Schema evolution
- **A single header signature per table** across the 1,097 files: same columns and same order from start to finish
  `[measured]` (`00_schema_by_partition.csv`). No columns appear or disappear.
- The announced evolution, if it exists, would have to be in the values (formats, scales, labels). Candidates
  seen in the inventory: `fraud_score` on different scales (0.89 vs 25.02 in rows from the same day), `México` vs
  `Mexico` in `transaction_country` (0.9% `Mexico`) and `ip_country` (6.6% `Mexico`) `[measured]`
  (`00_enum_values.csv`). Quantified in phase 1.

### A4. Actual enums vs dictionary
Source: `00_enum_vs_dictionary.csv` and `00_enum_values.csv` (`queries/00_enum_values.sql`) `[measured]`.

| Column | Dictionary | Actual | Note |
|---|---|---|---|
| `products.product_type` | Checking, Savings, Credit Card, Debit Card, Personal Loan, Mortgage, Investme… | Cuenta Ahorro 30.1%, Tarjeta Crédito 25.0%, Cuenta Corriente 25.0%, Tarjeta Débito 10.0%, Préstamo Personal 5.0%, Préstamo Hipotecario 3.0%, Inversión 1.5%, **Seguro** 0.5% | in Spanish; `Seguro` undocumented |
| `call_center_interactions.reason_category` | Transactional, Product, Technical, Commercial, Complaint | Transaccional 35.0%, Producto 22.0%, Queja 17.1%, Técnico 15.0%, Comercial 8.0%, **Retención** 3.0% | in Spanish; `Retención` undocumented |
| `call_center_interactions.channel` | Phone, Web Chat, WhatsApp, Email, App | + **Web** 0.5% | Phone = 85.0% |
| `customers.document_type` | DNI, CURP, CC, CE, Pasaporte | no **CURP** (DNI 69.8%) | customers from Mexico without CURP |
| `products.currency`, `transactions.currency` | MXN, COP, ARS, USD | USD 55.1%, COP 27.0%, ARS 17.9%; **no MXN** | complaints does have MXN (8.2%) |

Match the dictionary: `country`, `segment`, `product_status`, `agent_type`, `transaction_type`,
`transaction_status`, `survey_type`, `event_type`, `case_type`.

### A5. Derived and text fields: less information than expected
Source: `00_enum_values.csv`, `00_multivalue_values.csv` (`queries/00_multivalue_values.sql`) `[measured]`.

| Field | What was expected | What is there |
|---|---|---|
| `contact_reason` | granular reason | **identical to `reason_category`** (6 values) |
| `call_transcripts.detected_intents` | multi-label intents | **a single value**: `consulta_general` (95.1%), the rest null |
| `call_transcripts.detected_keywords` | keywords | 3 words (banco, cuenta, servicio) in different orders |
| `call_transcripts.main_topics` | topics | the same 6 categories as `reason_category` |
| `call_transcripts.customer_text` | customer free text | **42 distinct values**; 2 templates ("consultar el saldo de mi tarjeta de crédito" 30.1%, "saldo actual en mi cuenta de ahorros" 29.9%) |
| `call_transcripts.agent_text` | agent response | templates with **unfilled** placeholders (`{monto} {moneda}`, `{limite}`) |
| `call_transcripts.detected_language` | es | 100% `es` |
| `complaints.description` | customer's account of the issue | **5 templates** ("Queja relacionada con transactions/fees/technical/branch/service") |
| `complaints.resolution` | resolution text | 5 templates; 77.2% null |
| `complaints.origin_interaction_id` | FK to the originating interaction | **100% null** |
| `satisfaction_surveys.open_comments` | free-text comment | 13 fixed phrases; 52.4% null |
| `satisfaction_surveys.nps_category` | Promoter/Passive/Detractor | **no Promoter**: Detractor 21.2%, Passive 7.2%, null 71.6% |

Consequences:
- There is no real customer text to train or evaluate an intent classifier: the text is templated.
  Any language evaluation set (including Portuguese) will have to be generated by the team and labeled
  as such.
- The dictionary's "interaction → transcript → survey → complaint" chain breaks at complaints: they can only be
  linked by `customer_id` + time window, with the ambiguity that implies.
- The workflow mapping (phase 3) cannot rely on `contact_reason` or `detected_intents`. Available signals:
  `reason_category`, `complaints.category/subcategory`, mentioned products (`mentioned_products`,
  `affected_product_id`, `mentioned_entities.products`) crossed with `product_type`.

### A6. Uniform distributions (generator signature)
`complaints.category` 5 × ~20%, `complaints.subcategory` 5 × ~18% (+10% null), `customers.gender` F/M/O 3 × ~33%,
`transcription_model` 4 × ~25%, `accepts_marketing` and `has_linked_app` 50/50 `[measured]` (`00_enum_values.csv`).
Sign of a generator with uniform, independent distributions: per-workflow metrics might not
differ (see plan decision 2: confidence intervals and alternative criterion).

### A7. What is useful for the challenge
- **Portuguese among agents:** 129 of 1,200 agents (10.75%) list Portuguese `[measured]`
  (`00_multivalue_values.csv`). Customer text is 100% Spanish.
- **`response_code`** with real ISO 8583 codes: 00 (87.4%), 14, 51, 05, 54 (~1.9% each), null 5.0% `[measured]`.
  Useful for W2 (card declines).
- **`digital_events`**: `Login` 15.6%, `Error` 2.3% of events; `event_category=Authentication` 31.2% `[measured]`.
  Basis for the "errors and logins before calling" funnel.
- **`transactions.transaction_status`**: `Reversed` 1.0%, `Declined` 5.0%; `is_fraud` 0.098% `[measured]`.

## B. Quality by table (phase 1)
Source: `python -m eda.quality` → `outputs/tables/01_*.csv`, queries `docs/eda/queries/01_*.sql`. Read from the
Parquet cache (`data/_cache/`), a faithful copy of the CSV with verified counts (`scripts/build_cache.py`).

### Summary: announced vs measured
| Problem announced by the dictionary | What was measured | Where |
|---|---|---|
| ~2% duplicates | **0 duplicates** in the 12 tables: not by PK, not by content (same row with another ID), not re-delivered on another day. Not with loose business keys either | §B1 |
| ~5% nulls in optional fields | **Yes**: many optional columns with ~5% (or ~10%, ~15%, ~20%) random nulls, plus structural nulls | §B2 |
| FK orphans "small %" | **Not small in three FKs**: 99.997% in `customers.registration_branch_id`, 99.8% in `service_agents.assigned_branch_id`, 99.4% in `mentioned_products`. Also, valid FKs that point to **another customer's** product (100% in complaints) | §B3 |
| Late arrivals | **None**: the lag `process_date − event date` is 0 or −1 day (never positive) | §B4 |
| Schema evolution | **None** in headers (phase 0), and no material drift in values | §B6 |

What it did **not** announce but is there: impossible future dates, template texts, truncated survey scales,
`sla_breached` independent of everything, random currency in complaints, events before the product was opened,
invalid coordinates, inconsistent labels (`México`/`Mexico`).

### B1. Duplicates
- `dup_exact`, `dup_content_excl_pk` and `dup_content_excl_pk_process_date` = **0 in the 12 tables** `[measured]`
  (`01_quality_summary.csv`, `queries/01_duplicates.sql`). Method: `count(*) − count(DISTINCT hash(columns))`;
  validated by injecting 1,000 duplicate rows into interactions (it detects all of them).
- Loose business keys `[measured]` (`01_business_key_checks.csv`, `queries/01_business_key_checks.sql`):
  0 repeats in interactions (customer, date-time), transactions (product, date-time, amount) and (customer, day, amount,
  type), complaints (customer, date), customers (document) and (first name, last name, birth date). 263 interactions
  repeat (customer, day, reason, channel): customers who contact twice on the same day, not duplicates.
- **Non-unique emails**: 79,930 customers (54.4% of the 147,016 with an email) share their email with at least one other
  customer; there are 91,289 distinct emails `[measured]` (`01_business_key_checks.csv`). Email cannot serve as a
  customer identifier or as an identity factor (relevant for the challenge's authentication mock).
- Implication: the pipeline must have the duplicates check (it is evaluated), but today there is nothing to deduplicate.

### B2. Nulls
Source: `01_null_rates.csv` (`queries/01_null_rates.sql`) and `01_null_patterns.csv` (`queries/01_null_patterns.sql`)
`[measured]`.
- **Mandatory columns without nulls** in 11 of 12 tables. Exception: `digital_events.customer_id` 24.0% null,
  uniform across all `event_type` values (23.96–24.08%): random nulls, not anonymous pre-login sessions. Those
  events cannot be linked to a call.
- **Random "by design" nulls**: blocks of columns with ~5% (`response_code`, `audio_quality`, `ip_address`,
  `amount_usd` in COP/ARS, `credit_limit` and `days_past_due` in credit products), ~10% (`postal_code`,
  `occupation`, `mentioned_entities`), 15% (`credit_score`), 20% (`estimated_monthly_income`, `fraud_score`),
  ~30% (`customer_detected_accent`). Uniform across segments, channels and categories.
- **Structural nulls** (expected, not a defect):
  - `wait_time_seconds` exists **only for `Inbound Call`** (0% null); it is 100% null in Outbound Call, Chat, Email and
    Video. The phase 6 wait proxy only holds for inbound calls (70.0% of interactions,
    `00_enum_values.csv`).
  - `credit_limit` / `days_past_due`: 100% null outside Tarjeta Crédito and loans.
  - Complaint resolution fields (`resolution_date`, `resolution_days`, `resolution`): 77% null, because
    70% of the cases are open (Open, In Process).
  - `amount_usd`: 100% null when `currency = USD` (see §B5).
- **Relevant for W4:** `credit_score` 15.0% null and `estimated_monthly_income` 20.0% null, random across segments.
  An eligibility flow will have to handle missing data (the challenge explicitly asks for it).

### B3. FK orphans and customer ownership
Source: `01_fk_orphans.csv` (`queries/01_fk_orphans.sql`, `01_fk_orphans_mentioned_products.sql`) and
`01_consistency_checks.csv` (`queries/01_consistency_checks.sql`) `[measured]`.

| Relationship | Result |
|---|---|
| interactions, transcripts, surveys, complaints, transactions, digital_events → `customers` | 0 orphans |
| transactions → `products` | 0 orphans; the transaction's `customer_id` is **always** the product owner (C12 = 0) |
| transcripts / surveys → `call_center_interactions` | 0 orphans; same customer, same agent, survey after the interaction, at most 1 transcript and 1 survey per interaction (C01–C11 = 0) |
| `customers.registration_branch_id` → `branches` | **99.997% orphans**: 150,000 distinct IDs, one per customer, almost none exist |
| `service_agents.assigned_branch_id` → `branches` | **99.76% orphans** (831 of 833 non-null) |
| `call_center_interactions.mentioned_products` → `products` | **99.35% orphans** (545,118 of 548,680 mentioned IDs); the 3,562 that exist belong to **another customer** (C16 = 100%) |
| `complaints.affected_product_id` → `products` | 0 orphans, but the product belongs to **another customer** in 100% of cases (C15) |
| `digital_events.product_id` → `products` | 0 orphans, but it belongs to **another customer** in 99.999% (C20) |
| `complaints.origin_interaction_id` | 100% null |

Consequences:
- **The interaction → transcript → survey chain is solid and can be used for the scorecard.** Complaints is
  isolated: it links neither to the interaction nor to one of the customer's own products. Only via `customer_id` + time.
- **There is no reliable way to know the product of an interaction or a complaint** (the mentioned product IDs
  do not exist or belong to another customer). Mapping to workflows by product (phase 3) is limited to
  transactions → products, which is consistent.
- `branches` only joins cleanly from products, transactions and complaints.
- For the challenge ("per-customer record isolation"): a tool that trusts `affected_product_id` or
  `mentioned_products` would show another customer's data. The ownership check must live in the service layer.

### B4. Late arrivals
Source: `01_late_arrivals.csv`, `01_late_arrivals_hist.csv` (`queries/01_late_arrivals.sql`,
`01_late_arrivals_hist.sql`) `[measured]`.
- `partition_date = process_date` in 100% of the rows of the 6 fact tables.
- `lag_days = process_date − event date` takes **only 0 or −1** (surveys: 0, −1, −2). p50 = p95 = p99 = 0
  (surveys p50 = −1). **No record arrives late.**
- The −1 (25% in transactions and digital_events, 33% in interactions, transcripts and complaints) appears because the
  event falls in the early hours of the day after the `process_date`: a file's events run from 08:00 to
  08:00 the next day in interactions and complaints, and from 06:00 to 06:00 in transactions and digital_events `[measured]`
  (`01_day_boundary.csv`, `queries/01_day_boundary.sql`). Hypothesis `[assumption]`: the generator's "day" is shifted
  from midnight (time zone or operating day). In surveys, the −1/−2 is because the survey is answered after the interaction and
  filed under the interaction's date.
- Events dated after the end of the window (2026-06-18 00:00): 0.01–0.07% per table (R01, R16, R20, R41,
  R80), due to the same shift.
- Implication: the freshness policy and late-arrival handling cannot be demonstrated with this data. A
  labeled test fixture is needed (the challenge provides for it).

### B5. Impossible ranges and business rules
Source: `01_range_checks.csv` (`queries/01_range_checks.sql`) and complementary queries `[measured]`.

| Table | Finding | Violations / denominator |
|---|---|---|
| customers | `last_updated` after the S3 load (2026-08-31): **impossible future date** (up to 2027-06-15) | 5,957 / 150,000 (3.97%) |
| customers | `last_updated` after the end of the dataset | 9,316 / 150,000 (6.21%) |
| customers | under 18 at registration | 3,106 / 150,000 (2.07%) |
| customers | mobile phone prefix does not match the country | 72,548 / 145,293 (49.9%) |
| products | `last_updated` after the S3 load (impossible future date) | 15,939 / 400,000 (3.99%) |
| products | product opened before the customer registered (C17) | 199,596 / 400,000 (49.9%) |
| products | Tarjeta Crédito without `credit_limit` | 5,059 / 100,102 (5.05%) |
| transactions | transaction before the product was opened (C13) | 827,610 / 4,425,008 (18.7%) |
| transactions | `amount_usd` null when `currency = USD` | 2,437,979 / 2,437,979 (100%) |
| transactions | `amount_usd` null in COP/ARS | 99,477 / 1,987,029 (5.0%) |
| transactions | `transaction_country = 'Mexico'` instead of `'México'` | 40,515 / 2,146,309 (1.9%) |
| digital_events | `ip_country = 'Mexico'` instead of `'México'` | 1,038,174 / 7,281,067 (14.3%) |
| complaints | Resolved/Closed without `resolution_date` | 772 / 16,121 (4.8%) |
| complaints | `compensation_granted` > `claimed_amount` | 62 / 1,453 (4.3%) |
| complaints | `claimed_amount` without `currency` | 1,040 / 21,751 (4.8%) |
| branches | coordinates near (0, 0) | 167 / 350 (47.7%) |
| branches | longitude ≥ 0 (impossible in MX/CO/AR) | 83 / 350 (23.7%) |
| call_transcripts | `agent_text` / `full_text` with unfilled placeholders (`{monto}`, `{moneda}`, …) | 171,321 / 171,321 (100%) |

No violations: amounts ≤ 0, `resolution_days` negative or inconsistent with the dates (R28 = 0), date order in
complaints, `credit_score` outside 300–850, `sentiment_score` outside [−1, 1] or with the opposite sign to the label,
`fraud_score` outside 0–100, `accent_confidence` outside [0, 1].

**`amount_usd` consistency**: where it exists, it matches the day's exchange rate (deviation p50 ≈ 1%, p95 ≈ 2%,
0 cases > 5%) `[measured]` (`01_fx_consistency.csv`, `queries/01_fx_consistency.sql`).

**Currency by country** `[measured]` (`01_currency_by_country.csv`, `queries/01_currency_by_country.sql`):
- products and transactions: Mexico 100% USD (never MXN); Colombia 90% COP / 10% USD; Argentina 90% ARS / 10% USD.
- complaints: `currency` **independent of the country** (an Argentine customer files complaints in MXN, COP, USD or ARS at ~8% each;
  67.5% null). `claimed_amount` is not comparable across cases without normalizing the currency, and the currency is not credible.

**Survey scales** `[measured]` (`01_survey_scale_usage.csv`, `queries/01_survey_scale_usage.sql`):

| Type | Observed values | Distribution |
|---|---|---|
| CSAT | 1–4 (never 5) | 1: 3.5% · 2: 27.9% · 3: 57.3% · 4: 11.3% |
| CES | 1–4 | 1: 3.5% · 2: 27.8% · 3: 57.2% · 4: 11.6% (**the same distribution as CSAT**) |
| NPS | 2–7 (never 0, 1, 8, 9, 10) | 2–4: ~7.7% each · 5–7: ~25.7% each |

- NPS without promoters: with the standard definition (Detractor 0–6, Passive 7–8, Promoter 9–10), 74.5% of the
  NPS responses are detractors and 25.5% passives, so the bank-wide NPS would be **−74.5** `[measured]`
  (`01_survey_scale_usage.csv`). Nobody answers 8–10.
- CSAT and CES generated with the same distribution: they cannot be interpreted as distinct constructs.
- Reinforces plan decision 4 (do not average across types) and adds another: **absolute survey values cannot
  be interpreted as real satisfaction**; only relative comparisons between groups, with CIs, are useful.

**Complaints SLA** `[measured]` (`01_complaints_sla_consistency.csv`, `queries/01_complaints_sla_consistency.sql`):
`sla_breached` ≈ 20% **in every slice**: by resolution days (1–5 days: 19.95%; 26–30 days: 19.13%), by status
(Open 19.6%, Resolved 19.7%, Rejected 21.4%), by priority (Critical 19.2%, Low 20.1%) and by case type. **It does not depend
on resolution time.** "% SLA breached" does not measure process performance in this dataset.

### B6. Schema evolution in values
Source: `01_null_drift.csv` (`queries/01_null_rates.sql` grouped by month) `[measured]`.
- Criterion: a month is anomalous if its null rate departs from the overall rate by more than 4 binomial standard deviations.
- 5 of 134 columns exceed the threshold: 4 in digital_events (`app_version`, `browser`, `customer_id`, `ip_city`) with a
  monthly range ≤ 1.6 pp (detectable only because of the volume: 15.6M events / 37 months ≈ 420k/month, `00_row_counts.csv`) and `complaints.subcategory` (z = 4.2,
  borderline). None shows a step that would indicate a schema change. `[assumption]`: the digital_events variations
  come from the monthly channel mix (web vs app).
- Conclusion: **there is no material schema evolution**, neither in headers (phase 0) nor in values. Label "schema
  drift" candidates: `México`/`Mexico` (§B5), present throughout the period.

### B7. Volume by day of the week
Source: `01_rows_by_weekday.csv` (`queries/01_rows_by_weekday.sql`) `[measured]`.
- Saturday and Sunday have **half** the volume of a business day in interactions (0.50), transcripts (0.50), surveys
  (0.50) and complaints (0.50); transactions 0.60; digital_events 0.66.
- This explains the gap with the dictionary seen in phase 0: with weekends at 0.5035, the expected volume is
  (5 + 2 × 0.5035) / 7 = 0.858 of nominal, and interactions has 0.858; transactions predicts 0.886 and has 0.885.
  Complaints (0.839 vs 0.858 predicted) stays ~2% below with no explanation. `[projected]` on the `[assumption]` that
  the dictionary reports the nominal volume without the weekend reduction.

### B8. Transcript and survey coverage
Source: `01_coverage.csv` (`queries/01_coverage_transcripts_surveys.sql`) `[measured]`.
- **24.96%** of interactions have a transcript; the `has_transcript` flag matches the existence of
  the row exactly (C01 = C02 = 0). **31.0%** have a survey.
- Coverage is **flat** by `reason_category` (24.9–25.2%), channel (24.7–26.3%) and interaction type
  (24.7–25.2%); so is survey coverage (30.6–31.8%). There is no coverage bias along those dimensions. Per-workflow
  bias is measured in phase 3 (plan decision 3), but with this uniformity it is unlikely.
- Reminder (§A5): although coverage is good, transcript content is templated (546 distinct `full_text`,
  42 `customer_text` and 42 `agent_text` values in 171,321 rows; `01_business_key_checks.csv`) and `detected_intents`
  has a single value.

### B9. Checks the solution pipeline should have
Derived from the above, for the data engineering block of the pitch:
1. PK uniqueness and content duplicates (0 today; the check must exist anyway).
2. Customer ownership on every product FK (`affected_product_id`, `mentioned_products`, `digital_events.product_id`).
3. Future dates (`last_updated` > load date) and temporal order (transaction ≥ product opening).
4. Label normalization (`México`/`Mexico`) and currency normalization (`amount_usd` for USD = `amount`).
5. Survey scales by type, without averaging across types.
6. `process_date` vs event date lag, with an alert if a positive lag appears (none today).
7. Unfilled placeholders in text (`{…}`) before using transcripts as context for an LLM.

## C. Data engineering evidence for the pitch
The dataset's real problems (different from the ones the dictionary announces) are exactly the checks a
production pipeline would have to run. Each one with its figure and its query `[measured]`:

| # | Real problem | Figure | Query | Production check that detects it |
|---|---|---|---|---|
| 1 | Valid FK pointing to **another customer's** product | `complaints.affected_product_id` 100% (44,570/44,570); `digital_events.product_id` 99.999% | `01_consistency_checks.sql` (C15, C20) | Customer ownership on every FK before showing or acting (per-customer isolation) |
| 2 | Orphan FK in lists | `mentioned_products` 99.35% (545,118/548,680 IDs) | `01_fk_orphans_mentioned_products.sql` | Referential integrity on multi-value fields |
| 3 | Fake FK to branches | `customers.registration_branch_id` 99.997%, `service_agents.assigned_branch_id` 99.76% | `01_fk_orphans.sql` | Referential integrity in dimensions |
| 4 | Impossible future dates | `last_updated` > load date: 3.97% of customers, 3.99% of products | `01_range_checks.sql` (R52, R61) | `date ≤ ingestion date` |
| 5 | Temporal order violated | 18.7% of transactions before the product was opened; 49.9% of products before the customer registered | `01_consistency_checks.sql` (C13, C17) | Event order per entity |
| 6 | Shifted operating day | daily files run from 08:00 to 08:00 (interactions, complaints) and from 06:00 to 06:00 (transactions, digital_events); 25–33% of events dated the day after `process_date` | `01_day_boundary.sql`, `01_late_arrivals.sql` | Define the day cutoff explicitly in the contract; do not assume midnight |
| 7 | Inconsistent labels | `Mexico` vs `México`: 1.9% in transactions, 14.3% in digital_events | `01_range_checks.sql` (R47, R82) | Domain (enum) normalization |
| 8 | Incomplete derived field | `amount_usd` null in 100% of USD transactions | `01_range_checks.sql` (R43) | Derivation rule (`currency = USD ⇒ amount_usd = amount`) |
| 9 | Text with unfilled placeholders | `{monto}`, `{moneda}` in 100% of `agent_text` | `01_range_checks.sql` (R91) | Text validation before using it as context for an LLM |
| 10 | Non-unique identifiers | 54.4% of customers share an email with another customer | `01_business_key_checks.sql` | Uniqueness of attributes used to identify or authenticate |
| 11 | Enums different from the dictionary | `product_type` and `reason_category` in Spanish, `Seguro` and `Retención` undocumented, no `CURP` or `MXN` | `00_enum_values.sql` | Schema contract with explicit domains |
| 12 | Structural vs random nulls | `wait_time_seconds` only exists for Inbound Call; ~5/10/15/20% random nulls in optional fields | `01_null_patterns.sql`, `01_null_rates.sql` | Null rate per column with a threshold per null type |

What the dictionary announces and is **not** there (0 duplicates, 0 late arrivals, no schema evolution) is also
evidence: the pipeline must have those checks, and demonstrating freshness/late arrivals requires a **labeled
fixture** (the challenge provides for it). The interaction → transcript → survey and transactions → products chains are 100%
consistent (C01–C12 = 0): they are the safe joins for a solution.
