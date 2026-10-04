# Spec 03 — MCP server with the 7 customer tools

- **Feature:** a FastMCP server that gives the agent exactly seven tools over the gold data and Postgres, each scoped
  to the session's customer, idempotent where it writes, and re-checking the policies before acting.
- **Status:** Draft
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** AI Engineering (tools used safely; permissions in the service layer)
- **Depends on:** spec 01 (contract §6.3, store, ids), spec 02 (engine and clock) · **Enables:** 04 · **ADRs:** 0005,
  0006, 0008, 0010, 0012, 0016
- **Issue:** #5

> Minimal profile plus §7 and §8, because the search rules decide which transaction the customer disputes.

---

## 1. Introduction
The agent can only act through these tools. Every permission lives here, not in the prompt: the `customer_id` comes
from the session row, never from the arguments; a write re-checks the policy engine; a write is idempotent; the
verification tools read state back so the agent reports only what is verified. The server runs at
`https://mcp.nickoftime.salazarvalverdeai.com/mcp` (streamable HTTP, `X-API-Key`) and locally at
`http://localhost:8100/mcp`.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 come from issue #5 with the same numbers; AC-07 onward are added by this spec.

- **AC-01** — When customer X's session calls `search_transaction`, the tool shall return only X's transactions, even
  if the text mentions another customer. · [T]
- **AC-02** — If the session expired or does not exist, then every tool shall answer `SESSION_EXPIRED` with no data. · [T]
- **AC-03** — When `block_card` is called twice with the same `idempotency_key`, there shall be a single block. · [T]
- **AC-04** — When `block_card` completes, `get_product_status` shall return `Blocked` (an overlay row in Postgres; gold
  is never written). · [T]
- **AC-05** — If a fault is injected for a tool (`sessions.tool_faults`), then that tool shall answer `UNAVAILABLE`. · [T]
- **AC-06** — Without a valid API key, `https://mcp.nickoftime.salazarvalverdeai.com/mcp` shall answer 401. · [C]
- **AC-07** — When a MX customer says "1,250 pesos" for a USD transaction, `search_transaction` shall match it through the
  policy rate (18.0 MXN/USD) within ±2%. · [T]
- **AC-08** — `search_transaction` shall return only card transactions with status `Approved` or `Pending`, dated within
  `window_days` of `approx_date` and never after `DEMO_TODAY`, ranked by match quality, at most 4 (so the policy can
  see "more than 3"). · [T]
- **AC-09** — If `open_case` receives a `zone` different from the zone computed from `get_fraud_score` for that
  transaction, then it shall answer `DENY` with `POL-ZONE-MISMATCH` (G-IN-02). · [T]
- **AC-10** — If `block_card` is called for a product without an open case in the same session and run, or the policy
  engine does not allow the block, then it shall answer `DENY` with the policy id and write nothing. · [T]
- **AC-11** — No tool output shall contain another customer's data or personal fields (document number, e-mail, phone,
  address). · [T]
- **AC-12** — Every `DENY` shall be written to `policy_denials` with `trace_id`, `policy_id` and guardrail id. · [T]
- **AC-13** — Tool latency p95 shall stay under 800 ms on the full gold v1 (`reliability.tool_timeout_ms`). · [C]

