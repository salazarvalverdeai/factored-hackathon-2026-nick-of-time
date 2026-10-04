# 0005. Policy engine outside the model

- **Status:** Accepted
- **Date:** 2026-09-28
- **Deciders:** Freddy, GianMarco, Diego, David · **Owner:** @salazarvalverdeai
- **Related:** [`contracts/policies.yaml`](../../contracts/policies.yaml), specs 02, 03, 04

## Context
The challenge asks where AI is appropriate and where deterministic logic is preferable. Blocking a card, choosing an
approval mode and computing a legal deadline are money and compliance decisions: they must be explainable,
reproducible and immune to prompt injection.

## Decision
**The LLM understands, the rules decide, the tools act, verification confirms, a person closes.** Decisions live in
`contracts/policies.yaml` (`default: deny`), evaluated by plain code shared by the agent and the tools. The LLM never
reads or edits the file. Permissions are enforced inside the tools (the `customer_id` comes from the session). Every
denial is a row in `policy_denials` citing a guardrail id (`G-…`). Approval mode per action and zone (`auto`,
`manual_check`, `human_required`), a `supervised_mode` switch, and `close: human_only`.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| YAML policies + code evaluator (chosen) | Same input → same decision; each denial explainable; changed by PR | Rules written and tested by hand |
| LLM decides from a system prompt | Flexible | Not auditable, injectable, not reproducible |
| OPA / Rego | Standard policy engine | Another runtime for ~10 rules |

## Consequences
Policy changes are pull requests with tests; regulators and analysts can read why something happened. Ambiguous
language still needs the model upstream (understanding), never downstream (deciding).

## Confidence
High; this is the core differentiator.
