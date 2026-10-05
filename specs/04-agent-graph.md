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
  with options and not act; a call request below τ still registers the call and opens nothing (spec 02 rule 3a,
  D-031). · [T]
- **AC-03** — If the message carries an injection or asks for another customer's data, then the agent shall answer DENY
  with the guardrail id and report it for `policy_denials`. · [T]
- **AC-04** — If `block_card` does not answer after the retries, then the agent shall escalate with "action NOT
  confirmed" and never say "blocked". · [T]
- **AC-05** — The receipt, the handoff card and every reply shall contain only facts returned by tools; any number, date,
  time or id not in a tool result shall be dropped and logged (G-OUT-01). Statuses are held by the four-state rule
  (AC-18) and checked after the turn by the auditor's A5 (spec 18), which compares each stated status with the database
  read; the gate does not match them (task 04d) `[assumption]` (D-056, pending the lead). · [T]
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
  open the case and hand it off with the proposal `approve_block`. Exception: a call request that reports a charge
  opens the case without asking (never a block) and registers the call on it (spec 02 rule 3a, D-020). · [T]
- **AC-12** — When the zone is human, the agent shall open the case and emit a handoff card that validates against
  `handoff.schema.json`, with `copilot_proposal.requires_human = true`. · [T]
- **AC-13** — After 2 clarification turns without a single transaction, the agent shall hand off with reason
  `clarification_exhausted` and register a general call request (`request_call` with no case, spec 02 rule 5b), since
  no case can be opened without a transaction. · [T]
- **AC-14** — Every run shall return its LLM usage and its denials, so the api can write `llm_calls` and `policy_denials`. · [T]

