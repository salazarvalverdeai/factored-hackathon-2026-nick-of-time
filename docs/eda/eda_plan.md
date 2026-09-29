# EDA plan — evidence for the pitch

Goal: come out with a comparative table of the challenge's **4 workflows**, backed by queries, that lets us
choose 1 to 3 ideas and fill the 5 pitch blocks (`docs/pitch/pitch_brief.md`). The EDA is **cross-cutting**:
first the 4 workflows are examined with the same yardstick; only then do we go deeper into the winners.

Context: `docs/context/proyecto/01_reto_2026.md` (challenge metrics) and `02_dataset_latam_bank.md` (tables).

The 4 workflows (short names used throughout the repo):
`W1_accounts_payments` · `W2_cards` · `W3_disputes` · `W4_credit`

## Decisions agreed with Freddy (Sep 26, after the S3 inventory)
1. **Each scorecard metric with its own n and denominator. No composite index.** Interactions (all
   contacts) and complaints (cases that failed) are different populations; W3 lives in complaints by definition.
2. **Confidence intervals in phase 4.** If pain does not discriminate between workflows (overlapping CI95 in the
   pain metrics), the alternative criterion for comparing them is **label richness and feasibility**.
3. **Check the `has_transcript` bias per workflow before using `detected_intents`** (transcripts cover at
   most ~25% of interactions).
4. **Never average `main_score` across survey types** (CSAT, NPS, CES have different scales).
5. **Dimensions as a single snapshot** (inventory finding): `customers`, `products`, etc. are a single CSV with no
   history. Goes to phase 5 as a leakage risk for W2 and W4, and to "Gaps".
6. **Sync:** dimensions + core + full `transactions`. Full `digital_events` in the background and **only
   for the funnel of errors and logins prior to a call**. `campaign_sends` deferred.
7. **Incremental documents:** each phase writes its part in the document it belongs to
   (`data_quality.md` in phase 1, `workflow_mapping.md` in phase 3, dossier sections in phases 2 and 4–6);
   phase 7 consolidates. One commit per phase.

## Decisions agreed with Freddy (Sep 26, after phases 0 and 1)
8. **Parquet cache approved** (`data/_cache/`, gitignored; no `.parquet` goes into git).
9. **Section 8 of the dossiers = catalog of distinct templates** (transcripts and complaints), deduplicated, with
   frequency and assigned workflow, without identifiers or personal data. Subject to Slack question 4.
10. **Change of strategy.** A reason field without granularity, intents with a single value, template text and
    `sla_breached`/CSAT/NPS unrelated to anything imply that "the problem in numbers" will not discriminate between
    workflows and that an intent classifier over text is not a defensible learned component. Therefore:
    - Phase 4 continues; its expected conclusion is "outcomes do not discriminate", and it is **demonstrated** with intervals.
    - **Phase 5 becomes the central phase**, with a learnable-signal check per candidate label.
    - Phase 6 keeps the formula, but makes explicit that **volume is the only measured input** and pain is assumed.
    - The real quality problems go to `data_quality.md` as data engineering evidence for the pitch.
11. **Mapping (phase 3) without joint review**: versioned rules with high/medium/low confidence; coverage and % AMBIGUOUS
    per source. Freddy reviews it at the end on `workflow_mapping.md`.
12. **Autonomous mode in phases 2–7**: no checkpoints; one commit per phase; decisions in `findings.md` as "Decision
    made". Stop only on a technical blocker or a finding that invalidates the plan.
13. **Priority: breadth over depth.** First the 4 complete dossiers. Of the optional explorations, only the
    `digital_events` funnel of errors/logins prior to a call (W2), if it takes less than an hour. Phase 5 without
    elaborate models.

---

## Phase 0 — Inventory and load (`eda/inventory.py`)
**Questions**
- What files are in the bucket, in what format, with what partition structure, and how large are they?
- Do the row counts match the dictionary (150k, 400k, 800k, 80k, …)?
- What columns does each table have in each partition? Where does the schema change, and when?
- What real values do the enums take (`product_type`, `reason_category`, `case_type`, `status`, …)? The dictionary
  lists a truncated one ("Investme…").

**Deliverables**: `outputs/tables/00_inventory_files.csv`, `00_row_counts.csv`, `00_schema_by_partition.csv`,
`00_enum_values.csv`. Checkpoint with Freddy before phase 1.

