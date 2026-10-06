# Spec 15 — Model benchmark (cost vs quality, lean choice)

- **Feature:** one command that runs every candidate model on the same data and produces a table, a cost-versus-quality
  chart and an eligibility verdict per model, so each role (understanding, the agent) gets the **cheapest model that is
  good enough**, chosen from evidence.
- **Status:** Implemented (P1 deferred) (2026-10-06; sealed B1 run done, model map in ADR 0027 (Accepted); B2 and the
  `word` task deferred to P1, see §10)
- **Owner:** @salazarvalverdeai (B2 runs on @vldiego's harness) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning, Technical Judgment (explicit trade-offs of accuracy, latency and cost)
- **Depends on:** 09 (data), 11 (arms B0–B3), 10 (harness for B2), 04 (graph arms) · **Enables:** the model-selection
  ADR, `/evaluation`, the results slide · **ADRs:** 0009, 0015, 0019, 0020, 0027, 0028, 0030 ·
  **PRs:** #27 (spec), #43, #130, #179, #184, #221, #226
- **Issue:** #17

---

## 1. Introduction
"Which model?" is answered with numbers, not preference — and nothing is decided before the run. A **funnel** keeps it
cheap: **B1** screens many models on the understanding task alone (a few cents per model); **B2** runs the whole agent
only with a short list (the number that matters). A **lean rule**, written before any result, picks the cheapest model
whose quality is not significantly worse than the best — **per task**, because the agent uses an LLM for only two
tasks and each may get a different model, or none. Whether a model may be used in production is also a **result of the run**,
checked against public evidence on the run date. The model is chosen on development data; the held-out run in spec 10
then confirms it against S0, so nothing is tuned on the held-out.

## 3. Acceptance criteria (EARS)
Same numbers as issue #17; AC-10 onward are added by this spec.

- **AC-01** — When `make bench` runs, every arm in `eval/bench/arms.yaml` (B0 rules, B1 TF-IDF + LR, the LLM candidates
  of §4.1 and Jev) shall be evaluated on the same frozen test split. · [C]
- **AC-02 [P1]** — B2 shall run the graph with the short list of §4.3 and with S0 on the 20 dev cases × 4 runs. · [C]
  Deferred to P1 (2026-10-06): no B2 arm ran (`benchmark.json` `b2.arms` is empty); since no LLM arm met the B1 bar,
  there was no short list to run on the graph.
- **AC-03** — The output shall include a table with quality (macro-F1 per language over the five intents of spec 11 in
  B1; safe automated resolution, unsafe outcomes, `receipt_rate` and `coherence_rate` in B2), p50/p95 latency and cost
  (per 1,000 messages in B1, per case in B2). · [D]
- **AC-04** — The output shall include a cost-versus-quality chart, one point per model with its p95, the Pareto
  frontier highlighted, ready for `/evaluation` and the slides. · [D]
- **AC-05** — Each row shall store model id, version, prompt hash, the price used (with its source and date) and the run
  date. · [D]
- **AC-06** — If an arm is unavailable (no access, no quota, provider error), then it shall be recorded as
  "unavailable" with the reason and the benchmark shall continue. · [T]
- **AC-07** — The choice shall apply the lean rule of §4.4 **per task** (§4.2), copied into `eval/PROTOCOL.md` before
  any result, and the "model selection" ADR shall record, for each task, three rows — best measured, cheapest that meets
  the bar, chosen (cheapest that meets the bar and passes the production gate) — and the resulting model map, even if
  the no-LLM option wins. · [D]
- **AC-08** — If the projected spend of a run exceeds its budget (20 USD per full benchmark `[assumption]`), then the
  run shall stop before calling the models and say so (G-OPS-01). · [T]
- **AC-09** — B1 and B2 shall run only in historical mode (`replay`, fixed `DEMO_TODAY`), so every arm sees the same
  "today" and the same transactions; a run in live mode shall be refused. · [T]
- **AC-10** — The report shall include, per arm, a verdict for "benchmark" and for "production" on each criterion of
  §4.5, with the evidence URL and the date it was checked; no verdict is written before the run. · [D]
- **AC-11** — Before B1, each LLM candidate shall pass a structured-output smoke test (one valid JSON object matching
  the intent schema through the Bedrock Converse API); a model that fails is recorded "no structured output" and
  skipped. · [T]
- **AC-12 [P1]** — The `word` task shall report, per arm, the grounding pass rate (rewordings that keep every number, date,
  id and status exactly), the language check, the length check and the blind preference against the template. · [D]
  Deferred to P1 (2026-10-06): not run (`benchmark.json` `word.arms` is empty). Wording is covered instead by the
  ADR 0030 writer, whose every line passes the grounding gate at run time.

## 4. Functional requirements

### 4.1 Candidates (B1 screen)
The screen includes every text model available on demand in `us-east-2` that is **not more expensive than the
incumbent** (Haiku 4.5), one or two sizes per provider family, plus the incumbent, one quality ceiling and Jev. The list
lives in `eval/bench/arms.yaml`; adding a model is one line. Availability: `aws bedrock list-foundation-models` and
`list-inference-profiles` in `us-east-2` on 2026-10-04. Prices: AWS Price List offer files for `us-east-2` (US East,
Ohio), on-demand standard tier, read 2026-10-04, in USD per 1M tokens `[external]` — AmazonBedrock (publicationDate
2026-10-03) and AmazonBedrockFoundationModels (publicationDate 2026-09-30), URLs in §11; the files label some units
"1K tokens" while the values match the per-1M figures.

| Family | Candidates (Bedrock id) | Input / output per 1M |
|---|---|---|
| Amazon Nova | `amazon.nova-micro-v1:0` · `amazon.nova-lite-v1:0` · `amazon.nova-2-lite-v1:0` · `amazon.nova-pro-v1:0` | 0.035 / 0.14 · 0.06 / 0.24 · 0.33 / 2.75 · 0.80 / 3.20 |
| OpenAI open weights | `openai.gpt-oss-20b-1:0` · `openai.gpt-oss-120b-1:0` | 0.07 / 0.30 · 0.15 / 0.60 |
| Mistral | `mistral.ministral-3-8b-instruct` · `mistral.ministral-3-14b-instruct` · `mistral.mistral-large-3-675b-instruct` | 0.15 / 0.15 · 0.20 / 0.20 · 0.50 / 1.50 |
| Google Gemma | `google.gemma-3-12b-it` · `google.gemma-3-27b-it` | 0.09 / 0.29 · 0.23 / 0.38 |
| Meta Llama | `meta.llama3-3-70b-instruct-v1:0` · `meta.llama4-scout-17b-instruct-v1:0` · `meta.llama4-maverick-17b-instruct-v1:0` | 0.72 / 0.72 · 0.17 / 0.66 · 0.24 / 0.97 |
| Qwen | `qwen.qwen3-32b-v1:0` · `qwen.qwen3-235b-a22b-2507-v1:0` | 0.15 / 0.60 · 0.22 / 0.88 |
| NVIDIA | `nvidia.nemotron-nano-3-30b` | 0.06 / 0.24 |
| DeepSeek | `deepseek.v3.2` | 0.62 / 1.85 |
| Anthropic | `us.anthropic.claude-haiku-4-5-20251001-v1:0` (incumbent) · `us.anthropic.claude-sonnet-5-5` (preferred ceiling: cheaper than Sonnet 4.6, if the quota is granted) · `us.anthropic.claude-sonnet-4-6` (ceiling otherwise) | 1.10 / 5.50 · 2.20 / 11.00 · 3.30 / 16.50 |
| TypeSafe | Jev `jev-1.13.0` (typed answers, B1 only; in B2 only as the classifier inside S1) | 0.042 / free (gateway listing, not TypeSafe) |

Models offered only through inference profiles in `us-east-2` (Nova Micro, Nova Pro, Nova 2 Lite, Llama 4, Claude) are
called with their `us.` profile id. All LLM arms get the same prompt and the same structured-output schema. Temperature
is 0 where the model accepts it, otherwise the provider default, and the value used is recorded per arm (D-016); with
`tool_choice_mode` (D-011, below), these are the only request settings that may differ between arms.

**Structured-output method (D-011):** Converse tool use (`toolConfig` with the intent schema), `maxTokens` of at least
512, the same request in the smoke test and B1. `toolChoice` `tool` is documented only for Anthropic Claude 3+ and Amazon
Nova (ToolChoice API reference), so each arm walks the ladder `tool` → `any` → `auto`: it steps down only when Bedrock
rejects the mode (a ValidationException about tool use), the first accepted mode decides and its tool input must match
the schema, and the mode is recorded per arm (`tool_choice_mode`) for B1 to reuse. An arm whose reply fails the schema,
or that rejects every mode, is "no structured output". A ValidationException for an invalid model id or a required
inference profile is "unavailable" with a `config:` reason; any other ValidationException and botocore's
`ParamValidationError` are bugs in our request and stop the standalone smoke test. In B1 an arm is "unavailable" only
when it cannot start (its smoke call fails, for any reason, before any sentence is scored); once it started, an error
on one sentence (throttling after the retries, a dropped connection, a rejected input, an unreadable answer) scores that
sentence as a wrong prediction that stays in the denominator, as D-022 does for a missing tool call, and is counted
per error class in the arm's `errors` `[assumption]`. Each scored item is appended to the items file as it arrives, so
a crash leaves every item already paid for on disk. **Lifecycle:** each arm's model card state is recorded
in `arms.yaml`; five arms are Legacy (Gemma 3 12B and 27B, Llama 3.3 70B, Llama 4 Scout and Maverick; EOL 2027-03-30)
and may come back unavailable, since new customers cannot use Legacy models (AC-06). **Prices
(`eval/bench/prices.yaml`):** all but Jev come from the offer files above and match the table; the Anthropic rows are
the regional, non-global prices that the `us.` profiles pay `[external]`. Only Jev stays `[assumption]` (third-party
gateway listing).

### 4.2 Tasks — one model per task
The rules decide and the tools act, so the agent needs an LLM for only two tasks (spec 04); the analyst's console adds a
third, the judge (spec 18). Each task is screened and
chosen on its own, and may end with **no LLM** if no model beats the no-LLM option — the leanest outcome.

| Task | Where (spec 04) | What the model does | B1 metric | No-LLM option |
|---|---|---|---|---|
| `understand` | `understand` node, only when the classifier is below τ (cascade, spec 11 B3) | intent + slots as structured output | macro-F1 per language, recall of disputes and of `human_request`, slot accuracy (spec 11 §4.1) | B0 rules or B1 TF-IDF + LR |
| `word` | `respond` and `clarify` in S1/S2 | rewords an approved ES/PT template without changing any fact | grounding pass rate, language and length checks, blind preference against the template on 20 samples rated by two team members | templates only |
| `judge` | the analyst's second opinion (spec 18) | verdict on the engine's proposal with reasons tied to evidence | agreement with the expected proposals of the dev cases; share of reasons kept after grounding | no second opinion |

The result is a **model map** (for example `understand → model A`, `word → templates`) loaded by
`nick_of_time.config.resolve(arm)`; it becomes arm S1.

### 4.3 Short list (B2 agent)
At most 6 arms × 20 dev cases × 4 runs, isolated by `run_id`, on the harness of spec 10: the lean model map, the
runner-up map, Haiku 4.5 for both tasks (incumbent), the quality ceiling for both tasks (Sonnet 5.5 if its quota is
granted, else Sonnet 4.6 — this is S2) and S0 as reference.

`coherence_rate` = share of status replies (card, case, notification) whose stated status equals a fresh read of the
system at the end of the turn (spec 04 AC-19). It measures that the agent never reports a state it did not read.

### 4.4 Lean rule (pre-registered per task; thresholds from spec 11 §4.1)
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

### 4.5 Third-party gate (criteria only — the verdicts are an output)
The gate is evaluated **per arm when the benchmark runs**, from the provider's public documents, and written to
`eval/results/bench_gate.csv` (`arm, criterion, verdict: pass|fail|not documented, evidence_url, checked_on`).
"Not documented" fails a production criterion. No arm is excluded or chosen in this spec.
Implementation (`eval/bench/gate.py`): the CSV also carries `needed_benchmark` and `needed_production`; the evidence
lives in `eval/bench/gate_evidence.yaml` (by provider, with per-arm overrides); a criterion without evidence is "not
documented" and is stamped with the evaluation date; `version_pinning` comes from the provider's lifecycle policy (on
Bedrock each model id is one fixed version with its own EOL date and no automatic migration), and the id format is only
a fallback for a provider without that evidence (an id without a version is then "not documented"); `es_pt_quality`
stays "not documented" until the run measures it, and is a production-only criterion because the benchmark itself
measures it (D-012).

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

