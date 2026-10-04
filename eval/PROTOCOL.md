# Evaluation protocol (pre-registered)

Pre-registered rules for the three learned or model-chosen components of Nick of Time: the intent classifier (spec
11), the model benchmark (spec 15) and the fraud model (spec 17). It is written, reviewed and sealed **before any
test-split or test-window score exists** (ADR 0015). After sealing, nothing in sections 0 to 3 changes; a change means a
new, dated protocol version and a new seal, and the earlier results stay labeled with the earlier version.

- **Written:** 2026-10-04 by @salazarvalverdeai · **Reviewer:** @vldiego (Diego) · **Seal:** see "Seal" at the end.
- **Source of every rule:** the spec section cited in each block. Where the spec marks a threshold `[assumption]`, the
  label is kept here, because it has no external source.
- **Labels:** `[data]` measured on the dataset, `[external]` public source, `[assumption]` our choice without a source,
  `[simulated]` computed on generated data, `[projected]` extrapolated.
- **Figures whose label is missing in the spec** are marked `[assumption]` here, with the note "label missing in the
  spec; to be added to specs 11, 15 and 17 by the lead": the 60/15/25 split, the minimums of 100 and 20 test
  sentences, the 1.5 s and 6 s p95 limits, 20 blind samples, 20 dev cases x 4 runs, tree depth <= 6.
- **Not done here:** nothing is scored, no held-out sentence is read, no label of `data/gold_eval/` is read.

## 0. Common rules
1. **Frozen before use.** Every split is fixed and hashed before training or selection starts (spec 11 AC-06, spec 17
   AC-01). The test split or window is touched once, after the model or arm is frozen (spec 11 §5; spec 17 AC-05).
2. **Where the choice is made.** Only the agent benchmark B2 is chosen on the 20 dev cases and confirmed once on the
   held-out against S0 (spec 15 §8, Q3; ADR 0007). The classifier (spec 11), the B1 screen (spec 15) and the fraud model
   (spec 17) are decided once on their own frozen test split or window under the rules below.
3. **The conclusion is reported whether or not a model wins.** The simpler or cheaper option stays when no learned arm
   beats it (spec 11 §4.1 rule 4; spec 15 §4.4 rule 5; spec 17 §4.4 rule 5).
4. **Sources.** ADR 0015 (pre-registration); ADR 0007 (sealed held-out); ADR 0022 (which labels may be read when).

---

## 1. Intent classifier and injection detector (spec 11)

Source: `specs/11-intent-classifier.md` §3 (AC-01, AC-06, AC-07), §4, §4.1 and §8 (Q1, Q3).

### 1.1 Data and split
Sentence set of spec 09 (`eval/classifier/*.jsonl`), about 800 sentences in ES and PT with author ids
`[assumption, spec 11 §8; delivered by spec 09]`. Five intents: `unrecognized_charge`, `wrongful_charge`,
`status_inquiry`, `human_request`, `out_of_scope`.

| Split | Share `[assumption]` | May be used for | May not be used for |
|---|---|---|---|
| Train | 60% | fitting B1 (TF-IDF + LR) and the injection LR, rule development for B0 | scoring an arm for selection |
| Validation | 15% | τ, hyperparameters, prompt wording of B2, the one calibration split | the final reported score |
| Test | 25% | the final score of every arm, once, after the arms are frozen | any tuning, prompt edit, threshold or rule change |

- The split is **by author**, never by sentence: all sentences of one author are in one split (AC-06).
- At least **100 test sentences per language** and **20 per intent per language** `[assumption]` (AC-06). The [C]
  check of the split waits for spec 09; `tests/test_spec11_protocol.py` skips it until `eval/classifier` exists.
- The split files are hashed before training starts (see "Seal").
- B2 (LLM) gets the label definitions and no example from the test split (spec 11 §4).
- Results from a candidate of the same family as the LLM that paraphrased the sentences are flagged (spec 11 §8).

