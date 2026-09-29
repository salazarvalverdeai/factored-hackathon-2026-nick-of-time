# problem.md — W3 · Regulatory-clock dispute intake

**Decided on:** [date of the vote] · **Not reopened:** workflow, zones and thresholds, handoff format, eval case
format, team name.
**Labels:** `[data]` computed on the dataset (query in `queries/`) · `[external]` source with link ·
`[assumption]` · `[simulated]` measured in our harness · `[projected]`.

## 1. Problem
A customer sees a charge they do not recognize or a wrongful charge and files a complaint. It is **36.4% of complaints** `[data]`
(679/month on average out of 1,864), the reason with the worst FCR (**43.6% vs 76.6%** `[data]`), 63% with follow-up,
median duration 7.2 vs 4.9 min, NPS −85.3, resolution p50 16 days `[data]`, and the only one with a legal deadline per country
(MX: provisional credit ≤ business day 2 on debit and ruling ≤ 45 days; AR: 10 business days; CO: 15 days; BR: 10 business days)
`[external]` see `policies.yaml`.

## 2. Scope
**In:** ES/PT intake · mock identity (session + OTP with expiry) · identification of the customer's own
transaction · automatic ticket in all 3 zones · triage by `fraud_score` (≥ 50 verified action; 30–49
confirm; < 30 or null human) · block with post-condition · regulatory clock · handoff card · agent
view (copilot proposes, human decides) · traces + audit log · ES/PT held-out harness with attacks ·
public deploy · reproducible README.
**Out (on purpose):** case investigation, chargeback with the network, automatic credit, voice, real WhatsApp,
multi-agent, Graph RAG, fine-tuning.

## 2b. Deployment and scoring (decided Mon 28)
- **Graph on LangGraph Platform** (option A) with the tools as an MCP server on the EC2; option B (everything on EC2)
  stays documented as a direct migration (same graph, different tool adapter) and is not executed for lack of time.
  Condition: confirm on Slack that the synthetic text may leave AWS and declare it in the README.
- **`fraud_score` as a tool with a swappable provider** (`dataset` at the start; `rules`, `model` or `llm` by
  configuration). The score's source and version are recorded in the audit log and on the handoff card.

## 3. Solution in one sentence
The LLM understands, the rules (YAML) decide, the typed tools act, verification confirms, the traces
record, the human receives evidence.

## 4. Learned component vs baseline
ES/PT intent and slot classifier: keyword rules → embeddings + logistic regression → Jev
(third arm, only if it passes the ES/PT test on Wednesday 30). Same held-out, split by template. Secondary:
calibration of zones against `is_fraud`. Escalation by rules (AUC 0.501 `[data]`).

## 5. How it is measured
Final state (not text): did it block?, did it open a case?, did it escalate when it should?, did it deny when it should? Challenge metrics:
safe automated resolution, unsafe outcomes with denominator, escalation quality (missed and unnecessary),
p50/p95, cost per attempted case and per resolution, by language and segment, pass^4. See `eval/eval_case.schema.json`.

## 6. Accepted risks
Real text 0 (team set, labeled) · PT 0% in the data · 100% precision with score ≥ 50 comes from the generator
`[assumption]` · 20.6% of frauds without a score → human · complaints FK broken → dispute from `transactions` ·
Jev 12 days old → LR fallback · synthetic data to external APIs? (ask on Slack before Tuesday).

## 7. Ownership
| Person | Owner of |
|---|---|
| Freddy (AI/ML, lead, integrator) | `policies.yaml`, contracts, rules engine, classifier vs baselines, Jev, harness |
| Full stack | orchestrator, tools over the snapshot, mock identity, customer + agent UI, traces, graph, deploy |
| Data 1 (engineering) | pipeline with contracts, DuckDB snapshot, checks, late-arrivals fixture, `make setup` |
| Data 2 (analytics) | pitch queries, deadlines with source, business case, ES/PT set (writing and labeling), report |

## 8. Calendar
Mon 28 contracts and repo · Tue 29 skeleton · Wed 30 normal case end-to-end + Jev test · Thu 1 classifier,
ES/PT set, customer UI · Fri 2 agent view, traces, graph · Sat 3 full eval and deploy · Sun 4 video, slides,
README, secrets · Mon 5 submission first thing in the morning.