**Conversation design (improvements #12 and #15)**
- **AC-15** — The first reply of a session shall greet the customer by first name from `get_customer_profile` (never from
  the text), say what the assistant can do in at most 3 bullets, and say that a person reviews cases that need it. · [T]
- **AC-16** — Before acting, the agent shall state its plan as numbered steps; in the high zone it then executes, in the
  medium zone it waits for confirmation, except for a call request that reports a charge, which opens the case at once
  (AC-11; never a block in any zone: in the high zone the analyst decides the block after the call, D-029). · [T]
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
- **AC-33** — *(proposed in task 04a from review finding F-012, pending the lead's approval)* When the customer's
  message equals the label of a text chip offered in the previous reply (case, accents and end punctuation ignored),
  the agent shall route it by that chip's pending question — the intent the chip stands for, or the dispute being
  clarified — instead of the classifier's reading, so that typing a label and pressing its chip give the same result.
  · [T]

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
`injection_flagged`, `cross_customer`, `dispute_detected`, `active_case`, `candidates`, `selected_transaction`,
`score`, `decision` (spec 02), `plan` [steps], `clarification_turns`, `customer_confirmed` (about the selected
transaction; reset to null whenever `selected_transaction` changes), `actions` [{tool, action_id, state,
verification_id, read_at}], `case`, `receipt`, `handoff`, `reply`, `progress` [labels], `suggestions` [chips],
`guardrails_triggered`, `denials`, `usage`, `trace`. Internal fields kept on the thread (task 04a): `today` (the
session's date from `config.today(mode)`), `route` (the `screen()` result), `branch`, `body` and `row` (the reply lines
and the §4.5 row of the turn), `greet_pending`, and `language_last` (the thread's language when a request sends
`language: null`). Task 04b adds `answer` (this turn's reply to a confirm question or an option card), `existing_case`
(an active case on the selected transaction, AC-23), `display` (the `convert_amount` result), `decision_record`,
`next_node` and `path` (the nodes run after `route`, for the trace); `route` then holds the policy result of
`screen()` or `decide()`. `decision_record` (D-046, pending the lead; default) is `{node, input, decision}`: the
`DecisionInput` the graph built and the full `PolicyDecision` it got, on every turn that reaches `route`'s terminal
rules or `decide`; it goes into the `detail` of that node's `trace` step as JSON, so the auditor's A1 (spec 18) re-runs
`decide()` on it. Task 04c adds `writes` (the accepted write results, by tool, that `verify` reads back, and the
final error code of each write that failed, and `unanswered`: the writes with an attempt that got no answer) and `unconfirmed` (the tools whose action ended `not_confirmed`, shown in
the `verify` trace step as `<tools>: not_confirmed`). Task 04d adds `readings` (verify's post-condition reads by write tool) and `seen` (the other tool results the reply states: status reads, the call request and its read), which the grounding check of §4.3 reads. Per-turn fields are cleared when a turn starts; the turn's
`messages` and `action` are cleared when it ends. `injection_flagged` comes from the spec 11 classifier; `cross_customer` is set by `understand` in the graph
(task 04a) from a small ES/PT pattern set in `apps/agent`: a data word (saldo, cuenta/conta, tarjeta/cartão,
transacciones, movimientos, extracto/extrato, datos/dados; never cargo or compra) "of" a third party (otro cliente,
cliente + number, mi esposa / minha esposa…), so spec 02 rule 2 fires `POL-CROSS-CUSTOMER` (G-SES-02). The flag is
skipped when the text states own possession or a dispute ("en mi tarjeta", "no reconozco", "não fiz", "me
cobraron"…): precision over recall. Known misses, left to spec 11: "Quiero ver los cargos de Juan Pérez", "consulta
el cliente 12345", "dame la información de otro usuario", "movimientos de la cuenta 4455667788", "cuánto tiene mi
esposa en su cuenta", "transacciones del titular Pedro"; the tools still answer only for the session's customer.
A write the tool never answered, refused (an error answer), or that the graph did not try carries a graph-minted
`action_id` with state `not_confirmed`; the receipt and the handoff list only action ids returned by tools.

### 4.2 Nodes and edges
```
identity ─► greet ─► understand ─► route ─┬─► retrieve ─► decide ─┬─► plan ─► act ─► verify ─┬─► respond
                                          │                       │                         └─► connect ─► respond   (request_call = opened_case: the call on the case just opened, D-020)
                                          │                       ├─► plan ────────────────► respond   (confirm: the steps and the question; nothing acted)
                                          │                       ├─► duplicate ─┬─────────► respond   (AC-23: an active case on the charge; nothing opened)
                                          │                       │              └─► connect ─► respond   (rule 3a: the call on that case)
                                          │                       ├─► clarify ─────────────► respond   (ask: options or a request for details)
                                          │                       ├─► connect ─────────────► respond   (no case to open: rule 3a call, or rule 5b general call)
                                          │                       └─► refuse ──────────────► respond   (deny / reauthenticate)
                                          │   retrieve ──────────────────────────────────► respond   (a failed search or card read: no decision, retry chips)
                                          ├─► status ──────────────────────────────────────► respond   (answer_status: cards, cases, notifications)
                                          ├─► connect ─────────────────────────────────────► respond   (connect_person: request_call)
                                          └─► refuse ──────────────────────────────────────► respond   (rules 1–4: session, injection, other customer, out of scope)
```
| Node | Does | Tools / rules |
|---|---|---|
| `identity` | Reads `session_id`, `session_state`, `mode` and `arm` from the run config (injected by the api); never trusts ids in the text. Runs first, so `greet` knows the session and `understand` knows the mode's "today" (task 04a). A missing `session_state` counts as unverified (fail closed) | — |
| `greet` | First turn of a verified session only: name, capabilities, human reachable, starter chips | `get_customer_profile` · `messages.yaml greet.*` |
| `understand` | Language; injection detector; intent + slots with the arm's classifier; relative dates against the mode's "today"; an action chip skips the classifier (AC-32); a typed label of an offered text chip is read as that chip (AC-33) | spec 11 · LLM only in S1/S2 below τ, in a verified session, never for a flagged or cross-customer message; its slots must fit `search_transaction`'s input and its confidence is capped below τ, so the rules still ask, and an LLM-only `human_request` registers no call unless B0 also reads `human_request` (the turn asks, with the person chip) `[assumption]` (D-065, pending the lead); B0 stands when it fails (task 04f) |
| `route` | Runs spec 02 rules 1–4 with `engine.screen()` on the understood input: `reauthenticate`/`deny` → refuse; `connect_person` → connect (never refused); `answer_status` → status; nothing (a dispute, a call request that reports a charge, or a status question that reports a charge from a customer with no active case) → retrieve, then `decide` applies rules 5–9 (D-020). For a status question that reports a charge, `route` first reads the customer's cases and passes `active_case` (false when none is active), so the engine, not the graph, decides whether the dispute path goes on | `engine.screen()` · `list_my_cases` |
| `retrieve` | Finds the transaction with the slots (no search when the turn reports no charge and has no slot); an option card picks only a candidate the tool returned; a confirm answer keeps the transaction shown. For exactly one candidate it reads, in parallel, its card (`product_type`, `last4`), the score, the display amount and the customer's cases, then `get_case` on each active one to find a case on this transaction (AC-23). A failed search or card read is not a missing charge: the turn says so (`clarify.read_failed`), skips `decide`, counts no clarification turn, offers a retry (`show_recent`) and a person, and marks the `retrieve` trace step `error` with `<tool>: not_confirmed`; it never guesses `product_type`. A failed score read is a null score (zone human). A `tool_failure` handoff is not emitted: spec 02 has no input for it (follow-up for the lead) | `search_transaction` · `get_product_status` · `get_fraud_score` · `convert_amount` · `list_my_cases` · `get_case` |
| `decide` | The decision with rule ids, on tool facts only (score, amount, card and country from tools, never from the text); the graph runs what it returns: ask → `clarify`, deny → `refuse`, a case to open or `confirm` → `plan` (or `duplicate` when the charge has an active case), anything else → `connect` only when the decision sets `request_call` (`connect_person` below τ, the rule 5b handoff), else `respond`. The rule 5b line (`clarify.exhausted`) states only that no single charge was found; the `connect.*` line states the next step. With `request_call = "opened_case"` (rule 3a with a charge, D-020) the turn runs plan → act → verify like a dispute, then `connect`; whether the high zone blocks there is decided by the engine (D-029), never by the graph. Records the decision pair (D-046, §4.1) | spec 02 `engine.decide()` |
| `plan` | Numbered steps shown to the customer, built from the decision: open the case; block and verify only when `block_card` is in `allowed_actions`; the deadline; a person when the case goes to review or in `confirm`. The exact tool amount (two decimals when exact) plus the `convert_amount` line when it returned a rate in another currency (AC-25). In `confirm` it ends with `plan.confirm_ask` and the confirm chips; a typed yes/no right after that question counts as the chip. Any other plan goes on to `act` | `messages.yaml plan.*` |
| `duplicate` | AC-23: says the charge is already in the active case, with its id and stored deadlines from `get_case`; opens nothing and runs no other write (no block: the person on that case decides) `[assumption]`; a call request goes on that case. `TurnResult.decision` is `null` on that turn, since nothing the decision called for is run, or `connect_person` when the decision sets `request_call` and the call is registered; the engine's decision stays in the D-046 record `[assumption]` (D-050, pending the lead) | `messages.yaml duplicate.*`, `status.*_deadline` |
| `act` | Runs only the writes in `allowed_actions` (D-029: the engine decides whether a call request blocks): `open_case` first (dedupe), then `block_card`. **Invariant: every action in `allowed_actions` gets exactly one record**, also a step that is not tried, so `verify` answers every step the plan promised. No block when `open_case` returns `duplicate_of`, as in AC-23 `[assumption]`. `block_card` is still tried when `open_case` got no answer (`UNAVAILABLE`), since the server requires the open case (spec 03 AC-10) `[assumption]`; after any other `open_case` error it is not tried. Idempotency key `session:transaction:action:run`, where run is the LangGraph run id (`trace_id`); `policies.yaml` `reliability.idempotency_key` has no run part (follow-up for the lead). A call that answers `UNAVAILABLE` (a timeout or a transport error) is retried `reliability.tool_retries` times with the same arguments and key, so the server writes once; any other error is final. An accepted write is `requested`; one never answered, refused, or not tried gets a graph-minted `action_id` and `not_confirmed` (§4.1). A call request that reports a charge opens an `unrecognized_charge` case `[assumption]` | MCP |
| `verify` | Reads each accepted write with its `VERIFIED_WITH` tool and `action_id`, up to 1 + `tool_retries` times (800 ms timeout each). An action is `verified` only when the read returns that `action_id` with a `V-` id, on the same case, or on the same card with status `Blocked`. Otherwise it is `not_confirmed`, and the turn's decision becomes `escalate_unconfirmed_action`. **Invariant (task 04c review): the reply has exactly one line for each action in `allowed_actions`, in one of the four states: `verified` only with the `V-` id of a read of that action on that case or card; no line claims a block that is not verified and none promises a review without a verified case; each write is sent with one idempotency key, retries included** (`tests/test_spec04_act.py` fault grid). The reply then says `SIN CONFIRMAR` / `SEM CONFIRMAÇÃO` and never "blocked" (AC-04). The case id is given only once `get_case` verified it, with its `V-` id and stored deadline (`act.case_opened`, `receipt.*_deadline`). The block line is `receipt.card_blocked`. Every unconfirmed action gets its own line: with a verified case `status.action_not_confirmed`; with none, no case id and no promise of review (`act.case_not_confirmed` for the case, or `act.not_confirmed` when the turn registers a call or asks to sign in; `act.not_confirmed` for any other action) `[assumption]`. An `open_case` that returned `duplicate_of` and that `get_case` verified reports as `duplicate` does (decision `null`, or `connect_person` with a call; row `case_active`, D-050), and its block line is `act.decided_on_case` ("…SIN CONFIRMAR. La persona a cargo del caso {case_id} decide el bloqueo.", the case id from `get_case`), since that turn does not escalate `[assumption]`. A `block_card` answered `DENY` with `POL-HUMAN-REQUEST` (D-043: an open call request holds the block) is not done, but it is no tool failure: its line is `act.block_held` ("…SIN CONFIRMAR. No bloqueé tu tarjeta; una persona decide si bloquearla después de la llamada que pediste."), the turn does not escalate and its chips offer no new call (task 04d, D-056). An `open_case` (or, since task 04d, any write or verifying read) answered `SESSION_EXPIRED` gives each action's line (no call sentence) and then the sign-in line, decision `reauthenticate`, and goes to `respond`: `refuse.reauthenticate` ("no hice ningún cambio") only when no attempt went unanswered and no write was accepted, else `act.sign_in`, which does not say nothing changed. The receipt credit date follows D-030 (ADR 0023 item 5): the credit-deadline line only for an `unrecognized_charge`, a `wrongful_charge` shows the ruling date (the tools cannot tell a duplicate yet). The handoff card for the escalation (`tool_failure`) is built by `respond` (T5) | `get_case` · `get_product_status` · `messages.yaml act.*` |
| `status` | Re-reads in every turn that asks, never from the thread (AC-19), and answers with tool facts and the reading time (`read_at` in UTC to the minute `[assumption]`). A question that names a card and no case reads `list_my_cards` (at most 3 lines); one that names both reads both, cards first (task 04d); any other reads `list_my_cases`, then `get_case` on the case the web's case page names (`configurable.case_id`) only when that listing of the session's customer has it, else the first active, else the latest `[assumption]`, and states its status label (the `messages.yaml status.label` lookup of `queue_status`), its stored deadlines (or `deadline_unknown` for an active case) and the next step (`receipt.what_a_person_does`, or `status.case_done` for a resolved or closed case) (AC-06). No case → `status.no_cases`; no card → `status.no_cards`, with no reading time because `list_my_cards` returns `read_at` only per card. A failed read answers `status.read_failed`, states no status and marks the `status` trace step `error` with `<tool>: not_confirmed`. A status question with dispute words (D-020) reaches `status` only when `route` read an active case (or could not read the cases); its chips also offer "Reportar otro cargo" (F-010 `[assumption]`). Notifications are read for AC-26, P1 (D-001) | `list_my_cards` · `list_my_cases` · `get_case` |
| `connect` | Registers a call request where spec 02 `request_call` says: `active_or_general` → on the active case, or a general one; `opened_case` → on the case `open_case` returned this turn and `verify` confirmed (the existing case when it returned `duplicate_of`), so the reply names that case; if `open_case` or its verify fails (or no case was opened this turn), the call is a general request with no case, still registered (AC-28: never refuse), never on another charge's active case, while the case is reported as not confirmed (AC-18) `[assumption]` (task 04e review); `general` → a general request with no case (rule 5b). The active case is read in that turn with `list_my_cases`: the one the web's case page names when it is active, else the first active; if the read fails, a general request `[assumption]` (task 04e). A call on a case is read back once with `get_case` and its `action_id`: `verified` only with the read's V- id, else it stays `requested` (AC-18, no retries `[assumption]`); a general call stays `requested` (D-026). `opened_case` uses the case set this turn only when no `open_case` action of the turn is unverified (the contract with T4). It says the call request is registered and when to expect the call, using `expected_contact_by` from `request_call` (D-008); when it is `null`, the reply promises no time. Without a verified session, the bank's general contact path with no data | `request_call` · `messages.yaml connect.*` |
| `clarify` | Options (1 to `max_candidate_transactions` candidates, as cards labelled amount · date · merchant) or a request for amount/date; counts turns; a declined confirm answers `plan.declined` and clears the selection | templates in every arm; LLM wording deferred to spec 15's `word` gate (task 04f) |
| `route` (other language) | A verified session whose message B0 flags `other_language` (spec 11, G-IN-03 `[assumption]`) gets `refuse.other_language` (session language plus the same sentence in English once) and the `other_language` chip row, by rule: no LLM, no case | `messages.yaml refuse.other_language` |
| `refuse` | DENY or re-authenticate with no data and a way forward | templates in every arm (task 04f) |
| `respond` | Receipt from verified facts; the handoff card from tool results, and it may also carry an accepted-but-unverified case, flagged in `open_questions` ("case K-… not read back by get_case: confirm it exists before acting") `[assumption]` (D-056, pending the lead); reply from templates in every arm (task 04f: S1/S2 rewording is deferred to spec 15's `word` gate; until it passes, no LLM call words a reply, and `build.never_send` is kept as a utility for it); suggestion chips from §4.5. Task 04d: the receipt only once `get_case` verified the case opened this turn (`issued_at` is the turn's last post-condition `read_at`, `receipt_id` a hash of run and case, `case_url` null until the public host is configured `[assumption]`); the handoff card for any case `open_case` returned this turn, verified or not, never for a `duplicate_of` case `[assumption]`: reason `tool_failure` on `escalate_unconfirmed_action`, `identity_unverified` when the session expired mid-turn `[assumption]` (D-056), else the decision's `handoff_reason` when the schema lists it; proposal `approve_block` in the high or medium zone without a verified block, `request_customer_info` in the human zone `[assumption]`; score with `score_source`/`score_version` (D-033). Both list only action ids a tool returned (§4.1) | `nick_of_time.receipt` · `send_case_summary` · `request_call` · `request_reevaluation` · `add_case_info` · `messages.yaml suggest.*` |

### 4.3 Grounding check (ADR 0016)
Every number, date, time and id in `reply`, `receipt` and `handoff` is matched exactly against tool results and the
policy. Anything unmatched is removed, the template version is used instead, and `G-OUT-01` is added to the trace.
Task 04d: the check is the auditor's A4 rule (`nick_of_time.audit.check_grounding`, spec 18), applied per reply line,
per receipt and handoff list item and per field, against the turn's tool results (the score only for the handoff,
since it never reaches the customer) and, for the handoff, the decision's rule and guardrail ids. A shown time must match a tool time exactly: to the second when it shows seconds, else to the minute, so a reading
shown as `YYYY-MM-DD HH:MM UTC` (D-051) matches the tool's `read_at` and a wrong `HH:MM` is dropped; a plan step's own number is
not a fact `[assumption]`. `nick_of_time.receipt.build.papers` is the one entry point that builds and gates both
documents; what an unmatched field does comes from its contract schema (`customer_receipt.schema.json`,
`handoff.schema.json`): required and not nullable drops the whole receipt or card, nullable becomes null, any other
is left out (task 04d review); so an ungrounded receipt `deadline` becomes null rather than dropping the receipt
`[assumption]` (D-056, pending the lead). An action is listed only when a tool result states its `action_id`. The score
and the policy ids ground only the handoff card, never a reply line or a receipt fact (`notifications.never_send`). A
dropped fact adds `G-OUT-01` to `guardrails_triggered` and marks the `respond` trace step `error` with the count; a card
the gate trimmed also carries `G-OUT-01` in its own `guardrails_triggered`; a reply with no line left says
`status.read_failed` `[assumption]`. Statuses are checked by the four-state rule (AC-18) and A5, not here (AC-05).

### 4.4 Arms and modes (spec 01 §6.8)
Arms: `S0` rules + templates, no LLM · `S1` chosen classifier + the LLM chosen by spec 15 (Haiku 4.5 until the
benchmark runs) · `S2` Sonnet 4.6 · benchmark arms (spec 15).
The arm comes from `configurable.arm`; the production default is the arm chosen by the model-selection ADR (spec 15).
Modes (ADR 0020): `replay` (dataset, "today" = `DEMO_TODAY`) for evaluation and processed sample cases;
`live` (real today, recent synthetic transactions for demo customers) for the public demo.

### 4.5 Suggestion chips
Chips help the customer take the next step without typing. Three kinds: **text** (sends its label as the next message),
**action** (sends a structured `action`, skipping the classifier) and **link** (an internal route set by the server).
Labels and chip kinds (`text`, `action`, `link`) live in `messages.yaml suggest.*` (ES/PT); the action payload
(`type`, spec 01 §6.4) and the route are set by server code. ES examples below.
A decline in the confirm state (the `confirm_no` chip "No es ese cargo" or a typed "no") answers with `plan.declined`
and opens nothing [D-039 default, pending the lead].

| State after the turn | Chips |
|---|---|
| First turn (`greet`) | text "No reconozco un cargo" · text "Me cobraron dos veces" · text "¿Cómo va mi caso?" |
| `ask` — candidates shown as cards | action "Ninguno de estos" · text "Muéstrame mis últimos cargos" · action "Hablar con una persona" |
| `ask` — amount or date missing | text "Muéstrame mis últimos cargos" · text "No recuerdo el monto" · action "Hablar con una persona" |
| `confirm` (medium zone) | action "Sí, continúa" · action "No es ese cargo" · action "Hablar con una persona" |
| Case opened, actions verified (receipt) | link "Ver mi caso" · action "Enviarme el comprobante" · action "Que me llame una persona" |
| `handoff` or `escalate_unconfirmed_action` | link "Ver mi caso" · text "Agregar información" · action "Que me llame una persona" |
| `escalate_unconfirmed_action` — the case not verified (no case link) `[assumption]` | action "Hablar con una persona" · text "No reconozco un cargo" · text "¿Cómo va mi caso?" |
| `answer_status` — active case | link "Ver mi caso" · text "Agregar información" · action "Que me llame una persona" |
| `answer_status` — resolved, within the re-evaluation window | action "Pedir reevaluación" · link "Ver mi caso" · action "Que me llame una persona" |
| `answer_status` — resolved or closed (until AC-24), or a status question with dispute words (F-010) | link "Ver mi caso" · text "Reportar otro cargo" · action "Que me llame una persona" `[assumption]` |
| `answer_status` — cards | text "¿Cómo va mi caso?" · text "No reconozco un cargo" · action "Hablar con una persona" `[assumption]` |
| `answer_status` — no case | text "No reconozco un cargo" · text "Me cobraron dos veces" · action "Hablar con una persona" `[assumption]` |
| `answer_status` — read failed (`status.read_failed`) | text "¿Cómo va mi caso?" (reads again) · action "Hablar con una persona" · text "No reconozco un cargo" `[assumption]` |
| `connect_person` — with a case | link "Ver mi caso" · text "Reportar otro cargo" |
| `connect_person` — no case | text "Reportar otro cargo" · text "¿Cómo va mi caso?" · text "Me cobraron dos veces" (F-007, so every reply ends with 2–3 chips) |
| `connect_person` — `request_call` failed (`connect.request_failed`, action `not_confirmed`) | action "Hablar con una persona" (retries the call) · text "¿Cómo va mi caso?" · text "No reconozco un cargo" |
| `deny` / out of scope | text "No reconozco un cargo" · text "¿Cómo va mi caso?" · action "Hablar con una persona" |
| `reauthenticate` | link "Verificar de nuevo" · action "Hablar con una persona" (general contact path, AC-28) |
| `reauthenticate` — the session expired after the case was verified (task 04d) | link "Verificar de nuevo" · link "Ver mi caso" · action "Hablar con una persona" `[assumption]` |
| Case opened, the block held by an open call request (D-043, task 04d) | link "Ver mi caso" · text "Agregar información" · text "¿Cómo va mi caso?" (a call is already registered, AC-30) `[assumption]` (D-056) |

Rules: at most 3 chips; a path to a person is always among them, except right after `connect_person` or on a held block
(a call is already registered), and in the three starter chips of AC-31; every action chip passes AC-30: a chip about a case (`view_case`, `send_summary`,
`add_info`, `request_reevaluation`) only when the turn has a case, then a person chip is added and the row is filled to
2 chips when needed (task 04d). No row offers a block chip, and the re-evaluation chip waits for AC-24; chips are stored with the reply exactly as shown and the web shows them only under the last reply (spec 07).

## 5. Non-functional requirements
- **Latency:** p95 per turn ≤ 6 s with S1 `[assumption]`; first progress label within 1 s.
- **Cost:** ≤ 0.02 USD per case with S1 `[assumption]`, measured by the harness.
- **Graceful degradation:** if Bedrock fails or the per-conversation or daily budget is exhausted (G-OPS-01), the run continues
  as `S0` and says so in the trace. `[assumption]` The daily cap binds only runs the api starts (it passes the day's
  spend); runs started outside the api (Studio, the SDK, an eval run against the deployment) are not capped by it.
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
- **Q1 — replies:** templates by default; LLM rewording only in S1/S2, behind the grounding check. Task 04f: deferred until
  spec 15's `word` gate passes, so every arm sends templates.
- **Q2 — additions to spec 01** (§6): applied with the spec 01 update.
- **Q3 — returning customer:** status and stored deadline from `get_case`; new information through `add_case_info`; the
  full history lives in `/case/{id}`.
- **Q4 — reversed charges:** the agent says the charge was already reversed and opens no case.
- **Q5 — suggestion chips** (lead requirement): mandatory in the agent and the web; chosen by rules (§4.5), never by the
  LLM, so a chip never offers something the policy would deny.
- **D-008 (lead, 2026-10-04):** `request_call` returns `expected_contact_by`; `connect` says when to expect the call.
- Assumptions: the p95 ≤ 6 s and ≤ 0.02 USD per case targets are confirmed or corrected by the benchmark (spec 15).

## 9. Out of scope
Case investigation, chargebacks, provisional credit (always a person), voice, multi-agent designs, free-text outbound
messages.

## 10. Plan, tasks and verification
- [ ] T1 — State and graph skeleton on the spec 01 echo graph; `langgraph dev` locally · AC-07, AC-27. Task 04a: state,
      skeleton and AC-27 done in `apps/agent/agent/intake.py`, served as `dispute_intake` (D-048 applied once
      T3–T5 landed; the echo graph stays as `dispute_intake_echo`); `retrieve` landed in T3 and `status` in T6. Open: a
      `langgraph dev` run and AC-07 on Platform (T8)
- [x] T2 — `greet`, `understand` (rules arm + injection rules), `route` · AC-03, AC-09, AC-10, AC-15 (task 04a, with
      `refuse`, a general-call `connect` (AC-28 part; T6 puts the call on the active case) and AC-33 (proposed);
      tests `tests/test_spec04_graph.py`)
- [x] T3 — `retrieve`, `decide`, `plan`, `clarify`, `refuse` · AC-02, AC-11, AC-12, AC-13, AC-16, AC-23, AC-25
      (task 04b, with `duplicate` and the D-046 decision record; tests `tests/test_spec04_decide.py`). AC-02, AC-13
      and AC-23 done. Finished by later tasks: opening the case after the plan (AC-11, AC-12, AC-16: T4), the
      handoff card with `approve_block` / `requires_human` (AC-11, AC-12: T5) and the display amount on the receipt
      (AC-25: T5). Q4 (a reversed charge opens no case) is not handled yet
- [x] T4 — `act`, `verify` with retries, the four-state vocabulary and the unconfirmed path · AC-01, AC-04, AC-18
      (task 04c; tests `tests/test_spec04_act.py`). AC-04 and AC-18 done; AC-01 done except the receipt with a date
      (T5). Also opens the case for AC-11, AC-12 and AC-16; their handoff cards are T5. `messages.yaml` 0.5.0 adds
      `act.case_opened`, `act.case_not_confirmed`, `act.not_confirmed`, `act.decided_on_case` and `act.sign_in`
- [x] T5 — `respond`: receipt, handoff, grounding check, suggestion chips · AC-05, AC-20, AC-21, AC-22, AC-26,
      AC-29, AC-30, AC-31, AC-32 (task 04d; tests `tests/test_spec04_respond.py`). Done: AC-05, AC-20, AC-21, AC-22
      (no template claims an assignment), AC-29, AC-30; AC-31 and AC-32 were done in T2. Also finishes AC-01 (the
      receipt with a date) and the handoff cards of AC-11 and AC-12, plus D-043 and D-030. AC-26 (send by channel) is
      P1 (D-001) and open. Open follow-up: `add_case_info` for the "Agregar información" chip (AC-06, T6). Done in task 04d2: `status.no_cards`
      shows the listing's `read_at` (contract 1.4.0); the receipt row offers `check_case` ("¿Cómo va mi caso?") instead of
      "Enviarme el comprobante" until AC-26 exists; the `verify` lines show `read_at` as `YYYY-MM-DD HH:MM UTC` (D-051).
      `case_url`: when the public host is configured, build it only from `get_case`'s
      `case_id` and pass it through the gate.
      Status grounding (D-056, pending the lead): nothing fills `FinalState.status_replies` yet, so before T7 (S1/S2)
      either the api emits `status_replies` from the `status` turns or the gate matches the status label against the
      read's `queue_status`/`status`. Spec 18 follow-up: A4 still reduces a timestamp to its date; port the gate's
      exact time match into A4, and give A4 a `POL-[A-Z-]+` id shape (today only some policy ids yield a token, e.g.
      `POL-ZONE-HIGH` yields none), or add a `never_send` check in `respond`, before T7. Every end-to-end spec 04 test asserts how many facts the gate dropped (0 unless it
      injects one), so a node that does not hand `respond` a tool result it states fails the suite. Task 04f took
      the conservative option: no reply is reworded in any arm, so every status line stays template text matched to
      its read; `build.never_send` is ready for spec 15's `word` gate (A4 itself is unchanged)
- [ ] T6 — `status` and `connect` nodes and the returning-customer path · AC-06, AC-19, AC-24, AC-28. Task 04e:
      AC-19 and AC-28 done (re-read per status question, failed reads reported, the call on the active case or a
      general one, read back with `get_case`), plus the D-020 / F-010 cases (status or a person with dispute words);
      tests `tests/test_spec04_status.py`. AC-06 partial: `get_case` label, stored deadlines and next step done;
      recording new information with `add_case_info` (the "Agregar información" chip) is open. AC-24 (P1, D-001)
      is open, so no re-evaluation chip is offered yet
- [ ] T7 — progress stream; S1/S2 wiring (Bedrock, structured output); usage; graceful degradation to S0 · AC-14, AC-17.
      Task 04f did S1/S2 `understand` + usage + degradation (`nick_of_time.llm.steps`; tests
      `tests/test_spec04_arms.py`). AC-14 done: every run returns `usage` (one row per billed call; the api adds the
      session's `run_id`, D-023 `[assumption]`) and `denials`. `understand` asks the arm's LLM below τ
      (`clarify.intent_confidence_min`), only in a verified session and never for a flagged or cross-customer message,
      with forced tool use and the intent schema (D-011, D-016); its slots must fit `search_transaction`'s input and its
      confidence is capped below τ, and an LLM-only `human_request` registers no call unless B0 also reads one (D-065
      `[assumption]`). An LLM error, a timeout (4 s read + 2 s connect per request, one attempt `[assumption]`), output
      that fails the schema or the slot contract, a missing price or the G-OPS-01 cap (0.02 USD per conversation,
      checked before calling, D-064) runs the step as S0, marks the `understand` trace step `error` with
      `S1 -> S0: <reason>` and keeps any billed call in `usage`. D-058, availability first: a missing price (`anthropic`
      has none yet `[assumption]`) runs that turn as S0 (`no price (D-058)`); the graph's load only logs it, since S0
      and the echo graph share the Platform server, and CI's `config.check_prices()` test fails when a default
      production (bedrock) arm has no price row. Open: AC-17
      (progress stream, P1, D-001); S1/S2 rewording (spec 15 `word` gate). The per-day cap (G-OPS-01) is checked
      before calling too: the day's spend of every session (`configurable.llm_day_spent_usd`, the api's `llm_calls`
      sum, spec 05 AC-18) plus the call's estimate above `configurable.llm_day_cap_usd` (else env `DAILY_LLM_CAP_USD`,
      5 USD `[assumption]`) runs the step as S0 with `S1 -> S0: daily cap` and G-OPS-01
- [ ] T7a — Shared LLM client `nick_of_time.llm` (`fake`, `bedrock`, `anthropic`) and `nick_of_time.config.resolve(arm)`:
      forced tool use with the tool → any → auto ladder (D-011), temperature 0 or provider default recorded per arm
      (D-016), usage, latency and cost from a price table, `ProviderUnavailable` for provider errors (graph degrades to
      S0, section 5), `NoStructuredOutput` when the accepted mode returns no or schema-invalid input (caller decides;
      it carries the billed call's usage); timeouts connect 2 s, read 15 s, 2 attempts in total (Bedrock
      `total_max_attempts`) and 15 s, 1 retry (Anthropic) `[assumption]`; Anthropic is
      an operator switch (`LLM_PROVIDER=anthropic`), not a runtime failover; a per-task arm config (spec 15 section
      4.2) is planned for spec 15 T6 · supports AC-14; tests `tests/test_spec04_llm.py` (lead decision D-003)
- [ ] T8 — Platform deployment; `/agent` content · AC-07, AC-08
- [x] INT1 — the graph against the **real** MCP server, locally and offline · AC-01, AC-11, AC-12, AC-18, AC-28 (tests
      `tests/test_spec04_int_local.py`, harness `tests/local_mcp.py`). The harness builds the app `python -m mcp_server`
      serves (`mcp_server.__main__.build`: API-key middleware, gate, every tool module on main) over the entry point's
      MemoryStore (`MCP_DEV_MEMORY_STORE=1`) or, with `TEST_DATABASE_URL`, a PostgresStore in a throwaway schema; seeds a
      verified session for the case's customer; and runs the graph with the client config Platform uses (`MCP_URL`,
      `MCP_API_KEY`, a dummy key), its httpx client bound to the app through an ASGI transport, so no socket opens. Arm
      S0, replay (DEMO_TODAY 2026-06-01). Gold is a tiny fixture built from each eval case's `initial_state` (runs in
      CI) or the full gold: `GOLD_PATH=data/gold .venv/bin/python -m pytest -q tests/test_spec04_int_local.py` (skipped
      without it), plus `TEST_DATABASE_URL=postgresql://… -m postgres` for the store variant. Cases: EV-0001, dev
      EV-0101–0104, EV-0106 and a D-029 call request on EV-0001's charge; the medium-zone confirmation is sent as the
      confirm chip, since B0 reads only a bare "sí" as the answer. Wiring fixed: the graph now sends `X-Trace-Id` = the
      state's `trace_id` (each node that calls tools gets it in its config through `traced`), so every store event of a
      turn carries its one trace id, also on a run with no run id (spec 03 §6). The full-gold variant has a postgres
      param only when gold is present, so CI's `-m postgres` run (no gold) skips nothing. Found here and fixed
      in #139: dev EV-0115's pt injection opened a case (now DENY, G-IN-01). Open (B0 rules, spec 11): EV-0105, EV-0107,
      EV-0118 and EV-0119 are not understood by B0 as written
- [x] T-MSG — `contracts/messages.yaml`: ES/PT templates for greet, plan, connect, suggestion chips, status labels,
      receipt and notify (placeholders `{name}`, tool facts only). Supports AC-06, AC-10, AC-11, AC-15, AC-16, AC-18,
      AC-19, AC-21, AC-25, AC-26, AC-28, AC-29, AC-31, AC-32; behavior tested in T2–T6. T2–T7 extend the file (clarify,
      refuse, progress AC-17, duplicate AC-23, re-evaluation AC-24, reversed charge); each extension is a contract
      change that needs the lead's approval. MSG2 added refuse.deny, clarify.ask_what and plan.declined
      (ES/PT) for the web mock (supports AC-03, AC-11).
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
