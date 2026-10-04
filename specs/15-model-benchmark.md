# Spec 15 — Model benchmark (cost vs quality)

- **Feature:** one command that runs every candidate model on the same data and produces a table and a cost-versus-quality
  chart, so each role (understanding, the agent) gets its model from evidence.
- **Status:** Draft (updated 2026-10-04: historical mode, coherence metric, five intents, sources)
- **Owner:** @salazarvalverdeai (B2 runs on @vldiego's harness) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning, Technical Judgment (explicit trade-offs of accuracy, latency and cost)
- **Depends on:** 09 (data), 11 (arms B0–B3), 10 (harness for B2), 04 (graph arms) · **Enables:** the model-selection
  ADR, `/evaluation`, the results slide · **ADRs:** 0009, 0015, 0019, 0020 (proposed)
- **Issue:** #17

---

## 1. Introduction
"Which model?" is answered with numbers, not preference. Two levels: **B1** compares models on the understanding task
alone (fast, cheap, many runs); **B2** compares the whole agent with each model on full cases (slower, the number that
matters). The model is chosen on development data; the held-out run in spec 10 then confirms the chosen configuration
against S0, so nothing is tuned on the held-out.

## 3. Acceptance criteria (EARS)
Same numbers as issue #17.

- **AC-01** — When `make bench` runs, every B1 arm (rules · TF-IDF + LR · Claude Haiku 4.5 · Claude Sonnet 4.6 · Jev)
  shall be evaluated on the same frozen test split. · [C]
- **AC-02** — B2 shall run the graph with Haiku 4.5 and with Sonnet 4.6 (and Jev if it supports tool calling) on the 20
  dev cases × 4 runs. · [C]
- **AC-03** — The output shall include a table with quality (macro-F1 per language over the five intents of spec 11 in
  B1; safe automated resolution, unsafe outcomes, `receipt_rate` and `coherence_rate` in B2), p50/p95 latency and cost
  (per 1,000 messages in B1, per case in B2). · [D]
- **AC-04** — The output shall include a cost-versus-quality chart, one point per model with its p95, ready for
  `/evaluation` and the slides. · [D]
- **AC-05** — Each row shall store model id, version, prompt hash, the price used (with its source and date) and the run
  date. · [D]
- **AC-06** — If an arm is unavailable (for example Jev without access), then it shall be recorded as "unavailable" with
  the reason and the benchmark shall continue. · [T]
- **AC-07** — The choice shall be written in the "model selection" ADR applying the pre-registered rule (spec 11 §4 for
  B1; ADR 0015 for B2), even if the baseline wins. · [D]
- **AC-08** — If the projected spend of a run exceeds its budget (20 USD per full benchmark `[assumption]`), then the
  run shall stop before calling the models and say so (G-OPS-01). · [T]
- **AC-09** — B1 and B2 shall run only in historical mode (`replay`, fixed `DEMO_TODAY`), so every arm sees the same
  "today" and the same transactions; a run in live mode shall be refused. · [T]

## 4. Functional requirements
| Level | Arms | Data | Quality metric | Runs |
|---|---|---|---|---|
| **B1 — component** | B0 rules · B1 TF-IDF + LR · Haiku 4.5 · Sonnet 4.6 · Jev | test split of the sentence set (spec 09/11) | macro-F1 ES and PT (+ CI), slot accuracy | 1 per arm (LLM arms: temperature 0) |
| **B2 — agent** | S1 (Haiku 4.5) · S2 (Sonnet 4.6) · Jev (if tools work) · S0 as reference | 20 dev agent cases, historical mode, including the status and coherence cases of spec 10 | safe automated resolution, unsafe outcomes (gate = 0), `receipt_rate`, `coherence_rate`, pass^4 | 4 per case, isolated by `run_id` |

`coherence_rate` = share of status replies (card, case, notification) whose stated status equals a fresh read of the
system at the end of the turn (spec 04 AC-19). It measures that the agent never reports a state it did not read.

- **Prices:** `eval/bench/prices.yaml` with the on-demand price per 1M input and output tokens for each model, the source
  URL (Bedrock: the Amazon Bedrock pricing page) and the date checked, as ADR 0019 requires. Cost = tokens × price;
  Platform and infrastructure costs are reported apart.
- **Jev access** (researched 2026-10-04, sources in §11): TypeSafe AI's "System One" decision model — it returns typed
  answers (choice, score, yes/no) with probabilities, not free text, so it fits **B1** (intent as a choice question)
  and, in B2, only as the classifier inside S1 (free text still needs an LLM). API `https://api.typesafe.ai/v1/systemone`,
  `Authorization: Bearer`, key in `TYPESAFE_API_KEY` (SSM `/nickoftime/prod/TYPESAFE_API_KEY`), pinned model
  `jev-1.13.0`. Access is early access (console invite; new sign-ups were paused on 2026-09-22, per Wikipedia). Price reported by
  a gateway (opper.ai), not by TypeSafe: 0.042 USD per 1M input tokens, output free — to confirm in the console. English is its primary language; ES/PT must be measured. Without a
  key, AC-06 applies.

### 4.1 Third-party model gate (applies to every model arm)
A model can be **benchmarked** with synthetic data if it passes the "benchmark" column; it can be **chosen for
production** only if it also passes the "production" column. The result is recorded per arm in the ADR.

| Criterion | Benchmark | Production | Bedrock (Haiku 4.5 / Sonnet 4.6) | Jev (TypeSafe) | Anthropic API (fallback) |
|---|---|---|---|---|---|
| Data sent is synthetic only (ADR 0009) | required | — | ✅ | ✅ | ✅ |
| Provider does not train on our requests | required | required | ✅ (AWS) | ✅ (privacy policy) | ✅ (API terms) |
| Retention documented / zero retention available | — | required | ✅ | DPA; zero retention for enterprise only | ✅ |
| Processing region documented | — | required | ✅ `us-east-2` (+ US cross-region profile) | ❌ not documented | US |
| Security certification public (SOC 2 / ISO 27001) | — | required | ✅ | ❌ not public | ✅ |
| Credentials outside the repo, least privilege | required | required | IAM role / user | API key in SSM | API key in SSM |
| Version pinning | required | required | model id | `jev-1.13.0` | model id |
| Availability: GA, SLA or status page | — | required | ✅ | ❌ early access, `529 Overloaded` documented | ✅ |
| ES/PT quality measured on our data | required | required | B1/B2 | B1 | B1/B2 |

**Consequence:** Jev can be benchmarked; even if it wins B1, it is **not eligible for production** until its region,
certification and availability are documented. The ADR then records "best measured" and "best eligible" separately.
Sources for each cell are in §11; a cell without a source is marked ❌ (not documented).
- **Outputs:** `eval/results/bench_b1.csv`, `eval/results/bench_b2.csv`, `apps/web/public/data/benchmark.json`
  (spec 01 §6.2) and `docs/assets/benchmark_cost_quality.svg`.
- **Commands:** `make bench` (B1), `make bench-agent` (B2, uses the harness and the eval hooks of spec 01 §6.8).

## 5. Non-functional requirements
- B1 finishes in under 10 minutes; B2 in under 45 minutes `[assumption]`.
- Same data, same prompts and temperature 0 for every LLM arm; differences come only from the model.
- Never runs on the held-out set, and never in live mode (AC-09).

## 7. Data model touched
Reads the frozen sentence split and the dev agent cases; writes only result files.

## 8. Assumptions and open questions (gate 1)
- **Q1 — Jev:** request access (waitlist → console invite → key in SSM). Without a key by the benchmark run it is
  reported as unavailable. Approve the gate in §4.1?
- **Q2 — budget:** 20 USD per full benchmark run as the stop limit. OK?
- **Q3 — where to choose:** choose on dev (B2) and confirm on the held-out in spec 10 — never choose on the held-out. OK?
- **Q4 — Sonnet 4.5:** add it as an extra point on the chart (it is available on Bedrock), or keep only Haiku 4.5 and
  Sonnet 4.6? Proposal: only the two.

## 9. Out of scope
Public third-party benchmarks; fine-tuning; latency of Platform itself (reported, not optimized).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/bench/prices.yaml` with sources; budget guard; third-party gate table per arm · AC-05, AC-08
- [ ] T2 — B1 runner over spec 11 arms + LLM arms · AC-01, AC-06
- [ ] T3 — B2 runner on top of the harness (spec 10) with arms S0/S1/S2/Jev, historical mode only, `coherence_rate` · AC-02, AC-09
- [ ] T4 — table, JSON for `/evaluation`, cost-vs-quality chart · AC-03, AC-04
- [ ] T5 — "model selection" ADR · AC-07

## 11. Sources
External sources checked on 2026-10-04.
- **Jev (TypeSafe AI):** API and pinned version — https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models ·
  no training on user data, DPA, zero retention for enterprise only (region and certifications not stated) —
  https://docs.typesafe.ai/legal.md · sign-ups paused on 2026-09-22 — https://en.wikipedia.org/wiki/Jev_(AI_model) ·
  gateway price — https://opper.ai/typesafe/jev-1-13-0
- **Amazon Bedrock:** model providers have no access to prompts and completions —
  https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html · data not used to improve base models;
  in scope for ISO and SOC — https://aws.amazon.com/bedrock/security-compliance/ · cross-region inference profiles —
  https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html · prices —
  https://aws.amazon.com/bedrock/pricing/
- **Anthropic API (fallback):** "Anthropic may not train models on Customer Content from Services" —
  https://www.anthropic.com/legal/commercial-terms · SOC 2 Type II, ISO 27001, ISO 42001 —
  https://support.claude.com/en/articles/10015870-what-certifications-has-anthropic-obtained
- **Internal:** ADR 0009 (synthetic data only), ADR 0015 (pre-registered selection), ADR 0019 (official sources), ADR
  0020 (proposed, two modes), spec 11 §4 (decision rule), spec 10 (harness, held-out), `contracts/policies.yaml` G-OPS-01.
- Budget and run-time limits marked `[assumption]` have no external source.