- **Prices:** `eval/bench/prices.yaml` with the price per 1M input and output tokens per model, the source URL and the
  date checked (ADR 0019). Cost = tokens × price; Platform and infrastructure costs are reported apart.
- **Jev access:** key in SSM `/nickoftime/prod/TYPESAFE_API_KEY` since 2026-10-04; `check_jev` classified an ES and a PT
  sample on that date. Its API returns typed answers (choice, score, yes/no) with probabilities, not free text.
- **Outputs:** `eval/results/bench_b1.csv`, `bench_b2.csv`, `bench_gate.csv`, `apps/web/public/data/benchmark.json`
  (spec 01 §6.2) and `docs/assets/benchmark_cost_quality.svg`.
- **Commands:** `make bench` (B1), `make bench-agent` (B2, uses the harness and the eval hooks of spec 01 §6.8).

## 5. Non-functional requirements
- B1 finishes in under 15 minutes for ~20 arms; B2 in under 45 minutes `[assumption]`.
- Never runs on the held-out set, and never in live mode (AC-09).

## 7. Data model touched
Reads the frozen sentence split and the dev agent cases; writes only result files.

### 7.1 Web export shape (`benchmark.json`, answers spec 12 Q1)
`apps/web/public/data/benchmark.json` is `{generated_at, git_sha, source, data}` (spec 01 §6.2); `data` is below,
written once by T5 after the run. `protocol` comes from the seal block of `eval/PROTOCOL.md`, so `/evaluation` can apply the guard of spec 12 AC-05 (status other than `SEALED`: "development run" notice). A proportion is the rate object of spec 10 §7.2, `{value, numerator, denominator, ci_low, ci_high}`, with the 95% Wilson interval of spec 10 §4.1, computed by the exporter (the browser computes nothing, spec 12 §9; spec 12 AC-06). `null` marks a figure the run fills in.

