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
- **AC-14** — While the session is in `live` mode, `search_transaction` shall also search the customer's
  `demo_transactions` and flag those results `synthetic: true`; in `replay` it shall never read them. · [T]

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
- **AC-18** — `request_call` shall keep one open request per case; a second request returns the existing one; the result carries `expected_contact_by` computed from the policy key
  (ISO datetime in the country calendar and time zone), or `null` when the policy has none (D-008). · [T]
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
| `get_customer_profile` | R | First name, language, country, `display_currency` (session preference, else the country's from `policies.yaml`), confirmed channels with masked addresses. |
| `search_transaction` | R | Loads the session's customer; filters gold `transactions_enriched` to that customer's cards (`Tarjeta Débito`, `Tarjeta Crédito`), status `Approved`/`Pending`, `approx_date ± window_days` (default 7; if no date, the last 30 days) and `≤ clock.today(mode)`; in `live` also the customer's `demo_transactions` (AC-14). Optional filters: **amount** (±2%, compared in the transaction currency and in the customer's local currency through the policy rates MXN 18.0, ARS 350, COP 4,000), **merchant** (case- and accent-insensitive token match; null merchants still match on amount and date). Ranks by amount match, then date distance, then merchant similarity; returns ≤ 4 `Transaction` with `split` and `synthetic`. |
| `get_fraud_score` | R | Provider `dataset` (ADR 0006): `transactions.fraud_score` for a transaction of the session's customer, `source: "dataset"`, `version: "gold-v1"`; for a synthetic transaction, its generated score with `source: "synthetic"`. Another customer's transaction → `DENY POL-CROSS-CUSTOMER`. |
| `compute_deadline` | R | Country from the customer (`México`→MX, `Argentina`→AR, `Colombia`→CO), product from the card type, opened on `clock.today(mode, country)`, `abroad` when `transaction_country` ≠ customer country; delegates to `clock.deadline()` (spec 02); returns `source_url` and `verified_on`. |
| `open_case` | W | Duplicate check first (AC-15); recomputes the zone from the score (mismatch → AC-09); idempotent on `idempotency_key` (prefixed with `run_id`); writes `cases` (with `mode`, `related_case_id` when given) and `case_events(case_opened)`; returns `case_id`, deadlines and `duplicate_of`. |
| `block_card` | W | Requires an open case for that product in the session and run; asks `engine.check("block_card", zone, amount, country, supervised_mode)`; on allow, writes `product_overrides(Blocked)` and `case_events(card_blocked)`, returns `state: "requested"` (not yet verified). |
| `get_product_status` | R | Latest override for the product in the same `run_id`, else gold `product_status`; returns type, last 4, status, `verification_id`, `read_at`. No cache. |
| `list_my_cards` | R | The session customer's cards with the same fields as `get_product_status`. |
| `get_case` | R | Replaces `get_case_status`. Status label for the customer (`Recibido`, `En revisión`, `Resuelto`, `Cerrado` and PT equivalents from `messages.yaml`), stored deadlines with source, transaction, visible timeline, `taken_by_person` (an `assigned` event exists), `related_case_id`, `read_at`. |
| `list_my_cases` | R | The session customer's cases (active first) with status label, deadlines, last 4 and `updated_at`. |
| `add_case_info` | W | AC-17; writes `case_events(customer_info_added)`. |
| `request_call` | W | AC-18; `{preferred_time?}`; writes `case_events(call_requested)`; returns `{event_id, expected_contact_by}` (D-008). `expected_contact_by` is an ISO datetime the tool computes from `contact.callback_within_business_hours` in `policies.yaml`, in the customer's country business calendar and time zone (rules decide, never the LLM); when the policy has no value it is `null` and the tool never invents a time. `RequestCallResult.expected_contact_by` lands in `contracts/tools.py` v1.1 (task 01b). |
| `request_reevaluation` | W | AC-19; asks `engine.reevaluation_allowed()` (spec 02); writes `case_events(reevaluation_requested)` + `status_changed(review)`, or a new case + `case_events(related_case_opened)` on the closed case. |
| `convert_amount` | R | AC-20; never changes a deadline or a zone. |
| `send_case_summary` | N | AC-21; renders `messages.yaml receipt.*` with the case's verified facts, writes `notifications(trigger=on_request)` + `case_events(notification_sent)`, hands delivery to the api's sender (Telegram or Resend); returns `notification_id` and `state: "requested"`. |
| `list_my_notifications` | R | AC-22. |

**Case lifecycle** (with `case_queue.transitions` of `policies.yaml`):

