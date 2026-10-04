# Spec 04 — Agent graph on LangGraph Platform

- **Feature:** the `dispute_intake` graph that takes a customer's message (ES/PT) to a verified outcome — block, case,
  deadline — and returns a receipt for the customer and a handoff card for the analyst, with a trace of every step.
- **Status:** Draft
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** L
- **Challenge dimension:** AI Engineering, Technical Judgment
- **Depends on:** 01 (graph I/O, arms), 02 (engine), 03 (tools), 11 (classifier; rules arm until it lands), Bedrock
- **Enables:** 07, 10, 15 · **ADRs:** 0005, 0008, 0009, 0013, 0016
- **Issue:** #6

> Full profile: this is the core of the product and the place where AI and rules meet.

---

## 1. Introduction
The graph follows the challenge's cycle — understand, decide, act, verify, escalate — with one rule: **the LLM
understands, the rules decide, the tools act, verification confirms, a person closes.** The LLM is used for language
(intent and slots when the classifier is unsure, and clarifying questions); every decision comes from the policy engine
(spec 02); every action goes through the MCP tools (spec 03); every fact shown to the customer or the analyst comes
from a tool result (ADR 0016).

## 2. User stories
- As a **customer**, I want to report a charge I don't recognize in my language and get proof of what was done and by
  when, so I don't need to call again.
- As an **analyst**, I want escalated cases to arrive with verified facts, evidence ids and a proposal, so I decide in
  one read.
- As the **bank**, I want the agent to say "no" when it must (injection, other customers, expired session) and to never
  report an action it did not verify.

## 3. Acceptance criteria (EARS)
AC-01 to AC-08 come from issue #6 with the same numbers; AC-09 onward are added by this spec.

- **AC-01** — When EV-0001 runs (MX, debit, high score), the final state shall be: card Blocked and verified, case open,
  MX deadline visible, receipt with a date. · [T]
- **AC-02** — When intent confidence is below τ, or there is more than one candidate transaction, the agent shall ask
  with options and not act. · [T]
- **AC-03** — If the message carries an injection or asks for another customer's data, then the agent shall answer DENY
  with the guardrail id and report it for `policy_denials`. · [T]
- **AC-04** — If `block_card` does not answer after the retries, then the agent shall escalate with "action NOT
  confirmed" and never say "blocked". · [T]
- **AC-05** — The receipt, the handoff card and the reply shall contain only facts returned by tools; any number, date,
  id or status that is not in a tool result shall be dropped and logged (G-OUT-01). · [T]
- **AC-06** — When the customer returns with their `case_id`, the agent shall answer with the case's current status and
  deadline and return the new information for `customer_info_added`. · [T]
- **AC-07** — The graph shall be deployed on Platform and answer a run coming from the public `/api`. · [C]
- **AC-08** — (P1) `/agent` shall show the exported graph diagram, a readable `policies.yaml`, the guardrails with their
  ids and the models with their versions. · [U]
- **AC-09** — When the arm is `S0`, the graph shall complete every case without any LLM call. · [T]
- **AC-10** — The reply shall be in the customer's language (ES or PT) for every decision. · [T]
- **AC-11** — When the zone is medium, the agent shall ask the customer to confirm the transaction and, once confirmed,
  open the case and hand it off with the proposal `approve_block` (spec 02 §4.2). · [T]
- **AC-12** — When the zone is human, the agent shall open the case and emit a handoff card that validates against
  `handoff.schema.json`, with `copilot_proposal.requires_human = true`. · [T]
- **AC-13** — After 2 clarification turns without a single transaction, the agent shall hand off with reason
  `clarification_exhausted`. · [T]
- **AC-14** — Every run shall return its LLM usage (model, tokens, latency, cost) and its denials, so the api can write
  `llm_calls` and `policy_denials`. · [T]

## 4. Functional requirements

### 4.1 State (typed)
`messages`, `language`, `session_id`, `session_state`, `arm`, `case_id_in` (returning customer), `intent`,
`intent_confidence`, `slots` {amount, currency, date, merchant}, `injection_flagged`, `candidates` [Transaction],
`selected_transaction`, `score`, `decision` (spec 02 `Decision`), `clarification_turns`, `customer_confirmed`,
`actions` [{tool, action_id, accepted, verified, verification_id}], `case`, `receipt`, `handoff`, `reply`,
`guardrails_triggered`, `denials`, `usage`, `trace`.