### 1.2 Arms and metrics
Arms: B0 rules, B1 TF-IDF + LR, B2 LLM, B3 cascade (B1, below τ then B2); injection detector rules vs rules + LR
(spec 11 §4). All arms are scored on the same frozen test split (AC-02).

Metrics (AC-03, AC-04): macro-F1 per language with a 95% bootstrap CI; per-class F1; recall of disputes
(`unrecognized_charge` + `wrongful_charge` merged) and of `human_request` per language; slot accuracy; ECE; coverage at
τ; p50 and p95 latency; cost per 1,000 messages; injection recall and false-positive rate on legitimate messages.
A message that asks for a person must never get `out_of_scope` from any arm (AC-10; reported separately).

### 1.3 Floors (copied from spec 11 §4.1)
- macro-F1 ≥ 0.90 in ES and in PT `[assumption]`;
- recall ≥ 0.95 per language for "is a dispute" (the two dispute intents merged) and for `human_request` `[assumption]`;
- precision ≥ 0.95 on the messages accepted at τ (AC-07, unchanged);
- test split ≥ 100 sentences per language (AC-06), so the spec 09 set grows from 300–400 to about 800 sentences;
- comparisons between arms use paired McNemar on the same sentences, not a fixed point gap.

τ (AC-07): chosen on the validation split only, as the lowest threshold that keeps precision ≥ 0.95 on the messages the
classifier accepts `[assumption]`.

### 1.4 Decision rule (copied from spec 11 §4.1)
1. Discard any arm below a floor of §4.1 in either language.
2. Among the rest, choose the simplest (B0 < B1 < B3 < B2) that is not significantly worse than the best arm (paired
   McNemar, p ≥ 0.05).
3. It must meet p95 ≤ 1.5 s and ≤ 1 USD per 1,000 messages.
4. If no learned arm beats B0 with significance (McNemar, p < 0.05), keep B0 and report it.
5. Injection detector: adopt rules + LR only if it raises recall without exceeding 2% false positives.

The limits of 1.5 s, 1 USD and 2% were decided by the lead on 2026-10-04 (spec 11 §8, Q1); no external source
`[assumption]`.

### 1.5 Pre-registered (cannot change after sealing)
The intent set, the split rule and shares, the floors, τ rule, decision rule, metric list and the test sentences.

---

## 2. Model benchmark (spec 15)

Source: `specs/15-model-benchmark.md` §3 (AC-07), §4.2, §4.3, §4.4, §4.5 and §8 (Q3, Q4).

### 2.1 Data and split
| Data | May be used for | May not be used for |
|---|---|---|
| Frozen sentence split of spec 11 (B1 screen) | scoring every arm on the **test** split, once; validation only to fix prompts | prompt or arm changes after seeing test scores |
| 20 dev agent cases x 4 runs (B2, spec 10) `[assumption]` | choosing the model map on development data | scoring the held-out |
| Held-out agent cases (spec 10) | confirming the chosen map against S0, once | **choosing** a model; never used to choose (Q3) |

Historical mode only (`replay`, fixed `DEMO_TODAY`); live mode is refused (spec 15 AC-09). Same prompt, same
structured-output schema and temperature 0 for every LLM arm (spec 15 §4.1).

### 2.2 Tasks and metrics (spec 15 §4.2, AC-03, AC-12)
| Task | B1 metric | No-LLM option |
|---|---|---|
| `understand` | macro-F1 per language, recall of disputes and of `human_request`, slot accuracy (spec 11 §4.1) | B0 rules or B1 TF-IDF + LR |
| `word` | grounding pass rate, language and length checks, blind preference against the template on 20 samples `[assumption]` rated by two team members | templates only |
| `judge` | agreement with the expected proposals of the dev cases; share of reasons kept after grounding | no second opinion |

B2: safe automated resolution, unsafe outcomes, `receipt_rate`, `coherence_rate`; p50 and p95 latency; cost per case.
The `judge` task runs on Haiku 4.5 until it joins in P2 (spec 15 §8, Q4).

