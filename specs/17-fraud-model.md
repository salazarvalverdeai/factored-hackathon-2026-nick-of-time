# Spec 17 — Our fraud model versus the bank's score (small benchmark)

- **Feature:** a fraud model trained on gold transactions, compared with the bank's `fraud_score` as the baseline on a
  later time window, and shown to the analyst as a second signal only if it earns it. The bank's score keeps deciding
  the zones.
- **Status:** Draft (2026-10-04)
- **Owner:** @vldiego (proposed — already has access to the labels) · reviewer @salazarvalverdeai · **Priority:** P0
  benchmark, P1 analyst signal · **Size:** M
- **Challenge dimension:** Machine Learning (a learned model against a baseline), Technical Judgment
- **Depends on:** gold v1 and `gold_eval/transaction_labels`, ADR 0022 (proposed) · **Enables:** a second signal in the
  handoff card (specs 03, 04, console), the model inventory (ADR 0021), `/evaluation`
- **ADRs:** 0006, 0007, 0015, 0021 (proposed), 0022 (proposed) · **Issue:** to open after approval

---

## 1. Introduction
The bank's score decides the zones (ADR 0006). Where it speaks, it is strong: over the full history, a score ≥ 50 has
100% precision but catches 38.7% of all frauds, and a score ≥ 30 has 79.6% precision and catches 55.0% `[data]`. The
100% is probably a property of the synthetic generator `[assumption]`. It is silent on about a fifth of the frauds: in
gold v1, 19.8% of the 1,372 frauds have no score `[data]`.

The question is whether a model trained on transaction features adds signal — above all for frauds with no score or a
low score — without false alarms. Three models are compared with the bank's score on a later time window, with a rule
written before the test window is scored, and the conclusion is reported even if the bank's score wins.

## 2. User stories
- As an **analyst**, I want a second, independent fraud signal on a case — mostly when the bank's score is missing — so
  I spot a fraud the score did not flag.
- As the **bank**, I want any new model compared with the score we already use, on data it never saw, before it
  influences a decision.

## 3. Acceptance criteria (EARS)
**[P0]** in the submission · **[P1]** if time allows · **[P2]** nice to have.

- **AC-01 [P0]** — The split shall be by time (§4.1), fixed and hashed before training, and no transaction used by the
  agent cases of specs 09 and 10 shall be in the training window. · [C]
- **AC-02 [P0]** — Features shall use only fields known when the transaction happened; `product_status`, the `qc_*`
  columns, `process_date`, the labels and anything written later shall be excluded, checked by a test. · [T]
- **AC-03 [P0]** — Four arms shall be evaluated on the same test window: **S-bank** (the bank's score, null as the
  lowest), **M1** logistic regression on features without the score, **M2** gradient-boosted trees on features without
  the score, **M3** M2 plus the bank's score. · [C]
- **AC-04 [P0]** — The report shall include:
  - PR-AUC with a 95% bootstrap CI;
  - recall at the bank's precision levels (0.80 and 0.95);
  - recall on frauds with no bank score at an alert budget of 1% of those transactions `[assumption]`;
  - results by score band (none, < 30, 30–49, ≥ 50);
  - the Brier score;
  - recall by country and by segment;
  - p95 scoring latency;
  - every metric on all products and on the card subset. · [D]
- **AC-05 [P0]** — Training shall read labels only for the training and validation windows; the test labels shall be
  read once, by the evaluation step, after the model is frozen (ADR 0022). · [T]
- **AC-06 [P0]** — The decision rule of §4.3 shall be in `eval/PROTOCOL.md` before the test window is scored. · [D]
- **AC-07 [P1]** — If a model passes the rule, `get_fraud_score` shall return it as a second signal (`model_score`,
  `model_version`) next to the bank's score, and the handoff card shall show it to the analyst; the zone shall still
  come from the bank's score. · [T]
- **AC-08 [P1]** — The model shall be registered in the model inventory (ADR 0021) with owner, version, data windows,
  metrics and monitoring. · [D]
- **AC-09 [P2]** — Using the model to set zones shall require a policy entry, an ADR and the release gate of ADR 0021. · [D]

## 4. Functional requirements

### 4.1 Data and time split
Gold v1 transactions with status `Approved` or `Pending`, all product types (the product type is a feature). Cards —
the transactions a customer can dispute (spec 03) — are too few to train on alone, so the test is reported twice: on
all products and on the card subset, which is the number that matters for the product.

| Window | Months | Frauds, all products `[data]` | Frauds, cards `[data]` |
|---|---|---|---|
| Train | 2025-06 → 2026-01 | 896 | 314 |
| Validation (thresholds, calibration) | 2026-02 → 2026-03 | 182 | 68 |
| Test (scored once) | 2026-04 → 2026-05 | 211 | 75 |

The fraud rate is about 0.09%, so PR-AUC is the main metric, not ROC-AUC. With 75 card frauds in the test window the
card CIs are wide; that is reported, not hidden.

### 4.2 Features (only what is known at transaction time)
Amount in USD and its log; currency; channel; transaction type and category; merchant category; abroad
(`transaction_country` ≠ `customer_country`); hour and weekday; card type; customer segment. From the customer's
**earlier** transactions only: count and amount in the previous 1 h, 24 h and 7 days; amount against the customer's
median; first time at this merchant; distance and time from the previous transaction's location. Excluded:
`product_status` (a snapshot taken after the fact), the `qc_*` columns, `process_date` and the labels.

