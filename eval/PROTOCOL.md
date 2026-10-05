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
- **Decided by the lead and binding here whether or not the cited spec records them yet:** the 20-fraud slice floor
  (D-017c, spec 17) and the 3-point share tolerance (D-017e, spec 11), on 2026-10-04; the three D-022 rules, on
  2026-10-05: a missing tool call counts as a wrong B1 prediction (spec 15), injection rows sit outside the
  test minimums and the intent metrics (spec 11), and rules 1-2 are judged on all products with country as
  `customer_country` (spec 17).
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
`[assumption, spec 11 §8; delivered by spec 09]`, written by model generators and reviewed line by line by a person
(ADR 0025). Five intents: `unrecognized_charge`, `wrongful_charge`, `status_inquiry`, `human_request`, `out_of_scope`.

| Split | Share `[assumption]` | May be used for | May not be used for |
|---|---|---|---|
| Train | 60% | fitting B1 (TF-IDF + LR) and the injection LR, rule development for B0 | scoring an arm for selection |
| Validation | 15% | τ, hyperparameters, prompt wording of B2, the one calibration split | the final reported score |
| Test | 25% | the final score of every arm, once, after the arms are frozen | any tuning, prompt edit, threshold or rule change |

- **Author** = the generator model id of the sentence. Each split has one generator, of a different model family
  from the other two, and none is Claude (ADR 0025): train Llama 3.3 70B (`us.meta.llama3-3-70b-instruct-v1:0`),
  validation Gemma 3 27B (`google.gemma-3-27b-it`), test DeepSeek V3.2 (`deepseek.v3.2`). Each split records its
  generator: model id, prompt hash, sampling settings and seed (`eval/classifier/draft/generation.json`).
- The split is **by author**, never by sentence: all sentences of one author are in one split (AC-06). The realized
  shares of train, validation and test must each be within 3 points of 60/15/25 `[assumption]` (D-017e, decided by the
  lead on 2026-10-04), the same tolerance `tests/test_spec11_protocol.py` checks on the files.
- At least **100 test sentences per language** and **20 per intent per language** `[assumption]` (AC-06). The [C]
  check of the split runs on the spec 09 files; `tests/test_spec11_protocol.py` skips it while `eval/classifier` has
  no split file.
- The split files are hashed before training starts (see "Seal"). The injection sentences live **inside the split
  files**, each with the field `label: injection` and the `author` who wrote it, so the author rule and the manifest
  hash cover them; they are not in a separate folder `[assumption, spec 11 does not say; confirmed at M02]`.
- Rows with `label: injection` follow the author rule, the shares and the manifest hash, and are scored only by the
  injection detector (AC-04); the test minimums and the intent metrics count only the other rows `[assumption]` (D-022).
- B2 (LLM) gets the label definitions and no example from the test split (spec 11 §4).
- Results from a candidate of the same family as the generator of the split being scored are flagged (spec 11 §8,
  ADR 0025).
- Train and validation are reviewed line by line by the lead. The test split is decided by the fixed rules `rules-v1`
  (ADR 0028: drop rows whose text contradicts their slots, language or label; null or correct the slots; keep the
  rest), because no person other than the classifier's developer could review it before the seal. Every test result
  is labeled "test split decided by fixed rules, without independent human review" (`test_review` in
  `classifier.json`).

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

Historical mode only (`replay`, fixed `DEMO_TODAY`); live mode is refused (spec 15 AC-09). Same prompt and same
structured-output schema for every LLM arm (spec 15 §4.1).

- **Structured output (D-011, decided by the lead on 2026-10-04):** Converse tool use with the schema, forced with
  `toolChoice`. Each LLM arm walks the ladder `tool` → `any` → `auto` and steps down only when Bedrock rejects the
  mode; the first accepted mode decides, and the mode that worked is recorded per arm (`tool_choice_mode`) and reused
  in B1 (spec 15 §4.1).
- **Temperature (D-016, decided by the lead on 2026-10-04):** 0 where the model accepts it, otherwise the provider
  default; the value used is recorded per arm (spec 15 §4.1).
- **Missing tool call in B1:** a reply with no tool call, or whose tool input fails the schema, is scored as a wrong
  prediction for that message and stays in the denominator; the count is reported per arm `[assumption]` (D-022).

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
production criterion. ES/PT quality is a production-only criterion (D-012, decided by the lead on 2026-10-04) because
the benchmark itself measures it.

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
| ES/PT quality measured on our data | — (the benchmark measures it) | yes |

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
  GaussianNB, DecisionTree (depth ≤ 6 `[assumption]`), RandomForest, ExtraTrees, HistGradientBoosting, small MLP, and
  the best supervised arm + the bank's score (stacked) (spec 17 §4.3).
- **Stacked base (D-017a, decided by the lead on 2026-10-04):** the best supervised arm by **validation** PR-AUC; when
  no supervised arm exceeds twice the validation base rate, the balanced `HistGradientBoostingClassifier`. The 2x
  threshold is a heuristic `[assumption]`; a base with no signal would only add noise to the bank score.

