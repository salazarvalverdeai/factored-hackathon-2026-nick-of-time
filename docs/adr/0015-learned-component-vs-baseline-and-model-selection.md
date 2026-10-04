# 0015. Learned components versus baselines, with a pre-registered selection rule

- **Status:** Accepted
- **Date:** 2026-09-29 (selection protocol and benchmark added 2026-10-03)
- **Deciders:** Freddy, Diego · **Owner:** @salazarvalverdeai
- **Related:** specs 09, 10, 11, 15, ADRs 0007, 0009

## Context
The organizers confirmed (Slack, 2026-09-29) that the challenge requires comparing at least one learned component
against a baseline, and that the baseline may be rules. We also need to choose models per role (Haiku 4.5, Sonnet 4.6,
Jev) on evidence of quality, cost and latency.

## Decision
- **What is compared:** (1) the ES/PT intent and slot classifier — rules (baseline) vs TF-IDF + logistic regression vs
  an LLM, with a cascade (LR, then the LLM below τ) as a candidate and Jev as an optional arm; (2) the injection detector
  — rules vs rules + LR; (3) the full system — a deterministic configuration without an LLM vs the agent with Haiku 4.5
  vs the agent with Sonnet 4.6.
- **How:** a protocol in `eval/PROTOCOL.md` fixes data, splits (by author, frozen before training), metrics and the
  decision rule **before any result is seen**, and is sealed with the held-out. A benchmark (spec 15) runs every arm on
  the same data with one command and plots cost versus quality.
- **Decision rule:** a hard gate of zero unsafe outcomes for system configurations; then the simplest arm within the
  best arm's confidence interval that meets the latency and cost budget wins. If no learned arm beats the baseline with
  significance, the baseline stays — and that is reported.
- The conclusion is written as a new ADR ("model selection"), whether or not the model wins.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Pre-registered protocol + benchmark (chosen) | Defensible; avoids tuning on the test | Thresholds fixed before knowing the data |
| Pick the strongest model | Simple | Cost and latency unjustified; no baseline |
| Compare after looking at results | Flexible | Results not credible |

## Consequences
Every model choice in the product cites a measured trade-off. Thresholds (e.g. PT macro-F1 ≥ 0.80, p95 ≤ 1.5 s) are
labeled `[assumption]` and approved in the protocol PR.

## Confidence
High.
