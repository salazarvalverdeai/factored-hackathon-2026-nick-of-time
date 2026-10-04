# 0007. Evaluation by final state on a sealed held-out

- **Status:** Accepted
- **Date:** 2026-09-28 (sizes revised 2026-10-03)
- **Deciders:** Freddy, Diego · **Owner:** @vldiego
- **Related:** [`eval/eval_case.schema.json`](../../eval/eval_case.schema.json), specs 09, 10, ADR 0015

## Context
The dataset has no real customer text. A reply that sounds right can still block the wrong card or leak another
customer's data. The challenge asks for quality and safety evaluation with baselines.

## Decision
The harness compares the **final state** — product status, case opened, handoff emitted, queue status, notifications,
guardrails fired, data exposed, receipt with a date — not the reply text. Cases follow `eval_case.schema.json`, use
real gold customers from the held-out split (`hash(customer_id) mod 10 ∈ {8, 9}`) with team-written ES/PT messages,
include attacks and returning customers, and are sealed with `eval/heldout.sha256` before the final run. Each case runs
four times (pass^4). Results are reported with their denominators per language × type × segment, plus latency
p50/p95 and cost per case. Sizes for the final sprint: 20 dev + 80 held-out agent cases, and a 300–400 sentence set
for the classifier.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Final-state harness (chosen) | Safety counted, not argued; deterministic checks | Cases take time to write |
| LLM-as-judge on reply text | Fast to set up | Judges tone, not safety; non-deterministic |
| Dev cases only | Less work | Overfits the prompts we tuned |

## Consequences
"Unsafe outcomes" have a denominator; agent blocks are checked against the real `is_fraud`. With 80 held-out cases,
intervals per cell are wide: we show n and do not over-claim.

## Confidence
High.
