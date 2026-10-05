# Spec 03 — MCP server with the 16 customer tools

- **Feature:** a FastMCP server that gives the agent exactly sixteen tools over the gold data and Postgres — to find the
  charge, act on it, verify it, follow up on the case, and talk in the customer's currency — each scoped to the
  session's customer, idempotent where it writes, and re-checking the policies before acting.
- **Status:** Draft (tool contract v1.1, updated 2026-10-04: Q4 decided — 9 new or enriched tools, case lifecycle, modes)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** AI Engineering (tools used safely; permissions in the service layer)
- **Depends on:** spec 01 (contract §6.3, store, ids), spec 02 (engine, clock, fx) · **Enables:** 04 · **ADRs:** 0005,
  0006, 0008, 0010, 0016, 0019, 0020
- **Issue:** #5

> Minimal profile plus §7 and §8, because the search rules decide which transaction the customer disputes and the
> lifecycle rules decide what a returning customer can do.

---

## 1. Introduction
The agent can only act through these tools. Every permission lives here, not in the prompt: the `customer_id` comes
from the session row, never from the arguments; a write re-checks the policy engine; a write is idempotent; the read
tools return state from the database with the time of the reading, so the agent reports only what it verified. The
agent never writes an outbound message: the only notification tool sends an approved template. The server runs at
`https://mcp.nickoftime.salazarvalverdeai.com/mcp` (streamable HTTP, `X-API-Key`) and locally at
`http://localhost:8100/mcp`.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 come from issue #5 with the same numbers; AC-07 onward are added by this spec.

**Scope and safety**
- **AC-01** — When customer X's session calls `search_transaction`, the tool shall return only X's transactions, even
  if the text mentions another customer. · [T]
- **AC-02** — If the session expired or does not exist, then every tool shall answer `SESSION_EXPIRED` with no data. · [T]
- **AC-03** — When `block_card` is called twice with the same `idempotency_key`, there shall be a single block. · [T]
- **AC-04** — When `block_card` completes, `get_product_status` shall return `Blocked` (an overlay row in Postgres; gold
  is never written). · [T]
- **AC-05** — If a fault is injected for a tool (`sessions.tool_faults`), then that tool shall answer `UNAVAILABLE`. · [T]
- **AC-06** — Without a valid API key, `https://mcp.nickoftime.salazarvalverdeai.com/mcp` shall answer 401. · [C]
- **AC-11** — No tool output shall contain another customer's data or personal fields (document number, full e-mail,
  phone, address); `get_customer_profile` returns the first name only and channel addresses masked. · [T]
- **AC-12** — Every `DENY` shall be written to `policy_denials` with `trace_id`, `policy_id` and guardrail id. · [T]
- **AC-13** — Tool latency p95 shall stay under 800 ms on the full gold v1 (`reliability.tool_timeout_ms`). · [C]

**Finding the charge**
- **AC-07** — When a MX customer says "1,250 pesos" for a USD transaction, `search_transaction` shall match it through the
  policy rate (18.0 MXN/USD) within ±2%. · [T]
- **AC-08** — `search_transaction` shall return only card transactions with status `Approved` or `Pending`, dated within
  `window_days` of `approx_date` and never after `clock.today(mode)`, ranked by match quality, at most 4 (so the policy
  can see "more than 3"). · [T]
- **AC-14 [P1]** — While the session is in `live` mode, `search_transaction` shall also search the customer's
  `demo_transactions` and flag those results `synthetic: true`; in `replay` it shall never read them (P1, D-001 in
  spec 01 §10 T4). · [T]

**Acting**
- **AC-09** — If `open_case` receives a `zone` different from the zone computed from `get_fraud_score` for that
  transaction, then it shall answer `DENY` with `POL-ZONE-MISMATCH` (G-IN-02). · [T]
- **AC-10** — If `block_card` is called for a product without an open case in the same session and run, or the policy
  engine does not allow the block, then it shall answer `DENY` with the policy id and write nothing. · [T]