```json
{
  "label": "[simulated]",
  "protocol": {"status": "SEALED", "sha256": "…"},
  "mode": "replay", "demo_today": "2026-06-01", "run_date": "…",
  "b1": {"arms": [
    {"arm": "…", "model_id": "…", "version": "…", "prompt_hash": "…", "tool_choice_mode": "tool",
     "temperature": 0, "status": "ok", "unavailable_reason": null,
     "price": {"label": "[external]", "input_per_1m_usd": null, "output_per_1m_usd": null, "source": "…", "date": "…"},
     "macro_f1": {"es": null, "pt": null}, "macro_f1_ci": {"es": [null, null], "pt": [null, null]},
     "dispute_recall": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "human_request_recall": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "slot_accuracy": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "missing_tool_calls": null,
     "p50_ms": null, "p95_ms": null, "cost_per_1000_usd": null, "meets_bar": null, "pareto": null, "same_family_as_generator": null,
     "gate": {"benchmark_pass": null, "production_pass": null, "criteria": [
       {"criterion": "…", "needed_benchmark": null, "needed_production": null, "verdict": "pass",
        "evidence_url": "…", "checked_on": "…"}]}}
  ]},
  "word": {"arms": [
    {"arm": "…", "grounding_pass_rate": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "language_check": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "length_check": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "blind_preference": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}}
  ]},
  "judge": {"arms": [
    {"arm": "…", "agreement": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "reasons_kept": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}}
  ]},
  "b2": {"set": "dev", "cases": 20, "runs_per_case": 4, "arms": [
    {"arm": "S0", "safe_automated_resolution": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "unsafe_outcomes": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "receipt_rate": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null},
     "coherence_rate": {"value": null, "numerator": null, "denominator": null, "ci_low": null, "ci_high": null}, "p50_ms": null, "p95_ms": null, "cost_per_case_usd": null}
  ]},
  "model_map": {"understand": {"best_measured": "…", "cheapest_meeting_bar": "…", "chosen": "…"},
                "word": {}, "judge": {}}
}
```
- `label` is `[simulated]` (dev cases and sentences are generated). `mode` is always `replay` (AC-09), `demo_today` the
  fixed date (ADR 0020), `run_date` an ISO date (AC-05), the same replay date.