## Phase 1 — Data quality (`eda/quality.py`)
**Questions per table**
- Exact and PK duplicates (`customer_id`, `interaction_id`, `case_id`, …). Rate vs the announced ~2%.
- Nulls per column; which columns are "optional" and which should have no nulls.
- FK orphans (interactions without a customer, complaints without an origin interaction, transcripts without an interaction).
- Late arrivals: distribution of `process_date − event_date` in days. The S3 path has no `process_date`
  (only `year/month/day`) and everything was uploaded on Aug 31, 2026: the lag is simulated **inside the files**. It is
  measured with the `process_date` column if it exists, or with the partition date vs the event date.
- Impossible ranges: dates outside 2023-06-17..2026-06-17, negative amounts, `resolution_days` < 0,
  `main_score` out of scale.
- Coverage of transcripts and surveys over interactions (`has_transcript` vs actual transcripts), input to
  decision 3.

**Deliverables**: `01_quality_summary.csv` (one row per table), `01_null_rates.csv`, `01_late_arrivals.csv`.
Document: `docs/eda/data_quality.md` (phase 1 + inventory findings from phase 0).
This feeds the "Risks and gaps" block and the data engineering part of the pitch.

## Phase 2 — Demand (`eda/demand.py`)
Base: deduplicated `call_center_interactions`. Complements: `complaints`, and `digital_events` **only for the funnel
of errors and logins prior to a call** (decision 6; the real `event_type` values are validated in phase 0).
**Questions**
- Total monthly volume and by `reason_category`, `contact_reason`, `channel`, `country`, `interaction_type`.
- Top 30 `contact_reason` by volume. Stability over time (is there seasonality or a trend?).
- Monthly volume of `complaints` by `case_type`, `category`, `subcategory`, `reception_channel`.
- What share of interactions has a transcript (`has_transcript`) and an associated survey?

**Deliverables**: `02_monthly_volume_by_reason.csv`, `02_top_contact_reasons.csv`, `02_complaints_by_category.csv`,
monthly series figures.

## Phase 3 — Mapping to workflows (`eda/workflows.py`)
This is the most delicate phase: **no field says "workflow"**. An explicit, auditable mapping is built.
**Method**
1. List all distinct values of `contact_reason`, `complaints.category/subcategory`,
   `call_transcripts.detected_intents` and `main_topics` with their frequency.
2. Propose a rule dictionary `value → workflow` (W1–W4, `OTHER`, `AMBIGUOUS`) in
   `docs/eda/queries/03_workflow_mapping.csv`. Keyword rules only as a first pass; the final assignment
   is reviewed by hand with Freddy.
3. Measure coverage: % of interactions/complaints that fall into each workflow, into `OTHER` and into `AMBIGUOUS`.
4. **Before using `detected_intents`:** compare the workflow mix between interactions with and without a transcript
   (decision 3). If it differs, everything that comes from transcripts is reported as valid only for that subset.
5. Cross sources: do `contact_reason` and `detected_intents` agree for the same interaction? That measures how
   reliable the model-derived labels are.

**Deliverables**: `03_workflow_mapping.csv` (the rule table, versioned), `03_coverage_by_workflow.csv`,
`03_transcript_bias_by_workflow.csv`, `03_reason_vs_intent_agreement.csv`.
Document: `docs/eda/workflow_mapping.md` (rules, rationale for each assignment, agreement, OTHER/AMBIGUOUS) and
section (1) of each dossier.

## Phase 4 — Outcomes per workflow (`eda/outcomes.py`)
With the phase 3 mapping, compute **the same table for the 4 workflows**:

| Metric | Source | Note |
|---|---|---|
| Monthly volume | interactions + complaints | full months |
| FCR (`was_resolved`) | interactions | |
| Escalation (`was_escalated`), `requires_followup` | interactions | proxy for "needs a human" |
| Duration and wait (p50/p95) | interactions | cost proxy |
| % SLA breached (`sla_breached`) | complaints | |
| Resolution days (p50/p95) | complaints | |
| Compensation granted, amount claimed | complaints | disputes |
| CSAT / NPS / CES and `resolution_satisfaction` | surveys, complaints | **each type separately**, never average `main_score` across types |
| Sentiment (`detected_sentiment`) | interactions | derived label, handle with care |
| Repetition (`is_repeat_complainer`, re-contact at 7/30 days) | complaints, interactions | "not resolved" signal |

