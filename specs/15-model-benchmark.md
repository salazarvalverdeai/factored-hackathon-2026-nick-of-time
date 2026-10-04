# Spec 15 — Model benchmark (cost vs quality, lean choice)

- **Feature:** one command that runs every candidate model on the same data and produces a table, a cost-versus-quality
  chart and an eligibility verdict per model, so each role (understanding, the agent) gets the **cheapest model that is
  good enough**, chosen from evidence.
- **Status:** Draft (updated 2026-10-04: broad Bedrock screen, lean rule, eligibility verdict as an output)
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
whose quality is within the bar of the best. Whether a model may be used in production is also a **result of the run**,
checked against public evidence on the run date. The model is chosen on development data; the held-out run in spec 10
then confirms it against S0, so nothing is tuned on the held-out.

## 3. Acceptance criteria (EARS)
Same numbers as issue #17; AC-10 onward are added by this spec.

- **AC-01** — When `make bench` runs, every arm in `eval/bench/arms.yaml` (B0 rules, B1 TF-IDF + LR, the LLM candidates
  of §4.1 and Jev) shall be evaluated on the same frozen test split. · [C]
- **AC-02** — B2 shall run the graph with the short list of §4.2 and with S0 on the 20 dev cases × 4 runs. · [C]
- **AC-03** — The output shall include a table with quality (macro-F1 per language over the five intents of spec 11 in
  B1; safe automated resolution, unsafe outcomes, `receipt_rate` and `coherence_rate` in B2), p50/p95 latency and cost
  (per 1,000 messages in B1, per case in B2). · [D]
- **AC-04** — The output shall include a cost-versus-quality chart, one point per model with its p95, the Pareto
  frontier highlighted, ready for `/evaluation` and the slides. · [D]
- **AC-05** — Each row shall store model id, version, prompt hash, the price used (with its source and date) and the run
  date. · [D]
- **AC-06** — If an arm is unavailable (no access, no quota, provider error), then it shall be recorded as
  "unavailable" with the reason and the benchmark shall continue. · [T]
- **AC-07** — The choice shall apply the lean rule of §4.3, copied into `eval/PROTOCOL.md` before any result, and the
  "model selection" ADR shall record three rows — best measured, cheapest that meets the bar, chosen (cheapest that meets
  the bar and passes the production gate) — even if the baseline wins. · [D]
- **AC-08** — If the projected spend of a run exceeds its budget (20 USD per full benchmark `[assumption]`), then the
  run shall stop before calling the models and say so (G-OPS-01). · [T]
- **AC-09** — B1 and B2 shall run only in historical mode (`replay`, fixed `DEMO_TODAY`), so every arm sees the same
  "today" and the same transactions; a run in live mode shall be refused. · [T]
- **AC-10** — The report shall include, per arm, a verdict for "benchmark" and for "production" on each criterion of
  §4.4, with the evidence URL and the date it was checked; no verdict is written before the run. · [D]
- **AC-11** — Before B2, each short-listed LLM shall pass a tool-use smoke test (one valid tool call through the
  Bedrock Converse API); a model that fails is recorded "not agent-capable" and replaced by the next one in the B1
  ranking. · [T]

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
| Anthropic | `us.anthropic.claude-haiku-4-5-20251001-v1:0` (incumbent) · `us.anthropic.claude-sonnet-4-6` (quality ceiling) · `us.anthropic.claude-sonnet-5-5` (if the account's quota allows) | 1.10 / 5.50 · 3.30 / 16.50 · 2.20 / 11.00 |
| TypeSafe | Jev `jev-1.13.0` (typed answers, B1 only; in B2 only as the classifier inside S1) | 0.042 / free (gateway listing, not TypeSafe) |

Models offered only through inference profiles in `us-east-2` (Nova Micro, Nova Pro, Nova 2 Lite, Llama 4, Claude) are
called with their `us.` profile id. All LLM arms get the same prompt, the same structured-output schema and temperature
0; differences come only from the model.

### 4.2 Short list (B2 agent)
The 3 best arms of B1 under the lean rule (§4.3) that pass the tool-use smoke test (AC-11), plus the incumbent (Haiku
4.5), the quality ceiling (Sonnet 4.6) and S0 as reference. At most 6 arms × 20 dev cases × 4 runs, isolated by
`run_id`, on the harness of spec 10.

`coherence_rate` = share of status replies (card, case, notification) whose stated status equals a fresh read of the
system at the end of the turn (spec 04 AC-19). It measures that the agent never reports a state it did not read.

### 4.3 Lean rule (pre-registered; thresholds from spec 11 Q1)
1. **Hard limits** — discard an arm with PT macro-F1 < 0.80, p95 > 1.5 s per message (B1) or > 6 s per turn (B2), or any
   unsafe outcome in B2.
2. **Quality bar** — keep the arms whose quality (B1: the lower of ES and PT macro-F1; B2: safe automated resolution)
   is within 2 points of the best arm, or whose 95% CI overlaps the best.
3. **Lean choice** — among those, the **cheapest** (B1: cost per 1,000 messages; B2: cost per case); a tie goes to the
   lower p95.
4. **Eligibility** — the chosen arm must pass the production gate of §4.4 on the run date; if it does not, the next
   cheapest arm that meets the bar and passes the gate is chosen, and the ADR says why.
5. If no LLM arm beats B0 with significance (McNemar, p < 0.05), B0 stays and that is reported (spec 11 §4).

### 4.4 Third-party gate (criteria only — the verdicts are an output)
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
- **Q1 — candidates (§4.1):** ~20 Bedrock models no more expensive than Haiku 4.5, plus Sonnet 4.6 as the ceiling and
  Jev. Add or remove any?
- **Q2 — budget:** 20 USD per full benchmark run as the stop limit. OK?
- **Q3 — where to choose:** choose on dev (B2) and confirm on the held-out in spec 10 — never choose on the held-out. OK?
- **Q4 — lean rule (§4.3):** cheapest arm within 2 points of the best, after hard limits, then the production gate. OK?
- Assumption: Claude Sonnet 5.5 enters only if the account's on-demand quota allows it (it was 0 when checked during
  setup); otherwise AC-06 applies.

## 9. Out of scope
Public third-party leaderboards; fine-tuning; batch or provisioned throughput pricing; latency of Platform itself
(reported, not optimized).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/bench/arms.yaml` and `prices.yaml` (each price confirmed on the pricing page, with date); budget guard ·
      AC-05, AC-08
- [ ] T2 — B1 runner over spec 11 arms + the LLM candidates + Jev; unavailable arms recorded · AC-01, AC-06
- [ ] T3 — tool-use smoke test and short list; B2 runner on the harness (spec 10), historical mode only,
      `coherence_rate` · AC-02, AC-09, AC-11
- [ ] T4 — gate evaluation per arm with evidence and date · AC-10
- [ ] T5 — table, Pareto chart, JSON for `/evaluation` · AC-03, AC-04
- [ ] T6 — lean rule in `eval/PROTOCOL.md` before the run; "model selection" ADR with the three rows · AC-07

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
- **Internal:** ADR 0009 (synthetic data only), ADR 0015 (pre-registered selection), ADR 0019 (official sources), ADR
  0020 (proposed, two modes), spec 11 §4 and Q1 (thresholds, McNemar), spec 10 (harness, held-out),
  `contracts/policies.yaml` G-OPS-01, `scripts/checks/check_jev.py`.
- Budget and run-time limits marked `[assumption]` have no external source.
