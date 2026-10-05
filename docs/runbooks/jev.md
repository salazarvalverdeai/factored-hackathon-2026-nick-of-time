# Runbook · TypeSafe Jev

Benchmark arm for intent classification (specs 11 and 15). Researched 2026-10-04 from
[Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)), [Pydantic AI · TypeSafe](https://pydantic.dev/docs/ai/models/typesafe/),
the [API reference](https://docs.typesafe.ai/api.md), the [models page](https://docs.typesafe.ai/models) and the
[legal page](https://docs.typesafe.ai/legal.md).

## What it is
A "System One" **decision model** by TypeSafe AI (released 2026-09-15): it answers typed questions — `choice` (≤ 255
options), `score` (2–10 levels), yes/no — with probabilities and a confidence, not free text. It fits intent
classification; free-text replies still need an LLM. English is its primary language: ES/PT quality must be measured.

## Third-party gate (spec 15 §4.1)
| Criterion | Status |
|---|---|
| No training on customer requests | ✅ privacy policy |
| Retention | DPA; zero retention for enterprise only |
| Processing region | ❌ not documented |
| Public security certification | ❌ not documented |
| Availability | early access; `429`/`529 Overloaded` documented |

**Result:** eligible for the benchmark with synthetic data; **not eligible for production** until region,
certification and availability are documented.

## 1. Access (owner: lead)
**Done on 2026-10-04:** the project key is in SSM and `make check-jev` passes in ES and PT.
For a new key: console → Settings → Keys → create a key. New sign-ups were paused on 2026-09-22; if the key stops working
before the benchmark run, Jev is reported as "unavailable" (spec 15 AC-06).

## 2. Store the values
Production (SSM):
```bash
aws ssm put-parameter --profile nickoftime --region us-east-2 --type SecureString \
  --name /nickoftime/prod/TYPESAFE_API_KEY --value '<key>' --tags Key=Project,Value=nickoftime
```
Local `.env`:
```
TYPESAFE_API_KEY=<key>
JEV_MODEL=jev-1.13.0     # pin a version; jev-latest moves with releases
```

## 3. Access check
```bash
make check-jev
# OK    key accepted · models listed: jev-latest, jev-preview · pinned: jev-1.13.0
# OK    [es] model jev-1.13.0 chose unrecognized_charge (confidence …) in … ms · usage {…}
# OK    [pt] model jev-1.13.0 chose unrecognized_charge (confidence …) in … ms · usage {…}
```
`HTTP 401` → wrong key; `HTTP 422` → the request shape changed (the check prints the validation detail);
`HTTP 529` → overloaded, retry with backoff.

## Models (checked 2026-10-04)
There is one model, **`jev-1.13.0`**. `GET /v1/models` lists only the aliases `jev-latest` and `jev-preview`, and both
point to `jev-1.13.0` today; versioned ids are accepted even though they are not listed. Pin `jev-1.13.0` so the
benchmark is reproducible; the response's `model` field records the version that answered.

| | `jev-1.13.0` |
|---|---|
| Price | 0.042 USD per 1M input tokens; output tokens are free |
| Rate limits | 80 requests/s, 100K tokens/s (TypeSafe says they change without notice) |
| Context | 64k tokens per request; 32k for `state` plus the longest question |
| Input | text only (string, JSON object or array) |
| Languages | English is primary; other languages "handled but not equally well" — measure ES/PT |

Source: [docs.typesafe.ai/models](https://docs.typesafe.ai/models), checked 2026-10-04. Measured in the access check:
~350 ms and ~455 input tokens per one-question request.

## API summary
`POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer <key>`, body `{model, state, questions}`.
Each question is `{type, instructions, criteria}`: for `choice`, `criteria` maps each option to its description
(≤ 255 options); for `score`, an ordered list of 2–10 levels; for `noul` (yes/no), optional `{true, false}`
descriptions. Response `{model, answers{<key>: {type, choice, probabilities, confidence}}, usage}`.