- **AC-15** — If `open_case` is called for a transaction that already has an active (not closed) case of the same
  customer, then it shall return that case with `duplicate_of` and write nothing. · [T]

**Following up (returning customer)**
- **AC-16** — `get_case`, `list_my_cases`, `get_product_status` and `list_my_cards` shall read the database on every call
  and return `read_at`; `get_case` shall return the stored deadlines with their source (never recomputed), the
  customer-facing status label, the customer-visible timeline, `taken_by_person` and `related_case_id`. · [T]
- **AC-17** — `add_case_info` shall accept text only for an active case, at most 1,000 characters, and shall reject card
  numbers, CVV and passwords with `G-IN-04`; the stored text is marked as customer data. · [T]
- **AC-18** — `request_call` shall keep one open request per case; a second request returns the existing one; the
  result carries `expected_contact_by` (`YYYY-MM-DD` or `null`), computed from `contact.callback_within_business_days`
  counted from `clock.today(mode, country)` (replay: notice 2026-06-01 → 2026-06-02), stored in the `call_requested`
  event payload and never recomputed; `null` when the policy has none (D-008). · [T]
- **AC-19** — `request_reevaluation` shall: move a resolved case within the window back to `review` with
  `reevaluation_requested` and the reason; deny a resolved case outside the window with `POL-REEVAL-WINDOW`; open a new
  case with `related_case_id` for a closed case; and return an active case unchanged with `already_in_progress`. · [T]

**Currency and notifications**
- **AC-20** — `convert_amount` shall return `{amount, currency, rate, rate_source, as_of}` from `fx.convert()` (spec 02),
  or `converted: null` when no verified rate exists. · [T]
- **AC-21** — `send_case_summary` shall send only the approved receipt template, only to a channel confirmed by the
  customer (Telegram link or e-mail confirmation link), at most 3 times per hour per session; the e-mail addresses in
  the dataset are never loaded by this server. · [T]
- **AC-22** — `list_my_notifications` shall return each notification with its masked address and the delivery status of
  its latest `notification_deliveries` row (`queued|sent|delivered|bounced|failed`). · [T]

