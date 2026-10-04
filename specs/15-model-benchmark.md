# Spec 15 — Model benchmark (cost vs quality, lean choice)

- **Feature:** one command that runs every candidate model on the same data and produces a table, a cost-versus-quality
  chart and an eligibility verdict per model, so each role (understanding, the agent) gets the **cheapest model that is
  good enough**, chosen from evidence.
- **Status:** Draft (updated 2026-10-04: broad Bedrock screen, one model per task, lean rule, eligibility as an output;
  Q1–Q2 decided by the lead)
- **Owner:** @salazarvalverdeai (B2 runs on @vldiego's harness) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning, Technical Judgment (explicit trade-offs of accuracy, latency and cost)
- **Depends on:** 09 (data), 11 (arms B0–B3), 10 (harness for B2), 04 (graph arms) · **Enables:** the model-selection
  ADR, `/evaluation`, the results slide · **ADRs:** 0009, 0015, 0019, 0020 (proposed)
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
- **AC-02** — B2 shall run the graph with the short list of §4.3 and with S0 on the 20 dev cases × 4 runs. · [C]
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
- **AC-12** — The `word` task shall report, per arm, the grounding pass rate (rewordings that keep every number, date,
  id and status exactly), the language check, the length check and the blind preference against the template. · [D]

## 4. Functional requirements

### 4.1 Candidates (B1 screen)
The screen includes every text model available on demand in `us-east-2` that is **not more expensive than the
incumbent** (Haiku 4.5), one or two sizes per provider family, plus the incumbent, one quality ceiling and Jev. The list
lives in `eval/bench/arms.yaml`; adding a model is one line. Availability: `aws bedrock list-foundation-models` and
`list-inference-profiles` in `us-east-2` on 2026-10-04. Prices: AWS Price List API, US East (Ohio), on-demand standard
tier, 2026-10-04, in USD per 1M tokens `[external, to verify in T1 against the pricing page]` — the API labels some units
"1K tokens" while the values match the pricing page's per-1M figures.

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
called with their `us.` profile id. All LLM arms get the same prompt, the same structured-output schema and temperature
0; differences come only from the model.

### 4.2 Tasks — one model per task
The rules decide and the tools act, so the agent needs an LLM for only two tasks (spec 04). Each task is screened and
chosen on its own, and may end with **no LLM** if no model beats the no-LLM option — the leanest outcome.

| Task | Where (spec 04) | What the model does | B1 metric | No-LLM option |
|---|---|---|---|---|
| `understand` | `understand` node, only when the classifier is below τ (cascade, spec 11 B3) | intent + slots as structured output | macro-F1 per language, recall of disputes and of `human_request`, slot accuracy (spec 11 §4.1) | B0 rules or B1 TF-IDF + LR |
| `word` | `respond` and `clarify` in S1/S2 | rewords an approved ES/PT template without changing any fact | grounding pass rate, language and length checks, blind preference against the template on 20 samples rated by two team members | templates only |

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

## 8. Assumptions and open questions (gate 1)
- **Q1 — candidates (§4.1):** **Decided (lead, 2026-10-04):** the ~20 Bedrock models, Jev, and Sonnet 5.5 as the
  preferred ceiling because it is cheaper than Sonnet 4.6.
- **Q2 — budget:** **Decided (lead, 2026-10-04):** 20 USD per full run, and one model per task (§4.2) so each task
  pays only for what it needs.
- **Q3 — where to choose:** choose on dev (B2) and confirm on the held-out in spec 10 — never choose on the held-out. OK?
- **Q4 — lean rule (§4.4):** per task: hard limits, then "not significantly worse than the best", then the cheapest,
  then the production gate. OK?
- Assumption: Claude Sonnet 5.5 had an on-demand quota of 0 tokens per minute on 2026-10-04 (Service Quotas
  `L-94A31E46` cross-region, `L-31AB82D0` global; both adjustable). It enters only if an increase is granted before the
  run; otherwise it is recorded unavailable (AC-06) and Sonnet 4.6 is the ceiling.

## 9. Out of scope
Public third-party leaderboards; fine-tuning; batch or provisioned throughput pricing; latency of Platform itself
(reported, not optimized).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/bench/arms.yaml` and `prices.yaml` (each price confirmed on the pricing page, with date); budget guard ·
      AC-05, AC-08
- [ ] T2 — B1 runner over spec 11 arms + the LLM candidates + Jev; unavailable arms recorded · AC-01, AC-06
- [ ] T3 — structured-output smoke test; `word` task set (40 template instances from dev cases) and blind preference
      sheet · AC-11, AC-12
- [ ] T3b — short list and B2 runner on the harness (spec 10), historical mode only, `coherence_rate` · AC-02, AC-09
- [ ] T4 — gate evaluation per arm with evidence and date · AC-10
- [ ] T5 — table, Pareto chart, JSON for `/evaluation` · AC-03, AC-04
- [ ] T6 — lean rule per task in `eval/PROTOCOL.md` before the run; "model selection" ADR with the three rows per task
      and the model map · AC-07

## 11. Sources
External sources checked on 2026-10-04.
- **Bedrock availability:** `aws bedrock list-foundation-models --region us-east-2` and `list-inference-profiles`
  (team account, 2026-10-04) · model cards:
  https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-supported-models-features.html ·
  Converse API (tool use): https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- **Bedrock prices:** AWS Price List API (`aws pricing get-products --service-code AmazonBedrock` and
  `AmazonBedrockFoundationModels`, location US East (Ohio), 2026-10-04) · pricing page: https://aws.amazon.com/bedrock/pricing/
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
  0020 (proposed, two modes), spec 11 §4 and Q1 (thresholds, McNemar), spec 10 (harness, held-out),
  `contracts/policies.yaml` G-OPS-01, `scripts/checks/check_jev.py`.
- Budget and run-time limits marked `[assumption]` have no external source.
