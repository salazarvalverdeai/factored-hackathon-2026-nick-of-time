# Spec 04 — Agent graph on LangGraph Platform

- **Feature:** the `dispute_intake` graph that takes a customer's message (ES/PT) to a verified outcome — block, case,
  deadline — tells the customer what it is doing while it does it, returns a verified receipt and a handoff card, and
  answers status questions by reading the system again.
- **Status:** Draft — reviewed by the lead on 2026-10-04 (improvements #11–#16; suggestion chips added after the review)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** L
- **Challenge dimension:** AI Engineering, Technical Judgment
- **Depends on:** 01 (graph I/O, arms, modes), 02 (engine, clock), 03 (tools v1.1), 11 (classifier; rules arm until it
  lands), Bedrock · **Enables:** 07, 10, 15 · **ADRs:** 0005, 0008, 0009, 0013, 0016, 0019, 0020
- **Issue:** #6

> Full profile: this is the core of the product and the place where AI and rules meet.

---

## 1. Introduction
The graph follows the challenge's cycle — understand, decide, act, verify, escalate — with one rule: **the LLM
understands, the rules decide, the tools act, verification confirms, a person closes.** The LLM is used for language
(intent and slots when the classifier is unsure, and the wording of replies); every decision comes from the policy
engine (spec 02); every action goes through the MCP tools (spec 03); every fact shown comes from a tool result
(ADR 0016). Conversation design follows the
Guidelines for Human-AI Interaction (make clear what the system can do, explain why, support correction, keep a human
reachable) and avoids the chatbot risks named by the CFPB (inaccurate information, not recognizing that a customer
invokes a right, blocking access to a person). Sources in §11.

## 2. User stories
- As a **customer**, I want to report a charge in my language, see what the assistant is doing, and get proof of what
  was done and by when, so I do not need to call.
- As a **returning customer**, I want to ask "is my card blocked?" or "how is my case?" and get the current answer.
- As an **analyst**, I want escalated cases with verified facts, evidence ids and a proposal.
- As the **bank**, I want the agent to say "no" when it must and never report an action it did not verify.

## 3. Acceptance criteria (EARS)
AC-01 to AC-08 come from issue #6 with the same numbers; the rest are added by this spec.

**Core outcome**
- **AC-01** — When EV-0001 runs (MX, debit, high score, historical mode), the final state shall be: card Blocked and
  verified, case open, MX deadline visible, receipt with a date. · [T]
- **AC-02** — When intent confidence is below τ, or there is more than one candidate transaction, the agent shall ask
  with options and not act. · [T]
- **AC-03** — If the message carries an injection or asks for another customer's data, then the agent shall answer DENY
  with the guardrail id and report it for `policy_denials`. · [T]
- **AC-04** — If `block_card` does not answer after the retries, then the agent shall escalate with "action NOT
  confirmed" and never say "blocked". · [T]
- **AC-05** — The receipt, the handoff card and every reply shall contain only facts returned by tools; any number, date,
  id or status not in a tool result shall be dropped and logged (G-OUT-01). · [T]
- **AC-06** — When a returning customer asks about a case, the agent shall answer with `get_case` (status label, stored
  deadline, timeline) and record new information with `add_case_info`. · [T]
- **AC-07** — The graph shall be deployed on Platform and answer a run coming from the public `/api`. · [C]
- **AC-08** — (P1) `/agent` shall show the exported graph diagram, a readable `policies.yaml`, the guardrails with their
  ids and the models with their versions. · [U]

**Language and arms**
- **AC-09** — When the arm is `S0`, the graph shall complete every case without any LLM call. · [T]
- **AC-10** — The reply shall be in the customer's language (ES or PT) for every decision. · [T]

**Zones and handoff**
- **AC-11** — When the zone is medium, the agent shall show its plan and ask for confirmation; once confirmed, it shall
  open the case and hand it off with the proposal `approve_block`. · [T]
- **AC-12** — When the zone is human, the agent shall open the case and emit a handoff card that validates against
  `handoff.schema.json`, with `copilot_proposal.requires_human = true`. · [T]
- **AC-13** — After 2 clarification turns without a single transaction, the agent shall hand off with reason
  `clarification_exhausted`. · [T]
- **AC-14** — Every run shall return its LLM usage and its denials, so the api can write `llm_calls` and `policy_denials`. · [T]

**Conversation design (improvements #12 and #15)**
- **AC-15** — The first reply of a session shall greet the customer by first name from `get_customer_profile` (never from
  the text), say what the assistant can do in at most 3 bullets, and say that a person reviews cases that need it. · [T]
- **AC-16** — Before acting, the agent shall state its plan as numbered steps; in the high zone it then executes, in the
  medium zone it waits for confirmation. · [T]
- **AC-17** — While a run is in progress, the stream shall emit one customer-facing progress label per step (ES/PT, no
  internal terms). · [T]
- **AC-18** — Every action shown to the customer shall carry one of four states — in progress, requested, verified (with
  time), not confirmed — and "verified" only after the post-condition read. · [T]
- **AC-19** — When the customer asks for the status of a card or case, the agent shall read it again in that turn
  (`get_product_status`, `list_my_cards`, `get_case`, `list_my_cases`) and state the time of the reading; if the read
  fails, it shall say it could not verify and never state a status. · [T]
- **AC-20** — Every final reply shall offer a way to a person ("request a call") and, when a case exists, a link to
  `/case/{id}`, both as suggestion chips (§4.5). · [T]
- **AC-21** — The receipt shall show the card's last 4 digits, the verification id and time, the case id, the absolute
  deadline date with its legal source, what the AI did and what a person does next. · [T]
- **AC-22** — The agent shall never say a case is "assigned to an analyst" unless `get_case` shows `taken_by_person`. · [T]
- **AC-28** — When the intent is `human_request`, the agent shall register a call request (`request_call`) or, without
  a verified session, show the bank's general contact path; it shall never refuse. · [T]

**Suggestion chips (lead requirement, 2026-10-04)**
- **AC-29** — Every reply shall end with 2 or 3 suggestion chips (`suggestions`) chosen by the rule table of §4.5 from
  the decision and the state, in the customer's language; the LLM never writes or picks a chip, in any arm. · [T]
- **AC-30** — An action chip shall be offered only if it is allowed in the current state, checked against the engine
  and the latest tool reading (never "Bloquear mi tarjeta" after `get_product_status` read `Blocked`, never "Pedir
  reevaluación" for an active case). · [T]
- **AC-31** — On the first turn, the agent shall offer three starter chips: report an unrecognized charge, report a
  wrongful charge, check a case. · [T]
- **AC-32** — Pressing a text chip shall give the same result as typing its label; pressing an action chip shall send
  the structured `action` of spec 01 §6.4, which skips the classifier; a link chip opens an internal route set by the
  server, never by the model. · [T]

**Cases, money and modes (improvements #13 and #16)**
- **AC-23** — If the customer disputes a transaction that already has an active case, the agent shall not open another
  one and shall say so with the existing case id and deadline. · [T]
- **AC-24** — When the customer asks for re-evaluation, the agent shall use `request_reevaluation` and explain that a
  person decides. · [T]
- **AC-25** — Every amount shall be shown as the exact original amount, plus the customer's display currency as an
  approximation from `convert_amount`, with its rate source. · [T]
- **AC-26** — When the customer asks for the receipt by e-mail or Telegram, the agent shall use `send_case_summary`
  (template only, confirmed channels) and confirm delivery only from `list_my_notifications`. · [T]
- **AC-27** — The graph shall use the session's mode (historical or live) for "today" and for which transactions exist;
  it shall never read the system clock directly. · [T]

## 4. Functional requirements

### 4.1 State (typed)
`messages`, `language`, `session_id`, `session_state`, `mode` (`replay`|`live`), `arm`, `profile` {first_name,
display_currency, channels}, `case_id_in`, `intent`, `intent_confidence`, `slots` {amount, currency, date, merchant},
`injection_flagged`, `candidates`, `selected_transaction`, `score`, `decision` (spec 02), `plan` [steps],
`clarification_turns`, `customer_confirmed`, `actions` [{tool, action_id, state, verification_id, read_at}], `case`,
`receipt`, `handoff`, `reply`, `progress` [labels], `suggestions` [chips], `guardrails_triggered`, `denials`, `usage`,
`trace`.

### 4.2 Nodes and edges
```
greet ─► understand ─► identity ─► route ─┬─► retrieve ─► decide ─┬─► plan ─► act ─► verify ─► respond
                                          │                       ├─► clarify ─────────────► respond   (ask / confirm)
                                          │                       └─► refuse ──────────────► respond   (deny / reauthenticate)
                                          ├─► status ──────────────────────────────────────► respond   (answer_status: cards, cases, notifications)
                                          ├─► connect ─────────────────────────────────────► respond   (connect_person: request_call)
                                          └─► refuse ──────────────────────────────────────► respond   (rules 1–4: session, injection, other customer, out of scope)
```
| Node | Does | Tools / rules |
|---|---|---|
| `greet` | First turn only: name, capabilities, human reachable, starter chips | `get_customer_profile` · `messages.yaml greet.*` |
| `understand` | Language; injection detector; intent + slots with the arm's classifier; relative dates against the mode's "today" | spec 11 · LLM only in S1/S2 below τ |
| `identity` | Reads `session_state` and `mode` from the run config (injected by the api); never trusts ids in the text | — |
| `route` | Runs spec 02 rules 1–4 on the understood input: `reauthenticate`/`deny` → refuse; `connect_person` → connect (never refused); `answer_status` → status; a dispute → retrieve, then `decide` applies rules 5–9 | `engine.decide()` |
| `retrieve` | Finds the transaction; gets the score; converts amounts for display | `search_transaction` · `get_fraud_score` · `convert_amount` |
| `decide` | The decision with rule ids | spec 02 `engine.decide()` |
| `plan` | Numbered steps shown to the customer | `messages.yaml plan.*` |
| `act` | `open_case` (dedupe, related case), then `block_card` when allowed; idempotency key `session:transaction:action:run` | MCP |
| `verify` | Post-conditions; 2 retries, 800 ms timeout; failure → `not_confirmed` + escalation | `get_product_status` · `get_case` |
| `status` | Re-reads cards, cases or notifications and answers with the reading time | `list_my_cards` · `get_case` · `list_my_cases` · `list_my_notifications` |
| `connect` | Registers a call request on the active case (or a general one) and says when to expect it; without a verified session, the bank's general contact path with no data | `request_call` · `messages.yaml connect.*` |
| `clarify` | Options (≤ 3 candidates) or a request for amount/date; counts turns | templates; LLM wording in S1/S2 |
| `refuse` | DENY or re-authenticate with no data and a way forward | templates |
| `respond` | Receipt and handoff from verified facts; reply from templates (S1/S2 may reword, then the grounding check runs); suggestion chips from §4.5 | `nick_of_time.receipt` · `send_case_summary` · `request_call` · `request_reevaluation` · `add_case_info` · `messages.yaml suggest.*` |

### 4.3 Grounding check (ADR 0016)
Every number, date, id and status in `reply`, `receipt` and `handoff` is matched exactly against tool results and the
policy. Anything unmatched is removed, the template version is used instead, and `G-OUT-01` is added to the trace.

### 4.4 Arms and modes (spec 01 §6.8)
Arms: `S0` rules + templates, no LLM · `S1` chosen classifier + the LLM chosen by spec 15 (Haiku 4.5 until the
benchmark runs) · `S2` Sonnet 4.6 · benchmark arms (spec 15).
The arm comes from `configurable.arm`; the production default is the arm chosen by the model-selection ADR (spec 15).
Modes (ADR 0020): `replay` (dataset, "today" = `DEMO_TODAY`) for evaluation and processed sample cases;
`live` (real today, recent synthetic transactions for demo customers) for the public demo.

### 4.5 Suggestion chips
Chips help the customer take the next step without typing. Three kinds: **text** (sends its label as the next message),
**action** (sends a structured `action`, skipping the classifier) and **link** (an internal route set by the server).
Labels live in `messages.yaml suggest.*` (ES/PT); ES examples below.

| State after the turn | Chips |
|---|---|
| First turn (`greet`) | text "No reconozco un cargo" · text "Me cobraron dos veces" · text "¿Cómo va mi caso?" |
| `ask` — candidates shown as cards | action "Ninguno de estos" · text "Muéstrame mis últimos cargos" · action "Hablar con una persona" |
| `ask` — amount or date missing | text "Muéstrame mis últimos cargos" · text "No recuerdo el monto" · action "Hablar con una persona" |
| `confirm` (medium zone) | action "Sí, continúa" · action "No es ese cargo" · action "Hablar con una persona" |
| Case opened, actions verified (receipt) | link "Ver mi caso" · action "Enviarme el comprobante" · action "Que me llame una persona" |
| `handoff` or `escalate_unconfirmed_action` | link "Ver mi caso" · text "Agregar información" · action "Que me llame una persona" |
| `answer_status` — active case | link "Ver mi caso" · text "Agregar información" · action "Que me llame una persona" |
| `answer_status` — resolved, within the re-evaluation window | action "Pedir reevaluación" · link "Ver mi caso" · action "Que me llame una persona" |
| `connect_person` | link "Ver mi caso" (if a case exists) · text "Reportar otro cargo" |
| `deny` / out of scope | text "No reconozco un cargo" · text "¿Cómo va mi caso?" · action "Hablar con una persona" |
| `reauthenticate` | link "Verificar de nuevo" · action "Hablar con una persona" (general contact path, AC-28) |

Rules: at most 3 chips; a path to a person is always among them, except right after `connect_person`; every action chip
passes AC-30; chips are stored with the reply exactly as shown and the web shows them only under the last reply (spec 07).

## 5. Non-functional requirements
- **Latency:** p95 per turn ≤ 6 s with S1 `[assumption]`; first progress label within 1 s.
- **Cost:** ≤ 0.02 USD per case with S1 `[assumption]`, measured by the harness.
- **Graceful degradation:** if Bedrock fails or the per-conversation budget is exhausted (G-OPS-01), the run continues
  as `S0` and says so in the trace.
- **Safety:** customer text and tool outputs reach the LLM as delimited data; the LLM never sees `policies.yaml` and
  never writes outbound messages.
- **Observability:** LangSmith traces in development; the run's `trace` and `usage` are the source of truth for the api.
- **Message format:** ≤ 3 lines per message, bullets for steps, cards for the receipt and options, one question at a time.

## 6. API contract
Graph input, config and output follow spec 01 §6.4, with these additions (applied to spec 01 in the same review):
`configurable.session_state`, `configurable.mode`, and in `TurnResult`: `progress` [labels], `plan` [steps],
`usage` [{provider, model, tokens_in, tokens_out, latency_ms, cost_usd}], `denials` [{policy_id, guardrail_id, detail}],
`actions[].state` with the four-state vocabulary, and `suggestions` [{id, label, kind, action?, href?}] (§4.5).

## 7. Data model touched
None directly: the graph reads and writes only through the MCP tools (spec 03 v1.1); the api persists `usage` and
`denials` from the run output.

## 8. Decisions (gate 1, lead review 2026-10-04)
- **Q1 — replies:** templates by default; LLM rewording only in S1/S2, behind the grounding check.
- **Q2 — additions to spec 01** (§6): applied with the spec 01 update.
- **Q3 — returning customer:** status and stored deadline from `get_case`; new information through `add_case_info`; the
  full history lives in `/case/{id}`.
- **Q4 — reversed charges:** the agent says the charge was already reversed and opens no case.
- **Q5 — suggestion chips** (lead requirement): mandatory in the agent and the web; chosen by rules (§4.5), never by the
  LLM, so a chip never offers something the policy would deny.
- Assumptions: the p95 ≤ 6 s and ≤ 0.02 USD per case targets are confirmed or corrected by the benchmark (spec 15).

## 9. Out of scope
Case investigation, chargebacks, provisional credit (always a person), voice, multi-agent designs, free-text outbound
messages.

## 10. Plan, tasks and verification
- [ ] T1 — State and graph skeleton on the spec 01 echo graph; `langgraph dev` locally · AC-07, AC-27
- [ ] T2 — `greet`, `understand` (rules arm + injection rules), `route` · AC-03, AC-09, AC-10, AC-15
- [ ] T3 — `retrieve`, `decide`, `plan`, `clarify`, `refuse` · AC-02, AC-11, AC-12, AC-13, AC-16, AC-23, AC-25
- [ ] T4 — `act`, `verify` with retries, the four-state vocabulary and the unconfirmed path · AC-01, AC-04, AC-18
- [ ] T5 — `respond`: receipt, handoff, grounding check, suggestion chips · AC-05, AC-20, AC-21, AC-22, AC-26,
      AC-29, AC-30, AC-31, AC-32
- [ ] T6 — `status` and `connect` nodes and the returning-customer path · AC-06, AC-19, AC-24, AC-28
- [ ] T7 — progress stream; S1/S2 wiring (Bedrock, structured output); usage; graceful degradation to S0 · AC-14, AC-17
- [ ] T7a — Shared LLM client `nick_of_time.llm` (`fake`, `bedrock`, `anthropic`) and `nick_of_time.config.resolve(arm)`:
      forced tool use with the tool → any → auto ladder (D-011), temperature 0 or provider default recorded per arm
      (D-016), usage, latency and cost from a price table, `ProviderUnavailable` for provider errors (graph degrades to
      S0, section 5), `NoStructuredOutput` when the accepted mode returns no or schema-invalid input (caller decides;
      it carries the billed call's usage); timeouts connect 2 s, read 15 s, 2 attempts in total (Bedrock
      `total_max_attempts`) and 15 s, 1 retry (Anthropic) `[assumption]`; Anthropic is
      an operator switch (`LLM_PROVIDER=anthropic`), not a runtime failover; a per-task arm config (spec 15 section
      4.2) is planned for spec 15 T6 · supports AC-14; tests `tests/test_spec04_llm.py` (lead decision D-003)
- [ ] T8 — Platform deployment; `/agent` content · AC-07, AC-08
- [ ] Tests `tests/test_spec04_*.py` with the `fake` LLM and the fake MCP; EV-0001 end to end in historical mode

**Closing checklist:** every AC has a passing test or check · status → Implemented · ADR if a question changes a
decision · lessons to `CLAUDE.md`.

## 11. Sources
External sources checked on 2026-10-04.
- Amershi et al., *Guidelines for Human-AI Interaction* (CHI 2019, 18 guidelines):
  https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- CFPB, *Chatbots in consumer finance* (6 June 2023) — inaccurate information, failure to recognize disputes, doom loops
  without a person: https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/
- Nielsen Norman Group, Budiu, *The User Experience of Chatbots* (2018) — say what the bot can do, buttons plus text,
  an escape hatch to a person: https://www.nngroup.com/articles/chatbots/
- Rasa, *How to Create Effective Chatbot Conversation Designs* (2025) — short messages, quick replies, confirm critical
  actions: https://rasa.com/blog/how-to-design-chatbot-conversation
- Internal: ADR 0016 (grounding), ADR 0019 (official sources), `contracts/policies.yaml` (`clarify`, `reliability`,
  `notifications.never_send`), spec 02 (decisions), spec 03 (tools v1.1), improvement drafts #11–#16.
