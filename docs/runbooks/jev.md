# Runbook · TypeSafe Jev

Benchmark arm for intent classification (specs 11 and 15). Researched 2026-10-04 from
[Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)), [Pydantic AI · TypeSafe](https://pydantic.dev/docs/ai/models/typesafe/),
the [API reference](https://docs.typesafe.ai/api.md) and the [legal page](https://docs.typesafe.ai/legal.md).

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
Join the waitlist at typesafe.ai → console invite → console → Settings → Keys → create a key. New sign-ups were paused on
2026-09-22; if access does not arrive before the benchmark run, Jev is reported as "unavailable" (spec 15 AC-06).

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
# OK    [es] model jev-1.13.0 chose unrecognized_charge (confidence …) in … ms · usage {…}
# OK    [pt] model jev-1.13.0 chose unrecognized_charge (confidence …) in … ms · usage {…}
```
`HTTP 401` → wrong key; `HTTP 422` → the request shape changed (the check prints the validation detail);
`HTTP 529` → overloaded, retry with backoff.

## API summary
`POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer <key>`, body `{model, state, questions}`;
response `{model, answers{<key>: {choice, probabilities, confidence}}, usage}`. Reported price: 0.042 USD per 1M input
tokens, output free (gateway listing, to confirm in the console).
