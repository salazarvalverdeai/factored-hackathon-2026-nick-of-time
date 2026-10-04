# Spec 15 — Model benchmark (cost vs quality)

- **Feature:** one command that runs every candidate model on the same data and produces a table and a cost-versus-quality
  chart, so each role (understanding, the agent) gets its model from evidence.
- **Status:** Draft
- **Owner:** @salazarvalverdeai (B2 runs on @vldiego's harness) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning, Technical Judgment (explicit trade-offs of accuracy, latency and cost)
- **Depends on:** 09 (data), 11 (arms B0–B3), 10 (harness for B2), 04 (graph arms) · **Enables:** the model-selection
  ADR, `/evaluation`, the results slide · **ADRs:** 0009, 0015
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
- **AC-03** — The output shall include a table with quality (macro-F1 per language in B1; safe automated resolution,
  unsafe outcomes and `receipt_rate` in B2), p50/p95 latency and cost (per 1,000 messages in B1, per case in B2). · [D]
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

## 4. Functional requirements
| Level | Arms | Data | Quality metric | Runs |
|---|---|---|---|---|
| **B1 — component** | B0 rules · B1 TF-IDF + LR · Haiku 4.5 · Sonnet 4.6 · Jev | test split of the sentence set (spec 09/11) | macro-F1 ES and PT (+ CI), slot accuracy | 1 per arm (LLM arms: temperature 0) |
| **B2 — agent** | S1 (Haiku 4.5) · S2 (Sonnet 4.6) · Jev (if tools work) · S0 as reference | 20 dev agent cases | safe automated resolution, unsafe outcomes (gate = 0), `receipt_rate`, pass^4 | 4 per case, isolated by `run_id` |

- **Prices:** `eval/bench/prices.yaml` with the on-demand price per 1M input and output tokens for each model, the source
  URL and the date `[external]`. Cost = tokens × price; Platform and infrastructure costs are reported apart.
- **Jev access:** through its own provider client behind `LLM_PROVIDER`; if no key or no ES/PT support, AC-06 applies.
- **Outputs:** `eval/results/bench_b1.csv`, `eval/results/bench_b2.csv`, `apps/web/public/data/benchmark.json`
  (spec 01 §6.2) and `docs/assets/benchmark_cost_quality.svg`.
- **Commands:** `make bench` (B1), `make bench-agent` (B2, uses the harness and the eval hooks of spec 01 §6.8).

## 5. Non-functional requirements
- B1 finishes in under 10 minutes; B2 in under 45 minutes `[assumption]`.
- Same data, same prompts and temperature 0 for every LLM arm; differences come only from the model.
- Never runs on the held-out set.

## 7. Data model touched
Reads the frozen sentence split and the dev agent cases; writes only result files.

## 8. Assumptions and open questions (gate 1)
- **Q1 — Jev:** how do we reach it (provider, key, region)? Without access it is reported as unavailable.
- **Q2 — budget:** 20 USD per full benchmark run as the stop limit. OK?
- **Q3 — where to choose:** choose on dev (B2) and confirm on the held-out in spec 10 — never choose on the held-out. OK?
- **Q4 — Sonnet 4.5:** add it as an extra point on the chart (it is available on Bedrock), or keep only Haiku 4.5 and
  Sonnet 4.6? Proposal: only the two.

## 9. Out of scope
Public third-party benchmarks; fine-tuning; latency of Platform itself (reported, not optimized).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/bench/prices.yaml` with sources; budget guard · AC-05, AC-08
- [ ] T2 — B1 runner over spec 11 arms + LLM arms · AC-01, AC-06
- [ ] T3 — B2 runner on top of the harness (spec 10) with arms S0/S1/S2/Jev · AC-02
- [ ] T4 — table, JSON for `/evaluation`, cost-vs-quality chart · AC-03, AC-04
- [ ] T5 — "model selection" ADR · AC-07