- `b1_model` (AC-01, AC-05): the B1 TF-IDF + LR file the run scored, `{path, sha256, sklearn_version, source}`; on test
  it is the file of spec 11 `classifier.json` `b1_model`; with the reason instead when B1 could not run, `null` when
  the run had no B1 arm.
- `b1.arms[]` (AC-01, AC-03, AC-05, AC-06, AC-10): ids and hashes as stored per row; `status` is `ok`, `unavailable` or
  `no structured output`, with its reason; `price` in USD per 1M tokens with source and date, `label` `[external]`
  (`[assumption]` for Jev); `macro_f1` per language with its 95% interval; the recalls and `slot_accuracy` (§4.2) as
  rate objects; `missing_tool_calls` an integer count, each scored as a wrong prediction (`eval/PROTOCOL.md` §2.1,
  D-022); `p50_ms` and `p95_ms` in milliseconds per message; `cost_per_1000_usd`; `meets_bar` and `pareto` bools from
  §4.4 and AC-04 (the chart needs cost, p95, macro-F1 and `pareto`); `same_family_as_generator` bool, true when the
  arm's model family wrote the split it is scored on (the test split: DeepSeek V3.2), so its result is flagged
  (ADR 0025, `eval/PROTOCOL.md` §1.1).
- `gate` (AC-10, §4.5, rows of `bench_gate.csv`): `benchmark_pass` and `production_pass` bools; `criteria[]` one entry
  per criterion with what each level needs, `verdict` (`pass`, `fail` or `not documented`), evidence URL and check
  date `[external]`.