### 2.3 Lean rule per task (copied from spec 15 §4.4)
1. **Hard limits** — `understand`: the floors of spec 11 §4.1 (macro-F1 per language, dispute and `human_request`
   recall) and p95 ≤ 1.5 s per message; `word`: grounding pass rate ≥ 0.95 and preferred over the template in ≥ 60% of
   blind comparisons `[assumption]`; B2: p95 ≤ 6 s per turn and no unsafe outcome.
2. **Quality bar** — keep the arms that are not significantly worse than the best arm on the same items (paired
   McNemar, p ≥ 0.05; in B2, overlapping 95% CIs). A fixed "within 2 points" cannot be measured at this test size
   (spec 11 §4.1).
3. **Lean choice** — among those, the **cheapest** (B1: cost per 1,000 messages; B2: cost per case); a tie goes to the
   lower p95.
4. **Eligibility** — the chosen arm must pass the production gate of §4.5 on the run date; if it does not, the next
   cheapest arm that meets the bar and passes the gate is chosen, and the ADR says why.
5. If no LLM arm beats B0 with significance (McNemar, p < 0.05), B0 stays and that is reported (spec 11 §4).

Budget guard: a full benchmark stops before calling models if projected spend exceeds 20 USD `[assumption]` (spec 15
AC-08). The "model selection" ADR records, per task, best measured, cheapest that meets the bar and chosen (spec 15
AC-07).

### 2.4 Third-party gate (criteria copied from spec 15 §4.5; no verdicts)
The gate is evaluated per arm when the benchmark runs, from the provider's public documents. "Not documented" fails a
production criterion.

| Criterion | Needed to benchmark | Needed for production |
|---|---|---|
| Data sent is synthetic only (ADR 0009) | yes | — |
| Provider does not train on our requests | yes | yes |
| Retention documented; zero retention available | — | yes |
| Processing region documented | — | yes |
| Public security certification (SOC 2 / ISO 27001) | — | yes |
| Credentials outside the repo, least privilege | yes | yes |
| Version pinning | yes | yes |
| Availability: GA, SLA or status page | — | yes |
| ES/PT quality measured on our data | yes | yes |

### 2.5 Pre-registered (cannot change after sealing)
The task list, the metrics, the hard limits, the quality bar, the lean choice and the eligibility order, the gate
criteria of §2.4, and the budget. Gate **verdicts** are an output of the run, written with evidence URL and date; none
is pre-registered (spec 15 AC-10). Prices are recorded per run with source and date (spec 15 AC-05).

---

## 3. Fraud model (spec 17)

Source: `specs/17-fraud-model.md` §3 (AC-01, AC-05, AC-06), §4.1, §4.3, §4.4; ADR 0022 (labels by window).

### 3.1 Data and time split
Gold v1 transactions with status `Approved` or `Pending`, all products; test also reported on the card subset
(spec 17 §4.1). Frauds per window `[data]`:

| Window | Months | Frauds, all products | Frauds, cards | May be used for |
|---|---|---|---|---|
| Train | 2025-06 to 2026-01 | 896 | 314 | fitting; labels may be read (ADR 0022 rule 1) |
| Validation | 2026-02 to 2026-03 | 182 | 68 | thresholds and the one calibration split; labels may be read (ADR 0022 rule 1) |
| Test | 2026-04 to 2026-05 | 211 | 75 | the final score, **once**; labels read once by the evaluation step after the model file is frozen and its hash recorded (ADR 0022 rule 2) |

The test-window counts (211 and 75) are aggregate counts computed by the lead on 2026-10-04 (spec 17 §11); they carry
no per-transaction test label and are used in no model or threshold.

- No transaction of the agent cases (specs 09, 10) is in the training window (AC-01).
- Features use only fields known at transaction time; `product_status`, `qc_*`, `process_date` and labels are excluded
  (AC-02).