## 6. Tool contract and behavior
Models are those of `contracts/tools.py`; every tool also accepts the header `X-Trace-Id` (the graph's run id).

| Tool | Behavior |
|---|---|
| `search_transaction` | Loads the session's customer; filters gold `transactions_enriched` to that customer's cards (`Tarjeta Débito`, `Tarjeta Crédito`), status `Approved`/`Pending`, `approx_date ± window_days` (default 7; if no date, the last 30 days) and `≤ DEMO_TODAY`. Optional filters: **amount** (±2%, compared in the transaction currency and in the customer's local currency through the policy rates MXN 18.0, ARS 350, COP 4,000), **merchant** (case- and accent-insensitive token match; null merchants still match on amount and date). Ranks by amount match, then date distance, then merchant similarity; returns ≤ 4 `Transaction` with `split`. |
| `get_fraud_score` | Provider `dataset` (ADR 0006): `transactions.fraud_score` for a transaction of the session's customer, `source: "dataset"`, `version: "gold-v1"`. Another customer's transaction → `DENY POL-CROSS-CUSTOMER`. |
| `compute_deadline` | Country from the customer (`México`→MX, `Argentina`→AR, `Colombia`→CO), product from the card type, opened on `DEMO_TODAY`, `abroad` when `transaction_country` ≠ customer country; delegates to `clock.deadline()` (spec 02). |
| `open_case` | Recomputes the zone from the score (mismatch → AC-09); idempotent on `idempotency_key` (prefixed with `run_id`); writes `cases` and `case_events(case_opened)`; returns `case_id` and deadlines. A second case for the same transaction in the same run returns the existing one. |
| `block_card` | Requires an open case for that product in the session and run; asks `engine.check("block_card", zone, amount, country, supervised_mode)`; on allow, writes `product_overrides(Blocked)` and `case_events(card_blocked)`, returns `accepted: true` (not yet verified). |
| `get_product_status` | Latest override for the product in the same `run_id`, else gold `product_status`. Always reads the database (no cache). |
| `get_case_status` | Maps the case's queue status to `Open` / `In review` / `Closed`. Always reads the database. |

**Common rules:** API key middleware; session check first (AC-02); fault check second (AC-05); errors returned as
`ToolError`, never raised; per-session rate limit of 30 calls per minute (G-TOOL-01); strict Pydantic validation
rejects unexpected arguments.

## 7. Data model touched
Reads gold `transactions_enriched`, `products`, `customers` (country only) through DuckDB, loaded at startup into an
in-memory table of card transactions indexed by `customer_id` (≈ 516k rows). Reads and writes Postgres through
`nick_of_time.store`: `sessions` (read), `cases`, `case_events`, `product_overrides`, `idempotency`, `policy_denials`.

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — currency:** match MX pesos against USD transactions through the policy rate (18.0 `[assumption]`). Display in
  the customer's currency is covered by the proposed `convert_amount` tool (Q4).
- **Q2 — statuses:** `Declined` and `Reversed` transactions are excluded; a reversed charge is reported as already
  reversed (spec 04).
- **Q3 — order of writes:** `open_case` first (the ticket is always opened), then `block_card`, which requires the open case.
- **Q4 — open, under review:** tool contract v1.1 — enriched `get_product_status` and `get_case`, new `list_my_cards`,
  `list_my_cases`, `add_case_info`, `request_call`, `request_reevaluation`, `convert_amount` — and the case lifecycle:
  no duplicate active case per transaction; a resolved case can be sent back to review by a re-evaluation request; a
  closed case is never reopened, a new case is opened with `related_case_id`.
- Assumption: the DuckDB in-memory load fits the EC2 (t3.medium, 4 GB) — measured in T5.

## 9. Out of scope
Analyst tools (they live in the backend API, spec 05); notifications (spec 13); the agent logic (spec 04).

## 10. Plan, tasks and verification
Implementation goes in `feat/03-mcp-tools` once this spec, spec 01 and spec 02 are approved.
- [ ] T1 — FastMCP app, API key middleware, session and fault checks, rate limit · AC-02, AC-05, AC-06
- [ ] T2 — Gold loader (DuckDB in-memory, card transactions by customer) and `search_transaction` ranking · AC-01, 07, 08, 11
- [ ] T3 — `get_fraud_score`, `compute_deadline` · AC-11
- [ ] T4 — `open_case`, `block_card` with idempotency, engine re-check and denials · AC-03, 04, 09, 10, 12
- [ ] T5 — verification tools + latency benchmark on gold v1 · AC-04, AC-13
- [ ] T6 — Dockerfile and compose service `mcp`; tests `tests/test_spec03_*.py` against a gold fixture

**Closing checklist:** every AC has a passing test or check that cites it · status → Implemented · lessons to `CLAUDE.md`.