- `word.arms[]` (AC-12): `grounding_pass_rate`, `language_check`, `length_check` and `blind_preference` as rate
  objects. `judge.arms[]` (§4.2): `agreement` with the expected proposals and `reasons_kept` after grounding, rate
  objects.
- `b2` (AC-02, AC-03): `cases` and `runs_per_case` integers; per arm, rate objects, `p50_ms` and `p95_ms` per turn and
  `cost_per_case_usd`.
- `model_map` (AC-07): per task, the three rows as arm names (names carry no label); "no LLM" is written `"templates"`
  or `"none"` `[assumption]`.

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — candidates (§4.1):** **Decided (lead, 2026-10-04):** the ~20 Bedrock models, Jev, and Sonnet 5.5 as the
  preferred ceiling because it is cheaper than Sonnet 4.6.
- **Q2 — budget:** **Decided (lead, 2026-10-04):** 20 USD per full run, and one model per task (§4.2) so each task
  pays only for what it needs.
- **Q3 — where to choose:** **Decided (lead, 2026-10-04):** choose on dev (B2) and confirm on the held-out in spec 10;
  never choose on the held-out.
- **Q4 — lean rule (§4.4):** **Decided (lead, 2026-10-04):** per task: hard limits, then "not significantly worse than
  the best", then the cheapest, then the production gate. The `judge` task joins in P2; until then it runs on Haiku 4.5.
- Claude Sonnet 5.5 is **not available to the team account** on 2026-10-04: the applied quota is 0 tokens per minute
  (`L-94A31E46`, `L-31AB82D0`; AWS default 6,000,000), a quota request below the default is rejected, and a test call
  returns `AccessDeniedException` ("not available for this account … contact AWS Sales"). Access goes through AWS
  Sales; until then it is recorded unavailable (AC-06) and Sonnet 4.6 is the ceiling.
- **D-016 — temperature (lead, 2026-10-04):** 0 where the model accepts it, otherwise the provider default; the value
  used is recorded per arm (§4.1, `eval/PROTOCOL.md` §2.1).

## 9. Out of scope
Public third-party leaderboards; fine-tuning; batch or provisioned throughput pricing; latency of Platform itself
(reported, not optimized).

