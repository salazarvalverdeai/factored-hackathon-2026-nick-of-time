# 0009. LLM on Amazon Bedrock: Claude Sonnet 4.6 and Haiku 4.5

- **Status:** Accepted
- **Date:** 2026-09-29 (updated 2026-10-03)
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 04, 11, 15, ADR 0015

## Context
Bedrock in `us-east-2` offers Claude Sonnet 4.6, Sonnet 4.5 and Haiku 4.5 to this account; the Claude 5 family has a
quota of 0 (raising it requires AWS sales). The Anthropic use-case form was submitted on 2026-10-03. Platform runs
outside AWS, so it calls Bedrock with a dedicated IAM user limited to model invocation.

## Decision
Use Bedrock as the LLM provider: **Claude Sonnet 4.6** as the candidate for the graph and **Claude Haiku 4.5** for cheap,
structured tasks (intent and slot extraction). Which model serves which role is decided by the benchmark (ADR 0015,
spec 15), not by preference. A single client exposes `LLM_PROVIDER=bedrock|anthropic|fake`: the Anthropic API is the
fallback if Bedrock fails, and `fake` is used in CI. Every call is logged (`llm_calls`: model, tokens, latency, cost)
under the turn's trace id.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Bedrock + fallback (chosen) | IAM, no API keys on EC2; cost per case measured | Use-case form and quotas per account |
| Anthropic API only | Fastest access to new models | Keys to manage; synthetic data leaves AWS |
| One large model for everything | Simple | Latency and cost without measured gain |

## Consequences
The graph never knows the provider. If the fallback is used, it is declared in the README (data is synthetic).

## Confidence
High.