| Situation | What happens | Who decides |
|---|---|---|
| Same transaction, active case | No new case; the existing case id and deadline are returned (AC-15) | Automatic |
| Resolved case, customer disagrees, within the window | Back to `review` with the reason (`resolved → review` already exists) | A person |
| Resolved case, outside the window | `DENY POL-REEVAL-WINDOW`; the agent offers a call | Policy |
| Closed case | Never reopened by the customer; a new case with `related_case_id`; its deadline runs from the new notice `[assumption, verify per country in spec 02 T3]` | Registered automatically; decided by a person |
| Customer wants to close or reopen a case | Not allowed: closing and reopening are analyst actions in the api | — |

**Common rules:** API key middleware; session check first (AC-02); fault check second (AC-05); errors returned as
`ToolError`, never raised; strict Pydantic validation (`extra="forbid"`) rejects unexpected arguments; tool outputs
are typed data, delimited when passed to the LLM (G-IN-01); per-session limits of 30 calls/min, 5 writes/min and 3
notifications/hour `[assumption]` (G-TOOL-01, G-OPS-01); every call audited with `trace_id`, actor `agent` and an input
hash (G-OPS-02). The analysts' actions never appear in this server.

## 7. Data model touched
Reads gold `transactions_enriched`, `products` and `customers` through DuckDB; from `customers` the loader selects only
`customer_id`, `first_name` and `country`, so `email`, phones, `document_number` and `address` are never loaded (AC-11,
AC-21). Card transactions are loaded at startup into an in-memory table indexed by `customer_id` (≈ 516k rows). Reads
and writes Postgres through `nick_of_time.store`: `sessions` (read), `demo_transactions` (read, `live` only), `cases`,
`case_events`, `product_overrides`, `idempotency`, `policy_denials`, `notifications`, `notification_deliveries` (read),
`customer_channels` (read).

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — currency:** match MX pesos against USD transactions through the policy rate (18.0 `[assumption]`). Display in
  the customer's currency goes through `convert_amount` with official reference rates (spec 02 §4.4).
- **Q2 — statuses:** `Declined` and `Reversed` transactions are excluded; a reversed charge is reported as already
  reversed (spec 04).
- **Q3 — order of writes:** `open_case` first (the ticket is always opened), then `block_card`, which requires the open case.
- **Q4 — tool contract v1.1:** ~~open~~ **Decided (lead, 2026-10-04):** the 16 tools of §6 and the case lifecycle above
  (improvement #13).
- Assumption: the DuckDB in-memory load fits the EC2 (t3.medium, 4 GB) — measured in T5.

## 9. Out of scope
Analyst tools (they live in the backend API, spec 05); automatic notifications on each status change and the delivery
webhooks (api, spec 13); the agent logic (spec 04).

## 10. Plan, tasks and verification
Implementation goes in `feat/03-mcp-tools` once this spec, spec 01 and spec 02 are approved.
- [ ] T1 — FastMCP app, API key middleware, session and fault checks, rate limits, audit · AC-02, AC-05, AC-06
- [ ] T2 — Gold loader (DuckDB in-memory, card transactions by customer), `demo_transactions` in `live`, and
      `search_transaction` ranking · AC-01, 07, 08, 11, 14
- [ ] T3 — `get_customer_profile`, `get_fraud_score`, `compute_deadline`, `convert_amount` · AC-11, AC-20
- [ ] T4 — `open_case` (duplicates, related case), `block_card` with idempotency, engine re-check and denials · AC-03,
      04, 09, 10, 12, 15
- [ ] T5 — read tools (`get_product_status`, `list_my_cards`, `get_case`, `list_my_cases`) + latency benchmark on
      gold v1 · AC-04, AC-13, AC-16
- [ ] T6 — follow-up tools (`add_case_info`, `request_call`, `request_reevaluation`) · AC-17, AC-18, AC-19
- [ ] T7 — `send_case_summary`, `list_my_notifications` · AC-21, AC-22
- [ ] T8 — Dockerfile and compose service `mcp`; tests `tests/test_spec03_*.py` against a gold fixture

**Closing checklist:** every AC has a passing test or check that cites it · status → Implemented · lessons to `CLAUDE.md`.

## 11. Sources
- Internal: `contracts/tools.py` (models), `contracts/policies.yaml` (`actors.customer.tools`, `case_queue.transitions`,
  `amount_gate` rates, `reliability.tool_timeout_ms`, guardrail ids), `contracts/gold_contract.md` (gold tables), ADR
  0006 (score provider), ADR 0016 (guardrails), ADR 0019 (official sources), ADR 0020 (two modes), spec 02
  §4.3–4.4 (clock, reference rates, re-evaluation window), improvement drafts #13 and #13b (tool catalog).
- MCP streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- The ARS 350 and COP 4,000 rates are the dataset's fixed implied rates (`contracts/policies.yaml` comments); MXN 18.0
  and the rate limits are `[assumption]`.