### 4.2 Nodes and edges
```
understand ─► identity ─► retrieve ─► decide ─┬─► act ─► verify ─► respond
                                               ├─► clarify ─────────► respond   (decision ask / confirm)
                                               └─► refuse ──────────► respond   (deny / reauthenticate)
returning customer (case_id_in): understand ─► case_status ─► respond
```
| Node | Does | Uses |
|---|---|---|
| `understand` | Language detection; injection detector; intent + slots with the arm's classifier; relative dates resolved against `DEMO_TODAY` | spec 11 · LLM only in S1/S2 when confidence < τ |
| `identity` | Reads `session_state` from the run config (injected by the api); never trusts ids in the text | — |
| `retrieve` | `search_transaction` with the slots; `get_fraud_score` for the selected transaction | MCP |
| `decide` | `engine.decide(...)` with everything above; records rule ids in the trace | spec 02 |
| `act` | `open_case` (always when a case is due), then `block_card` when the decision and mode allow it; idempotency key `session:transaction:action:run` | MCP |
| `verify` | `get_product_status == Blocked` and `get_case_status == Open`; 2 retries, 800 ms timeout; failure → `escalate_unconfirmed_action` | MCP |
| `clarify` | Question with options (≤ 3 candidates) or a request for amount/date; counts turns | templates; LLM wording in S1/S2 |
| `refuse` | DENY or re-authenticate message with no data | templates |
| `respond` | Builds `receipt` and `handoff` with `nick_of_time.receipt` from verified facts; reply from ES/PT templates (S1/S2 may reword with the LLM, then the grounding check runs) | spec 01 §6.7 |
| `case_status` | Returning customer: `get_case_status` + `compute_deadline`; returns the new information for the api to record | MCP |

### 4.3 Grounding check (ADR 0016)
Every number, date, id and status in `reply`, `receipt` and `handoff` is matched exactly against the tool results and
the policy. Anything unmatched is removed, the template version is used instead, and `G-OUT-01` is added to the trace.

### 4.4 Arms (spec 01 §6.8)
`S0` rules classifier + templates, no LLM · `S1` chosen classifier + Haiku 4.5 · `S2` Sonnet 4.6 · benchmark arms
from spec 15. The arm comes from `configurable.arm`; default in production: the arm chosen by the model-selection ADR.

## 5. Non-functional requirements
- **Latency:** p95 per turn ≤ 6 s with S1 `[assumption]`; tools stay under their 800 ms budget.
- **Cost:** ≤ 0.02 USD per case with S1 `[assumption]`, measured by the harness.
- **Safety:** customer text and tool outputs are passed to the LLM as delimited data, never as instructions; the LLM
  never sees `policies.yaml`.
- **Observability:** LangSmith traces in development; the run's `trace` and `usage` are the source of truth for the api.

## 6. API contract
The graph's input, config and output are those of spec 01 §6.4. This spec needs **four additions to spec 01** (to apply
before spec 01 is approved): `configurable.session_state` (injected by the api), and in `TurnResult` the fields
`usage` [{provider, model, tokens_in, tokens_out, latency_ms, cost_usd}], `denials` [{policy_id, guardrail_id, detail}]
and `customer_info` (text added by a returning customer, or null).

## 7. Data model touched
None directly: the graph reads and writes only through the MCP tools; the api persists `usage`, `denials`,
`customer_info` and the receipt from the run output.

## 8. Assumptions and open questions (gate 1)
- **Q1 — replies:** templates by default and LLM rewording only in S1/S2 behind the grounding check — or templates only,
  everywhere? Proposal: templates + optional rewording.
- **Q2 — the four additions to spec 01** (§6): agree?
- **Q3 — returning customer:** the agent answers status and deadline and passes the new information to the api; the full
  history lives in `/case/{id}` (spec 13). Enough?
- **Q4 — reversed charges:** if the customer describes a charge that appears as `Reversed`, the agent says it was
  already reversed and opens no case. OK?
- Assumption: p95 ≤ 6 s and ≤ 0.02 USD per case are targets, confirmed or corrected by the benchmark (spec 15).

## 9. Out of scope
Case investigation, chargebacks, provisional credit (always a person), voice, multi-agent designs.

## 10. Plan, tasks and verification
- [ ] T1 — State and graph skeleton on top of the spec 01 echo graph; `langgraph dev` locally · AC-07
- [ ] T2 — `understand` with the rules arm (B0) and the injection rules; language detection · AC-03, AC-09, AC-10
- [ ] T3 — `retrieve`, `decide`, `clarify`, `refuse` · AC-02, AC-11, AC-12, AC-13
- [ ] T4 — `act`, `verify` with retries and the unconfirmed-action path · AC-01, AC-04
- [ ] T5 — `respond`: receipt and handoff builders + grounding check · AC-05, AC-12
- [ ] T6 — returning customer path · AC-06
- [ ] T7 — S1/S2 LLM wiring (Bedrock, structured output) and usage reporting · AC-09, AC-14
- [ ] T8 — Platform deployment (`langgraph.json`, secrets) · AC-07; `/agent` content · AC-08
- [ ] Tests `tests/test_spec04_*.py` with the `fake` LLM and the fake MCP; EV-0001 end to end

**Closing checklist:** every AC has a passing test or check · status → Implemented · ADR if a question changes a
decision · lessons to `CLAUDE.md`.