### 4.3 Decision rule (pre-registered)
1. **No precision loss:** at the bank's precision levels (0.80 and 0.95), the model's recall is at least the bank's.
2. **Value:** M3's PR-AUC beats S-bank with non-overlapping 95% bootstrap CIs, **or** M1/M2 catch at least 30% of the
   frauds with no bank score at the 1% alert budget `[assumption]`.
3. **Fairness:** no country or segment has a recall below 80% of the overall recall `[assumption]`; otherwise the
   result is reported as a blocker.
4. **Lean:** the simplest arm that passes (M1 < M2 < M3).
5. If no arm passes, the bank's score stays alone and the benchmark is reported as is.

### 4.4 Scope for the submission
| Phase | What | Criteria |
|---|---|---|
| **P0 — in** | Time split, features, four arms, report, decision rule, results in `/evaluation` | AC-01 – AC-06 |
| **P1 — if time allows** | Second signal for the analyst through `get_fraud_score` and the handoff card; model inventory entry | AC-07, AC-08 |
| **P2 — nice to have** | The model setting zones, with a policy entry, an ADR and the release gate | AC-09 |

## 5. Non-functional requirements
- Reproducible: fixed seeds; the model file carries the hash of its training data; scikit-learn only (no new heavy
  dependencies).
- Scoring p95 ≤ 50 ms per transaction `[assumption]`.

## 6. API contract
```python
model = load_fraud_model("models/fraud-m2-v1.joblib")
r = model.score(transaction)     # {score: 0..100, version, top_features: [..3]}
```
P1 only: `GetFraudScoreOut` adds `model_score` and `model_version` (spec 03, minor change).

## 7. Data model touched
Reads gold `transactions_enriched` and `gold_eval/transaction_labels` (windows of ADR 0022). Writes
`models/fraud-*.joblib`, `eval/results/fraud_benchmark.csv`, `apps/web/public/data/fraud_benchmark.json` and the
versioned queries under `queries/fraud/`.

## 8. Assumptions and open questions (gate 1)
- **Q1 — owner:** Diego (has label access and owns the data), with the lead as reviewer? Or the lead?
- **Q2 — data and windows:** train on all products (Approved/Pending), report the test on all products and on cards;
  train Jun–Jan, validation Feb–Mar, test Apr–May. OK?
- **Q3 — rule thresholds:** 30% of the frauds with no score at a 1% alert budget; fairness at 80% of the overall recall.
  OK?
- **Q4 — use:** in the submission only as a second signal for the analyst; zones stay with the bank's score. OK?
- **Q5 — algorithms:** logistic regression and scikit-learn's histogram gradient boosting. OK?

## 9. Out of scope
Deep learning or graph features; streaming features; using the model for automation in the submission; scheduled
retraining (ADR 0021, P2).

## 10. Plan, tasks and verification
- [ ] T1 [P0] — versioned queries for the monthly label counts and the time split; split hash · AC-01
- [ ] T2 [P0] — feature builder from earlier transactions only + leakage test · AC-02
- [ ] T3 [P0] — four arms, validation-set calibration, decision rule in `eval/PROTOCOL.md` · AC-03, AC-05, AC-06
- [ ] T4 [P0] — test-window evaluation, report, `fraud_benchmark.json` for `/evaluation` · AC-04
- [ ] T5 [P1] — `model_score` in `get_fraud_score` and the handoff card; inventory entry · AC-07, AC-08

## 11. Sources
- Bank score thresholds over the full history: [`queries/pitch/p08_fraud_score_thresholds.sql`](../queries/pitch/p08_fraud_score_thresholds.sql)
  → `p08_fraud_score_thresholds.csv` (≥ 50: precision 100%, recall of all frauds 38.69%; ≥ 30: 79.58% and 54.98%)
  `[data]`; the 100% caveat: `docs/README.md` (zones row).
- Gold v1 counts (1,477,723 transactions, 1,372 frauds, 19.8% of frauds without a score; frauds per window for all
  products and for cards, Approved/Pending): aggregate queries over `data/gold/transactions_enriched` and
  `data/gold_eval/transaction_labels`, run on 2026-10-04 by the lead; versioned in T1 `[data]`.
- Labels only in `gold_eval`: `contracts/gold_contract.md` R3 and G1.
- Saito and Rehmsmeier, *The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary
  Classifiers on Imbalanced Datasets*, PLOS ONE (2015): https://doi.org/10.1371/journal.pone.0118432
- Davis and Goadrich, *The Relationship Between Precision-Recall and ROC Curves*, ICML (2006):
  https://doi.org/10.1145/1143844.1143874
- Federal Reserve, FDIC and OCC, *SR 26-2* (17 April 2026) — a non-generative model is in its scope: outcomes analysis,
  ongoing monitoring, model inventory: https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf
- Internal: ADR 0006 (score as a swappable input), ADR 0015 (pre-registration), ADR 0021 (proposed), ADR 0022 (proposed).
- Thresholds marked `[assumption]` have no external source.