- Arms: S-bank (the bank's `fraud_score`, null as lowest), IsolationForest, LogisticRegression, SGD (log loss),
  GaussianNB, DecisionTree (depth ≤ 6 `[assumption]`), RandomForest, ExtraTrees, HistGradientBoosting, small MLP, and the
  best supervised arm + the bank's score (stacked) (spec 17 §4.3).

### 3.2 Metrics (spec 17 AC-04)
PR-AUC with a 95% bootstrap CI; recall at the bank's precision levels (0.80 and 0.95); recall on frauds with no bank
score at an alert budget of 1% of those transactions `[assumption]`; results by score band (none, < 30, 30–49, ≥ 50);
the Brier score; recall by country and by segment; cost and efficiency on the same machine: training time, scoring p95
per transaction, throughput, model size and peak memory; every metric on all products and on the card subset.

### 3.3 Decision rule (copied from spec 17 §4.4)
1. **Hard limits:** at the bank's precision levels (0.80 and 0.95), recall is at least the bank's; no country or segment
   has a recall below 80% of the overall recall `[assumption]`; scoring p95 ≤ 50 ms and model size ≤ 200 MB
   `[assumption]`.
2. **Value:** the arm beats S-bank — PR-AUC higher with the 95% bootstrap CI of the difference above zero — **or** it
   catches at least 30% of the frauds with no bank score at the 1% alert budget `[assumption]`.
3. **Quality bar:** keep the arms whose PR-AUC is not significantly worse than the best arm (paired bootstrap on the
   same test transactions).
4. **Lean choice:** among those, the cheapest to run — lowest scoring p95, then smallest model, then shortest training;
   a tie goes to the simpler family (linear < tree < ensemble < neural < stacked).
5. If no arm passes, the bank's score stays alone and the benchmark is reported as is.

### 3.4 Pre-registered (cannot change after sealing)
Window boundaries, arm list, metrics, thresholds and the rule above. The bank's score keeps deciding the zones; a model
that passes is only a second signal for the analyst (spec 17 §8, Q4).

---

## Seal

Procedure (manual step M02, Diego): review this file, approve it, then fill the block below **before** any test-split
or test-window score exists, and pin it with a git tag `protocol-v1` on the sealing commit. The spec 09 sentences are
not delivered yet, so the split hash cannot be computed today. Once any result exists (`eval/results/*`,
`models/intent-*`, `models/injection-*`, `models/fraud-*`, `apps/web/public/data/classifier.json`,
`apps/web/public/data/benchmark.json`, `apps/web/public/data/fraud_benchmark.json`), the status can no longer be
UNSEALED: the test fails.

**What is hashed.** (a) Protocol: the sha256 of the bytes of this file with the seal block removed (every line from the
line that is exactly the begin marker through the line that is exactly the end marker, inclusive; only the trailing
`\n` of a line is ignored). From the repository root:

```
sed '/^<!-- SEAL:BEGIN -->$/,/^<!-- SEAL:END -->$/d' eval/PROTOCOL.md | shasum -a 256
```

(b) Classifier splits: the sha256 of a manifest with one line `<sha256 of file>␣␣<path>` per split file (train,
validation and test) of `eval/classifier/*.jsonl` (top level only; subfolders are not split files), in C-locale path
order; it fails when no file matches. The layout of spec 09 is `[assumption]` and must be confirmed before M02:

```
files=$(find eval/classifier -maxdepth 1 -name '*.jsonl' | LC_ALL=C sort); test -n "$files" && echo "$files" | xargs shasum -a 256 | shasum -a 256
```

(c) Two references recorded at M02, not recomputed by the test: the agent held-out hash in `eval/heldout.sha256` (ADR
0007) and the fraud split hash (spec 17 T1). When SEALED, both must be filled, and the first must equal the hash in
`eval/heldout.sha256` when that file exists.

`tests/test_spec11_protocol.py` recomputes (a) and (b) with exactly these methods and fails on any mismatch.

<!-- SEAL:BEGIN -->
- Status: UNSEALED
- Protocol sha256: pending
- Classifier split manifest sha256: pending
- Agent held-out sha256 (eval/heldout.sha256, ADR 0007): pending
- Fraud split hash (spec 17 T1): pending
- Sealed by: pending
- Sealed on: pending
<!-- SEAL:END -->