**Scorecard rules** (decisions 1, 2 and 4):
- Each cell carries value, **n, explicit denominator** (e.g. "deduplicated W2 interactions" vs "W2 complaints
  with non-null `sla_breached`") and **CI95**: Wilson for proportions, bootstrap (seed 42) for medians/p95.
- **No composite index** and no aggregate ranking.
- If the CI95 of the pain metrics overlap across workflows, pain is declared non-discriminating and the
  comparison moves to the alternative criterion: label richness (phase 5) and feasibility in 10 days.

Also, per workflow: distribution by country, channel and segment (`customers.segment`), because the challenge asks to
compare outcomes by segment and by language. Note: `segment` is the value at cutoff (single snapshot), not at the time
of the contact.

**Expected conclusion (decision 10):** "outcomes do not discriminate between workflows". It is demonstrated, not assumed:
CI95 per cell and, in addition, an independence test (chi-square and Cramér's V) of each outcome against
`reason_category`, channel, country and segment. If any metric does discriminate, it is reported and the conclusion changes.

**Deliverables**: `04_workflow_scorecard.csv` (the central pitch table, long format: workflow × metric ×
{value, n, denominator, ci_low, ci_high, query}), `04_scorecard_by_country.csv`, `04_scorecard_by_segment.csv`,
`04_recontact.csv`. Document: section (3) of each dossier.

## Phase 5 — Labels, baseline and learnable signal (`eda/labels.py`) — CENTRAL PHASE
The challenge requires evaluating **a learned component against a baseline** with valid labels and no leakage.

**Learnable-signal check (decision 10).** For each candidate label — `was_escalated`, `was_resolved`,
`requires_followup` (interactions), `sla_breached` (complaints), `is_fraud`, `transaction_status = Declined`,
`transaction_status = Reversed` (transactions), `product_status = Blocked` (card products), `days_past_due > 0`
(credit products):
- Structured features **available before the event** (nothing known only at closing: duration, sentiment,
  resolution, `response_code`, later statuses). Dimension features are a single snapshot: they are flagged as a risk.
- **Temporal split** (training on the oldest period, testing on the most recent; for products, by
  `opening_date`).
- Trivial baseline (majority class) vs logistic regression and a tree of depth ≤ 4. Seed 42.
- Test metrics: AUC with CI95 (Hanley-McNeil), average precision vs prevalence, F1 with CI95 (bootstrap).
- Rule: if the AUC CI95 includes 0.5 (or the F1 does not beat the baseline), **the label is noise and is discarded**.
  If there is no signal in any label, that is the finding and it goes to the pitch.
**Questions**
- What labels exist per workflow? Candidates: `contact_reason` / `reason_category` (intent),
  `detected_intents` (derived multi-label), `was_escalated` (needs a human), `was_resolved` (resolvable),
  `complaints.status`/`sla_breached` (breach risk), `is_fraud` (disputes), `product_status=Blocked`
  (cards), `days_past_due`/`credit_score` (credit).
- Label quality: class distribution, imbalance, consistency across sources (phase 3).
- **Fields with leakage** (known only after closing): `resolution`, `resolution_days`, `resolution_date`,
  `compensation_granted`, `resolution_satisfaction`, `was_resolved` if predicted before the call ends,
  later surveys. List them explicitly.
- **Dimensions as a single snapshot (decision 5):** `customers` and `products` are a single snapshot at cutoff. Every
  status field (`product_status`, `days_past_due`, `current_balance`, `credit_limit`, `credit_score`, `segment`,
  `customer_status`) reflects the final status, not the one at the time of the contact. Direct leakage risk for
  **W2** (`product_status=Blocked` as label or feature) and **W4** (`credit_score`, `days_past_due`). Measure how much
  it weighs: e.g. products with `last_transaction_date` after the interaction.
- How many transcripts are there per workflow and what is the typical length? That decides whether an intent classifier
  over text is feasible in 10 days.
- Possible splits: by time (event date; `process_date` if it exists as a column) and by customer
  (`customer_id`). Check how many customers have interactions in more than one month.

**Deliverables**: `05_labels_inventory.csv`, `05_leakage_fields.csv`, `05_transcripts_by_workflow.csv`,
`05_split_feasibility.csv`, `05_learnable_signal.csv` (label × model × metrics with CI). Suggested baseline per
workflow according to where there is signal (no TF-IDF over template text).
Document: section (4) of each dossier.

## Phase 6 — Cost and business case (`eda/cost.py`)
**Questions**
- Agent minutes per workflow (`duration_seconds` + `wait_time_seconds`) per month: `[measured]`.
- Cost per contact = minutes × cost per agent minute: `[assumption]` with a source (leave the parameter in the
  script, do not hardcode a number).
- % "safely automatable" per workflow: first approximation `[assumption]` = interactions not escalated,
  resolved on first contact, with no later complaint. State explicitly that it is a bound, not a measurement.
- Savings `[projected]` = volume × % automatable × cost difference. Same formula for the 4 workflows.
- **Explicit in every table (decision 10):** volume is the only `[measured]` input; pain (SLA, CSAT, FCR) does not
  discriminate, and the % automatable and the cost are `[assumption]`.

**Deliverables**: `06_cost_by_workflow.csv`, `06_business_case_inputs.csv` with columns `valor` (value), `etiqueta`
(label: measured/assumption/projected), `fuente` (source). Document: section (5) of each dossier.

## Phase 7 — Wrap-up: documents for the claude.ai Project
The documents are uploaded to a claude.ai Project to cross-check them against external research. Each one must
stand on its own, with every figure labeled (`[measured]`/`[assumption]`/`[projected]`) and with its query file.

1. **Workflow dossiers** `docs/eda/workflows/W1_accounts_payments.md`, `W2_cards.md`, `W3_disputes.md`,
   `W4_credit.md`. Same structure in all four:
   1. Workflow definition and the mapping rules that feed it, with coverage and % ambiguous
   2. Demand: monthly volume, channels, countries, segments, seasonality
   3. Outcomes: each metric with n, denominator, interval and query
   4. Available labels, quality, fields with leakage, suggested baseline and split
   5. Cost proxies and business case inputs, labeled
   6. Workflow-specific gaps
   7. Possible explorations with an effort estimate
   8. Template catalog: all distinct text templates (transcripts and complaints) assigned to the
      workflow, with their frequency, without identifiers (decision 9)
2. **`docs/eda/data_quality.md`**: everything from phase 1 plus the inventory findings (single snapshot of
   dimensions, no `process_date` in the path, late arrivals simulated inside the files, transcript
   coverage).
3. **`docs/eda/workflow_mapping.md`**: versioned rule table, rationale for each assignment, reason vs intent
   agreement, `has_transcript` bias and what ended up in OTHER/AMBIGUOUS.
4. **`docs/eda/findings.md` becomes the index**: 1-page summary per workflow pointing to each dossier,
   the same-yardstick comparison (scorecard with n, denominator and CI), "Gaps", "Possible explorations",
   "Decisions made" and the 1 to 3 candidate ideas.
5. **`docs/eda/executive_summary.md`** (1 page, opened in the Project together with the dossiers): what the dataset has
   and does not have, in which workflow there is learnable signal and with which label, ranking by the alternative criterion
   (labels, feasibility, deterministic signals), 1 to 3 candidate ideas with the 2–3 numbers that support them, and the
   questions for Slack.
6. Copy the numbers to `docs/pitch/pitch_brief.md`.
7. List of questions that came up for Slack `#technical-help` (add to `04_brechas_y_preguntas.md`).
8. Final report to Freddy (20 lines max).

The dossiers are generated with `python -m eda.report` from `outputs/tables/` so the figures do not get out of
sync. Section 8 is the template catalog (decision 9), subject to Slack question 4.

---

## Optional explorations (if time is left over or if a workflow calls for it)
- Transcript text: length, vocabulary by country/accent, how many mention amounts or dates (useful for
  entity extraction in disputes).
- `digital_events`: funnel of errors and failed logins before a call (do people call because the app failed?).
- `products`: blocked cards and their relation to declined transactions and later calls.
- `service_agents.languages`: does any agent speak Portuguese? Useful for the language block.
- Correlation between `wait_time_seconds` and CSAT.
- Fraud (`is_fraud`, `fraud_score`) only as a signal for disputes; it is not the challenge.

## What this EDA does NOT do
- It does not train models. It only leaves labels, a suggested baseline and feasible splits.
- It does not build the production pipeline. It leaves the list of quality checks that pipeline will have to run.
- It does not decide the workflow. It presents the 4 with the same yardstick; the decision belongs to the pitch and the vote.