## 10. Plan, tasks and verification
- [x] T1 — `eval/bench/arms.yaml` and `prices.yaml` (each price confirmed in the AWS Price List offer files, with
      date); budget guard · AC-05, AC-08
- [x] T2 — B1 runner over spec 11 arms + the LLM candidates + Jev; unavailable arms recorded · AC-01, AC-06
      (`eval/bench/b1.py`: smoke then B1 with exactly `smoke.converse_request`, the `understand` prompt and schema of
      spec 04; B1 TF-IDF + LR is the spec 11 model, trained or loaded by the command as T5 says; per-sentence errors scored
      wrong and counted in `errors`, items appended to disk as they arrive, §4.1; the tool description is the
      production one, `nick_of_time.llm.base.TOOL_DESCRIPTION`, so the request equals what S1 sends, and a missing
      slot key is scored as null, D-078)
- [ ] T3 — structured-output smoke test (done, `eval/bench/smoke.py`, AC-11; live run pending Bedrock invoke
      rights); `word` task set (40 template instances from dev cases) and blind preference sheet (pending spec 09) ·
      AC-11, AC-12
- [ ] T3b — short list and B2 runner on the harness (spec 10), historical mode only, `coherence_rate` · AC-02, AC-09
- [x] T4 — gate evaluation per arm with evidence and date · AC-10
- [x] T5 — table, Pareto chart, JSON for `/evaluation` · AC-03, AC-04 (`eval/bench/report.py`, `chart.py`; `make bench`
      writes the result files only on the sealed test split, after the shared seal guard of spec 10
      (`check_seal` with the classifier split manifest, then `claim_run("bench")` before any model call; it refuses a
      second run or an existing official output) and labels them `test_review: rules-v1` (PROTOCOL §1.1, ADR 0028);
      `make bench-dev` writes a labeled development run to the git-ignored `eval/.runs/bench/`; `--from-items`
      re-renders the table and the chart without models; failed sentences are reported as `errors`, apart from missing
      tool calls; `es_pt_quality` is written by the run, AC-10). B1 TF-IDF + LR (spec 11): `make bench-dev` trains it as
      `make classifier` does (fit on train, sigmoid-calibrated on validation, fixed seed) into its run folder; `make
      bench` never refits it on test and loads the exact file the classifier-test run recorded in `classifier.json`
      `b1_model` (path and sha256), refused before the claim when that record, the file or its hash is missing or
      differs, so **`make classifier-test` runs before `make bench`**; `benchmark.json` records the file as `b1_model`.
      The run date and the development folder name are the fixed replay `DEMO_TODAY` the arms read (ADR 0020), never
      a `DEMO_TODAY` set in the environment.
- [x] T6 — lean rule per task in `eval/PROTOCOL.md` before the run; "model selection" ADR with the three rows per task
      (rule computed by `report.select`, with the reading of §2.3 where it is silent in `SELECTION_READING`,
      `[assumption]` pending lead decision D-077; ADR 0027 drafted as Proposed with development numbers only)
      and the model map · AC-07. Run order on test: `make classifier-test`, then `make bench` (T5), so the B1 row is
      the model spec 11 exported.


### Result on the sealed test split (closing review, 2026-10-06)
One run of `make bench` under `protocol-v1`, started 2026-10-06T01:43:43Z (`eval/results/bench/bench.start.json`), on the
236 test sentences of spec 11, 24 arms (18 measured). All figures are `[simulated]` (model-written sentences, ADR 0025;
test split decided by `rules-v1`, ADR 0028). Sources: `apps/web/public/data/benchmark.json` (generated
2026-10-06T02:07:29Z), `eval/results/bench_b1.md`, `bench_b1.csv`, `bench_gate.csv`, `bench_b1_items.jsonl`, and the
chart `docs/assets/benchmark_cost_quality.svg`.

