# Runbook · Amazon Bedrock (Claude)

**Status (2026-10-04):** enabled. Claude Haiku 4.5 and Claude Sonnet 4.6 answer in `us-east-2`; the Claude 5 family has
a quota of 0 on this account. Decision record: [ADR 0009](../adr/0009-llm-on-amazon-bedrock.md).

## One-time account setup (done)
1. Bedrock console (`us-east-2`) → Model catalog → Anthropic → submit the **use-case form** once per account.
2. Model access agreements are created on first invocation.
3. Quotas: Service Quotas → Amazon Bedrock → per-model tokens/requests per minute (Haiku 4.5: 5 M tokens/min).

## Who can call it
| Principal | How |
|---|---|
| EC2 (`nickoftime-app`) | instance role `nickoftime-ec2-role` — no keys |
| LangGraph Platform | IAM user `svc-nickoftime-langgraph` (invoke only); keys stored as deployment secrets |
| Team members | IAM users in group `nickoftime-bedrock`, with their own access keys |

## Local configuration (`.env`)
```
AWS_PROFILE=nickoftime
AWS_REGION=us-east-2
BEDROCK_MODEL_FAST=us.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_MODEL_GRAPH=us.anthropic.claude-sonnet-4-6
```
The profile lives in `~/.aws/credentials`; the check uses it explicitly, so dataset keys an older `.env` may still
export are ignored.

## Access check
```bash
make check-bedrock
# OK    BEDROCK_MODEL_FAST us.anthropic.claude-haiku-4-5-… answered in 792 ms (tokens in 13, out 4)
# OK    BEDROCK_MODEL_GRAPH us.anthropic.claude-sonnet-4-6 answered in 717 ms (tokens in 13, out 4)
```
`AccessDeniedException … use case details have not been submitted` → step 1. `… not available for this account` → the
model has quota 0 (Service Quotas).
