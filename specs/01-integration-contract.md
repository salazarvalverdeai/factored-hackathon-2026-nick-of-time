# Spec 01 — Integration contract + stubs

- **Feature:** the contract the three of us build against — folders, REST API, MCP tools, graph I/O, Postgres schema,
  customer receipt, evaluation hooks — plus stubs so nobody waits for anybody.
- **Status:** Draft (contract 1.1.0, updated 2026-10-04: 16 customer tools, two time modes, action states, delivery status)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** AI Engineering, Technical Judgment
- **Depends on:** framework (#2) · **Enables:** 03, 05, 07, 08, 10, 13, 16 · **ADRs:** 0005, 0007, 0008, 0010, 0013, 0017, 0019,
  0020
- **Issue:** #3 · **Approval:** all three (@salazarvalverdeai, @gianzk, @vldiego)

> Full profile: this spec *is* the contract. Contract version **1.1.0** (1.0.0 was the first review draft; 1.1.0 adds
> the approved improvements #12–#16 before approval). Any change after approval is a PR that all three approve and that
> bumps the version (minor = additive, major = breaking).

---

## 1. Introduction
Option A (ADR 0008) splits the system into four deployables — **web**, **api**, **mcp**, **agent** — plus Postgres and
the read-only gold. Three people build them in parallel. This spec fixes every seam between them so each owner can
build and test alone against stubs, and the pieces fit when they meet.

```
browser ──► web (Next.js) ──► api (FastAPI) ──► LangGraph Platform: graph "dispute_intake" ──► mcp (FastMCP)
                                   │                                    │                         │
                                   └────────────► Postgres ◄────────────┼─────────────────────────┤
                                                                        └──► Bedrock               └──► gold (DuckDB, read-only)
```

## 2. User stories
- As **GianMarco**, I want the REST routes, their payloads and the Postgres schema fixed, so the web and api can be
  built before the agent exists.
- As **Diego**, I want the evaluation hooks and the final-state shape fixed, so the harness can run against a stub.
- As **Freddy**, I want the MCP tool contract and the graph I/O fixed, so the agent can be built against a fake MCP.

## 3. Acceptance criteria (EARS)
Copied from issue #3 (same numbers). Evidence: [T] test · [C] command · [U] screenshot · [D] file.

- **AC-01** — This spec shall fix the folder layout, the REST routes and their models, the MCP contract, the graph
  input and output (`TurnResult`), the Postgres schema, the `customer_receipt` contract, and `expected.receipt` plus the
  `customer_returns` type in `eval_case.schema.json`. · [D] this file
- **AC-02** — When the local stack starts (`docker compose -f infra/compose.dev.yml up`), `/api/health` and every route in
  §6.2 shall answer with this contract's shape, using fixture data. · [T] `tests/test_spec01_api_stub.py`
- **AC-03** — When the fake MCP server receives a call to any of the 16 tools of §6.3, it shall answer with the model
  from `contracts/tools.py`. · [T] `tests/test_spec01_mcp_stub.py`
- **AC-04** — The echo graph shall return a valid `TurnResult` that includes a sample receipt that validates against
  `contracts/customer_receipt.schema.json`. · [T] `tests/test_spec01_graph_stub.py`
- **AC-05** — The spec PR shall carry the approvals of all three team members. · [U] PR review list
- **AC-06** — If a client sends a `session_id` or `customer_id` in a chat payload, then the api shall ignore it and use
  only the server-side session. · [T]
- **AC-07** — When a session is created, its mode (`replay` or `live`) shall be stored and never change; every business
  date served for that session shall come from `clock.today(mode)`. · [T]
- **AC-08** — While a session is in `live` mode, `search_transaction` shall also return the customer's rows of
  `demo_transactions`, each flagged `synthetic: true`; the eval seed shall always create `replay` sessions. · [T]

## 4. Functional requirements
- **FR-01** One shared Python package (`nick_of_time`) holds the contract models, the policy engine, the clock, the
  receipt builder and the Postgres store; every Python app imports it — nobody re-declares a contract model.
- **FR-02** Postgres is the only mutable state. Event tables are append-only; a case's status is its last
  `status_changed` event.
- **FR-03** The api is the only public entry for browsers. It proxies agent runs to Platform and injects the session.
- **FR-04** The mcp server is reachable only with an API key; every tool takes `session_id` and resolves the customer
  from Postgres.
- **FR-05** Evaluation hooks exist only when `EVAL_MODE=true` and are never deployed to production.
- **FR-06** Stubs implement every route and tool with fixtures so that each owner can develop offline.

## 5. Non-functional requirements
- **Performance:** api routes other than agent runs p95 < 300 ms; MCP tools p95 < 800 ms (`reliability.tool_timeout_ms`).
- **Security:** no secret in the repo or the browser; analyst routes require a Cognito JWT; customer routes require
  the `not_session` cookie (httpOnly, Secure, SameSite=Lax); MCP requires `X-API-Key`.
- **Observability:** every request carries `trace_id` (the LangGraph run id when there is one; otherwise a UUID) into
  `case_events`, `llm_calls` and `policy_denials`.
- **Time:** all business dates use `clock.today(mode)` — `DEMO_TODAY` in `replay`, the real date in the customer's
  country time zone in `live` (ADR 0020; it supersedes ADR 0012). Timestamps are UTC ISO-8601; dates
  `YYYY-MM-DD`.

## 6. Contracts

### 6.1 Repository layout and ownership
```
apps/
  web/                    Next.js app — @gianzk (page content: see specs 12, 04, E1)
  api/                    FastAPI app, package `api` — @gianzk
    migrations/           Postgres schema (Alembic) — @gianzk, schema fixed by §6.5
  mcp/                    FastMCP server, package `mcp_server` — @salazarvalverdeai
  agent/                  LangGraph graph, package `agent` — @salazarvalverdeai
packages/
  nick_of_time/           shared package — @salazarvalverdeai
    contracts.py          re-exports contracts/tools.py models + TurnResult + receipt models
    policy/               policy engine + regulatory clock (spec 02)
    store/                Postgres access used by api and mcp (tables of §6.5)
    receipt.py            deterministic receipt and handoff builders (ADR 0016)
    ids.py                identifier generation (§6.7)
contracts/                policies.yaml · tools.py · *.schema.json — source of truth (lead approves)
eval/                     cases, PROTOCOL.md, harness, results — @vldiego
infra/                    compose files, Caddyfile, deploy scripts — @gianzk
langgraph.json            Platform deployment of apps/agent — @salazarvalverdeai
```
The empty `apps/api/{audit,classifier,graph,policy,tools}/` folders from the scaffold are removed: the graph lives in
`apps/agent`, tools in `apps/mcp`, policy in `packages/nick_of_time/policy`.
Every Python app runs on 3.13, the version CI tests, so `langgraph.json` sets `"python_version": "3.13"` (Platform
otherwise builds on 3.11). Every deployment of a Python app ships `contracts/`, because the package reads its JSON
schemas and `policies.yaml` at runtime.

### 6.2 REST API (`apps/api`, prefix `/api`)
OpenAPI is generated from the code at `/api/docs`; this table is the agreed contract. Errors always use
`{"code": "DENY|NOT_FOUND|SESSION_EXPIRED|UNAUTHENTICATED|UNAVAILABLE|INVALID", "policy_id": str|null, "message": str}`.

**Public and customer routes** (customer routes need the `not_session` cookie)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status, version, contract_version, git_sha, gold_version, policies_version, platform_revision, models: {graph, fast}, prompt_hash, classifier_version, today: {replay, live}}` | 200 |
| GET | `/api/demo/customers` | — | `[{customer_id, display_name, country, segment, scenario, language}]` (6 demo customers, spec 09) | 200 |
| POST | `/api/sessions` | `{customer_id, mode: "replay"\|"live"}` (default `live`) | `{session_id, mode, today, otp_demo, expires_at}` — the OTP is shown on screen (mock, ADR 0017) | 201 / 404 |
| POST | `/api/sessions/{session_id}/verify` | `{otp}` | `{verified, expires_at}` + sets `not_session` cookie | 200 / 401 / 410 |
| * | `/api/agent/...` | LangGraph Server protocol subset: `POST threads`, `POST threads/{id}/runs/stream`, `GET threads/{id}/state` | proxied to Platform; `configurable.session_id` injected from the cookie; any client `session_id`/`customer_id` is dropped (AC-06); the stream carries only `CustomerTurn` items and progress events, and `threads/{id}/state` returns the last `CustomerTurn`, never the raw thread state (D-013) | 200 / 401 |
| GET | `/api/notifications` | — | `[{notification_id, case_id, event, channel, masked_address, text, delivery_status, created_at}]` for the session's customer ("My notifications"); `delivery_status` = `queued\|sent\|delivered\|bounced\|failed` | 200 / 401 |
| GET | `/api/me/products` | — | `[ProductView]` (§6.6) — "My cards", read fresh on each call | 200 / 401 |
| GET | `/api/me/cases` | — | `[CustomerCaseSummary]` (§6.6) — the customer's cases, active first | 200 / 401 |
| PUT | `/api/me/preferences` | `{display_currency?, language?}` | the stored preferences (kept in the session) | 200 / 400 / 401 |
| GET | `/api/cases/{case_id}` | — | `CustomerCaseView` (§6.6) if the case belongs to the session's customer | 200 / 403 / 404 / 401 |
| POST | `/api/cases/{case_id}/info` | `{text}` | `{event_id}` → event `customer_info_added` | 201 / 403 / 401 |
| POST | `/api/cases/{case_id}/call-request` | `{preferred_time?}` | `{event_id}` → event `call_requested` | 201 / 403 / 401 |
| POST | `/api/cases/{case_id}/reevaluation` | `{reason}` | `{event_id, case_id}` — a resolved case returns to `review`; a closed case gets a new case with `related_case_id` (spec 03) | 201 / 403 / 409 / 401 |
| POST | `/api/cases/{case_id}/channels/telegram` | — | `{deep_link, expires_at}` (one-time token, TTL 15 min) | 201 / 403 / 401 |
| POST | `/api/cases/{case_id}/channels/email` | `{email}` | `{confirmation_sent: true}` — confirmation link to that address | 202 / 400 / 403 / 401 |
| GET | `/api/channels/email/confirm` | `?token=` | redirect to `/case/{id}` with a confirmed banner | 302 / 410 |
| POST | `/api/telegram/webhook` | Telegram update; header `X-Telegram-Bot-Api-Secret-Token` | `{ok: true}` | 200 / 401 |
| POST | `/api/resend/webhook` | Resend e-mail event (`email.sent`, `email.delivered`, `email.bounced`, `email.failed`, …); headers `svix-id`, `svix-timestamp`, `svix-signature` verified with `RESEND_WEBHOOK_SECRET` | `{ok: true}` → row in `notification_deliveries` | 200 / 401 |

An expired session returns the standard `401` with `code: "SESSION_EXPIRED"` in the error body; a missing session returns
`401` with `code: "UNAUTHENTICATED"`. The UI reads `code` to show "verify again" instead of a login screen.

`[assumption]` (D-013, default pending the lead) Customer routes emit only customer projections, so score, policy ids
and transcript never reach the browser (`notifications.never_send`): `CustomerTurn` (§6.4) and `CustomerCaseView`
(§6.6). `TurnResult` and `CaseView` stay inside the api, the agent, the eval hooks and the analyst console.

**Analyst routes** (Cognito JWT in `Authorization: Bearer`; `actor_id` = token `sub`)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/console/cases` | `?status=&zone=&country=` | `[CaseSummary]` (§6.6), sorted by SLA then zone | 200 / 401 |
| GET | `/api/console/cases/{case_id}` | — | `{case: CaseView, handoff: handoff.schema.json, events: [CaseEvent]}` | 200 / 401 / 404 |
| POST | `/api/cases/{case_id}/action` | `AnalystActionIn` (`contracts/tools.py`) | `AnalystActionOut` | 200 / 401 / 403 / 409 |
| GET | `/api/console/settings` | — | `{supervised_mode, score_provider, policies_version}` | 200 / 401 |
| PUT | `/api/console/settings` | `{supervised_mode}` | same as GET; event `settings_changed` with actor | 200 / 401 |
| POST | `/api/console/demo/reset` | — | `{demo_transactions, sample_cases}` — regenerates the live-mode synthetic transactions and re-seeds the processed sample cases (spec 05) | 200 / 401 |

**Evaluation hooks** (only when `EVAL_MODE=true`; never in production) — see §6.8.

**Insight data for web pages:** static JSON files under `apps/web/public/data/` produced by scripts:
`evaluation_summary.json` (spec 10), `benchmark.json` (spec 15), `classifier.json` (spec 11), `pitch_numbers.json`,
`ops_kpis.json` (spec 14), `data_quality.json` (spec 12). Each file has `{generated_at, git_sha, source, data}`; the
shape of `data` is fixed in the producing spec.

### 6.3 MCP server (`apps/mcp`)
- **Endpoint:** `https://mcp.nickoftime.salazarvalverdeai.com/mcp`, streamable HTTP transport; header `X-API-Key`
  (value in SSM `/nickoftime/prod/MCP_API_KEY`). Locally `http://localhost:8100/mcp`.
- **Tools** — exactly the 16 of `contracts/policies.yaml` `actors.customer.tools`; each has `<Name>In` / `<Name>Out`
  models in `contracts/tools.py` (v1.1; spec 03 fixes their behavior). Kind: R read · W write · N notification.

| Tool | Kind | Purpose | Writes | Verified with |
|---|---|---|---|---|
| `get_customer_profile` | R | First name, language, country, display currency, confirmed channels | — | — |
| `search_transaction` | R | Find the disputed charge (gold; plus `demo_transactions` in `live`) | — | — |
| `get_fraud_score` | R | The bank's score with its source and version | — | — |
| `compute_deadline` | R | Legal deadline for a new case, with `source_url` and `verified_on` | — | — |
| `open_case` | W | Open the case; no duplicate active case; closed case → new case with `related_case_id` | `cases`, `case_events` (`case_opened`) | `get_case` |
| `block_card` | W | Block the card | `product_overrides`, `case_events` (`card_blocked`) | `get_product_status` |
| `get_product_status` | R | One card: type, last 4, status, `verification_id`, `read_at` | — | — |
| `list_my_cards` | R | The customer's cards with status | — | — |
| `get_case` | R | Customer view of a case: status label, stored deadlines with source and `deadline_verified_on`, visible timeline, `taken_by_person`, `related_case_id`, `read_at` (replaces `get_case_status`) | — | — |
| `list_my_cases` | R | The customer's cases | — | — |
| `add_case_info` | W | Customer adds information to an active case | `case_events` (`customer_info_added`) | `get_case` |
| `request_call` | W | Customer asks a person to call | `case_events` (`call_requested`) | `get_case` |
| `request_reevaluation` | W | Re-evaluate a resolved case (→ `review`) or open a related case for a closed one | `case_events` (`reevaluation_requested`) or `cases` | `get_case` |
| `convert_amount` | R | Amount in the display currency, with rate, source and date | — | — |
| `send_case_summary` | N | Send the receipt template to a confirmed channel | `notifications`, `case_events` (`notification_sent`) | `list_my_notifications` |
| `list_my_notifications` | R | Notifications with masked address and delivery status | — | — |

  The analysts' actions (approve credit, unblock, close, reopen) stay in the api behind Cognito and never appear in
  the MCP.
  `[assumption]` (D-014, pending the lead): the `open_case` and `get_case` results carry `deadline_verified_on`
  with the stored deadline, so a receipt re-sent later can fill `deadline.verified_on` (§6.7, ADR 0019); the models
  land with T4.

- **Errors:** every tool returns `ToolError` (`DENY`, `NOT_FOUND`, `SESSION_EXPIRED`, `UNAVAILABLE`) instead of raising;
  a `DENY` is also written to `policy_denials` with its `policy_id`.
- **Session:** each call loads `sessions` by `session_id`; expired or unverified → `SESSION_EXPIRED`. The
  `customer_id` never comes from the arguments.
- **Fault injection:** if the session row has `tool_faults` (set only by the eval seed, §6.8), the listed tools answer
  `UNAVAILABLE`.
- **Idempotency:** every W and N tool stores `idempotency_key` → result in `idempotency`; a repeated key returns the
  stored result without a second write.
- **Mode:** each call reads `sessions.mode`; tools never read the system clock (AC-07, AC-08).

### 6.4 Graph I/O (`apps/agent`, LangGraph Platform)
- **Graph id:** `dispute_intake` in `langgraph.json`. **Input:** `{"messages": [{"role": "user", "content": str}],
  "language": "es"|"pt"|null, "action": {"type": "confirm|choose_option|verify_now|request_call|request_reevaluation|send_summary", "value": str}|null}`
  — `action` carries a button or chip press and skips the classifier (`confirm` takes `yes|no`, `choose_option` takes a
  transaction id or `none`). **Config** (injected by the api, never by the client):
  `configurable.session_id` (required), `configurable.session_state`, `configurable.mode`, `configurable.arm` and
  `configurable.case_id` (optional, for a returning customer).
- **Output state** (`TurnResult`, also the last item of a streamed run):

```json
{
  "reply": "string — customer-facing, ES or PT",
  "language": "es | pt",
  "decision": "block_and_open_case | confirm | ask | handoff | answer_status | connect_person | deny | reauthenticate | escalate_unconfirmed_action | null",
  "zone": "high | medium | human | null",
  "intent": "unrecognized_charge | wrongful_charge | status_inquiry | human_request | out_of_scope | null",
  "intent_confidence": 0.0,
  "options": [{"id": "TRX-…", "label": "USD 1,250.00 · 2026-05-31 · TIENDA X"}],
  "case_id": "K-… | null",
  "plan": ["Bloquear tu tarjeta ····4417", "Abrir tu caso y calcular tu fecha límite", "Enviarte el comprobante"],
  "progress": [{"step": "block_card", "label": "Bloqueando tu tarjeta…", "state": "verified", "at": "ISO-8601"}],
  "actions": [{"tool": "block_card", "action_id": "A-…", "state": "in_progress | requested | verified | not_confirmed", "verification_id": "V-… | null", "read_at": "ISO-8601 | null"}],
  "suggestions": [{"id": "view_case", "label": "Ver mi caso", "kind": "link", "href": "/case/K-…"},
                  {"id": "send_summary", "label": "Enviarme el comprobante", "kind": "action", "action": {"type": "send_summary"}},
                  {"id": "request_call", "label": "Que me llame una persona", "kind": "action", "action": {"type": "request_call"}}],
  "receipt": "customer_receipt | null",
  "handoff": "handoff.schema.json object | null",
  "guardrails_triggered": ["G-IN-01"],
  "denials": [{"policy_id": "…", "guardrail_id": "G-IN-01", "detail": "…"}],
  "usage": [{"provider": "bedrock", "model": "…", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}],
  "mode": "replay | live",
  "trace": [{"node": "understand", "status": "ok | deny | error", "ms": 412, "detail": "intent=unrecognized_charge conf=0.93"}],
  "trace_id": "uuid (Platform run id)"
}
```
- `receipt` is present whenever a case was opened; `handoff` whenever the case goes to `review`. Both are built by
  `nick_of_time.receipt` from the same verified facts (ADR 0016).
- `progress` items are also streamed as custom events while the run is in progress (spec 04 AC-17);
  `answer_status` and `connect_person` come from spec 02 rules 3a–3b.
- `suggestions` holds 2 or 3 chips chosen by rules (spec 04 §4.5): `kind` is `text` (the web sends `label` as the next
  message), `action` (the web sends `action` as the next input) or `link` (`href` is an internal route set by the
  server: a `/` path of URL-safe characters, so never `//`, `/\`, a tab or a newline). The web shows them only under
  the last reply. The four action states are the only vocabulary for an action, in every surface; a `verified` action
  carries `verification_id` and `read_at`, and a `progress` item says `verified` only when `actions[]` holds a
  verified record of the same tool (`step` = `tool`). `options` holds at most `clarify.max_candidate_transactions`.
- `CustomerTurn` = `TurnResult` without `handoff`, `zone`, `usage`, `trace` and `denials[].policy_id`
  (`TurnResult.for_customer()`); it is the only shape the browser receives (D-013 `[assumption]`, §6.2).
  `G-…` guardrail ids may appear in the chat; `notifications.never_send.policy_ids` means `POL-…` rule ids; receipts
  and notifications carry neither. `denials[].detail` comes only from a `messages.yaml` template, never from engine
  output.

### 6.5 Postgres schema (owned by `apps/api/migrations`, used through `nick_of_time.store`)
Append-only tables are marked **AO** (no `UPDATE`/`DELETE`; enforced by grants and a test).

| Table | Columns (type) | Notes |
|---|---|---|
| `sessions` | `session_id` text PK · `customer_id` text null · `otp_hash` text · `verified_at` timestamptz null · `expires_at` timestamptz · `language` text · `mode` text (`replay\|live`) · `display_currency` text null · `tool_faults` text[] · `run_id` text null · `arm` text null · `created_at` | TTL 15 min; `mode` fixed at creation; `run_id`/`arm` set only by the eval seed |
| `cases` | `case_id` text PK · `customer_id` · `transaction_id` · `product_id` · `country` · `product_type` · `zone` · `dispute_type` · `credit_deadline` date null · `ruling_deadline` date null · `deadline_source` text · `deadline_source_url` text · `deadline_verified_on` date null · `related_case_id` text null · `mode` text · `run_id` text null · `trace_id` · `created_at` | static facts only; `deadline_verified_on` `[assumption]` (D-014); `case_id` from `ids.new_id("case")` has 10^6 values, so the insert retries on a PK conflict (T9, §10) |
| `demo_transactions` | same columns as gold `transactions` · `synthetic` bool (always true) · `scenario` text · `generated_at` | `live` mode only; deleted and regenerated by "Reset demo"; never copied to gold, lakehouse or eval |
| `case_events` **AO** | `event_id` text PK · `case_id` FK · `seq` int · `type` text · `actor` text · `payload` jsonb · `customer_visible` bool · `trace_id` · `created_at` | unique (`case_id`, `seq`) |
| `product_overrides` **AO** | `override_id` PK · `product_id` · `status` · `case_id` · `actor` · `run_id` text null · `created_at` | current status = latest row **for the same `run_id`**, else gold |
| `notifications` **AO** | `notification_id` PK · `case_id` · `customer_id` · `event` · `channel` (`log\|telegram\|email`) · `masked_address` · `text` · `trigger` (`auto\|on_request`) · `provider_message_id` null · `created_at` | |
| `notification_deliveries` **AO** | `delivery_id` PK · `notification_id` FK · `status` (`queued\|sent\|delivered\|bounced\|failed`) · `provider_event` jsonb · `created_at` | delivery status = latest row |
| `customer_channels` **AO** | `channel_id` PK · `customer_id` · `channel` · `address` (chat id or e-mail) · `event` (`linked|confirmed|revoked`) · `created_at` | latest row per channel wins |
| `link_tokens` | `token` PK · `case_id` · `channel` · `expires_at` · `used_at` null | one-time |
| `idempotency` | `key` PK · `action` · `result` jsonb · `run_id` text null · `created_at` | the key is prefixed with `run_id` when present |
| `policy_denials` **AO** | `denial_id` PK · `trace_id` · `session_id` · `policy_id` · `guardrail_id` · `detail` jsonb · `created_at` | |
| `llm_calls` **AO** | `call_id` PK · `trace_id` · `provider` · `model` · `tokens_in` · `tokens_out` · `latency_ms` · `cost_usd` numeric · `created_at` | |
| `settings_events` **AO** | `event_id` PK · `key` · `value` jsonb · `actor` · `created_at` | `supervised_mode` = latest |

**Case event types** (`case_events.type`, visible to the customer when marked ✓): `case_opened` ✓ · `card_blocked` ✓ ·
`block_verified` ✓ · `status_changed` ✓ · `handoff_emitted` · `assigned` ✓ (a person took the case) ·
`analyst_action` · `customer_info_added` ✓ · `call_requested` ✓ · `reevaluation_requested` ✓ · `related_case_opened` ✓ ·
`notification_sent` ✓ · `receipt_issued` ✓ · `telegram_linked` ✓ · `email_confirmed` ✓.
Queue statuses (from `policies.yaml`): `new → verification | review → resolved → closed`.

### 6.6 View models (api)
- `CaseSummary`: `{case_id, customer_id, country, zone, queue_status, credit_deadline, ruling_deadline, sla_due_at,
  priority, tags, created_at}`.
- `CaseView`: `CaseSummary` + `{transaction: {transaction_id, amount, currency, date, merchant, synthetic},
  product_last4, status_label, taken_by_person, related_case_id, mode, receipt: customer_receipt|null,
  timeline: [{event_id, type, label, created_at}] (customer-visible only), deadline_countdown_days,
  deadline_source, deadline_source_url, deadline_verified_on (`[assumption]` D-014, §6.5; a deadline date always
  comes with its source and an `https://` URL, ADR 0019),
  channels: {telegram: bool, email: bool}, notifications: [{notification_id, channel, masked_address,
  delivery_status, created_at}]}`.
- `CustomerCaseView`: `CaseView` without `customer_id`, `zone`, `priority`, `tags` and `sla_due_at`
  (`CaseView.for_customer()`); `GET /api/cases/{case_id}` returns it (D-013 `[assumption]`).
- `CustomerCaseSummary`: `{case_id, status_label, credit_deadline, ruling_deadline, product_last4, related_case_id,
  updated_at}`.
- `ProductView`: `{product_id, type, last4, status, verification_id, read_at}`.
- `[assumption]` `priority` is `normal|high` (raised by `case_queue.deadline_sla`); `transaction.amount` is a number,
  as in `contracts/tools.py` `Transaction`. Ids follow `nick_of_time.ids`; `last4` is 4 digits; timestamps carry
  their UTC offset. Python models: `nick_of_time.contracts`.

### 6.7 Customer receipt (`contracts/customer_receipt.schema.json`, new)
```json
{
  "receipt_id": "RC-…", "case_id": "K-…", "language": "es | pt", "issued_at": "ISO-8601",
  "verified_facts": [{"fact": "string", "source_id": "TRX-… | PRD-… | V-… | K-…"}],
  "mode": "replay | live", "product_last4": "4417",
  "amount": {"original": {"amount": "1250.00", "currency": "USD"}, "display": {"amount": "22500", "currency": "MXN", "rate": "18.0", "rate_source": "…", "as_of": "YYYY-MM-DD"} },
  "actions": [{"label": "Tarjeta bloqueada", "action_id": "A-…", "state": "verified", "verification_id": "V-…", "verified_at": "ISO-8601"}],
  "deadline": {"country": "MX", "product": "debit", "credit_deadline": "YYYY-MM-DD", "ruling_deadline": "YYYY-MM-DD", "deadline_source": "Banxico Circular 3/2012, as amended by Circular 14/2018", "source_url": "https://…", "verified_on": "YYYY-MM-DD"},
  "what_ai_did": "string (template)", "what_a_person_does": "string (template)",
  "next_steps": ["string"], "case_url": "https://nickoftime.salazarvalverdeai.com/case/K-…"
}
```
Required: `receipt_id, case_id, language, issued_at, verified_facts, actions, deadline, what_ai_did,
what_a_person_does`. Never contains score, policy ids or transcript (`notifications.never_send`). `amount.display` is
an approximation from `convert_amount` and is omitted when no verified rate exists (ADR 0019); `deadline` is null for a
country without a verified clock entry (`POL-CLOCK-UNKNOWN`). Optional fields may be null or absent, except
`next_steps`, an array that is empty by default. Structural rules, in the schema and the model alike:
- accepted ≠ verified: an action with `state: "verified"` carries a `V-` `verification_id` and `verified_at`;
- a non-null `deadline` has at least one non-null date, an `https://` `source_url` and `verified_on`;
- `source_id` is a gold transaction or product id or a `K-`/`V-` id, in the shapes below;
- `case_url` is `https://`, `deadline.country` is two upper-case letters, `deadline.product` is `debit|credit`, and
  every timestamp carries its UTC offset (RFC 3339; the model rejects naive datetimes).

The schema's `examples[0]` is the sample receipt `[simulated]` that stubs and the echo graph return
(`nick_of_time.contracts.sample_receipt()`): a MX debit notice on `DEMO_TODAY` 2026-06-01 about a USD charge on
2026-05-31 (gold México rows are USD `[data]`), credit by 2026-06-03 and source fields from spec 02 §4.3 row 1;
`amount.display` is null because no verified rate exists yet. `nick_of_time.contracts.CustomerReceipt` mirrors the
schema; a test feeds the same good and bad receipts to both.

**Identifiers** (`nick_of_time.ids`): case `K-` + 6 digits · action `A-` · verification `V-` · event `E-` ·
receipt `RC-` · notification `N-` · session `S-` + 16 url-safe chars. `[assumption]` `A-`, `V-`, `E-`, `RC-` and `N-`
take 12 upper-case hex characters; a case id has only 10^6 values, so the store retries on a primary-key conflict.
Transaction and product ids come from gold unchanged: `TRX-` + 20 and `PRD-` + 12 upper-case letters or digits
(`ids.GOLD_PATTERN`; gold `transactions` and `products` `[data]`).

### 6.8 Evaluation hooks (`EVAL_MODE=true` only)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/eval/seed` | `{initial_state: eval_case.initial_state, run_id: str, arm: str}` | `{session_id, thread_id, run_id, arm, mode: "replay"}` — the mode is always `replay` (ADR 0020); always returns a `session_id`: `verified` (OTP done), `expired` (expires_at in the past) or `none` (row with no customer and no verification, so every tool answers `SESSION_EXPIRED` and the expected decision is `reauthenticate`). Applies `fixtures` as overlays and `tool_faults` |
| GET | `/api/eval/final-state/{session_id}` | — | `FinalState` below |

**Isolation between runs (pass^4).** Every row written while serving a seeded session carries its `run_id`
(`sessions`, `cases`, `case_events` through their case, `product_overrides`, `idempotency`, `notifications`,
`policy_denials`, `llm_calls`), and every read of mutable state filters by the session's `run_id` (product status =
latest override for the same `run_id`, else gold). Rows are never reset or deleted, so the append-only rule holds and
each of the four runs starts from the same gold state. The harness uses `run_id = <case_id>:<arm>:<k>` (k = 1…4).

**Arms (system configurations).** One deployment serves every arm: `seed` stores `arm` in the session and the api
injects it as `configurable.arm`; the graph resolves it with `nick_of_time.config.resolve(arm)`.

| Arm | Understanding | Replies | LLM |
|---|---|---|---|
| `S0` | rules classifier (B0) | deterministic templates | none |
| `S1` | classifier chosen by spec 11 | templates + LLM for clarifying questions | Claude Haiku 4.5 |
| `S2` | same as S1 | same as S1 | Claude Sonnet 4.6 |
| benchmark arms (spec 15, B2) | as S1 | as S1 | the arm's model (e.g. `jev`) |

S0–S2 are named here and are the system comparison of ADR 0015; spec 15 can add arms without changing this contract.

`FinalState` (one per session, i.e. per run):
```json
{
  "run_id": "EV-0001:S1:3", "arm": "S1",
  "decision": "…", "zone": "…", "intent": "…",
  "transaction_id": "TRX-… | null", "product_id": "PRD-… | null", "candidate_transaction_ids": ["TRX-…"],
  "product_status": "Blocked | Active | …", "case_open": true, "case_id": "K-… | null", "queue_status": "…",
  "handoff_emitted": true, "receipt_issued": true, "receipt_has_deadline": true,
  "notifications": ["case_opened"], "guardrail_ids": ["G-IN-01"], "other_customer_data_exposed": false,
  "mode": "replay", "action_states": {"block_card": "verified"},
  "status_replies": [{"subject": "PRD-… | K-…", "stated_status": "Blocked", "read_status": "Blocked"}],
  "turns": [{"turn": 1, "latency_ms": 2140, "tokens_in": 1830, "tokens_out": 210, "cost_usd": 0.0031}],
  "totals": {"latency_ms": 2140, "tokens_in": 1830, "tokens_out": 210, "cost_usd": 0.0031},
  "run_meta": {"git_sha": "…", "platform_revision": "…", "policies_version": 2, "provider": "bedrock",
               "model_graph": "…", "model_fast": "…", "prompt_hash": "sha256:…", "classifier_version": "…"}
}
```
`transaction_id`/`product_id` are the ones acted on (block or case); per-turn latency feeds p50/p95, totals feed the
cost per case; `status_replies` compares each status the agent stated with a fresh read at the end of the turn and
feeds `coherence_rate` (spec 15). The harness drives turns through `/api/agent/...` with the seeded session and compares `FinalState`
against `expected`.

**Schema change (`eval/eval_case.schema.json`, minor):** add `"customer_returns"` to `type`; add
`expected.receipt: {"issued": bool, "has_deadline": bool}` and `initial_state.case_id` (for returning customers)
with its fixture `initial_state.case: {transaction_id, dispute_type, zone, queue_status, opened_on}` (each requires the
other); the seed computes the stored deadline with the clock at `opened_on`. `[assumption]` (default until spec 10
confirms) the seed maps a fixture `case_id` to a fresh id per run, because rows are never deleted and the four runs
must stay isolated by `run_id`.
`expected.decision` and `expected.intent` use the `TurnResult` vocabulary of §6.4, so `answer_status` and
`connect_person` are added and `status_inquiry` replaces `inquiry` (spec 11 Q4), plus `human_request`. The example
cases use charge dates inside the gold window, since eval sessions are always `replay` (`DEMO_TODAY` 2026-06-01,
ADR 0020), and gold-format placeholder ids (`CLI-`, `TRX-`, `PRD-`). EV-0001's charge falls within the 48 h before
the notice (spec 02 §4.3); an older-charge case is added once spec 02 T3 verifies that row.

### 6.9 Configuration names
`DEMO_TODAY` · `DATABASE_URL` · `GOLD_PATH` / `GOLD_S3_URI` · `MCP_URL` · `MCP_API_KEY` · `LANGGRAPH_API_URL` ·
`LANGSMITH_API_KEY` · `LLM_PROVIDER` (`bedrock|anthropic|fake`) · `BEDROCK_MODEL_GRAPH` · `BEDROCK_MODEL_FAST` ·
`COGNITO_USER_POOL_ID` · `COGNITO_CLIENT_ID` · `TELEGRAM_BOT_TOKEN` · `TELEGRAM_WEBHOOK_SECRET` · `RESEND_API_KEY` ·
`EVAL_MODE` · `DEFAULT_SESSION_MODE` (`live`) · `RESEND_WEBHOOK_SECRET`. `DEMO_TODAY` applies only to `replay`
sessions. Names only in `.env.example`; values in SSM (`/nickoftime/prod/*`) or the Platform deployment secrets.

## 7. Data model touched
Creates the Postgres schema of §6.5 and the receipt schema of §6.7; reads gold v1 (`gold/v1/` in S3, local
`data/gold/`) read-only; never reads `gold_eval`. `demo_transactions` lives only in Postgres and never flows into gold,
the lakehouse or evaluation (ADR 0020).

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (all):** shared package name `nick_of_time` under `packages/` — OK? (Diego: OK)
- **Q2 (@gianzk):** `/chat` uses agent-chat-ui against the `/api/agent/...` proxy (LangGraph Server protocol), so the
  session is injected server-side — OK, or do you prefer a single `POST /api/chat/runs` SSE route?
- **Q3 (@gianzk):** Alembic for migrations under `apps/api/migrations` — OK?
- **Q4 (@vldiego):** ~~`FinalState` and the seed hook are enough?~~ **Answered in review:** added run isolation by
  `run_id`, `transaction_id`/`product_id` acted on, `run_meta` (models, prompt hash, versions), arms S0/S1/S2 selected
  through `seed`, per-turn latency and cost, and the `session: "none"` behavior (§6.8).
- **Q5 (all):** ~~`440` for an expired session?~~ **Decided (lead):** standard `401` with `code: SESSION_EXPIRED`
  in the body (§6.2).
- **Q6 (lead):** ~~are the 7 tools enough for the messages the agent must send?~~ **Decided (lead, 2026-10-04):** the
  16 tools of §6.3 (improvement #13), the four action states, delivery status for notifications, display currency and
  the two time modes (ADR 0020). The coherence rules become harness cases (spec 10).
- Assumption: analysts and customers use the same origin (`nickoftime.salazarvalverdeai.com`); no CORS.
- Assumption: Platform reaches the MCP over the internet with the API key; locally `langgraph dev` + local MCP.

## 9. Out of scope
Real logic of policies (spec 02), tools (03), graph (04), backend persistence (05) and UIs (07, 08, 13, 16) —
only their seams and stubs.

## 10. Plan, tasks and verification
Implementation goes in one `feat/01-*` branch per task (for example `feat/01-package-skeleton`, then
`feat/01-contract-models` stacked on it).
- [x] T1 — `packages/nick_of_time` skeleton: `contracts.py` (re-export + `TurnResult`, `CustomerReceipt`, `FinalState`,
      view models, customer projections), `ids.py` · covers AC-01 · `tests/test_spec01_contracts.py`
- [x] T2 — `contracts/customer_receipt.schema.json` + `eval_case.schema.json` minor change + example cases updated ·
      covers AC-01, AC-04 (receipt half; the echo graph is T5) · `tests/test_spec01_contracts.py`
- [ ] T3 — api stub: every route of §6.2 and §6.8 returning fixtures validated by the models; `mode` on sessions ·
      covers AC-02, AC-06, AC-07
- [ ] T4 — `contracts/tools.py` v1.1 and `policies.yaml` `actors.customer.tools` with the 16 tools; fake MCP server
      returning fixtures from those models, `synthetic` rows in `live` · covers AC-03, AC-08
- [ ] T5 — echo graph `dispute_intake` returning a `TurnResult` with a sample receipt; `langgraph.json` sets
      `"python_version": "3.13"` (§6.1) · covers AC-04
- [ ] T6 — `infra/compose.dev.yml` (api stub, mcp stub, postgres) and `.env.example` names of §6.9 · covers AC-02
- [x] T7 — remove the empty `apps/api/{audit,classifier,graph,policy,tools}` folders
- [ ] T8 — tests `tests/test_spec01_*.py` citing AC-02, AC-03, AC-04, AC-06, AC-07, AC-08
- [ ] T9 — the store's case insert retries with a fresh `ids.new_id("case")` on a `case_id` primary-key conflict
      (§6.5); a test forces one collision · lands with the store's first insert

**Closing checklist:** every AC has a passing test or check · status → Implemented · contract version recorded in
`/api/health` · lessons added to `CLAUDE.md`.

## 11. Sources
External sources checked on 2026-10-04.
- Telegram Bot API, `setWebhook` (`secret_token` → header `X-Telegram-Bot-Api-Secret-Token`):
  https://core.telegram.org/bots/api#setwebhook
- Resend, webhook signature headers `svix-id`, `svix-timestamp`, `svix-signature`:
  https://resend.com/docs/webhooks/verify-webhooks-requests · e-mail event types (`email.sent`, `email.delivered`,
  `email.bounced`, `email.failed`, …): https://resend.com/docs/webhooks/event-types
- langgraph-cli 0.4.32, `langgraph_cli/config.py`: `DEFAULT_PYTHON_VERSION = "3.11"` when `langgraph.json` has no
  `python_version`: https://pypi.org/project/langgraph-cli/0.4.32/
- jsonschema, format validation (`date-time` is checked only with `rfc3339-validator` installed):
  https://python-jsonschema.readthedocs.io/en/stable/validate/#validating-formats
- Internal: `contracts/gold_contract.md` R1 (gold window), `contracts/policies.yaml` (queue statuses, tools,
  `notifications.never_send`), `contracts/tools.py`, ADRs 0005, 0007, 0008, 0010, 0013, 0016, 0017, 0019, 0020,
  improvement drafts #12 (action states), #13 (tool catalog), #16 (two modes).
