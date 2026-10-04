# 0016. Guardrails: injection detector with rules + LR, exact-match output grounding

- **Status:** Accepted
- **Date:** 2026-09-29
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 04, spec 11, `contracts/policies.yaml` (`guardrails`)

## Context
Customer text and tool outputs can carry instructions; replies can state numbers, dates, ids or statuses that no tool
returned. The challenge evaluates when the system says "no" and whether it reports only what happened.

## Decision
- **Input (G-IN-01):** customer text and tool outputs are passed as delimited data; an injection detector made of rules
  plus a logistic regression routes suspicious messages to a DENY with the guardrail id, logged in `policy_denials`.
- **Output (G-OUT-01/02):** every number, date, id or status in a reply, the receipt or the handoff card must match a
  tool result or the policy **exactly**; anything else is dropped and logged. "Blocked" is said only when
  `get_product_status == Blocked`; a case id only when `get_case_status == Open`.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Rules + LR detector, exact grounding (chosen) | Deterministic, cheap, testable in CI | Rules need maintenance |
| Llama Guard or a hosted guardrail model | Broader coverage | Another model to host and evaluate |
| LLM-as-judge for grounding | Handles paraphrase | Non-deterministic; can itself hallucinate |

## Consequences
The receipt is built from a deterministic template filled with tool results, so it is grounded by construction.

## Confidence
High.
