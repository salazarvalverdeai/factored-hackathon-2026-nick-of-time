# 0006. The bank's fraud score as an optional, swappable input

- **Status:** Accepted
- **Date:** 2026-09-28 (amended 2026-09-29)
- **Deciders:** Freddy, GianMarco, Diego, David · **Owner:** @salazarvalverdeai
- **Related:** spec 02, [`contracts/tools.py`](../../contracts/tools.py) (`ScoreProvider`)

## Context
The dataset carries the bank's `fraud_score` (0–100, null for 20.6% of frauds). On the EDA, score ≥ 50 has 100%
precision and 48.8% recall on frauds with a score; ≥ 30 has 79.6% precision `[data]` — a property of the synthetic
generator `[assumption]`. Whether the score is available in real time is unknown.

## Decision
Consume the score through a `get_fraud_score` tool with a configurable provider (`dataset` now; `rules`, `model`,
`llm` later); source and version go to the audit log and the handoff card. Zones: **high ≥ 50**, **medium 30–49**,
**human < 30**. **The score is a nice-to-have input, not a dependency** (2026-09-29): triage is driven by the bank's
policy rules, and `score: null` is its own rule with its own `policy_id` that routes to the human zone with the intake
complete. A score from the `llm` provider always forces the human zone. The pitch does not say "triage by fraud score".

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Swappable provider, optional (chosen) | Works with or without the score; auditable source | One more indirection |
| Train our own fraud model | Independence from the bank | Duplicates the bank's capability; out of scope |
| LLM judges the transaction | No data needed | Not calibrated, not explainable |

## Consequences
The zone is always computed from a tool, never from a number in the customer's text. In production the score must be
available at intake time; otherwise every case goes to the human zone with the intake done.

## Confidence
Medium: the 100% precision is a generator artifact; the harness reports block precision against `is_fraud`.