### 3.2 Metrics (spec 17 AC-04)
PR-AUC with a 95% bootstrap CI; recall at the bank's precision levels (0.80 and 0.95); recall on frauds with no bank
score at an alert budget of 1% of those transactions `[assumption]`; results by score band (none, < 30, 30–49, ≥ 50);
the Brier score; recall by country and by segment; cost and efficiency on the same machine: training time, scoring p95
per transaction, throughput, model size and peak memory; every metric on all products and on the card subset.

### 3.3 Decision rule (copied from spec 17 §4.4)
1. **Hard limits:** at the bank's precision levels (0.80 and 0.95), recall is at least the bank's; no country or segment
   has a recall below 80% of the overall recall `[assumption]`; scoring p95 ≤ 50 ms and model size ≤ 200 MB
   `[assumption]`. The overall, per-country and per-segment recall of this floor are measured at the 1% alert budget
   (the top 1% of the window by score) `[assumption]` (D-017b). The floor applies only to country and segment slices
   with at least 20 frauds in the window; smaller slices are reported with their fraud count and not enforced
   `[assumption]` (D-017c).
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

### 3.4 Pre-registered (cannot change after sealing)
Window boundaries, arm list, metrics, thresholds and the rule above. The bank's score keeps deciding the zones; a model
that passes is only a second signal for the analyst (spec 17 §8, Q4).

---

## Seal

Procedure (manual step M02, Diego): review this file, approve it, then fill the block below **before** any test-split
or test-window score exists, and pin it with a git tag `protocol-v1` on the sealing commit. The split hash (b) needs
the spec 09 sentences and the held-out reference of (c) needs the spec 10 held-out, so M02 waits for both. Diego
confirms at M02 that the spec 09 layout matches (b) below; until then it stays `[assumption]`. `eval/heldout.sha256`
holds exactly one sha256 (64 lowercase hex characters); SEALED requires 64-hex values in both reference fields of (c)
and the test fails otherwise. Once any result exists (`eval/results/*`, `models/intent-*`, `models/injection-*`,
`models/fraud-*`, `apps/web/public/data/classifier.json`, `apps/web/public/data/benchmark.json`,
`apps/web/public/data/fraud_benchmark.json`), the status can no longer be UNSEALED: the test fails.

**What is hashed.** (a) Protocol: the sha256 of the bytes of this file with the seal block removed (every line from the
line that is exactly the begin marker through the line that is exactly the end marker, inclusive; only the trailing
`\n` of a line is ignored). From the repository root:

```
sed '/^<!-- SEAL:BEGIN -->$/,/^<!-- SEAL:END -->$/d' eval/PROTOCOL.md | shasum -a 256
```

(b) Classifier splits: the sha256 of a manifest with one line `<sha256 of file>␣␣<path>` per split file (train,
validation and test) of `eval/classifier/*.jsonl` (top level only; subfolders are not split files), in C-locale path
order; it fails when no file matches. The layout of spec 09 is `[assumption]`: top-level files whose names start with
`train`, `validation` and `test`, each row with `author`, `language` and `intent` (injection rows carry
`label: injection`) and the other fields of spec 09 §7.6; `eval/classifier/draft/` holds the unreviewed drafts and is
not hashed; confirmed at M02 as above:

```
files=$(find eval/classifier -maxdepth 1 -name '*.jsonl' | LC_ALL=C sort); test -n "$files" && echo "$files" | xargs shasum -a 256 | shasum -a 256
```

(c) Two references recorded at M02, not recomputed by the test: the agent held-out hash in `eval/heldout.sha256` (ADR
0007) and the fraud split hash (spec 17 T1). When SEALED, both must be filled, and the first must equal the hash in
`eval/heldout.sha256` when that file exists.

`tests/test_spec11_protocol.py` recomputes (a) and (b) with exactly these methods and fails on any mismatch.

<!-- SEAL:BEGIN -->
- Status: SEALED
- Protocol sha256: 533fc516c78509868b95e1d674bbeeee2555285d68bc4856f229623aa7aaa2d2
- Classifier split manifest sha256: 6334f41a5c9c6787cd2d107fd051e24cd38ad7c82de9897ed8ce6a4a6496e99b
- Agent held-out sha256 (eval/heldout.sha256, ADR 0007): 7e44a5956db2f292a48360490297f445ba41dd341ba23d47fad22926dc0b5b80
- Fraud split hash (spec 17 T1): 877a3a2386375dd35fe535e29f1f04d2326fa79bcc5c65349b151cda445df15a
- Sealed by: @salazarvalverdeai (lead, for the spec 09 owner; reviewed by the lead because Diego could not continue); test split decided by rules-v1 (ADR 0028)
- Sealed on: 2026-10-05
<!-- SEAL:END -->