| Arm | Accuracy [95% CI] | Macro-F1 ES / PT | `human_request` recall | p95 ms | USD per 1k msgs |
|---|---|---|---|---|---|
| Sonnet 4.6 (best measured) | 0.979 [0.951, 0.991] | 0.966 / 0.991 | 45/47 | 1,369 | 5.15 |
| Mistral Large 3 | 0.975 [0.946, 0.988] | 0.966 / 0.983 | 45/47 | 1,368 | 0.31 |
| DeepSeek V3.2 | 0.966 [0.935, 0.983] | 0.950 / 0.983 | 45/47 | 9,684 | 0.69 |
| Haiku 4.5 | 0.924 [0.883, 0.951] | 0.932 / 0.915 | 43/47 | 1,631 | 1.84 |
| B1 TF-IDF + LR | 0.915 [0.873, 0.945] | 0.916 / 0.914 | 42/47 | 1.4 | 0 |
| B0 rules | 0.614 [0.551, 0.674] | 0.583 / 0.668 | 30/47 | 0.31 | 0 |

- **Model map (AC-07):** `understand` → **B0 rules** (no LLM): every measured arm fails rule 1, because the best
  Spanish `human_request` recall is 21/23 = 0.913 against a floor of 0.95 per language; `word` → templates (the ADR 0030
  writer is a separate, switchable setting); `judge` → Haiku 4.5 (not benchmarked, P2). Recorded in ADR 0027 with the
  D-077 reading.
- **Unavailable or no structured output (AC-06, AC-11):** Gemma 3 12B and 27B, Llama 3.3 70B and Nemotron Nano 3 returned
  no tool call; Sonnet 5.5 is not enabled on the account; Jev had no key.
- **Spend:** 2.52 USD `[data]` (PR #226).

### Open items (closing review, 2026-10-06)
Every [T] criterion has a citing test (`python scripts/ci/ac_coverage.py` on `main` at `a2fa15e`).
- **B2 on the graph (AC-02, T3b, P1)** and the **`word` task (AC-12, T3, P1)**: not run.
- **Live smoke run (T3).** The structured-output smoke ran inside `make bench` (AC-11); T3 stays open for the `word` set.
## 11. Sources
External sources checked on 2026-10-04.
- **Bedrock availability:** `aws bedrock list-foundation-models --region us-east-2` and `list-inference-profiles`
  (team account, 2026-10-04) · model cards:
  https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-supported-models-features.html ·
  Converse API (tool use): https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html ·
  ToolChoice (`tool` only for Anthropic Claude 3 and Amazon Nova):
  https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html
- **Bedrock lifecycle and version pinning:** https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html
  ("Migration will not happen automatically"; "New customers can't use Legacy models") · model cards (state, EOL date
  per id), linked per arm in `eval/bench/arms.yaml`: https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html
- **Bedrock prices:** AWS Price List offer files, `us-east-2`, read 2026-10-04 — AmazonBedrock (publicationDate
  2026-10-03): https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-2/index.json ·
  AmazonBedrockFoundationModels (publicationDate 2026-09-30):
  https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrockFoundationModels/current/us-east-2/index.json ·
  pricing page: https://aws.amazon.com/bedrock/pricing/
- **Evidence for the gate, to re-check on the run date:**
  - Amazon Bedrock — model providers have no access to prompts and completions:
    https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html · data not used to improve base models;
    in scope for ISO and SOC: https://aws.amazon.com/bedrock/security-compliance/ · cross-region inference profiles:
    https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html
  - Anthropic API (fallback) — "Anthropic may not train models on Customer Content from Services":
    https://www.anthropic.com/legal/commercial-terms · SOC 2 Type II, ISO 27001, ISO 42001:
    https://support.claude.com/en/articles/10015870-what-certifications-has-anthropic-obtained
  - Jev (TypeSafe AI) — API and versions: https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models · privacy,
    DPA and retention: https://docs.typesafe.ai/legal.md · access history: https://en.wikipedia.org/wiki/Jev_(AI_model) ·
    gateway price: https://opper.ai/typesafe/jev-1-13-0
- **Bedrock quotas:** `aws service-quotas list-service-quotas --service-code bedrock --region us-east-2` (2026-10-04).
- **Internal:** ADR 0009 (synthetic data only), ADR 0015 (pre-registered selection), ADR 0019 (official sources), ADR
  0020 (two modes), spec 11 §4 and Q1 (thresholds, McNemar), spec 10 (harness, held-out),
  `contracts/policies.yaml` G-OPS-01, `scripts/checks/check_jev.py`.
- Budget and run-time limits marked `[assumption]` have no external source.