## 6. Tool contract and behavior
Models are `<Name>In` / `<Name>Out` in `contracts/tools.py` v1.1; every tool also accepts the header `X-Trace-Id` (the
graph's run id). Kind: R read · W write · N notification.

| Tool | Kind | Behavior |
|---|---|---|
| `get_customer_profile` | R | First name, language, country, `display_currency` (session preference, else the country's from `policies.yaml`: `amount_gate.by_country.<CC>.currency` until spec 02 FR-09 adds `display_currency` `[assumption]`), confirmed channels with masked addresses (`a···@domain`, Telegram `···` + last 4 `[assumption]`) from the store's `customer_channels` accessor (task 01g, PR #87; none listed until T8 wires it). A customer missing from gold or a country outside the policy answers `UNAVAILABLE`. |
| `search_transaction` | R | Loads the session's customer; filters gold `transactions_enriched` to that customer's cards (`Tarjeta Débito`, `Tarjeta Crédito`), status `Approved`/`Pending`, `approx_date ± window_days` (default 7; if no date, the last 30 days) and `≤ clock.today(mode)`; in `live` also the customer's `demo_transactions` (AC-14). Optional filters: **amount** (±2%, compared in the transaction currency and in the customer's local currency through the policy rates MXN 18.0, ARS 350, COP 4,000), **merchant** (case- and accent-insensitive token match; null merchants still match on amount and date). Ranks by amount match, then date distance, then merchant similarity; returns ≤ 4 `Transaction` with `synthetic`, without `fraud_score` or `split` (D-026). Ties break on `transaction_id`; a null `amount_usd` is the amount for USD and amount ÷ the policy rate (2 decimals) for ARS/COP `[assumption]`; `amount_usd` is internal (matching only) and never rendered to the customer. "Today" is `clock.today(mode, country)` (spec 02, PR #67): `DEMO_TODAY` 2026-06-01 in replay, the real date in the customer's time zone in `live`; until AC-14 lands, a `live` session searches gold only `[assumption]`. |
| `get_fraud_score` | R | Provider `dataset` (ADR 0006): `transactions.fraud_score` for a transaction of the session's customer, `source: "dataset"`, `version: "gold-v1"`; for a synthetic transaction, its generated score with `source: "synthetic"`. Another customer's transaction answers the same `NOT_FOUND` as an unknown id (no existence oracle; D-052, confirmed by the lead 2026-10-05; contract wording in PR #107); the probe is still written to `policy_denials` with `POL-CROSS-CUSTOMER` (`scope.cross_customer_request: deny_and_log`), its rule's guardrail (G-SES-02) and best-effort (a failed write still answers `NOT_FOUND`), its policy id never shown. |
| `compute_deadline` | R | Country from the customer (`México`→MX, `Argentina`→AR, `Colombia`→CO, `Brasil`/`Brazil`→BR, `Perú`→PE, `Chile`→CL), product from the card type (`Tarjeta Débito`→debit, `Tarjeta Crédito`→credit), opened on `clock.today(mode, country)`, `abroad` when `transaction_country` ≠ customer country (a null `transaction_country` is not abroad, the earlier ruling date `[assumption]`), `charged_at` the gold transaction date; delegates to `clock.deadline()` (spec 02 §4.3); returns `deadline_source`, `source_url` and `verified_on`. Another customer's transaction answers `NOT_FOUND` as `get_fraud_score` does. A country with no verified entry, or none that maps to `policies.yaml` `countries`, answers `UNAVAILABLE` with `POL-CLOCK-UNKNOWN` and no date, since `ComputeDeadlineOut` requires a source `[assumption]`: the case is still opened and a person decides. |
| `open_case` | W | Duplicate check first (AC-15); recomputes the zone from the score (mismatch → AC-09); idempotent on `idempotency_key` (prefixed with `run_id`); writes `cases` (with `mode`, `related_case_id` when given) and `case_events(case_opened)`; when the engine's own `queue_status_after` for this dispute is `review` (spec 02 §4.2: medium or human zone, or a high-zone block a person must approve), also `status_changed(review)` in the same write, so it commits or rolls back with the case (`[assumption]` pending D-063/D-066); returns `case_id`, deadlines and `duplicate_of`. |
| `block_card` | W | Requires an open case for that product in the session and run; asks `engine.check("block_card", zone, supervised_mode=…, call_requested=…, amount=…, currency=…, country=…)` (spec 02 §6; `call_requested` is true while the case has an open call (§8, D-042), so the block is denied, D-029); on allow, writes `product_overrides(Blocked)` and `case_events(card_blocked)`, returns `state: "requested"` (not yet verified). In the same write it moves a `new` case to `verification` (`approval.manual_check_leaves_case_in`: the automatic action ran; the customer label `En revisión` claims nothing about the block, so accepted ≠ verified holds); a move another writer already made is not an error, any other failure fails the write (`[assumption]` pending D-063/D-066). |
| `get_product_status` | R | Latest override for the product in the same `run_id`, else gold `product_status`; returns type, last 4, status and `read_at`, plus `action_id` + `verification_id` only when called with a write's `action_id` whose post-condition holds (D-025). No cache. It never moves a case (`[assumption]` pending D-063: the writes move the queue; a high-zone case held by a call request is moved to `review` by `request_call`, task 03d1, PR #124). |
| `list_my_cards` | R | The session customer's cards with the same fields as `get_product_status`, never with an `action_id` or `V-`: a listing verifies no write (D-025). |
| `get_case` | R | Replaces `get_case_status`. Status label for the customer (`Recibido`, `En revisión`, `Resuelto`, `Cerrado` and PT equivalents from `messages.yaml`), stored deadlines with source, transaction, visible timeline, `taken_by_person` (an `assigned` event exists), `related_case_id`, `read_at`. |
| `list_my_cases` | R | The session customer's cases (active first) with status label, deadlines, last 4 and `updated_at`. |
| `add_case_info` | W | AC-17; writes `case_events(customer_info_added)`. |
| `request_call` | W | AC-18; `{preferred_time?}`; writes `case_events(call_requested)`; returns `{event_id, expected_contact_by}` (D-008): a `YYYY-MM-DD` date or `null`, computed by the tool from `contact.callback_within_business_days` with `clock.add_business_days` (spec 02), stored in the event and never recomputed; the tool never invents a date. `RequestCallResult.expected_contact_by` (`Optional[date]`) lands in `contracts/tools.py` v1.1 (task 01b). |
| `request_reevaluation` | W | AC-19; asks `engine.reevaluation_allowed()` (spec 02); writes `case_events(reevaluation_requested)` + `status_changed(review)`, or a new case + `case_events(related_case_opened)` on the closed case. `already_in_progress` writes nothing and returns the `action_id` and `event_id` of the write that holds the case active (the original `open_case` `A-`, or an earlier `request_reevaluation`); the agent reports it as "already in review", never as a new verified action (spec 04, task 04c). |
| `convert_amount` | R | AC-20; never changes a deadline or a zone. `to_currency` null → the profile's display currency. A result without a `rate_source`, or in a currency other than the one asked, counts as no verified rate. Until spec 02 T7 ships `fx.convert()`, no rate is verified, so it answers `converted: null`; the `amount_gate` rates are never used (spec 02 §4.2). |
| `send_case_summary` | N | AC-21; renders `messages.yaml receipt.*` with the case's verified facts, writes `notifications(trigger=on_request)` + `case_events(notification_sent)`, hands delivery to the api's sender (Telegram or Resend); returns `notification_id` and `state: "requested"`. |
| `list_my_notifications` | R | AC-22. |

`get_fraud_score` never returns `source: "synthetic"` in `replay`: synthetic transactions exist only in `live` (ADR 0020
rule 2), and only a live synthetic score decides as `[simulated]` (spec 02 D-027; the handoff card carries it as
`score_source`, D-033). A T3 test pins it.

**Case lifecycle** (with `case_queue.transitions` of `policies.yaml`):

| Situation | What happens | Who decides |
|---|---|---|
| Same transaction, active case | No new case; the existing case id and deadline are returned (AC-15) | Automatic |
| Resolved case, customer disagrees, within the window | Back to `review` with the reason (`resolved → review` already exists) | A person |
| Resolved case, outside the window | `DENY POL-REEVAL-WINDOW`; the agent offers a call | Policy |
| Closed case | Never reopened by the customer; a new case with `related_case_id`; its deadline runs from the new notice `[assumption, verify per country in spec 02 T3]` | Registered automatically; decided by a person |
| Customer wants to close or reopen a case | Not allowed: closing and reopening are analyst actions in the api | — |

**Common rules:** API key middleware (every route but `/health`, which returns no customer data and no secret, answers 401 without a valid
`X-API-Key`; an `MCP_API_KEY` under 32 characters refuses to start); session check first (AC-02); fault check second
(AC-05); then per-session limits of 30 calls/min, 5 writes/min (W and N tools) and 3 notifications/hour (D-041),
counting admitted calls only `[assumption]` (G-TOOL-01, G-OPS-01); then strict Pydantic validation (`extra="forbid"`),
which answers `DENY` to an unexpected argument such as `customer_id`. A rate-limit or schema `DENY` cites
`POL-DEFAULT-DENY` and G-TOOL-01 (D-040). Errors are returned as `ToolError`, never raised: a tool with no handler yet,
a failing handler or a failing audit answers `UNAVAILABLE`. Tool outputs are typed data, delimited when passed to the
LLM (G-IN-01). Every call is audited as one JSON line on stdout (D-040) with `trace_id` (`X-Trace-Id`, else a minted
`mcp-` id), actor `agent` and hashes of the input and the session id, never either one; every `DENY` is a
`policy_denials` row (AC-12); a handler's `DENY` cites its rule's guardrail (`policies.yaml` `rules.<id>.guardrail`,
passed to the gate), else G-POL-01 (T4). A handler's
`NOT_FOUND` that carries a policy id (a cross-customer probe) is written as a denial too, best-effort and with the
rule's own guardrail, and answered without it (D-052, confirmed 2026-10-05).
The analysts' actions never appear in this server.

**Verification, call requests and score sources** `[assumption]` (defaults pending the lead):
- D-025: a write returns `state: "requested"` and no `V-` id. The read that verifies it (`VERIFIED_WITH` in
  `contracts/tools.py`) mints the `verification_id` and the store persists it with that read (event `action_verified`,
  task 01c).
  `get_case`, `get_product_status` and `list_my_notifications` take an optional `action_id` and return it with a
  `verification_id` only when that write's post-condition holds; otherwise, and for a plain status read, they return
  `read_at` only (both ids or neither). A duplicate that writes nothing (`open_case` AC-15, `request_call` AC-18,
  `request_reevaluation` `already_in_progress` AC-19) returns the original write's `action_id` and, for the last two,
  its `event_id`, so the action stays verifiable.
- D-026: `search_transaction` returns no `fraud_score` or `split`, because the zone comes only from `get_fraud_score`.
  A `request_call` without `case_id` writes no `case_events` row. It returns `case_id: null`, its `action_id` and an
  `event_id` (`E-`) that keys an append-only `call_requests` row. No customer read verifies it, so the agent reports it
  only as `requested`, never as verified. Task 03d1 added `call_requests` to spec 01 §6.5 and to §7 here.
- D-027: `synthetic` is a score source. `get_fraud_score` returns `source: "synthetic"` with the stored score of a
  live-mode `demo_transactions` row (`policies.yaml` `scoring.providers.synthetic`).

## 7. Data model touched
Reads gold `transactions_enriched`, `products` and `customers` through DuckDB; from `customers` the loader selects only
`customer_id`, `first_name` and `country`, so `email`, phones, `document_number` and `address` are never loaded (AC-11,
AC-21). From `products` (`apps/mcp/mcp_server/cards.py`, T4) only the card rows' `product_id`, `customer_id`, type,
`product_status` and the last 4 digits of `product_number` (the full number is never loaded); from
`transactions_enriched` also each card transaction's `transaction_country`, which tells `open_case` an operation
abroad. Card transactions are loaded at startup into an in-memory table indexed by `customer_id` (≈ 516k rows). Reads
and writes Postgres through `nick_of_time.store`: `sessions` (read), `demo_transactions` (read, `live` only), `cases`,
`case_events`, `product_overrides`, `idempotency`, `policy_denials`, `notifications`, `notification_deliveries` (read),
`customer_channels` (read), `call_requests` (a call with no case, D-026). Takes the store's `serialize` lock (a
Postgres transaction-level advisory lock) on `open_case:<run>:<customer>:<transaction>` around the duplicate check and
the insert (AC-15, task 03c), and so does `request_reevaluation`'s related case (task 03d1).
`contracts/policies.yaml` gains the rule `POL-ZONE-MISMATCH` (G-IN-02, AC-09; D-060: `version` stays 2, since the
engine's behavior does not change).

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — currency:** match MX pesos against USD transactions through the policy rate (18.0 `[assumption]`). Display in
  the customer's currency goes through `convert_amount` with official reference rates (spec 02 §4.4).
- **Q2 — statuses:** `Declined` and `Reversed` transactions are excluded; a reversed charge is reported as already
  reversed (spec 04).
- **Q3 — order of writes:** `open_case` first (the ticket is always opened), then `block_card`, which requires the open case.
- **Q4 — tool contract v1.1:** ~~open~~ **Decided (lead, 2026-10-04):** the 16 tools of §6 and the case lifecycle above
  (improvement #13).
- **D-040 (lead, 2026-10-04):** the tool-call audit is a stdout log line for now; gate denials cite `POL-DEFAULT-DENY`
  with G-TOOL-01, with no `contracts/` change. **D-041 (lead, 2026-10-04):** the notification limit is per session (AC-21).
- **Source of `call_requested` for `block_card` (task 03c, T4) — decided by the lead, 2026-10-04 (D-042, ADR 0024):**
  store-backed. `BlockCardIn` gains no field: like every other `check()` input (the case zone, `settings_events`, the
  gold transaction), the flag comes from trusted state, not from the agent. It is true while the case has an open call:
  the case has a `call_requested` event **or** was opened with `handoff_reason` `person_requested`, and no
  `approve_block`, `resolve` or `close_case` on that case followed. The second condition covers spec 04's `connect`
  fallback: when `open_case` or its verify fails, the call is registered as a general request with no case, so a case
  already written in `review` with `person_requested` may have no `call_requested` event, and it must stay held.
  `[assumption]` (pending lead decision D-055): 03c reads the opening reason from the `handoff_emitted` event of the
  opening turn (a store event type already in spec 01 §6.5, not customer-visible), whose payload carries
  `handoff_reason`; if that event is absent the hold is not open. No field is added to `OpenCaseIn` or any contract.
  So a later plain-dispute turn about the same transaction is denied with `POL-HUMAN-REQUEST`. The hold is per case: a
  different charge opens a new case, which has no hold unless its own turn asked for a person. In the turn of the call
  request the order is spec 04's `act` → `verify` → `connect` (`open_case`, then `request_call` on that case); until
  that write, `decide()` leaving `block_card` out of `allowed_actions` is the guard.
- **End of the hold and the later-turn block (decided by the lead, 2026-10-05; D-042, D-043, ADR 0024):** only the
  analyst actions `approve_block`, `resolve` and `close_case` (spec 05) end the hold, while `take`,
  `request_customer_info`, `mark_ambiguous` and every other analyst action keep it (D-042); `decide()` stays without
  the store and gains no input, so on a later turn that proposes `block_card` while the hold is open, the tool's
  `check()` re-check denies it with `POL-HUMAN-REQUEST` and the agent reports it as not done (D-043). The end
  condition lives in the store and is built and tested in task 03c: tests there show that `take` and
  `request_customer_info` keep the deny and each of `approve_block`, `resolve` and `close_case` lifts it; that a case
  opened with `person_requested` whose call went out as a general request after a failed verify (no `call_requested`
  event on the case) is still held; and that
  the hold is per case (a block on another case of the same customer is not denied by it).
- Assumption: the DuckDB in-memory load fits the EC2 (t3.medium, 4 GB) — measured in T5.
- Single worker, defense in depth (task 03c): the server runs one uvicorn worker (T8), and `open_case` still takes the
  store's advisory lock on the transaction, so two calls with different keys through separate connections open one
  case (AC-15).
- `supervised_mode` (task 03c, follow-up): the console's toggle (spec 08 AC-05, stored as `settings_events`, spec 01 §6.5) does not reach the MCP
  yet; `block_card` passes `supervised_mode=False` and only the file's `approval.supervised_mode` switch applies.

## 9. Out of scope
Analyst tools (they live in the backend API, spec 05); automatic notifications on each status change and the delivery
webhooks (api, spec 13); the agent logic (spec 04).

## 10. Plan, tasks and verification
Implementation goes in one `feat/03-*` branch per task (T1: `feat/03-mcp-server`).
- [x] T1 — FastMCP app, API key middleware, session and fault checks, rate limits, audit · AC-02, AC-05, AC-06 ·
      `apps/mcp/mcp_server/{server,gate}.py`, `tests/test_spec03_server.py`
- [x] T2 — Gold loader (DuckDB in-memory, card transactions by customer), `demo_transactions` in `live`, and
      `search_transaction` ranking · AC-01, 07, 08, 11, 14 · `apps/mcp/mcp_server/{gold,reads}.py`,
      `tests/test_spec03_reads.py`. AC-14 (`demo_transactions` in `live`) is P1 and stays open
- [x] T3 — `get_customer_profile`, `get_fraud_score`, `compute_deadline`, `convert_amount` · AC-11, AC-20. Profile,
      score and convert in `reads.py` (task 03b part 1, PR #106); `compute_deadline` and live search on
      `clock.today` (task 03b2), tests in `tests/test_spec03_{reads,deadline}.py`
- [x] T4 — `open_case` (duplicates, related case), `block_card` with idempotency, engine re-check and denials · AC-03,
      04, 09, 10, 12, 15 · `apps/mcp/mcp_server/{writes,cards}.py`, `tests/test_spec03_case_and_block.py` (task 03c);
      the entry point wires the factory `writes_handlers(gold, policies, store)`; the card index is built over the
      same folder as `gold` (`cards.cards_of`) and loads on its first read, once per process.
      `POL-ZONE-MISMATCH` (G-IN-02) added to `policies.yaml` `rules` (D-060). `[assumption]`s: pending D-054, the
      block is for a case of that card of the session's customer and run in `new`, `verification` or `review` (never
      resolved or closed), the one opened under the call's trace id when there is one, else the newest, since a case
      records no session; the hold reads any `handoff_emitted` `person_requested` of the case (a superset of the
      opening turn's, fail closed, pending D-055); `supervised_mode` is false in `check()` (§8); the idempotency
      arguments hash leaves out `session_id`; a key reused with other arguments, or a blank or unstorable key (its own
      message), answers `DENY` `POL-DEFAULT-DENY`; so does a related case that is open, and a `Declined` or `Reversed`
      transaction (Q2); a transaction with no `transaction_country` is not abroad; the customer's country needs only a
      `COUNTRY` mapping, so a country with no amount gate still opens its case (no clock entry: POL-CLOCK-UNKNOWN)
- [x] T5 — read tools (`get_product_status`, `list_my_cards`, `get_case`, `list_my_cases`) + latency benchmark on
      gold v1 · AC-04, AC-13, AC-16 · `apps/mcp/mcp_server/{case_reads,bench}.py`, `tests/test_spec03_case_reads.py`
      (task 03c; factory `case_reads_handlers(gold, policies, store)`). A verifying read mints a V- only for a write of
      the session's customer and run, of that case or card, that `VERIFIED_WITH` gives to this read, and whose
      post-condition holds; any other `action_id` gets a plain reading. `[assumption]` the timeline labels (ES/PT)
      live in `case_reads.TIMELINE_LABEL` until `messages.yaml` carries them; `related_case_id` of a closed case is the
      newest case opened to follow it. AC-13 `[C]`: `PYTHONPATH=.:packages:apps/mcp python -m mcp_server.bench --gold
      data/gold --customers 200` on gold v1, 2026-10-05, one local laptop process, `Gate.call` without HTTP over the
      in-memory store `[data]`: every tool p95 ≤ 7.12 ms (`open_case`; `block_card` 5.95, `search_transaction` 1.50,
      `get_case` 1.56, the others < 1 ms) against the 800 ms budget; gold load 0.35 s, peak RSS 433 MB. Postgres
      round trips and the EC2 are not measured `[assumption]`; the §8 t3.medium memory assumption holds on this
      reading (433 MB of 4 GB)
- [x] Queue status after the agent's writes (task 03c, `[assumption]` pending D-063/D-066) ·
      `tests/test_spec03_queue_status.py`: the write tools move the queue through `store.change_status` (it enforces
      `case_queue.transitions`; spec 02 §4.5); reads never move a case. The D-029 call-request case is moved to
      `review` by `request_call` (task 03d1, PR #124). Gaps: a high-zone case whose `escalate_unconfirmed_action`
      turn (spec 09 EV-0118) leaves it `new` depends on who writes `handoff_emitted`, pending D-066; and
      `notifications.events.in_review` ("Un analista está revisando tu caso") is wrong for a case that opens in
      `review` with no analyst yet, a wording change recorded for spec 13
- [x] T6 — follow-up tools (`add_case_info`, `request_call`, `request_reevaluation`) · AC-17, AC-18, AC-19 ·
      `apps/mcp/mcp_server/followups.py` (`followups_handlers`, wired by name by T8), the store's `call_requests`
      (D-026), `tests/test_spec03_followups.py` on both backends. `[assumption]`s: a PII rejection cites
      `POL-OUT-OF-SCOPE`, the only rule of G-IN-04 (the gate writes G-POL-01 until T4 maps rule guardrails); a call stays
      open until `approve_block`, `resolve` or `close_case` (the D-042 hold end); the re-evaluation window is 30 days
      (spec 02 §4.4 proposal) until `reevaluation_allowed()` ships; a related case copies the closed case's facts and
      zone, opens on today, goes to `review`, keeps the reason in its `reevaluation_requested` and takes its deadline
      from gold with `abroad` false (none without the charge); its result has `case_id` = the new case and
      `related_case_id` = the closed one; a write on a closed case is `DENY POL-DEFAULT-DENY`
- [ ] T7 — `send_case_summary`, `list_my_notifications` · AC-21, AC-22
- [ ] T8 — entry point, Dockerfile and compose service `mcp` · AC-02, AC-06, AC-12 · `apps/mcp/mcp_server/__main__.py`,
      `apps/mcp/Dockerfile`, `tests/test_spec03_entrypoint.py`. Done (task 03d2): `python -m mcp_server` reads
      `MCP_API_KEY` (deploy writes it from SSM `/nickoftime/prod/MCP_API_KEY`; under 32 characters the server refuses
      to start, and the key is never logged), `DATABASE_URL` → `PostgresStore` (the in-memory store only with
      `MCP_DEV_MEMORY_STORE=1`), `GOLD_PATH` (gold v1 mounted read-only at `/gold/v1`, spec 06 FR-09) and
      `GOLD_VERSION` (else `v<version>` from the gold manifest); one uvicorn worker, because the rate limiter counts in
      one process. The gate reads `sessions` and writes `policy_denials` through the store's accessors (task 01g). The
      read handlers (T2, T3) are wired here; the modules of T4–T7 (`writes`, `case_reads`, `followups`, `notify`) are
      imported when present and either fill `server.HANDLERS` on import or define `<name>_handlers(...)` factories
      whose parameters are named `gold`, `policies`, `store`, `channels` or `guardrails` `[assumption]`. An absent
      module is skipped (its tools answer `UNAVAILABLE`); a present one that fails to import, a factory missing a
      dependency or failing, or an unknown tool name stops startup (fail closed), so a deploy's health wait fails
      instead of shipping it. `/health` adds the gold and policies versions, the store backend, the handler count and
      the loaded and absent module names, never customer data or a secret. The image runs the real
      server; `infra/compose.dev.yml` keeps `mcp_server.fake` for local work. Open: the `tools/list` descriptions
      (today `<name> (spec 03 §6)`), set from what spec 04 binds for the agent (owner: spec 04 / T8)

**Closing checklist:** every AC has a passing test or check that cites it · status → Implemented · lessons to `CLAUDE.md`.

## 11. Sources
- Internal: `contracts/tools.py` (models), `contracts/policies.yaml` (`actors.customer.tools`, `case_queue.transitions`,
  `amount_gate` rates, `reliability.tool_timeout_ms`, guardrail ids), `contracts/gold_contract.md` (gold tables), ADR
  0006 (score provider), ADR 0016 (guardrails), ADR 0019 (official sources), ADR 0020 (two modes), spec 02
  §4.3–4.4 (clock, reference rates, re-evaluation window), improvement drafts #13 and #13b (tool catalog).
- MCP streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- The ARS 350 and COP 4,000 rates are the dataset's fixed implied rates (`contracts/policies.yaml` comments); MXN 18.0
  and the rate limits are `[assumption]`.
