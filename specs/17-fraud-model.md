# Spec 17 — Our fraud model versus the bank's score (small benchmark)

- **Feature:** a fraud model trained on gold transactions, compared with the bank's `fraud_score` as the baseline on a
  later time window, and shown to the analyst as a second signal only if it earns it. The bank's score keeps deciding
  the zones.
- **Status:** Draft (2026-10-04; gate 1 closed by the lead)
- **Owner:** @salazarvalverdeai · **Priority:** P0 benchmark, P1 analyst signal · **Size:** M
- **Challenge dimension:** Machine Learning (a learned model against a baseline), Technical Judgment
- **Depends on:** gold v1 and `gold_eval/transaction_labels`, ADR 0022 · **Enables:** a second signal in the
  handoff card (specs 03, 04, console), the model inventory (ADR 0021), `/evaluation`
- **ADRs:** 0006, 0007, 0015, 0021, 0022 · **Issue:** #28

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
- **AC-03 [P0]** — Every arm of §4.3 shall be evaluated on the same test window, from the bank's score to the
  scikit-learn screen and the best model stacked with the score. · [C]
- **AC-04 [P0]** — The report shall include:
  - PR-AUC with a 95% bootstrap CI;
  - recall at the bank's precision levels (0.80 and 0.95);
  - recall on frauds with no bank score at an alert budget of 1% of those transactions `[assumption]`;
  - results by score band (none, < 30, 30–49, ≥ 50);
  - the Brier score;
  - recall by country and by segment;
  - cost and efficiency on the same machine: training time, scoring p95 per transaction, throughput, model size and
    peak memory;
  - every metric on all products and on the card subset. · [D]
- **AC-05 [P0]** — Training shall read labels only for the training and validation windows; the test labels shall be
  read once, by the evaluation step, after the model is frozen (ADR 0022). · [T]
- **AC-06 [P0]** — The decision rule of §4.4 shall be in `eval/PROTOCOL.md` before the test window is scored. · [D]
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

Split record `[data]`, gold v1 (reproduce: `python -m scripts.ml.fraud_split --gold $GOLD --eval $GOLD_EVAL --out <dir
outside the repo>`; the opt-in test `tests/test_spec17_split_features.py::test_ac_01_real_gold_split_hash_and_counts`
asserts it): transactions per window — train 925,246, validation 224,784, test 238,990; frauds — train 896,
validation 182 (match the table above); split hash (sha256 over the window definitions and the sorted
`transaction_id|window` pairs)
`877a3a2386375dd35fe535e29f1f04d2326fa79bcc5c65349b151cda445df15a`. Later tasks must recompute it and stop if it differs.

The fraud rate is about 0.09%, so PR-AUC is the main metric, not ROC-AUC. With 75 card frauds in the test window the
card CIs are wide; that is reported, not hidden.

### 4.2 Features (only what is known at transaction time)
Amount in USD and its log; currency; channel; transaction type and category; merchant category; abroad
(`transaction_country` ≠ `customer_country`); hour and weekday; product type. From the customer's
**earlier** transactions only: count and amount in the previous 1 h, 24 h and 7 days; amount against the customer's
median; first time at this merchant; distance and time from the previous transaction's location. Excluded:
`product_status` (a snapshot taken after the fact), the `qc_*` columns, `process_date` and the labels.
Implementation choices (`scripts/ml/fraud_features.py`) `[assumption]`:
- History is **all** strictly earlier transactions of the customer (timestamp smaller; a same-time transaction is never
  history), whatever their status: a Declined attempt is known at authorization, and a later status such as Reversed
  must not shape earlier features (D-009). Feature rows are emitted only for Approved/Pending transactions.
- Rows without a `customer_id` use the product as the entity; `amount_usd` falls back to `amount` when the currency is
  USD; the bank's `fraud_score` and `response_code` are not features (the score is the baseline arm and enters only the
  stacked arm).
- `customer_segment` is **not** a feature: gold holds one snapshot taken at the cut, so it can rewrite history
  (`contracts/gold_contract.md`, `docs/eda/data_quality.md` §A1) (D-010). `customer_country` and `product_type` are
  kept, assuming they are stable at transaction time.
- `km_from_prev` uses the closest strictly earlier transaction **with a known location**; `secs_since_prev` uses the
  closest strictly earlier transaction of any kind.
- Cold start: gold begins on 2025-06-01, so early rows have no history. Share of Approved/Pending transactions with no
  earlier transaction of the customer `[data]`: 61.5% in 2025-06, 23.9% in 2025-07, 10.7% in 2025-08, 0.8% in 2026-01
  (computed with `build_features` on gold v1). The windows and counts are not changed. Task 17b adds one feature,
  `n_prev` (count of strictly earlier transactions of the entity, any status), so the models can tell a thin history
  from a quiet customer `[assumption]`; validation metrics are reported by month so the effect is visible. Risk,
  recorded and pending the lead: `n_prev` grows with calendar time, so it can encode the period rather than the
  customer (|ROC-AUC| 0.522 on train+validation `[data]`, probably from the extra frauds of 2025-06).

Signal search before the test window (D-015, `scripts/ml/fraud_signal_search.py`; reproduce with `python -m
scripts.ml.fraud_signal_search --gold $GOLD --eval $GOLD_EVAL --out <dir outside the repo>`). 31 more candidates, built
only from fields known at transaction time and from strictly earlier rows (DuckDB RANGE frames that end 1 µs before the
row), in eleven families: customer velocity; card velocity; declines before (earlier Declined rows only: the decline
codes on Reversed and Pending rows go with a final status that is not known at transaction time, D-009); novelty (first
country, city, channel or merchant category; time since the last visit to the merchant); geo jumps (km and km/h from the
previous located transaction, km from the customer's mean location); amount against the customer's history; hour and
weekday habit; product age, customer tenure and age in complete years; merchant and city load in the last hour;
complaints created in the 90 days before and in an earlier daily file (gold has no late arrivals,
`docs/eda/data_quality.md` §B4); and category rates: smoothed fraud rates of merchant, city, branch and merchant
category × country learned on train labels only. A candidate counts as signal only if its train and validation 95%
bootstrap CIs (stratified, 2,000 replicates) exclude 0.5 on the same side and its validation ROC-AUC is at least 0.02
from 0.5 `[assumption]`. Result on gold v1 `[data]`, stated as a bound: **none passes**. Every non-degenerate train CI
includes 0.5 and lies within [0.469, 0.525] (29 of 31; `card_n_1h` and `declines_24h` have near-zero-width CIs because
no train fraud has a non-zero value), and so does every non-degenerate CI on late train (2025-09 → 2026-01, past the
cold start, 531 frauds), within [0.462, 0.534]. Validation ROC-AUC spans 0.465–0.547; its largest deviation from 0.5,
0.047 (time since the card's previous transaction: 0.547 [0.505, 0.590], train 0.494), is below 0.062, the 95th
percentile of the largest deviation over the 31 candidates under permuted validation labels, so the family-wise test
does not reject. With 182 validation frauds a continuous full-coverage candidate's CI is about ±0.04, so the rule cannot
detect |AUC − 0.5| below about 0.04: a true deviation of 0.04 passes about half the time and 80% power needs about 0.06,
so the train range (half-width 0.019 at 896 frauds) is the tighter bound; a weaker single-feature signal is not ruled
out. The bank score, as a positive control, gives 0.728 [0.673, 0.780]. Reversals before the transaction are not
candidates: gold keeps each row's final status with no reversal time, so a reversal is not known at transaction time
(D-009). The features above stay as they are; §4.4 rule 5 covers the outcome.

### 4.3 Arms — a lean scikit-learn screen
The dataset is large enough for all of these (about 1.39 million Approved/Pending transactions, 896 frauds to train).
Each supervised arm handles the imbalance with class weights or by down-sampling legitimate transactions in the
training window only, and is calibrated on the validation window.

| Family | Arm (scikit-learn) | Why it is in the screen |
|---|---|---|
| Baseline | **S-bank** — the bank's `fraud_score`, null as the lowest | what we must beat |
| No labels | `IsolationForest` | anomaly score without labels: a floor for "learning from labels helps" |
| Linear | `LogisticRegression`, `SGDClassifier` (log loss) | cheap, fast, readable weights |
| Probabilistic | `GaussianNB` | the cheapest supervised arm |
| Tree | `DecisionTreeClassifier` (depth ≤ 6) | rules an analyst can read |
| Ensembles | `RandomForestClassifier`, `ExtraTreesClassifier`, `HistGradientBoostingClassifier` | usually the strongest on tabular data |
| Neural | `MLPClassifier` (small) | checks whether a non-linear model beyond trees adds anything |
| Stacked | the best supervised arm + the bank's score | whether our model adds to the score rather than replacing it |

Stacked base (D-017a, decided by the lead on 2026-10-04): the best supervised arm by validation PR-AUC; when none
exceeds twice the validation base rate, the balanced `HistGradientBoostingClassifier` (a base with no signal would only
add noise to the bank score; on gold v1 a linear base gave stacked PR-AUC 0.460 against 0.589 for the bank score alone
`[data]`). The 2x threshold is a heuristic `[assumption]`: at this prevalence one fraud ranked near the top can lift a
no-signal arm above it. The alternatives weighed before D-017a were to always stack on the balanced HGB or to require
the bootstrap lower bound of the arm's PR-AUC to be above the base rate.

Kernel SVMs and k-nearest neighbours are left out: scikit-learn documents that `SVC` fit time grows at least
quadratically with the number of samples and is impractical beyond tens of thousands of rows.

### 4.4 Decision rule (pre-registered, lean)
1. **Hard limits:** at the bank's precision levels (0.80 and 0.95), recall is at least the bank's; no country or segment
   has a recall below 80% of the overall recall `[assumption]`; scoring p95 ≤ 50 ms and model size ≤ 200 MB
   `[assumption]`. The overall, per-country and per-segment recall of this floor are measured at the 1% alert budget (the
   top 1% of the window by score) `[assumption]` (D-017b). The floor applies only to country and segment slices with at
   least 20 frauds in the window; smaller slices are reported with their fraud count and not enforced `[assumption]`
   (D-017c).
2. **Value:** the arm beats S-bank — PR-AUC higher with the 95% bootstrap CI of the difference above zero — **or** it
   catches at least 30% of the frauds with no bank score at an alert budget of 1% of those transactions (AC-04)
   `[assumption]` (D-017d).
3. **Quality bar:** keep the arms whose PR-AUC is not significantly worse than the best arm (paired bootstrap on the
   same test transactions).
4. **Lean choice:** among those, the cheapest to run — lowest scoring p95, then smallest model, then shortest training;
   a tie goes to the simpler family (linear < tree < ensemble < neural < stacked).
5. If no arm passes, the bank's score stays alone and the benchmark is reported as is.

Rules 1-2 are judged on all products; the card subset is reported with its CI and does not gate `[assumption]` (D-022);
country is `customer_country`.

Note on rule 1 (validation evidence behind D-017c, `scripts/ml/fraud_screen.py` on gold v1) `[data]`: at the 1% window
budget S-bank itself misses the 80% floor in the Plus segment (recall 0.463 on 54 frauds against 0.588 overall, 0.79x),
and Premium and Student have 9 and 10 frauds. `customer_segment` is not a feature (D-010) but is still a reporting
slice, and each slice records its fraud count (`n_fraud`).

### 4.5 Scope for the submission
| Phase | What | Criteria |
|---|---|---|
| **P0 — in** | Time split, features, the screen of §4.3 with quality and cost, lean rule, results in `/evaluation` | AC-01 – AC-06 |
| **P1 — if time allows** | Second signal for the analyst through `get_fraud_score` and the handoff card; model inventory entry | AC-07, AC-08 |
| **P2 — nice to have** | The model setting zones, with a policy entry, an ADR and the release gate | AC-09 |

## 5. Non-functional requirements
- Reproducible: fixed seeds; the model file carries the hash of its training data; scikit-learn only (the same library
  as spec 11's TF-IDF + LR; no gradient-boosting libraries outside it).
- Cost and efficiency are measured on one machine, recorded in the report (CPU, memory), for every arm.
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

### 7.1 Web export shape (`fraud_benchmark.json`, answers spec 12 Q1)
`apps/web/public/data/fraud_benchmark.json` is `{generated_at, git_sha, source, data}` (spec 01 §6.2); `data` is
below, written once by T4 after the test window is scored. `protocol` comes from the seal block of `eval/PROTOCOL.md`, so `/evaluation` can apply the guard of spec 12 AC-05 (status other than `SEALED`: "development run" notice). A proportion is the rate object of spec 10 §7.2, `{value, numerator, denominator, ci_low, ci_high}`, with the 95% Wilson interval of spec 10 §4.1, computed by the exporter (the browser computes nothing, spec 12 §9; spec 12 AC-06). `null` marks a figure the run fills in.

```json
{
  "label": "[data]",
  "protocol": {"status": "SEALED", "sha256": "…", "fraud_split_hash": "…"},
  "windows": {"train": {"from": "…", "to": "…"}, "validation": {"from": "…", "to": "…"},
              "test": {"from": "…", "to": "…", "transactions": null, "frauds": null}},
  "machine": {"cpu": "…", "memory_gb": null},
  "chosen_arm": "S-bank",
  "arms": [
    {"arm": "HistGradientBoostingClassifier", "family": "ensemble", "version": "…", "passes_rule": null,
     "cost": {"train_seconds": null, "score_p95_ms": null, "throughput_per_s": null, "model_mb": null,
              "peak_memory_mb": null},
     "subsets": {
       "all": {
         "pr_auc": null, "pr_auc_ci": [null, null], "brier": null,
         "recall_at_bank_precision": {"0.80": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "0.95": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}},
         "recall_no_score_at_1pct": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null},
         "by_score_band": [{"band": "none", "n_fraud": null, "recall": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}}],
         "by_country": [{"country": "…", "n_fraud": null, "recall": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}}],
         "by_segment": [{"segment": "…", "n_fraud": null, "recall": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}}]},
       "card": {}}}
  ]
}
```
- `label` is `[data]` (gold v1; test labels read once, ADR 0022). `protocol` adds `fraud_split_hash` (spec 17 T1, hex
  string). `windows` are ISO months of ADR 0022, with the test window's transaction and fraud counts. `machine` is
  the one machine that measured every arm (§5). `chosen_arm` is the arm of §4.4 or `S-bank` when none passes (rule 5).
- `arms[]` (AC-03): `arm` is the scikit-learn class, `S-bank` or `stacked`; `passes_rule` is the bool of §4.4.
- `cost` (AC-04): seconds, milliseconds, transactions per second and megabytes.
- `subsets.all` and `subsets.card` (AC-04: every metric on both): `pr_auc` with its 95% bootstrap interval, `brier`, the
  recalls at the bank's precision levels and `recall_no_score_at_1pct` (the 1% alert budget is `[assumption]`) as
  rate objects, and the breakdowns by score band (`none`, `<30`, `30-49`, `>=50`), country and segment, each with
  `n_fraud`. Slices below 20 frauds are shown and not enforced (D-017c).

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — owner:** the lead.
- **Q2 — data and windows:** train on all products (Approved/Pending), report the test on all products and on cards;
  train Jun–Jan, validation Feb–Mar, test Apr–May.
- **Q3 — rule thresholds:** 30% of the frauds with no score at a 1% alert budget; fairness at 80% of the overall recall.
- **Q4 — use:** in the submission only as a second signal for the analyst; zones stay with the bank's score.
- **Q5 — algorithms:** the lean scikit-learn screen of §4.3, with cost and efficiency measured for each arm.
- **D-009 — feature history (2026-10-04; default applied by the orchestrator, pending lead confirmation):** history
  is every strictly earlier transaction of the customer, whatever its status; feature rows only for Approved/Pending
  (§4.2).
- **D-010 — customer segment (2026-10-04; default applied by the orchestrator, pending lead confirmation):**
  `customer_segment` is not a feature, because gold holds one snapshot taken at the cut (§4.2).
- **D-015 — signal search before the test window (2026-10-04, lead):** look for transaction-time signal beyond §4.2 on
  train and validation only, before task 17c scores the test window; outcome in §4.2.
- **D-017a — stacked base (2026-10-04, lead):** best supervised arm by validation PR-AUC, else the balanced HGB when
  none exceeds twice the validation base rate `[assumption]` (§4.3).
- **D-017b — operating point (2026-10-04, lead):** overall, per-country and per-segment recall of the rule-1 floor at
  the 1% alert budget of the window `[assumption]` (§4.4).
- **D-017c — slice minimum (2026-10-04, lead):** the floor applies only to slices with at least 20 frauds; smaller
  slices are reported with their fraud count `[assumption]` (§4.4).
- **D-017d — rule-2 wording (2026-10-04, lead):** "at an alert budget of 1% of those transactions (AC-04)" (§4.4).
- **D-017e — split shares (2026-10-04, lead):** within 3 points of 60/15/25 `[assumption]`; it applies to spec 11 and
  is listed here because it was decided with D-017a–d.
- **D-022 — scope of the rule (2026-10-04; default applied by the orchestrator, pending lead confirmation):** rules 1-2
  judged on all products; the card subset reported with its CI and not gating; country is `customer_country`
  `[assumption]` (§4.4).

## 9. Out of scope
Deep learning or graph features; streaming features; using the model for automation in the submission; scheduled
retraining (ADR 0021, P2).

## 10. Plan, tasks and verification
- [x] T1 [P0] — versioned queries for the monthly label counts and the time split; split hash · AC-01
- [x] T2 [P0] — feature builder from earlier transactions only + leakage test · AC-02
- [x] T3 [P0] — the arms of §4.3 with calibration on validation (Platt scaling; legitimate rows down-sampled 100 per
      fraud in train only, plus class weights where available `[assumption]`), cost and efficiency harness
      (`scripts/ml/fraud_screen.py`; models and outputs outside the repo, the protocol seal forbids results inside it);
      train and validation only, so the test-window part of AC-03 is task 17c · AC-03 (screen), AC-05
- [ ] T3b [P0] — lean rule in `eval/PROTOCOL.md` · AC-06 · #47 (merged); PROTOCOL §3.1 and §3.3 synced with §4.3–4.4
      by PR #60 (open; task PROT2; D-017a–e, D-022), and §4.4 rules 1–2 copied back from PROTOCOL §3.3
- [x] T3c [P0] — signal search beyond §4.2 on train and validation (`scripts/ml/fraud_signal_search.py`, D-015): no
      candidate passes, the feature list is unchanged · AC-02, AC-05
- [ ] T4 [P0] — test-window evaluation, report, `fraud_benchmark.json` for `/evaluation` · AC-04
- [ ] T5 [P1] — `model_score` in `get_fraud_score` and the handoff card; inventory entry · AC-07, AC-08

## 11. Sources
- Bank score thresholds over the full history: [`queries/pitch/p08_fraud_score_thresholds.sql`](../queries/pitch/p08_fraud_score_thresholds.sql)
  → `p08_fraud_score_thresholds.csv` (≥ 50: precision 100%, recall of all frauds 38.69%; ≥ 30: 79.58% and 54.98%)
  `[data]`; the 100% caveat: `docs/README.md` (zones row).
- Gold v1 counts (1,477,723 transactions, 1,372 frauds, 19.8% of frauds without a score; frauds per window for all
  products and for cards, Approved/Pending): aggregate queries over `data/gold/transactions_enriched` and
  `data/gold_eval/transaction_labels`, run on 2026-10-04 by the lead; train and validation counts are versioned in
  `queries/fraud/f01_monthly_counts.sql`; the test-window counts are re-derived only by the evaluation step (ADR 0022)
  `[data]`.
- Labels only in `gold_eval`: `contracts/gold_contract.md` R3 and G1.
- Saito and Rehmsmeier, *The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary
  Classifiers on Imbalanced Datasets*, PLOS ONE (2015): https://doi.org/10.1371/journal.pone.0118432
- Davis and Goadrich, *The Relationship Between Precision-Recall and ROC Curves*, ICML (2006):
  https://doi.org/10.1145/1143844.1143874
- Liu, Ting and Zhou, *Isolation Forest*, IEEE ICDM (2008): https://doi.org/10.1109/ICDM.2008.17
- scikit-learn user guide — linear models https://scikit-learn.org/stable/modules/linear_model.html, SGD
  https://scikit-learn.org/stable/modules/sgd.html, naive Bayes https://scikit-learn.org/stable/modules/naive_bayes.html,
  trees https://scikit-learn.org/stable/modules/tree.html, ensembles https://scikit-learn.org/stable/modules/ensemble.html,
  neural networks https://scikit-learn.org/stable/modules/neural_networks_supervised.html, outlier detection
  https://scikit-learn.org/stable/modules/outlier_detection.html, calibration
  https://scikit-learn.org/stable/modules/calibration.html · `SVC` scaling:
  https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html
- Federal Reserve, FDIC and OCC, *SR 26-2* (17 April 2026) — a non-generative model is in its scope: outcomes analysis,
  ongoing monitoring, model inventory: https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf
- Internal: ADR 0006 (score as a swappable input), ADR 0015 (pre-registration), ADR 0021, ADR 0022.
- Thresholds marked `[assumption]` have no external source.
